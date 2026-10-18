"""MCP server entry point, with a readable failure when the extra is missing.

`qbt-mcp` is installed by the base package but needs the optional `mcp` extra
to run. Importing the server module directly from the console script turns that
into `ModuleNotFoundError: No module named 'mcp'`, which reads like a broken
install rather than a missing extra. Deferring the import lets the error say
what to type instead.
"""

from __future__ import annotations

import sys

EXTRA_HINT = """qbt-mcp needs the optional 'mcp' extra, which is not installed.

  uvx --from 'qbt-kit[mcp]' qbt-mcp        # one-off
  uv add 'qbt-kit[mcp]'                    # in a project
  pip install 'qbt-kit[mcp]'

The 'qbt' CLI works without it."""


def main() -> None:
    try:
        from qbtkit.mcp.server import main as _main
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised by test
        if exc.name in {"mcp", "pydantic"}:
            print(EXTRA_HINT, file=sys.stderr)
            raise SystemExit(2) from exc
        raise
    _main()
