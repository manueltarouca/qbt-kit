"""The `torrentcreator` scope — new in qBittorrent 5.0, documented in no wiki page.

Creating a torrent is a background task: `addTask` queues it, `status` polls,
`torrentFile` fetches the finished .torrent as bytes, `deleteTask` cleans up.
Found only by extracting endpoints from the source; see docs/TRACEABILITY.md.
"""

from __future__ import annotations

from ._types import (
    Binary,
    Body,
    Endpoint,
    Json,
    NoContent,
    Param,
    Wire,
    flag,
    integer,
    register,
    text,
)

register(
    Endpoint(
        scope="torrentcreator",
        name="addTask",
        method="POST",
        since=(2, 11, 2),
        summary="Queue creation of a .torrent from a local path on the server.",
        returns=Json("TorrentCreatorTask"),
        body=Body.URLENCODED,
        params=(
            text("sourcePath", required=True),
            text("torrentFilePath", summary="where to write the .torrent"),
            flag("private"),
            flag("startSeeding"),
            flag("optimizeAlignment"),
            integer("pieceSize", summary="0 lets qBittorrent choose"),
            integer("paddedFileSizeLimit"),
            text("comment"),
            text("source"),
            Param("trackers", Wire.PIPE_LIST),
            Param("urlSeeds", Wire.PIPE_LIST),
            text("format", summary="v1, v2 or hybrid"),
        ),
        mutating=True,
    ),
    Endpoint(
        scope="torrentcreator",
        name="status",
        method="GET",
        since=(2, 11, 2),
        summary="Status of one creation task, or all of them.",
        returns=Json("TorrentCreatorStatus"),
        params=(text("taskID"),),
    ),
    Endpoint(
        scope="torrentcreator",
        name="torrentFile",
        method="POST",
        since=(2, 11, 2),
        summary="Fetch the finished .torrent as raw bytes.",
        returns=Binary("application/x-bittorrent"),
        body=Body.URLENCODED,
        params=(text("taskID", required=True),),
    ),
    Endpoint(
        scope="torrentcreator",
        name="deleteTask",
        method="POST",
        since=(2, 11, 2),
        summary="Discard a creation task.",
        returns=NoContent,
        body=Body.URLENCODED,
        params=(text("taskID", required=True),),
        mutating=True,
    ),
)
