"""The `auth` scope.

Specced for completeness, but `Client` does not route login through the generic
call path: success cannot be judged from status or body, because 4.6/5.0/5.1
answer a *failed* login with HTTP 200 and the body "Fails." while 5.2 returns an
empty 204. The client instead checks whether a session cookie was issued, which
is the one rule that holds on every tested version. See compat.py.
"""

from __future__ import annotations

from ._types import Body, Endpoint, NoContent, RawText, register, text

register(
    Endpoint(
        scope="auth",
        name="login",
        method="POST",
        summary="Authenticate and receive a session cookie. The only endpoint "
        "that does not require an existing session.",
        returns=RawText,  # "Ok." / "Fails." on <=5.1, empty 204 on 5.2+
        body=Body.URLENCODED,
        params=(text("username", required=True), text("password", required=True)),
    ),
    Endpoint(
        scope="auth",
        name="logout",
        method="POST",
        summary="Invalidate the current session.",
        returns=NoContent,
        mutating=True,
    ),
)
