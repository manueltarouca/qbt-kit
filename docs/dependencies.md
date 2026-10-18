# Dependencies, and why each one is here

This package runs with a user's credentials and can delete their data, so every
dependency is a liability. Each is justified below with what stdlib cannot do,
and vetted before it landed.

## Runtime

### httpx (>=0.28, BSD-3-Clause)

What stdlib lacks: connection pooling across the ~123 calls a session makes,
per-request timeouts, and a cookie jar that survives redirects. `urllib` has
none of the three — the auth probe in `tests/contract/probe_auth.py` is written
on `urllib` deliberately, and needed a hand-rolled `CookieJar` plus an opener
per call to do it.

Vetted: `encode/httpx`, the library behind `requests`' successor ecosystem;
0.28.1 published 2024-12-06. No transitive surprises (`httpcore`, `idna`,
`certifi`, `anyio`).

Note: httpx's DEBUG logging prints `Authorization` and `Cookie` headers.
`client.py` lowers the `httpx` and `httpcore` loggers to INFO explicitly rather
than relying on callers not to enable DEBUG.

### typer (>=0.27)

What stdlib lacks: 123 generated subcommands across 10 scopes, each with its own
typed options, `--help` and shell completion. `argparse` can express this but the
per-endpoint option construction would be hand-rolled; typer reads the
dynamically built signatures in `cli.py` directly.

Vetted: by the FastAPI author, built on `click`. 0.27.3 published 2026-10-06.

## Optional

### mcp (>=2.3, MIT)

Only needed for `qbt-mcp`, hence an extra rather than a core dependency. The
floor is 2.3 because the current major is 2.x; a `>=1.2` floor would resolve a
long-dead API.

## Development

`ruff` (lint and format), `ty` (types), `pytest` with `pytest-asyncio`. All
Astral except pytest. `ty` is pinned loosely at >=0.0.89 and is **advisory** in
CI rather than a gate, because it is pre-1.0 and still moving; it becomes a gate
when it stabilises.

## Deliberately not used

- **A bencode library.** `tests/contract/mktorrent.py` implements bencode in 30
  lines of stdlib, on purpose: building test fixtures with a dependency that the
  code under test might also use would couple setup to the thing being verified.
  Validated against reality — qBittorrent derived the same infohash from our
  fixture, and our parser read qBittorrent's own generated .torrent.
- **`qbittorrent-api`.** Mature and offers full library coverage with version
  gating; see README for why this exists alongside it. Its source is a useful
  cross-check for the spec, not a dependency.
- **A retry library.** The retry policy here is deliberately narrow (transport
  errors only, never on 4xx) and is a dozen lines.
