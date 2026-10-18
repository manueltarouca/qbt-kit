"""The `transfer` scope — global rates, limits and the alternative-speed mode."""

from __future__ import annotations

from ._types import Body, Endpoint, Json, NoContent, RawText, flag, integer, register, text

register(
    Endpoint(
        scope="transfer",
        name="info",
        method="GET",
        summary="Global transfer statistics: rates, totals, connection status.",
        returns=Json("TransferInfo"),
    ),
    Endpoint(
        scope="transfer",
        name="downloadLimit",
        method="GET",
        summary="Global download limit in bytes/s (0 = unlimited).",
        returns=RawText,
    ),
    Endpoint(
        scope="transfer",
        name="setDownloadLimit",
        method="POST",
        summary="Set the global download limit in bytes/s.",
        returns=NoContent,
        body=Body.URLENCODED,
        params=(integer("limit", required=True),),
        mutating=True,
    ),
    Endpoint(
        scope="transfer",
        name="uploadLimit",
        method="GET",
        summary="Global upload limit in bytes/s.",
        returns=RawText,
    ),
    Endpoint(
        scope="transfer",
        name="setUploadLimit",
        method="POST",
        summary="Set the global upload limit in bytes/s. Note this throttles "
        "uploads while downloading too, and peers reciprocate, so a low "
        "value can slow downloads rather than just saving bandwidth.",
        returns=NoContent,
        body=Body.URLENCODED,
        params=(integer("limit", required=True),),
        mutating=True,
    ),
    Endpoint(
        scope="transfer",
        name="speedLimitsMode",
        method="GET",
        summary="Whether the alternative speed limits are active (1) or not (0).",
        returns=RawText,
    ),
    Endpoint(
        scope="transfer",
        name="toggleSpeedLimitsMode",
        method="POST",
        summary="Flip between normal and alternative speed limits.",
        returns=NoContent,
        mutating=True,
    ),
    Endpoint(
        scope="transfer",
        name="setSpeedLimitsMode",
        method="POST",
        since=(2, 11, 3),
        summary="Set the alternative speed limits mode explicitly rather than "
        "toggling, which is safer when you do not know the current state.",
        returns=NoContent,
        body=Body.URLENCODED,
        params=(flag("mode", required=True),),
        mutating=True,
    ),
    Endpoint(
        scope="transfer",
        name="banPeers",
        method="POST",
        since=(2, 3, 0),
        summary="Ban peers permanently, host:port pipe-separated.",
        returns=NoContent,
        body=Body.URLENCODED,
        params=(text("peers", required=True),),
        mutating=True,
    ),
)
