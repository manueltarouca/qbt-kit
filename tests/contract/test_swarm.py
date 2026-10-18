"""Can the two containers actually trade data?

Everything downstream — dead-swarm detection, availability semantics, stall
behaviour — depends on a real transfer happening between seeder and leecher. No
tracker and no DHT, so peers are introduced explicitly with `torrents/addPeers`.
"""

from __future__ import annotations

import time

import pytest
from harness import Swarm
from mktorrent import build, infohash, make_content
from peering import connect

from qbtkit.client import Client

pytestmark = pytest.mark.contract

CONTENT = {"ep01.bin": 2 << 20, "ep02.bin": 2 << 20, "ep03.bin": 2 << 20}
_COUNTER = iter(range(1000))


def _next() -> int:
    return next(_COUNTER)


def _seed_content(swarm: Swarm, name: str) -> tuple[bytes, str]:
    """Create uniquely-named content on the seeder.

    The name is per-test on purpose: sharing a content name across tests meant
    one test's leftover torrent could satisfy another's "is anything at 100%?"
    assertion, which hid a real failure behind a passing one.
    """
    root = swarm.seeder.dir / "downloads" / name
    make_content(root, CONTENT)
    data = build(root, piece_length=1 << 18)
    return data, infohash(data)


def _wait(fn, timeout: float = 60.0, interval: float = 1.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = fn()
        if last:
            return last
        time.sleep(interval)
    return last


def test_seeder_serves_and_leecher_completes(
    swarm: Swarm, seeder: Client, leecher: Client
) -> None:
    data, ih = _seed_content(swarm, "sw-complete")

    # The seeder already has the files, so it rechecks straight to 100%.
    seeder.call("torrents/add", torrents=data, savepath="/downloads")
    got = _wait(
        lambda: (
            [t for t in seeder.call("torrents/info", hashes=ih) if t["progress"] >= 1.0] or None
        )
    )
    assert got, f"seeder did not reach 100%: {seeder.call('torrents/info')}"
    assert got[0]["hash"] == ih, "our infohash must match qBittorrent's"

    # The leecher starts empty and is told where the seeder is.
    leecher.call("torrents/add", torrents=data, savepath="/downloads")
    _wait(lambda: leecher.call("torrents/info") or None, timeout=20)
    assert connect(
        leecher, seeder, ih, swarm.leecher.peer_address, swarm.seeder.peer_address
    ), "peers never connected"

    done = _wait(
        lambda: (
            [t for t in leecher.call("torrents/info", hashes=ih) if t["progress"] >= 1.0]
            or None
        ),
        timeout=90,
    )
    lstate = leecher.call("torrents/info", hashes=ih)
    sstate = seeder.call("torrents/info", hashes=ih)
    assert done, (
        "leecher never completed.\n"
        f"  leecher: progress={lstate[0]['progress']} "
        f"state={lstate[0]['state']} conns={lstate[0]['connections_count']} "
        f"seeds={lstate[0]['num_complete']}/{lstate[0]['num_incomplete']}\n"
        f"  seeder:  progress={sstate[0]['progress'] if sstate else 'NO SUCH TORRENT'} "
        f"state={sstate[0]['state'] if sstate else '-'} "
        f"conns={sstate[0]['connections_count'] if sstate else '-'}\n"
        f"  seeder content_path={sstate[0]['content_path'] if sstate else '-'}"
    )
    assert done[0]["size"] == sum(CONTENT.values())


def test_availability_reflects_a_live_swarm(
    swarm: Swarm, seeder: Client, leecher: Client
) -> None:
    """While a transfer is in flight, availability exceeds progress.

    `availability - progress` is a *stall* diagnostic: it answers "do the peers
    I can reach hold the pieces I am missing?". On a local bridge a 6 MiB file
    completes in well under a second, so the window where progress < 1 is too
    short to sample — the leecher is therefore rate-limited to stretch it. That
    is not a contrivance: it reproduces the shape of the real case, where
    progress sits still and availability tells you whether waiting is futile.
    """
    data, ih = _seed_content(swarm, f"sw-{_next()}")
    seeder.call("torrents/add", torrents=data, savepath="/downloads")
    _wait(
        lambda: (
            [t for t in seeder.call("torrents/info", hashes=ih) if t["progress"] >= 1.0] or None
        )
    )

    # 256 KiB/s over 6 MiB leaves roughly 20s of observable transfer.
    leecher.call("torrents/add", torrents=data, savepath="/downloads", dlLimit=256 * 1024)
    _wait(lambda: leecher.call("torrents/info") or None, timeout=20)
    assert connect(
        leecher, seeder, ih, swarm.leecher.peer_address, swarm.seeder.peer_address
    ), "peers never connected"

    samples: list[tuple[float, float]] = []
    deadline = time.time() + 60
    while time.time() < deadline:
        t = leecher.call("torrents/info", hashes=ih)[0]
        samples.append((t["progress"], t["availability"]))
        if t["availability"] - t["progress"] > 0.05 and t["progress"] < 1.0:
            break
        if t["progress"] >= 1.0:
            break
        time.sleep(0.5)

    healthy = [(p, a) for p, a in samples if a - p > 0.05 and p < 1.0]
    assert healthy, (
        "availability never exceeded progress mid-transfer against a seeder "
        f"holding the whole file; samples (progress, availability): {samples[:12]}"
    )
    progress, availability = healthy[0]
    assert availability >= 0.9, (
        f"a single complete peer should push availability near 1.0, got "
        f"{availability} at progress {progress}"
    )


def test_dead_swarm_is_distinguishable_from_a_slow_one(
    swarm: Swarm, seeder: Client, leecher: Client
) -> None:
    """With the seeder gone, availability converges down to progress.

    This is the condition that made twelve real downloads unfinishable: not
    slowness, but a swarm that collectively lacks the missing pieces.
    """
    data, ih = _seed_content(swarm, f"sw-{_next()}")
    seeder.call("torrents/add", torrents=data, savepath="/downloads")
    _wait(
        lambda: (
            [t for t in seeder.call("torrents/info", hashes=ih) if t["progress"] >= 1.0] or None
        )
    )
    leecher.call("torrents/add", torrents=data, savepath="/downloads", dlLimit=128 * 1024)
    _wait(lambda: leecher.call("torrents/info") or None, timeout=20)
    assert connect(
        leecher, seeder, ih, swarm.leecher.peer_address, swarm.seeder.peer_address
    ), "peers never connected"

    # Let some data move, then remove the only source of the rest.
    _wait(
        lambda: (
            [t for t in leecher.call("torrents/info", hashes=ih) if t["progress"] > 0.0] or None
        ),
        timeout=60,
    )
    seeder.call("torrents/delete", hashes=ih, deleteFiles=False, confirm=True)

    gap = _wait(
        lambda: (
            [
                t
                for t in leecher.call("torrents/info", hashes=ih)
                if t["progress"] < 1.0 and t["availability"] - t["progress"] <= 0.05
            ]
            or None
        ),
        timeout=60,
    )
    state = leecher.call("torrents/info")[0]
    assert gap, (
        "availability should fall to progress once no peer holds the remainder; "
        f"progress={state['progress']} availability={state['availability']}"
    )
