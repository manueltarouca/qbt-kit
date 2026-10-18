"""Introducing peers reliably on a trackerless, DHT-less swarm.

`torrents/addPeers` is a hint: qBittorrent may drop it, and a single call is not
enough once a session has been busy. So the introduction is retried, and made
from both sides — a leecher asking for a seeder is more likely to connect if the
seeder has also been told about the leecher.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable

from qbtkit.client import Client
from qbtkit.errors import QbtError


def _is_connected(t: dict) -> bool:
    """Has the leecher actually met a peer?

    `connections_count` only exists from qBittorrent 5.2, and reading it
    unconditionally made every peering test fail with a bare KeyError on 4.6,
    5.0 and 5.1 — which looked like a broken swarm rather than a missing field.
    Peer counts and progress are present on every supported version.
    """
    if (n := t.get("connections_count")) is not None:
        return bool(n > 0 or t["progress"] > 0)
    return bool(t.get("num_seeds", 0) > 0 or t.get("num_leechs", 0) > 0 or t["progress"] > 0)


def connect(
    leecher: Client,
    seeder: Client,
    infohash: str,
    leecher_addr: str,
    seeder_addr: str,
    timeout: float = 90.0,
) -> bool:
    """Keep introducing the two until the leecher reports a connected peer."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for client, addr in ((leecher, seeder_addr), (seeder, leecher_addr)):
            # The torrent may not exist on the other side yet; the next
            # round will try again.
            with contextlib.suppress(QbtError):
                client.call("torrents/addPeers", hashes=infohash, peers=[addr])
        for _ in range(6):
            t = leecher.call("torrents/info", hashes=infohash)
            if t and _is_connected(t[0]):
                return True
            time.sleep(0.5)
    return False


def wait_for(fn: Callable[[], object], timeout: float = 60.0, interval: float = 0.5) -> object:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = fn()
        if last:
            return last
        time.sleep(interval)
    return last
