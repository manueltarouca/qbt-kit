#!/usr/bin/env python3
"""Probe a qBittorrent server's auth behaviour and report the facts.

Milestone 1 exists because revision 1 of the plan got four auth details wrong.
This script establishes them empirically per version, so the client's auth layer
is built from measurements rather than from the wiki.

    probe_auth.py --url http://127.0.0.1:18080 -u testuser -p testpass123

It reports, and exits non-zero only on a transport failure — a surprising
*answer* is data, not an error. Stdlib only, so it runs before the package does.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import sys
import urllib.error
import urllib.parse
import urllib.request


def call(
    url: str,
    data: dict | None = None,
    headers: dict | None = None,
    jar: http.cookiejar.CookieJar | None = None,
    method: str | None = None,
) -> tuple[int, str, str]:
    """Return (status, body, set_cookie_names)."""
    # `data={}` must still mean "POST with an empty body"; urlencode({}) is ""
    # which is falsy, so testing `if data` silently turns such calls into GETs.
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(
        url,
        data=body,
        headers=headers or {},
        method=method or ("POST" if body is not None else "GET"),
    )
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar)
        if jar is not None
        else urllib.request.BaseHandler()
    )
    try:
        with opener.open(req, timeout=15) as r:
            return (
                r.status,
                r.read().decode("utf-8", "replace"),
                dict(r.headers).get("Set-Cookie", ""),
            )
    except urllib.error.HTTPError as e:
        return (
            e.code,
            e.read().decode("utf-8", "replace"),
            dict(e.headers).get("Set-Cookie", ""),
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("-u", "--username", default="testuser")
    ap.add_argument("-p", "--password", default="testpass123")
    ap.add_argument("--json", action="store_true", help="emit findings as JSON")
    args = ap.parse_args()
    base = args.url.rstrip("/") + "/api/v2"
    found = {}

    # 1. Is anything readable without authenticating?
    st, body, _ = call(f"{base}/app/webapiVersion")
    found["unauth_version_status"] = st
    print(f"  unauthenticated app/webapiVersion     -> HTTP {st} {body.strip()[:40]!r}")

    # 2. Bad credentials: 200 'Fails.' on <=5.1, 401 on 5.2+, 403 when banned.
    st, body, _ = call(
        f"{base}/auth/login", {"username": args.username, "password": "definitely-wrong"}
    )
    found["bad_login_status"] = st
    found["bad_login_body"] = body.strip()[:20]
    print(f"  login with wrong password             -> HTTP {st} {body.strip()[:20]!r}")

    # 3. Good credentials, and what the session cookie is actually called.
    jar = http.cookiejar.CookieJar()
    st, body, _raw = call(
        f"{base}/auth/login", {"username": args.username, "password": args.password}, jar=jar
    )
    names = [c.name for c in jar]
    found["good_login_status"] = st
    found["good_login_body"] = body.strip()[:20]
    found["cookie_names"] = names
    print(f"  login with correct password           -> HTTP {st} {body.strip()[:20]!r}")
    print(f"  session cookie name(s)                -> {names or 'NONE'}")
    if not names:
        print("  !! no cookie issued — the seeded password hash is wrong")
        found["authenticated"] = False
    else:
        # 4. Now version is readable.
        st, ver, _ = call(f"{base}/app/webapiVersion", jar=jar)
        found["webapi_version"] = ver.strip()
        found["authenticated"] = st == 200
        print(f"  authenticated app/webapiVersion       -> HTTP {st} {ver.strip()!r}")

        # 5. Host-header port mismatch. Default-on validation rejects this with a
        #    bare 401 that looks exactly like bad credentials.
        host = urllib.parse.urlparse(args.url).hostname
        st, body, _ = call(f"{base}/app/version", jar=jar, headers={"Host": f"{host}:9999"})
        found["host_header_mismatch_status"] = st
        print(f"  authenticated, Host port mismatched  -> HTTP {st} {body.strip()[:30]!r}")

        # 6. Does this version support API keys at all, and does Bearer work?
        st, body, _ = call(f"{base}/app/rotateAPIKey", {}, jar=jar)
        found["rotate_api_key_status"] = st
        # returns JSON {"apiKey": "..."} rather than a bare token
        try:
            key = json.loads(body).get("apiKey", "")
        except (json.JSONDecodeError, AttributeError):
            key = body.strip()
        print(
            f"  app/rotateAPIKey                      -> HTTP {st}"
            f"{' (not supported on this version)' if st == 404 else ''}"
        )
        if st == 200 and key:
            st, ver, _ = call(
                f"{base}/app/webapiVersion", headers={"Authorization": f"Bearer {key}"}
            )
            found["bearer_status"] = st
            print(f"  Bearer auth with that key             -> HTTP {st} {ver.strip()!r}")
            st, _, _ = call(f"{base}/app/webapiVersion", headers={"X-Api-Key": key})
            found["x_api_key_status"] = st
            print(
                f"  X-Api-Key header with the same key    -> HTTP {st}"
                f"{'  (not a supported mechanism)' if st != 200 else ''}"
            )
        else:
            found["bearer_status"] = None

        call(f"{base}/auth/logout", {}, jar=jar)

    if args.json:
        print(json.dumps(found, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
