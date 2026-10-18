#!/usr/bin/env python3
"""Coverage gate for CI.

    tools/build_coverage.py --target release-5.2.3 --strict
    tools/build_coverage.py --target release-5.2.3 --json coverage.json

The ledger itself lives in `qbtkit.coverage` so that `qbt coverage` and this
gate are the same computation. They used to be separate, which is how the
installed CLI could be broken while CI stayed green.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from qbtkit import coverage as cov  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=cov.DEFAULT_TARGET)
    ap.add_argument("--json", dest="json_out")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero if the spec does not cover the target",
    )
    args = ap.parse_args()

    try:
        ledger = cov.build(args.target)
    except cov.UnknownTarget as exc:
        sys.exit(str(exc))

    print(cov.render(ledger))

    if args.json_out:
        (ROOT / args.json_out).write_text(json.dumps(ledger.as_dict(), indent=2) + "\n")

    if args.strict:
        if ledger.phantoms:
            print(f"\nFAIL: {len(ledger.phantoms)} phantom endpoint(s)", file=sys.stderr)
            return 1
        if ledger.specced != ledger.total:
            missing = ledger.total - ledger.specced
            print(f"\nFAIL: {missing} endpoint(s) not specced", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
