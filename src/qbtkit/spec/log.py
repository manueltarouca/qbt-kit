"""The `log` scope — the server's own log buffer."""

from __future__ import annotations

from ._types import Endpoint, Json, flag, integer, register

register(
    Endpoint(
        scope="log",
        name="main",
        method="GET",
        summary="Main log entries, filterable by severity and by `last_known_id`.",
        returns=Json("LogEntry"),
        params=(
            flag("normal"),
            flag("info"),
            flag("warning"),
            flag("critical"),
            integer("last_known_id", summary="return only entries after this id"),
        ),
    ),
    Endpoint(
        scope="log",
        name="peers",
        method="GET",
        summary="Peer log: bans and blocked connections.",
        returns=Json("PeerLogEntry"),
        params=(integer("last_known_id"),),
    ),
)
