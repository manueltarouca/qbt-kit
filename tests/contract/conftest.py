"""Contract-test fixtures, and the guard that keeps them off real servers.

The author's own qBittorrent manages a live media pipeline. A test that deletes,
relocates or re-categorises torrents there destroys real state, so the guard is
code rather than a note in a README.
"""

from __future__ import annotations

import os
import pathlib
import sys
from collections.abc import Iterator
from urllib.parse import urlparse

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from harness import PASSWORD, USERNAME, Swarm

from qbtkit.client import Client
from qbtkit.spec.app import LOCKOUT_KEYS

# Ports owned by containers this harness created. Anything else on loopback is
# presumed to be a real server and refused.
_OWNED: set[int] = set()

DEFAULT_TAG = os.environ.get("QBT_TEST_TAG", "5.2.3-1")


def guard(url: str) -> None:
    """Refuse any target this harness did not create."""
    parsed = urlparse(url)
    host, port = parsed.hostname, parsed.port
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError(f"contract tests only talk to containers, not {host!r}")
    if port not in _OWNED:
        raise RuntimeError(
            f"refusing to use {url}: port {port} is not a container this harness "
            f"started (owned: {sorted(_OWNED) or 'none'}). The author's real "
            f"qBittorrent listens on loopback too, and these tests mutate state."
        )


@pytest.fixture(scope="module")
def swarm() -> Iterator[Swarm]:
    """A seeder and leecher pair, torn down unconditionally.

    Module-scoped rather than session-scoped. The transfer tests passed when run
    per-file and failed when run after the scenario file, and no single action in
    the scenarios reproduced it in isolation — churn, preference resets and
    category moves were each ruled out by hand. Rather than leave a known
    order-dependent failure in the suite, each module gets its own containers so
    no file can poison another. It costs about a minute per module and buys
    determinism.
    """
    s = Swarm(DEFAULT_TAG)
    try:
        s.up()
        _OWNED.update({s.seeder.port, s.leecher.port})
    except Exception:
        s.down()
        raise
    try:
        yield s
    finally:
        _OWNED.difference_update({s.seeder.port, s.leecher.port})
        s.down()


def _client_for(url: str, *, read_only: bool = False) -> Client:
    guard(url)
    # Ambient credentials are ignored on purpose: the user's real QBT_URL or
    # QBT_API_KEY must never leak into a test session.
    return Client(
        url,
        username=USERNAME,
        password=PASSWORD,
        api_key=None,
        read_only=read_only,
        use_keychain=False,
    )


@pytest.fixture
def leecher(swarm: Swarm) -> Iterator[Client]:
    c = _client_for(swarm.leecher.url)
    try:
        yield c
    finally:
        c.close()


@pytest.fixture
def seeder(swarm: Swarm) -> Iterator[Client]:
    c = _client_for(swarm.seeder.url)
    try:
        yield c
    finally:
        c.close()


@pytest.fixture(autouse=True)
def _clean_swarm(request: pytest.FixtureRequest) -> Iterator[None]:
    """Remove every torrent from both nodes around each test.

    The swarm is session-scoped so the containers are not rebuilt per test, but
    that leaves torrent state shared: one test completing a download left the
    next one asserting against a torrent that was already at 100%. Each test
    therefore starts from an empty queue on both nodes.
    """
    if "swarm" not in request.fixturenames:
        yield
        return
    s: Swarm = request.getfixturevalue("swarm")

    def wipe() -> None:
        for node in (s.seeder, s.leecher):
            c = _client_for(node.url)
            try:
                hashes = [t["hash"] for t in c.call("torrents/info")]
                if hashes:
                    c.call("torrents/delete", hashes=hashes, deleteFiles=True, confirm=True)
            finally:
                c.close()

    wipe()
    try:
        yield
    finally:
        wipe()


@pytest.fixture(autouse=True)
def _quiet_httpx() -> None:
    """Keep per-request INFO lines out of failure output."""
    import logging

    logging.getLogger("httpx").setLevel(logging.WARNING)


@pytest.fixture(autouse=True)
def _scrub_ambient_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove the user's own credentials from the environment for every test."""
    for var in ("QBT_URL", "QBT_API_KEY", "QBT_USERNAME", "QBT_PASSWORD"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def _restore_preferences(request: pytest.FixtureRequest) -> Iterator[None]:
    """Undo preference changes a test makes, on both nodes.

    Several scenarios have to set global preferences to provoke the behaviour
    they are about — queueing limits, share limits. Those are server-wide and
    outlive the test, and deleting the torrents afterwards does not undo them.
    That leaked state is not hypothetical: `max_seeding_time=0` left on the
    seeder stops it the instant a torrent completes, so a later test that needs
    a *working seeder* finds nothing to connect to, and fails with the useless
    symptom "peers never connected".

    Snapshotting and diffing keeps each test honest about what it changed
    without making every author remember to clean up.
    """
    if "swarm" not in request.fixturenames:
        yield
        return
    s: Swarm = request.getfixturevalue("swarm")

    def snapshot() -> dict[str, dict]:
        out = {}
        for node in (s.seeder, s.leecher):
            c = _client_for(node.url)
            try:
                out[node.url] = c.call("app/preferences")
            finally:
                c.close()
        return out

    before = snapshot()
    try:
        yield
    finally:
        for url, original in before.items():
            c = _client_for(url)
            try:
                now = c.call("app/preferences")
                revert = {
                    k: v
                    for k, v in original.items()
                    # Only keys the test actually moved, and never the WebUI
                    # keys the client refuses anyway — reverting those would
                    # turn a leak into a lockout.
                    if k not in LOCKOUT_KEYS and k in now and now[k] != v
                }
                if revert:
                    c.call("app/setPreferences", json=revert)
            finally:
                c.close()
