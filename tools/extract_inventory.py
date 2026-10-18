#!/usr/bin/env python3
"""Extract the authoritative endpoint inventory from the qBittorrent source.

The wiki lags and omits whole scopes (torrentcreator and clientdata are absent
from the 4.1 page), so the contract we measure coverage against is the source:
every WebUI endpoint is a method named `<name>Action()` on a `*Controller`, and
the scope is the controller's name.

    tools/extract_inventory.py --ref master -o src/qbtkit/inventory/master.json

Writes {"ref", "fetched_at", "endpoints": [{"scope","name","source"}...]}.
Stdlib only, so it runs in CI without installing anything.
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com/repos/qbittorrent/qBittorrent/contents/src/webui/api"
RAW = "https://raw.githubusercontent.com/qbittorrent/qBittorrent/{ref}/src/webui/api/{name}"

# apicontroller is the abstract base, not a routable scope.
NOT_A_SCOPE = {"apicontroller.cpp"}

ACTION = re.compile(r"\b\w*Controller::(\w+)Action\s*\(", re.MULTILINE)


def get(url: str, token: str | None = None) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "qbt-kit-inventory",
            "Accept": "application/vnd.github+json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as f:
        return f.read()


def scope_of(filename: str) -> str:
    """appcontroller.cpp -> app, torrentscontroller.cpp -> torrents."""
    stem = filename[: -len("controller.cpp")]
    # The route scope is the controller name lowercased; qBittorrent registers
    # TorrentsController under "torrents", TorrentCreatorController under
    # "torrentcreator", and so on.
    return stem.lower()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="master", help="git ref or tag (e.g. release-5.2.3)")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--token", help="GitHub token, to avoid rate limits")
    args = ap.parse_args()

    try:
        listing = json.loads(get(f"{API}?ref={args.ref}", args.token))
    except urllib.error.HTTPError as e:
        sys.exit(f"listing src/webui/api at {args.ref} failed: HTTP {e.code}")

    files = sorted(
        f["name"]
        for f in listing
        if f["name"].endswith("controller.cpp") and f["name"] not in NOT_A_SCOPE
    )
    if not files:
        sys.exit(f"no controllers found at ref {args.ref!r} — wrong ref?")

    endpoints = []
    for name in files:
        body = get(RAW.format(ref=args.ref, name=name), args.token).decode("utf-8", "replace")
        found = sorted(set(ACTION.findall(body)))
        if not found:
            print(f"  WARNING: no actions matched in {name}", file=sys.stderr)
        for action in found:
            endpoints.append({"scope": scope_of(name), "name": action, "source": name})
        print(f"  {scope_of(name):16s} {len(found):3d} endpoint(s)  <- {name}", file=sys.stderr)

    endpoints.sort(key=lambda e: (e["scope"], e["name"]))
    doc = {
        "ref": args.ref,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "endpoint_count": len(endpoints),
        "endpoints": endpoints,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, sort_keys=False)
        f.write("\n")
    print(
        f"\n{len(endpoints)} endpoints across {len(files)} scopes -> {args.out}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
