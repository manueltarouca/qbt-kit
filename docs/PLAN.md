# qbt-kit — plan

> **Historical.** This is the plan as written before implementation, kept
> because it records *why* each decision was made. Where it disagrees with
> the code, the code is right — see [TESTING.md](TESTING.md) and
> [TRACEABILITY.md](TRACEABILITY.md) for what actually shipped.


> Revision 2. Revised after independent review; every factual claim below was
> verified against the qBittorrent source at the named tag, or against the
> running server. See `docs/REVIEW-1.md` for the findings and their disposition.

## Goal

A complete, typed Python client for the qBittorrent WebUI API, exposed three ways:

1. **`qbt`** — a CLI with strict 1:1 coverage of every endpoint.
2. **`qbt-mcp`** — an MCP server with ~12 task-level tools plus a raw escape hatch.
3. **`qbtkit`** — the importable library both are built on.

Published open-source (PyPI + GitHub under `manueltarouca`), with Claude skills
for driving it.

Primary target **qBittorrent 5.2.3 = WebAPI 2.15.1**. Compatibility floor
discussed under "Version support" — it is not simply 4.1.

## Endpoint surface — 123 on the target

Counted from `*Action()` methods in `src/webui/api/`, cross-checked between the
`.cpp` definitions and `.h` declarations (both give 123). The wiki is not the
denominator: the 4.1 page documents 78.

| scope | 4.1.9 | 5.2.3 | note |
|---|---|---|---|
| `auth` | 2 | 2 | |
| `app` | 6 | 16 | incl. `cookies`, `rotateAPIKey`, `getDirectoryContent` |
| `log` | 2 | 2 | |
| `sync` | 2 | 2 | delta protocol via `rid` |
| `transfer` | 7 | 9 | |
| `torrents` | 38 | 61 | |
| `rss` | 10 | 14 | experimental upstream |
| `search` | 11 | 11 | 4.1 had `categories`, since removed |
| `torrentcreator` | – | 4 | new in 5.0, in no wiki page |
| `clientdata` | – | 2 | in no wiki page |
| **total** | **78** | **123** | |

`master` currently has 132; those 9 extra are tracked but not claimed.
Measurement machinery and the coverage ledger: `docs/TRACEABILITY.md`.

## Architecture: one spec, generated surfaces

Writing 123 endpoints by hand across client + CLI + MCP + docs is four chances
to drift. A single declarative spec is the source of truth, and everything else
is generated from it.

The review's sharpest point was that the spec primitives are the hard part, not
the generation. This API is irregular in ways a naive `Endpoint(params=[...])`
cannot express, so the primitives must cover:

- **Body encoding** — urlencoded vs multipart (`torrents/add`,
  `torrents/parseMetadata`, `search/installPlugin`).
- **Param wire-encoding** — pipe-joined `hashes` with an `all` sentinel;
  `"true"`/`"false"` strings; JSON embedded in a form field
  (`app/setPreferences json=`, `rss/setRule ruleDef=`, `app/setCookies cookies=`);
  pipe-delimited lists (`filePrio id=`, `addPeers peers=`).
- **Return kinds** — JSON, empty, **binary** (`torrents/export`,
  `torrentcreator/torrentFile`), and **text sentinel** (see "Login dialects").
- **Per-param versioning** — `torrents/renameFile` moved from `id`/`name` to
  `oldPath`/`newPath` at WebAPI 2.4; `torrents/add` `paused` → `stopped` at 2.11.
- **`since` and `until`** — `until` is genuinely needed, e.g.
  `search/categories` existed in 4.1 and was removed.
- **`mutating` / `destructive` flags** — required for the safety gates below.

`sync/maindata` delta merging and the `search` job lifecycle are stateful and
live in the library, not the spec.

```python
Endpoint(
    scope="torrents", name="setLocation", method="POST",
    body=Urlencoded,
    params=[Param("hashes", Hashes, required=True),
            Param("location", str, required=True)],
    returns=NoContent,
    since=(2, 0, 0),
    mutating=True, destructive=False,
    summary="Move a torrent's files, keeping the torrent valid.",
)
```

### Layout

```
src/qbtkit/
  spec/            # declarative endpoint spec, one module per scope
    _types.py      # Param/Endpoint/Hashes/Returns/body-encoding primitives
    torrents.py app.py rss.py search.py sync.py transfer.py log.py auth.py
    torrentcreator.py clientdata.py
  client.py        # transport: auth, retries, version gating, errors
  models.py        # response dataclasses, tolerant of unknown keys
  cli/             # Typer app generated from the spec
  mcp/             # MCP server: curated tools + qbt_call
  compat.py        # bidirectional rename table across API versions
tests/
docs/
inventory/         # extracted endpoint inventories per upstream tag
tools/             # extract_inventory.py, build_coverage.py
```

## Auth — probe, don't predict

The obvious design (read `app/webapiVersion`, then pick a mechanism) **cannot
work**: only `auth/login` is public, and `app/webapiVersion` returns **403**
unauthenticated. Verified against the running 5.2.3 server.

So authentication probes, then version-gates everything after:

