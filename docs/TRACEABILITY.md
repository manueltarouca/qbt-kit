# Traceability and coverage measurement

How the coverage claim is built and gated. This describes what exists;
`PLAN.md` records the original design, which was more elaborate than what
turned out to be needed.

## Why this exists

"100% coverage" is only meaningful against a denominator, and the obvious
denominator is wrong. The 4.1 wiki page documents **78** endpoints; qBittorrent
5.2.3 actually ships **123**; master has **132**. Two whole scopes
(`torrentcreator`, `clientdata`) appear in no wiki page at all. Measuring
against the wiki would have declared victory 36 endpoints short.

So the denominator is extracted from the source, committed, and diffable.

## Layer 1 — the inventory (the denominator)

`tools/extract_inventory.py` reads `src/webui/api/*controller.cpp` from a given
git ref and extracts every `<name>Action()` method, which is how qBittorrent
declares a routable endpoint. Scope comes from the controller name.

Committed snapshots, regenerable in CI:

| ref | endpoints | role |
|---|---|---|
| `release-4.1.9` | 78 | compatibility floor |
| `release-5.2.3` | **123** | primary target |
| `master` | 132 | early warning only, never the target |

Measured facts this already produced:

- **48** endpoints exist in 5.2.3 but not 4.1.9 → these need version gating.
- **3** exist in 4.1.9 but not 5.2.3: `search/categories`, `torrents/pause`,
  `torrents/resume`. The latter two are the `stop`/`start` rename.
- **9** exist only on master (`transfer/setSpeedLimits`, `rss/importRules`,
  `torrents/downloadFile`, `app/getFreeSpaceAtPath`, …). Known but unclaimed.

## Layer 2 — the ledger

`qbtkit.coverage` joins the inventory against the spec. `qbt coverage` prints
it and `tools/build_coverage.py --strict` gates CI on the *same* computation —
they shared no code once, which is how the installed CLI could be broken while
CI stayed green.

Per scope it reports:

| field | source | meaning |
|---|---|---|
| `scope` | inventory | identity |
| `total` | inventory | endpoints this server version exposes |
| `specced` | `src/qbtkit/spec/` | endpoints with a spec entry |
| `missing` | derived | exposed upstream, absent from the spec |
| `phantoms` | derived | specced but **not** present upstream |

Phantoms are the subtle half. A typo in a spec `name` would otherwise sit in
the numerator forever while matching no real endpoint — and a blocklist entry
with the same typo guards nothing, which is exactly what happened to
`web_ui_host_header_validation`.

There is no per-endpoint CLI, MCP, docs or contract-test column, and no
exceptions file. The CLI and MCP columns were dropped because they could only
ever read 100%: both are generated from the spec, so they cannot disagree with
it. Endpoints that cannot be tested carry an `untestable` reason on the spec
entry — `app/shutdown` says "terminates the server under test" — and the ledger
reports the count.

## Layer 3 — the gates

Unit tests, so failures are local and fast:

1. **`test_spec_covers_target`** — every endpoint in `release-5.2.3.json` has a
   spec entry. This is the gate that makes the coverage claim true.
2. **`test_spec_has_no_phantoms`** — every spec entry exists in at least one
   inventory. Catches typos and invented endpoints.
3. **`test_cli_matches_spec`** — generated CLI command count equals spec count.
4. **`test_every_endpoint_mcp_reachable`** — each endpoint is reachable through
   a curated tool or `qbt_call`.

And one contract test, because only a real server can confirm it:

5. **`test_every_blocklisted_preference_key_actually_exists`** — every key in
   the `setPreferences` blocklist appears in the server's own `app/preferences`.

CI additionally runs a **drift job** on pushes to `main`: re-extract `master`
and compare the endpoint list against the committed snapshot. It warns rather
than fails, because an endpoint appearing upstream is news, not a broken build.
It compares endpoints only — the documents also carry a `fetched_at`, so
diffing whole files reported drift on every push.

## Reporting

`qbt coverage` prints the ledger; `--json` writes it for diffing:

```
qbt-kit coverage — target release-5.2.3

  scope               n   spec  progress
  torrents           61     61  ████████████████████  61/61
  app                16     16  ████████████████████  16/16
  ...
                   ----
  TOTAL             123    123  ████████████████████  100.0%

  specced            123/123  100.0%
  marked untestable   12       (reason recorded per endpoint)
```

## Boundary of the claim

The claim is: *every endpoint qBittorrent 5.2.3 exposes has a spec entry, and
is therefore reachable from both the CLI and the MCP server.* It is explicitly
**not**: that every endpoint is contract-tested — 12 are marked untestable and
many more are simply not exercised — nor that every parameter of
`app/setPreferences` is typed. That object is large and undocumented, so the
documented subset is typed and the remainder passes through unmodified.
