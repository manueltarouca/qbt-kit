# qbt-kit roadmap

```
                                                   target: 123 endpoints on qBittorrent 5.2.3
                                                   floor:   93 endpoints on 4.4.5 (verified)

M0 ─ plan + traceability                   ████████████████████  done
     ├─ inventory extracted from source    ✔  4 refs: 4.1.9 / 4.4.5 / 5.2.3 / master
     ├─ coverage ledger designed           ✔  5 CI gates, 4 separate percentages
     ├─ independent review                 ✔  24 findings, all dispositioned
     └─ found 45 endpoints the wiki omits  ✔  incl. 2 undocumented scopes
        │
M1 ─ auth, measured not read               ████████████████████  done
     ├─ credential seeding (PBKDF2)        ✔  authenticated first try
     ├─ probed 4.6 / 5.0 / 5.1 / 5.2       ✔  all four dialects recorded
     ├─ compat.py                          ✔  renames + version gates
     └─ one universal success rule         ✔  "cookie issued", replaces 3 dialects
        │
M2 ─ spec primitives + generation          ████████████████████  done
     ├─ _types.py                          ✔  body/wire/returns/version/safety
     ├─ torrents spec (61)                 ✔  61/61, zero phantoms
     ├─ client transport on httpx          ✔  probe auth, gating, error mapping
     ├─ CLI generated from spec            ✔  61 commands, 1:1 with the spec
     ├─ coverage ledger live               ✔  `qbt coverage` → 49.6%
     └─ 32 unit tests, ruff + ty clean     ✔  red-green verified on the gates
        │
M3 ─ remaining scopes                      ████████████████████  done
     ├─ app 16  transfer 9  sync 2  log 2  ✔  all exercised live
     ├─ auth 2                             ✔  behaviour already measured in M1
     └─ setPreferences lockout blocklist   ✔  17 keys refused client-side
        │
M4 ─ experimental + new scopes             ████████████████████  done
     ├─ rss 14                             ✔  upstream-experimental, shape-checked
     ├─ search 11                          ✔  needs plugin + internet; partly stubbed
     ├─ torrentcreator 4                   ✔  5.0+, in no wiki page
     └─ clientdata 2                       ✔  in no wiki page
        │
M5 ─ contract test harness                 ████████████████████  done
     ├─ seeder + leecher on a podman net   ✔  module-scoped, unique names
     ├─ synthetic torrents                 ✔  stdlib bencode writer, deterministic
     ├─ scenarios from real bugs           ✔  19 tests in 74s, all green
     └─ preference leaks undone per test   ✔  a leaked share limit broke seeding
        │
M6 ─ MCP server                            ████████████████████  done
     ├─ 15 curated tools                   ✔  incl. swarm_health
     ├─ qbt_call + safety gates            ✔  destructive needs confirm; --read-only
     ├─ preferences blocklist              ✔  WebUI/auth keys refused
     ├─ env-var config                     ✔  QBT_URL/API_KEY/READ_ONLY, no OAuth
     └─ dogfooded via .mcp.json           ✔  drove a real 15-file import
        │
M7 ─ release + dogfood                     ████████████░░░░░░░░  awaiting approval
     ├─ LICENSE + PEP 639 metadata         ✔  MIT, carried in the wheel
     ├─ skill in the repo                  ✔  CLI usage + swarm-health rule
     ├─ PyPI via trusted publishing        ·  pending trusted-publisher setup
     └─ retire the ad-hoc scripts          ·  dl-ready.py, search.py's qbt half
```

## Coverage, by scope

Filled bars are endpoints with a spec entry, verified against the endpoint
inventory extracted from upstream C++ source rather than from the wiki.

```
scope            n   spec
torrents        61   ████████████████████  61/61   ✔
app             16   ████████████████████  16/16   ✔
rss             14   ████████████████████  14/14   ✔
search          11   ████████████████████  11/11   ✔
transfer         9   ████████████████████  9/9   ✔
torrentcreator   4   ████████████████████  4/4   ✔
auth             2   ████████████████████  2/2   ✔
clientdata       2   ████████████████████  2/2   ✔
log              2   ████████████████████  2/2   ✔
sync             2   ████████████████████  2/2   ✔
                ───
                123
```

## Critical path

```
M1 auth ──▶ M2 spec+client ──┬──▶ M3 scopes ──┬──▶ M6 MCP ──▶ M7 release
                             └──▶ M4 scopes ──┘
                                     ▲
                             M5 harness (parallel, gates M3/M4 claims)
```

M5 can start any time after M2 and does not block M3/M4 from being *written* —
only from being *claimed as tested*. M6 needs the client, not the full scope
coverage, so an MCP server over `torrents` alone is shippable early if wanted.

## What "done" means per milestone

| | gate |
|---|---|
| M2 | `qbt torrents list` works against a container; `qbt coverage` reports 61/61 for torrents; ruff + ty clean |
| M3 | spec covers 100% of `release-5.2.3.json` minus rss/search/torrentcreator/clientdata |
| M4 | `test_spec_covers_target` passes with zero unexplained gaps |
| M5 | all four versions green in CI; scenario tests reproduce the known bugs |
| M6 | safety-gate tests pass, including via `qbt_call` |
| M7 | `uvx --from qbt-kit qbt doctor` works on a clean machine |
```
