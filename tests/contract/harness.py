"""Container orchestration for the contract tests.

Deliberately not compose: there is no compose provider we can rely on across
machines, and direct `podman` calls give deterministic teardown plus the exact
port discipline this API needs.

Two qBittorrent containers on a private network. No tracker and no DHT: peers
are introduced explicitly with `torrents/addPeers`, which keeps the swarm
entirely local and means the tests cannot reach, or be reached from, the public
internet.

Port discipline matters. `validateHostHeader` is on by default and rejects any
request whose Host header carries a port different from the listening port, with
a bare 401 that is indistinguishable from bad credentials. So each container
listens on, and publishes, the *same* number.
"""

from __future__ import annotations

import functools
import json
import os
import pathlib
import secrets
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request

# Podman Desktop on macOS installs here and does not always land on PATH for
# non-interactive shells; PATH lookup still happens below.
PODMAN = "/opt/podman/bin/podman"
IMAGE = "docker.io/qbittorrentofficial/qbittorrent-nox"
RUNTIME_ENV = "QBT_CONTAINER_RUNTIME"
HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = pathlib.Path.home() / ".cache" / "qbt-kit-contract"
USERNAME = "testuser"
PASSWORD = "testpass123"
BT_PORT = 6881


@functools.cache
def runtime_exe() -> str:
    """Find a container runtime, preferring podman but accepting docker.

    The author develops against podman; GitHub's runners ship docker and no
    podman, so hardcoding one meant the contract job could only ever pass in
    one of the two places. Every command this harness issues (run, rm, logs,
    inspect, network, exec) is spelled identically in both CLIs, so discovery
    is enough and no abstraction layer is needed. Set QBT_CONTAINER_RUNTIME to
    force a specific binary.
    """
    if override := os.environ.get(RUNTIME_ENV):
        return override
    if pathlib.Path(PODMAN).exists():
        return PODMAN
    for exe in ("podman", "docker"):
        if shutil.which(exe):
            return exe
    raise RuntimeError(
        f"no container runtime found: install podman or docker, or set "
        f"{RUNTIME_ENV} to the binary to use"
    )


