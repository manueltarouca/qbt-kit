"""The `sync` scope — the delta protocol.

Both endpoints take a response id (`rid`): pass 0 for a full snapshot, then the
`rid` from the previous response to receive only what changed. Merging those
deltas is stateful and belongs in the library rather than the spec.
"""

from __future__ import annotations

from ._types import Endpoint, Json, integer, register, text

register(
    Endpoint(
        scope="sync",
        name="maindata",
        method="GET",
        summary="Everything that changed since `rid`: torrents, categories, tags, "
        "server state. Pass rid=0 for a full snapshot.",
        returns=Json("MainData"),
        params=(integer("rid", summary="response id from the previous call; 0 = full"),),
    ),
    Endpoint(
        scope="sync",
        name="torrentPeers",
        method="GET",
        summary="Peers of one torrent, as a delta against `rid`.",
        returns=Json("TorrentPeers"),
        params=(text("hash", required=True), integer("rid")),
        untestable="empty without a second peer in the swarm",
    ),
)
