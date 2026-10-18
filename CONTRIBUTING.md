# Contributing

Thanks for looking. The project has one unusual property worth understanding
before you change anything: **the endpoint surface is generated from a spec, and
the spec is checked against qBittorrent's own source.** That shapes most of the
workflow below.

## Setup

```sh
uv sync --all-extras
uv run pytest tests/unit -q          # fast, no containers
uv run ruff check . && uv run ruff format --check .
uv run ty check src tools tests      # same paths CI checks
```

`ty` runs with `continue-on-error` in CI because it is pre-1.0, which means a
type error leaves the job green and only shows up as an annotation. Run it over
all three paths locally — checking `src` alone will not reproduce what CI sees.

## Adding or changing an endpoint

Do not add a CLI command or an MCP tool by hand. Add an `Endpoint` to the right
module under `src/qbtkit/spec/`, and the client, the CLI command and the
coverage ledger follow from it. A spec entry records the wire format, the
parameters, the return kind, the version it appeared in, and whether it mutates
or destroys — the safety gates read those flags, so getting them right is how
the gates stay correct.

Then prove the surface still lines up with upstream:

```sh
uv run python tools/build_coverage.py --target release-5.2.3 --strict
```

This fails on two things: an endpoint qBittorrent exposes that the spec misses,
and an endpoint the spec claims that qBittorrent does not have. The second is
the one that catches typos in a `name`.

The inventories under `src/qbtkit/inventory/` are extracted from the qBittorrent
C++ source per release tag, not transcribed from the wiki. They ship inside the
package because `qbt coverage` reads them at runtime — the wiki documents 78
endpoints where 5.2.3 ships 123. Regenerate one with:

```sh
uv run python tools/extract_inventory.py --ref release-5.2.3 -o src/qbtkit/inventory/release-5.2.3.json
```

## Tests

Unit tests cover signatures, safety gates and spec invariants. They cannot
cover behaviour, so anything about how a *running* qBittorrent responds belongs
in `tests/contract/`, which drives real containers:

```sh
uv run pytest -m contract tests/contract -q        # ~70s
QBT_TEST_TAG=4.6.7-1 uv run pytest -m contract tests/contract -q
```

Podman and Docker both work; the harness finds whichever is installed and
`QBT_CONTAINER_RUNTIME` forces a specific binary.

Contract tests refuse to run against anything but containers they started
themselves. That guard is deliberate and should stay: the author's own
qBittorrent runs on loopback too, and these tests delete torrents.

Please write the failing test first and check it fails for the reason you think.
Several bugs here were originally "fixed" against tests that passed before the
fix, and `docs/TESTING.md` lists the behaviours that cost real time to learn.

## Style

- `ruff` for lint and format, 96 columns. Markdown is excluded from formatting
  so hand-laid-out snippets in docs stay readable.
- `ty` runs in CI but does not gate the build, since it is pre-1.0.
- Explain *why* in comments where the reason is not obvious from the code. Most
  comments in this codebase exist because something surprising happened.

## Releasing

Publishing is deliberately not automated on tags. It needs a manual
`workflow_dispatch` run with the `publish` input ticked, because a version
number on PyPI can never be reused.
