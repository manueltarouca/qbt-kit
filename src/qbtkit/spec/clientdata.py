"""The `clientdata` scope — documented in no wiki page.

A small key-value store qBittorrent exposes for WebUI clients to persist their
own state (column layouts, filters) server-side. Found by extracting endpoints
from the source rather than from documentation.
"""

from __future__ import annotations

from ._types import Body, Endpoint, Json, NoContent, Param, Wire, register, text

register(
    Endpoint(
        scope="clientdata",
        name="load",
        method="GET",
        since=(2, 11, 4),
        summary="Read stored client data for a key.",
        returns=Json("ClientData"),
        params=(text("id", required=True),),
    ),
    Endpoint(
        scope="clientdata",
        name="store",
        method="POST",
        since=(2, 11, 4),
        summary="Write client data for a key. The payload is JSON in a form field.",
        returns=NoContent,
        body=Body.URLENCODED,
        params=(text("id", required=True), Param("data", Wire.JSON_BLOB, required=True)),
        mutating=True,
    ),
)
