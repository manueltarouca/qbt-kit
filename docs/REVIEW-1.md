# Plan review 1 — findings and disposition

> **Historical.** An independent review of the plan below, conducted before
> implementation. Kept for the reasoning; every finding was dispositioned.


Independent review of `PLAN.md` revision 1 (2026-10-18), by a review-only agent
on a different model. Every finding below was re-verified before acting;
verification method is stated. Nothing was accepted on the reviewer's authority
alone, and one of its corrections was itself wrong.

## Verified and fixed

| # | finding | how verified | fix |
|---|---|---|---|
| C1 | 5.2.3 is WebAPI **2.15.1**, not 2.11.x | `app/webapiVersion` on the live server returns `2.15.1` | version table rewritten; full 4.1.9→5.3 mapping recorded |
| C2 | Bearer auth gate wrong — it appears in **5.2.0**, not 2.11.2 | `grep -ci bearer` on `webapplication.cpp`: 0 in 5.0.0, 0 in 5.1.0, 3 in 5.2.0 | auth now **probes** instead of predicting |
| C3 | Session cookie is **`QBT_SID_<port>`** on 5.2, not `SID` | source: `SESSION_COOKIE_NAME_PREFIX = "QBT_SID_"` at `webapplication.cpp:75`, composed with the port at `:472` | client uses the cookie jar and never names the cookie |
| C4 | `qbt_call` bypassed every safety gate | read of own plan — the gates were only on curated tools | `mutating`/`destructive` added to the spec; `qbt_call` enforces them; tested |
| C5 | Endpoint count wrong; `torrentcreator` missing | own extraction from source | count corrected to **123**; both missing scopes added |
| M1 | `pause`/`resume` were **removed** in 5.0, not aliased | own inventory diff: absent from `release-5.2.3.json`, present in `4.1.9` | `compat.py` translates bidirectionally; no reliance on server tolerance |
| M2 | Login has three dialects (200 `Fails.` ≤5.1, 401 on 5.2, 403 banned) | source: `authcontroller.cpp` across tags | text-sentinel return kind added; contract test per version |
| M3 | `app/webapiVersion` **requires auth** | live server, no credentials → **HTTP 403** | auth sequence reordered: probe → authenticate → read version |
| M4 | Real footgun is **Host-header port validation**, not Referer/Origin | source: `validateHostHeader`, default-on in `preferences.cpp` | harness joins the private network and uses port 8080 throughout; `qbt doctor` distinguishes the two 401 causes |
| M5 | Coverage test was self-referential | read of own plan | already addressed by `docs/TRACEABILITY.md`, which diffs the spec against the extracted upstream inventory; kept the CLI==spec check as a secondary |
| M6 | Contract tests need services the stack lacked | reasoning about the endpoint list | fixture sidecar added (nginx for `.torrent`/RSS, tracker, second peer); `search/*` marked shape-checked only |
| M7 | 4.1 floor not testable; 5.0/5.1 missing from matrix | Docker Hub tag list — official images start at 4.4.5 | matrix is 4.6.7 / 5.0.2 / 5.1.2 / 5.2.3; floor question raised with the maintainer rather than silently decided |
| M8 | Containers need credential seeding | source: random temp password printed since 4.6.1 | harness seeds `qBittorrent.conf` with a known PBKDF2 hash |
| M9 | PyPI **`qbt` is taken** | `pypi.org/pypi/qbt/json` → 200; `qbt-kit`/`qbtkit`/`qbt-mcp` → 404 | distribution is `uvx --from qbt-kit qbt`; `qbt-mcp` published separately |
| M10 | Spec primitives insufficient for this API's irregularities | spot-checked the cited endpoints | primitives expanded: body encoding, wire-encoding, binary/text returns, per-param versioning, `until` |
| M11 | `preferences` writes can lock the user out | source: the listed keys are writable | WebUI/auth/network keys blocklisted in MCP and warned in CLI |
| m1 | Secrets in MCP client config; httpx DEBUG logs headers | known httpx behaviour | explicit logging filter, not an intention; skill recommends Keychain over env |
| m2 | One Keychain item cannot hold two secrets | `security` semantics | two accounts: `webui` and `api-key` |
| m3 | Error codes should derive from the fixed server mapping | source: `webapplication.cpp` error mapping | derived, with a dedicated exception for the unusual **415** |
| m4 | `move_torrents` forcing a recheck is expensive | observed directly — rechecking 36 GB of archive took real time | recheck is opt-in |
| m5 | Add Python 3.14 | current as of Oct 2026 | matrix is 3.11–3.14 |
| m6 | Prior art `qbittorrent-api` unmentioned | PyPI | README states the differentiation; its source is a spec cross-check |
| m7 | `--network none` remark was a non-sequitur | read of own plan | removed |
| m8 | Sequence an auth vertical slice first | judgement, well argued | adopted as milestone 1 |

## Corrected the reviewer

**C5 count.** The review states 5.2.3 has **121** endpoints. It has **123**.
The reviewer's own table omits the `clientdata` scope (2 endpoints) — the same
class of omission it correctly caught in revision 1 for `torrentcreator`.
Verified by extracting both the `.cpp` definitions and the `.h` declarations
independently; both yield 123, and per-scope counts agree exactly.

Scope totals used: auth 2, app 16, clientdata 2, log 2, rss 14, search 11,
sync 2, torrentcreator 4, torrents 61, transfer 9.

## Nothing skipped

Every other finding was accepted. One is deferred as a question rather than a
decision: whether to claim 4.1 as the compatibility floor and test it under
emulation, or state the floor as 4.4 and call 4.1 best-effort. Flagged in
`PLAN.md` under "Version support".