def container(*args: str, check: bool = True, timeout: int = 180) -> str:
    exe = runtime_exe()
    out = subprocess.run(
        [exe, *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if check and out.returncode != 0:
        raise RuntimeError(
            f"{pathlib.Path(exe).name} {' '.join(args)} failed:\n{out.stderr.strip()}"
        )
    return out.stdout.strip()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class Node:
    """One qBittorrent container, reachable from the host and from its peer."""

    def __init__(self, name: str, tag: str, port: int, network: str) -> None:
        self.network = network
        self.name = name
        self.tag = tag
        self.port = port
        self.dir = FIXTURES / name
        self.url = f"http://127.0.0.1:{port}"

    # ------------------------------------------------------------- lifecycle

    def start(self) -> None:
        self.dir and self._reset_dir()
        subprocess.run(
            [
                "python3",
                "-I",
                str(HERE / "seed_config.py"),
                "--out",
                str(self.dir / "config/qBittorrent/config/qBittorrent.conf"),
                "--port",
                str(self.port),
                "--username",
                USERNAME,
                "--password",
                PASSWORD,
            ],
            check=True,
            capture_output=True,
        )
        container("rm", "-f", self.name, check=False)
        container(
            "run",
            "-d",
            "--name",
            self.name,
            "--network",
            self.network,
            "-e",
            "QBT_LEGAL_NOTICE=confirm",
            "-e",
            f"QBT_WEBUI_PORT={self.port}",
            "-e",
            "PUID=0",
            "-e",
            "PGID=0",
            "-p",
            f"127.0.0.1:{self.port}:{self.port}",
            "-v",
            f"{self.dir / 'config'}:/config",
            "-v",
            f"{self.dir / 'downloads'}:/downloads",
            f"{IMAGE}:{self.tag}",
        )

    def _reset_dir(self) -> None:
        if self.dir.exists():
            subprocess.run(["rm", "-rf", str(self.dir)], check=True)
        (self.dir / "config/qBittorrent/config").mkdir(parents=True)
        (self.dir / "downloads").mkdir(parents=True)

    def isolate(self) -> None:
        """Belt and braces: assert isolation through the API, not just the ini.

        The ini keys are easy to misplace (they did get misplaced once, under
        the wrong section), and a silently-ignored key means a test swarm that
        can reach the public DHT. The API names are stable, so set them again
        and let the caller verify.
        """
        import urllib.parse

        jar_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
        jar_opener.open(
            f"{self.url}/api/v2/auth/login",
            urllib.parse.urlencode({"username": USERNAME, "password": PASSWORD}).encode(),
            timeout=10,
        )
        payload = json.dumps({"dht": False, "pex": False, "lsd": False})
        jar_opener.open(
            f"{self.url}/api/v2/app/setPreferences",
            urllib.parse.urlencode({"json": payload}).encode(),
            timeout=10,
        )

    def open_downloads(self) -> None:
        """Let the host write into the bind-mounted downloads directory.

        The container runs qBittorrent as root (PUID=0), which is fine under
        rootless podman because container-root maps back to the invoking user.
        Under rootful docker — every Linux CI runner — container-root is real
        root, so the directory qBittorrent takes ownership of cannot be written
        by the test process, and every test that seeds content dies with
        EACCES. Opening the permissions from inside the container is the one
        fix that works the same under both.
        """
        container("exec", self.name, "chmod", "-R", "0777", "/downloads", check=False)

    def wait_ready(self, timeout: int = 90) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f"{self.url}/api/v2/app/version", timeout=3)
            except urllib.error.HTTPError:
                return  # 403 means it is up and demanding auth
            except (urllib.error.URLError, OSError):
                time.sleep(1)
            else:
                return
        raise RuntimeError(f"{self.name} never became ready\n{self.logs()}")

    def stop(self) -> None:
        container("rm", "-f", self.name, check=False)

    def logs(self, lines: int = 20) -> str:
        return container("logs", "--tail", str(lines), self.name, check=False)

    # ----------------------------------------------------------------- info

    @property
    def ip(self) -> str:
        """Address on the private network, for peer introduction."""
        raw = container("inspect", self.name, "--format", "{{json .NetworkSettings.Networks}}")
        nets = json.loads(raw)
        for net in nets.values():
            if net.get("IPAddress"):
                return str(net["IPAddress"])
        raise RuntimeError(f"{self.name} has no address on {self.network}")

    @property
    def peer_address(self) -> str:
        return f"{self.ip}:{BT_PORT}"


class Swarm:
    """A seeder and a leecher of the same qBittorrent version."""

    def __init__(self, tag: str) -> None:
        self.tag = tag
        # Names and the network are unique per swarm: module-scoped fixtures
        # create and tear down several of these in one session, and reusing
        # fixed names makes the second creation collide with the first's
        # teardown.
        uniq = f"{os.getpid()}{secrets.token_hex(2)}"
        self.network = f"qbtk-net-{uniq}"
        self.seeder = Node(f"qbtk-seed-{_slug(tag)}-{uniq}", tag, free_port(), self.network)
        self.leecher = Node(f"qbtk-leech-{_slug(tag)}-{uniq}", tag, free_port(), self.network)

    def up(self) -> Swarm:
        container("network", "create", self.network, check=False)
        for node in (self.seeder, self.leecher):
            node.start()
        for node in (self.seeder, self.leecher):
            node.wait_ready()
            node.isolate()
            node.open_downloads()
        return self

    def down(self) -> None:
        for node in (self.seeder, self.leecher):
            node.stop()
        container("network", "rm", "-f", self.network, check=False)


def _slug(tag: str) -> str:
    return tag.replace(".", "").replace("-", "")
