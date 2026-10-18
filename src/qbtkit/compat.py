"""Version differences, measured rather than read.

Every value here was established by running `tests/contract/probe_auth.py`
against a seeded container of that version. Where the wiki and the measurement
disagreed, the measurement won; where an earlier draft of the plan guessed, it
was wrong. See docs/REVIEW-1.md.

Measured 2026-10-18 on linux/arm64, official `qbittorrent-nox` images.
"""

from __future__ import annotations

from typing import NamedTuple

# --------------------------------------------------------------------------- #
# What each version actually does


class AuthDialect(NamedTuple):
    login_ok_status: int
    login_ok_body: str | None  # None when the body is empty
    login_bad_status: int
    login_bad_body: str | None
    cookie_name: str  # informational only — never match on it, see below
    api_keys: bool  # Authorization: Bearer supported


DIALECTS: dict[str, AuthDialect] = {
    "2.9.3": AuthDialect(200, "Ok.", 200, "Fails.", "SID", False),  # qBittorrent 4.6.7
    "2.11.2": AuthDialect(200, "Ok.", 200, "Fails.", "SID", False),  # 5.0.2
    "2.11.4": AuthDialect(200, "Ok.", 200, "Fails.", "SID", False),  # 5.1.2
    "2.15.1": AuthDialect(204, None, 401, "Unauthorized", "QBT_SID_<port>", True),  # 5.2.3
}

# The universal rule, and why it exists.
#
# Login success cannot be judged from the status code: 5.0/5.1 answer a *failed*
# login with HTTP 200 and the body `Fails.`, so "2xx means success" authenticates
# nobody and reports success. It cannot be judged from the body either, since
# 5.2 returns an empty 204 on success.
#
# It can be judged from the cookie. Measured across 4.6.7, 5.0.2, 5.1.2 and
# 5.2.3: a failed login sets no cookie on any of them. So the only check needed
# is whether the transport's cookie jar gained a session cookie — which also
# avoids naming that cookie, necessary because 5.2 calls it `QBT_SID_<port>`
# while earlier versions call it `SID` (user-configurable on 5.0/5.1).
LOGIN_SUCCESS_IS_COOKIE_ISSUED = True

# Also measured on every version: only `auth/login` is public. `app/version` and
# `app/webapiVersion` both return 403 unauthenticated, so version detection
# cannot precede authentication — authenticate by probing, then read the version.
VERSION_REQUIRES_AUTH = True

# And on every version: a `Host` header whose port differs from the listening
# port is rejected with a bare 401, indistinguishable from bad credentials.
# `validateHostHeader` is on by default. Diagnose, do not retry.
HOST_HEADER_VALIDATION_401 = True


# --------------------------------------------------------------------------- #
# Renames

# `pause`/`resume` were *removed* in 5.0, not aliased: the old names 404 there.
# So translation runs in both directions rather than relying on tolerance.
RENAMES: dict[tuple[str, str], tuple[tuple[int, int, int], str]] = {
    # (scope, canonical name): (first version using it, name before that)
    ("torrents", "start"): ((2, 11, 0), "resume"),
    ("torrents", "stop"): ((2, 11, 0), "pause"),
}

# Parameter renames, same principle.
PARAM_RENAMES: dict[tuple[str, str, str], tuple[tuple[int, int, int], str]] = {
    ("torrents", "add", "stopped"): ((2, 11, 0), "paused"),
    ("torrents", "renameFile", "oldPath"): ((2, 4, 0), "id"),
    ("torrents", "renameFile", "newPath"): ((2, 4, 0), "name"),
}


# The 5.0 rename reached filter *values* too. qBittorrent answers an unknown
# filter with an empty list rather than an error, so an untranslated value reads
# as "nothing matched" — a silent wrong answer rather than a visible failure.
FILTER_VALUE_RENAMES: dict[str, tuple[tuple[int, int, int], str]] = {
    "stopped": ((2, 11, 0), "paused"),
    "running": ((2, 11, 0), "resumed"),
}


def wire_filter_value(value: str, version: tuple[int, int, int]) -> str:
    """The `filter=` value to put on the wire for this server version."""
    entry = FILTER_VALUE_RENAMES.get(value)
    if entry is None:
        return value
    since, older = entry
    return value if version >= since else older


def parse_version(raw: str) -> tuple[int, int, int]:
    """'2.15.1' -> (2, 15, 1). Tolerates a missing patch component."""
    parts = [int(p) for p in raw.strip().split(".")[:3]]
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2])


def wire_name(scope: str, name: str, version: tuple[int, int, int]) -> str:
    """The name to put on the wire for this server version."""
    entry = RENAMES.get((scope, name))
    if entry is None:
        return name
    since, older = entry
    return name if version >= since else older


def wire_param(scope: str, endpoint: str, param: str, version: tuple[int, int, int]) -> str:
    """The parameter name to put on the wire for this server version."""
    entry = PARAM_RENAMES.get((scope, endpoint, param))
    if entry is None:
        return param
    since, older = entry
    return param if version >= since else older


def supports_api_keys(version: tuple[int, int, int]) -> bool:
    """API keys arrived with qBittorrent 5.2.0 / WebAPI 2.15.

    Measured: `app/rotateAPIKey` returns 404 on 2.9.3, 2.11.2 and 2.11.4, and
    200 on 2.15.1. An earlier draft gated this at 2.11.2 — which is 5.0.0 — and
    would have sent `Authorization: Bearer` to servers that ignore it, then
    reported a credentials problem.
    """
    return version >= (2, 15, 0)