1. If an API key is available, send `Authorization: Bearer <key>` on a cheap
   call. API keys exist only from **qBittorrent 5.2.0 / WebAPI 2.15.x** —
   verified: zero `bearer` references in 5.0.0 and 5.1.0 source, three in 5.2.0.
   A `≥2.11.2` gate (an earlier draft of this plan) would have sent Bearer to
   5.0/5.1 servers, which ignore it and 403 for want of a session.
2. On 403, fall back to `POST auth/login`.
3. Only once authenticated, read `app/webapiVersion` and cache it per client.

### Login dialects

Three behaviours, all needing handling:

| version | bad credentials |
|---|---|
| ≤ 5.1 | HTTP **200** with body `Fails.` |
| 5.2+ | HTTP **401** |
| any | HTTP **403** once the IP is banned after repeated failures |

A `returns=NoContent` spec entry would read `Fails.` as success. Hence the
text-sentinel return kind.

### Never name the session cookie

In 5.2.3 the cookie is **`QBT_SID_<port>`**
(`SESSION_COOKIE_NAME_PREFIX = "QBT_SID_"` plus the WebUI port). On 5.0/5.1 the
name is a user preference defaulting to `SID`; on 4.x it is `SID`. The client
uses the transport's cookie jar and never refers to the cookie by name.

### Credentials

Resolution order: explicit argument → env (`QBT_URL`, `QBT_API_KEY`,
`QBT_USERNAME`, `QBT_PASSWORD`) → macOS Keychain → config file
(`~/.config/qbt-kit/config.toml`).

Keychain needs **two entries**, since one item holds one secret:

```
security find-generic-password -s qbittorrent -a webui    -w   # password
security find-generic-password -s qbittorrent -a api-key  -w   # API key (5.2+)
```

Secrets are never printed or logged. That is enforced with an explicit logging
filter, because httpx's DEBUG logging prints `Authorization` and `Cookie`
headers — an intention is not a control.

## The real connection footgun: Host-header validation

Not Referer/Origin. `isCrossSiteRequest` treats a request with *neither* header
as not cross-site, and httpx sends neither, so nothing is needed there.

What does bite is `validateHostHeader`, **enabled by default**: if the `Host`
header carries a port different from the server's listening port, the request is
rejected with a bare **401** that looks exactly like bad credentials. This fires
behind podman port mapping, SSH tunnels and most reverse proxies.

Consequences:
- The container harness must publish the **same port number** it listens on, or
  seed `WebUI\HostHeaderValidation=false`.
- `qbt doctor` must distinguish "401 with no session established" →
  Host-header validation, from "401 after login" → bad credentials.

## Version support

| version | WebAPI | status |
|---|---|---|
| 4.1.x–4.3.x | 2.2.1+ | **best-effort, untested.** Code paths present and version-gated, but no official container image exists to verify against, so the README does not claim them. |
| **4.4.5** | 2.8.2 | **verified floor** — oldest official image |
| 4.6.7 | 2.9.3 | tested |
| 5.0.x / 5.1.x | 2.11.2 / 2.11.4 | tested — the versions that differ most |
| **5.2.3** | **2.15.1** | primary target |

Decided 2026-10-18: claim what is tested. 4.1 shimming stays in the code, but
the supported range is stated as 4.4+ rather than asserting a floor CI never
exercises.

5.0/5.1 are in the matrix deliberately: configurable cookie name, no Bearer
auth, and 200-`Fails.` login all differ there from 5.2.

Renames translate **bidirectionally** through `compat.py`. `pause`/`resume` were
**removed** in 5.0, not aliased — verified, they are absent from 5.2.3 and
return 404 — so the client cannot rely on servers tolerating either spelling.

## MCP surface

~12 curated tools written for how a model works, not mirroring HTTP:
`list_torrents`, `torrent_detail`, `add_torrent`, `control_torrents`,
`delete_torrents`, `move_torrents`, `categories`, `tags`, `swarm_health`,
`transfer_status`, `search`, `preferences`, plus `qbt_call`.

`swarm_health` reports **availability − progress**, because a stalled torrent is
usually not slow but mathematically stuck, and that difference is the tell.
Encoding it means a model need not rediscover it.

`move_torrents` wraps `setLocation` and waits for the move to land. Recheck
afterwards is **opt-in**, not default — `setLocation` already keeps the torrent
valid, and a recheck is a full hash pass over potentially tens of GB.

### Safety gates apply to `qbt_call` too

The gap the review found: curated destructive tools were gated while the raw
escape hatch reached everything ungated — a model could call `torrents/delete`
with `deleteFiles=true`, or `app/shutdown`, straight through it.

So the gates derive from spec attributes and `qbt_call` enforces them:

- `destructive=True` requires an explicit `confirm`.
- Under `--read-only`, every `mutating=True` endpoint is refused, including via
  `qbt_call`.
- `app/setPreferences` **blocklists** WebUI, auth and network keys
  (`web_ui_username`, `web_ui_password`, `web_ui_port`, `web_ui_address`,
  `use_https`, `bypass_local_auth`, `web_ui_host_header_validation`,
  `web_ui_domain_list`, `web_ui_csrf_protection_enabled`) — writing any of them
  severs the connection or weakens security.

