"""Does the harness itself work, and does the guard hold?

These run first: if the swarm cannot form, every scenario below it is noise.
"""

from __future__ import annotations

import pytest
from conftest import _OWNED, guard
from harness import Swarm

from qbtkit.client import Client

pytestmark = pytest.mark.contract


def test_guard_refuses_unowned_loopback_ports() -> None:
    """The author's real qBittorrent is on loopback too; refuse it explicitly."""
    with pytest.raises(RuntimeError, match="not a container this harness started"):
        guard("http://127.0.0.1:8080")


def test_guard_refuses_remote_hosts() -> None:
    with pytest.raises(RuntimeError, match="only talk to containers"):
        guard("http://192.0.2.10:8080")  # RFC 5737 documentation address


def test_guard_allows_owned_ports() -> None:
    _OWNED.add(65000)
    try:
        guard("http://127.0.0.1:65000")
    finally:
        _OWNED.discard(65000)


def test_both_nodes_authenticate(swarm: Swarm, leecher: Client, seeder: Client) -> None:
    assert leecher.auth_mode == "cookie"
    assert seeder.auth_mode == "cookie"
    assert leecher.version == seeder.version


def test_nodes_have_private_addresses(swarm: Swarm) -> None:
    """Peers are introduced by address, so both need one on the private net."""
    assert swarm.seeder.ip != swarm.leecher.ip
    assert swarm.seeder.peer_address.endswith(":6881")


def test_nodes_start_empty(leecher: Client, seeder: Client) -> None:
    assert leecher.call("torrents/info") == []
    assert seeder.call("torrents/info") == []


def test_dht_is_off(leecher: Client) -> None:
    """A test swarm must not be able to reach the public internet."""
    prefs = leecher.call("app/preferences")
    assert prefs["dht"] is False
    assert prefs["pex"] is False
    assert prefs["lsd"] is False
