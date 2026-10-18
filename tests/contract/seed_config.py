#!/usr/bin/env python3
"""Write a qBittorrent.conf with deterministic WebUI credentials.

Containers cannot be left to default: since 4.6.1 a server with no password set
prints a *random* temporary password to stdout, and before that it was
admin/adminadmin. Either way the harness would have to scrape logs, which is
fragile across the version matrix. Seeding the config instead makes credentials
identical on every version.

The hash format is from src/base/utils/password.cpp (verified at release-5.2.3):
PBKDF2-HMAC-SHA512, 100000 iterations, 16-byte salt, 64-byte derived key,
stored as base64(salt) + ":" + base64(key) inside @ByteArray(...).

    seed_config.py --out /tmp/cfg/qBittorrent.conf --password testpass123

Stdlib only.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os

ITERATIONS = 100_000
SALT_LEN = 16  # 4 x uint32 in the C++
KEY_LEN = 64  # sha512 digest size


def pbkdf2_value(password: str, salt: bytes | None = None) -> str:
    """Return the @ByteArray(...) value qBittorrent stores for a password."""
    if salt is None:
        salt = os.urandom(SALT_LEN)
    if len(salt) != SALT_LEN:
        raise ValueError(f"salt must be {SALT_LEN} bytes, got {len(salt)}")
    key = hashlib.pbkdf2_hmac(
        "sha512", password.encode("utf-8"), salt, ITERATIONS, dklen=KEY_LEN
    )
    return (base64.b64encode(salt) + b":" + base64.b64encode(key)).decode("ascii")


CONF = """[LegalNotice]
Accepted=true

[Preferences]
WebUI\\Enabled=true
WebUI\\Address=*
WebUI\\Port={port}
WebUI\\Username={username}
WebUI\\Password_PBKDF2="@ByteArray({pbkdf2})"
WebUI\\LocalHostAuth=true
WebUI\\CSRFProtection=false
WebUI\\HostHeaderValidation={host_header}
WebUI\\ClickjackingProtection=false
Downloads\\SavePath={save_path}
Downloads\\PreAllocation=false
General\\Locale=en

[BitTorrent]
# These belong under [BitTorrent], not [Preferences]: the keys are
# BitTorrent/Session/* in the source (sessionimpl.cpp), and putting them in
# [Preferences] silently does nothing — which left DHT enabled and the test
# swarm able to reach the public internet.
Session\\DefaultSavePath={save_path}
Session\\DHTEnabled=false
Session\\PeXEnabled=false
Session\\LSDEnabled=false
Session\\Port=6881
Session\\Encryption=0
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--username", default="testuser")
    ap.add_argument("--password", default="testpass123")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--save-path", default="/downloads")
    ap.add_argument(
        "--host-header-validation",
        choices=("true", "false"),
        default="true",
        help="leave true to mirror production; false only for the "
        "test that proves the mismatch 401",
    )
    ap.add_argument("--salt-hex", help="fixed salt, for reproducible fixtures")
    args = ap.parse_args()

    salt = bytes.fromhex(args.salt_hex) if args.salt_hex else None
    value = pbkdf2_value(args.password, salt)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(
            CONF.format(
                port=args.port,
                username=args.username,
                pbkdf2=value,
                save_path=args.save_path,
                host_header=args.host_header_validation,
            )
        )
    # DHT/PeX/LSD are off so a test swarm cannot reach the public internet and
    # cannot be reached from it. Peers are introduced explicitly.
    print(
        f"wrote {args.out}  user={args.username} port={args.port} "
        f"host_header_validation={args.host_header_validation}"
    )


if __name__ == "__main__":
    main()