These gates get their own tests.

## CLI UX

```
qbt torrents list --category tv --sort progress
qbt torrents add <magnet> --category tv --auto-tmm
qbt health                     # swarm health across the queue
qbt doctor                     # version, auth mode, endpoint availability
qbt coverage                   # the coverage ledger
qbt call torrents/info --param filter=downloading   # raw 1:1 escape hatch
```

`--json` everywhere; human tables by default. `qbt call <scope>/<name>`
guarantees literal reachability where no friendly subcommand exists.

## Measured auth facts (milestone 1, qBittorrent 5.2.3)

Established against a seeded container rather than taken from the wiki:

| probe | result |
|---|---|
| unauthenticated `app/webapiVersion` | **403** — version is unreadable before auth |
| `auth/login`, wrong password | **401** |
| `auth/login`, correct password | **204** (not 200) |
| session cookie name | **`QBT_SID_18080`** — prefix + WebUI port |
| authenticated `app/webapiVersion` | **2.15.1** |
| authenticated, `Host` port mismatched | **401**, indistinguishable from bad credentials |
| `app/rotateAPIKey` | **POST**, returns JSON `{"apiKey": …}` |
| `Authorization: Bearer <key>` | **200** |
| `X-Api-Key: <key>` | **403** — not a supported mechanism |

Reproduce with `tests/contract/probe_auth.py --url … --json`. The same probe
runs against each version in the matrix; differences become `compat.py` entries.

## Testing

Detail in `docs/TESTING.md`. The essentials:

- Integration tests **never** touch the author's live instance; the harness
  refuses loopback targets it does not own and ignores ambient credentials.
- Containers, not the host WebUI: seeder + leecher + tracker on a private
  network, with synthetic torrents built by a standalone bencode writer so test
  setup does not depend on the code under test.
- A fixture sidecar is needed for endpoints requiring external services: a
  static HTTP server for `.torrent` files and RSS XML, the tracker for
  `reannounce`, and the second qBittorrent as a peer so `sync/torrentPeers` and
  `pieceAvailability` are non-empty. `search/*` needs a plugin and outbound
  internet — those are shape-checked only, and marked as such.
- Containers need **credential seeding**: since 4.6.1 a server with no password
  prints a random temporary one to stdout; before that it was
  `admin`/`adminadmin`. The harness seeds `qBittorrent.conf` rather than parsing
  logs.
- Coverage is verified **against the extracted upstream inventory**, not against
  itself. The self-referential check (CLI count == spec count) stays, but the
  claim rests on diffing the spec against `inventory/release-5.2.3.json`.

## Publishing

- MIT. `pyproject.toml` with `uv`.
- **`uvx qbt` will not work** — PyPI `qbt` is taken by an unrelated package
  (verified: `/pypi/qbt/json` returns 200). `qbt-kit`, `qbtkit` and `qbt-mcp` are
  free. Distribution is `uvx --from qbt-kit qbt`, and `qbt-mcp` is published as
  its own thin package so the MCP entry point works bare.
- Astral toolchain throughout: **uv** (project, locking, `uv build`/`uv publish`,
  `uv_build` backend), **ruff** for lint *and* format, **ty** for types. CI runs
  ruff as a hard gate; `ty` is **advisory** for now because it is still at
  0.0.89 — pre-1.0 and moving. It becomes a gate when it stabilises.
- CI: ruff check + format, ty (advisory), unit tests on 3.11–3.14, contract tests
  across the version matrix, PyPI publish on tag via trusted publishing.
- Error types derive from the server's fixed mapping rather than per-endpoint
  hand-typing: AccessDenied→403, BadParams→400, BadData→**415**, Conflict→409,
  NotFound→404, Unauthorized→401. The 415 is unusual enough to deserve its own
  exception.
- Dependencies vetted before adding, justified in `docs/dependencies.md`:
  `httpx`, `typer`, `mcp`.
- README states why this exists along**`qbittorrent-api`**, which already offers
  full library coverage with version gating. The differentiation is the 1:1 CLI,
  the MCP server, and the spec-driven coverage ledger — not library novelty. Its
  source is a useful cross-check for the spec.

## Sequencing

1. **Auth vertical slice first.** Prove cookie name, login dialects, Bearer and
   Host-header validation against 4.6, 5.1 and 5.2 containers. Everything else
   is cheap once this is right, and all of it was wrong in revision 1.
2. Spec primitives + generation, proven on `torrents` alone.
3. Remaining scopes: app, transfer, sync, log.
4. `rss`, `search`, `torrentcreator`, `clientdata`.
5. MCP server and skills.
6. Dogfood: move the maintainer's ad-hoc download scripts onto the client,
   and update the companion skill.

## Risks

- **RSS and Search are experimental upstream** and change without notice.
- **`app/setPreferences` is a large untyped nested object.** Type the documented
  subset, pass the rest through, never silently drop unknown keys.
- **Scope.** 123 endpoints is a lot; the sequencing above exists so the project
  is useful before it is complete.
