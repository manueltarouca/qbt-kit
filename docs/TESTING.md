# Testing strategy

How the test suite is built and why. This describes what exists; `PLAN.md`
records the original design, which differs in places.

## Rule: never the author's live instance

Integration tests run against qBittorrent in containers, never against
`127.0.0.1:8080`. A developer's own instance manages real downloads; a test that
deletes, relocates or re-categorises torrents there destroys real state.

This is enforced in code, not documentation. The harness refuses to start if the
target resolves to a loopback address outside the test network, or if
`QBT_URL`/`QBT_API_KEY` from the user's environment leak into the test session:

The containers get random free ports, so the guard tracks the ports it owns
and refuses everything else on loopback. An environment variable would have
been weaker — anything can set one — whereas a port this harness did not open
is provably not its container:

```python
def guard(url: str) -> None:
    parsed = urlparse(url)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError(f"contract tests only talk to containers, not {parsed.hostname!r}")
    if parsed.port not in _OWNED:
        raise RuntimeError(f"refusing to use {url}: port {parsed.port} is not a container ...")
```

The fixtures build a client from the container's own credentials with
`use_keychain=False`, and an autouse fixture strips `QBT_*` from the
environment, so neither the Keychain nor ambient variables can reach a test.

## Why unit tests are not enough

Red-green on the spec catches signature drift. It cannot catch any of the
behaviours that actually caused bugs in practice:

- `torrents/pause` silently became `stop` in 5.0 — a call that 404s, not a
  type error.
- `availability` is only meaningful once a torrent has peers; a *queued*
  torrent reports `0.0`, which looks identical to a dead swarm.
- `setLocation` moves partial data asynchronously — the call returns before the
  move completes, and `save_path` updates before the bytes land.
- `setForceStart` overrides share limits, so stop-on-complete silently stops
  applying.
- Resume data on disk lags by `save_resume_data_interval` (60 min default), so
  anything reading `.fastresume` disagrees with the API.

Each of those becomes an integration test with a named scenario.

## Topology

A private container network with two qBittorrent nodes, created directly by
`tests/contract/harness.py` rather than by compose:

```
qbt-seeder   — holds the complete data, seeds it
qbt-leecher  — the system under test, starts empty
```

There is no tracker. The two nodes are introduced to each other with
`torrents/addPeers`, which needs no tracker and no DHT, so the network stays
sealed. Compose was planned and dropped: the harness has to create a network,
wait for readiness, seed credentials and tear down deterministically on
failure, and doing that in Python was simpler than doing it in YAML and then
shelling out to inspect it.

Both qBittorrent containers run the same pinned image tag; the version matrix
in CI varies it to test the compatibility claims rather than assert them:

| image tag | WebAPI | why it is in the matrix |
|---|---|---|
| `4.6.7-1` | 2.9.3 | oldest official image; `pause`/`resume` era |
| `5.0.2-1` | 2.11.2 | configurable cookie name, no Bearer |
| `5.1.2-1` | 2.11.4 | 200-`Fails.` login |
| `5.2.3-1` | 2.15.1 | primary target; `QBT_SID_<port>`, Bearer |

4.1 is **not** in the matrix: official images start at 4.4.5 and the only 4.1
image is a 2019 linuxserver build that is likely amd64-only, so emulated here.

### Port mapping must preserve the port number

`validateHostHeader` is on by default and rejects any request whose `Host`
header carries a port different from the server's listening port — with a bare
**401** that is indistinguishable from bad credentials.

So the harness must publish the *same* number it listens on
(`-p 127.0.0.1:8080:8080`), not an arbitrary high port, or else seed
`WebUI\HostHeaderValidation=false` in the container config. Mapping
`54321:8080` and wondering why every call 401s is the trap.

Because each container needs a distinct host port, the runner either varies the
*internal* port to match, or joins the private network itself and addresses
containers by name on 8080. The latter is cleaner and is what the harness does.

### Credential seeding

Containers cannot be left to default: since **4.6.1** a server with no password
set prints a random temporary password to stdout, and before that it was
`admin`/`adminadmin`. The harness writes `qBittorrent.conf` before first start
with a known `WebUI\Password_PBKDF2` (and an `AuthSubnetWhitelist` covering the
test network), so credentials are deterministic across the whole matrix rather
than scraped from logs.

## Test content: synthetic, not borrowed

Test torrents are generated at setup from random bytes, and the `.torrent`
files are built by a small stdlib bencode writer in
`tests/contract/mktorrent.py`.

Three reasons this beats using real torrents as the default:

1. **Deterministic.** Known piece count, known sizes, so assertions about piece
   ranges and per-file progress are exact.
2. **Self-contained.** No internet, no tracker reachability, no flakiness; CI
   runs offline.
3. **Independent of the code under test.** Building torrents with our own
   `torrentcreator` endpoints would make setup depend on the thing being
   verified. The bencode writer is deliberately separate and dumb.

Content shapes, chosen to mirror the real cases:

| fixture | shape | exercises |
|---|---|---|
| `single_small` | one 8 MiB file | add, complete, stop-on-complete |
| `multi_file` | 5 files, mixed sizes | per-file progress, `filePrio` deselection |
| `season_pack` | 10 files, uniform | deselecting already-held items, partial completion |
| `large_sparse` | 1 file, 512 MiB, piece size 1 MiB | piece-range maths, preallocation |

### Optional real-world tier

A separate, network-dependent, non-default suite (`-m realworld`) uses a
**Debian netinst ISO** torrent — freely redistributable and well seeded — purely
as a smoke test that the client works against a swarm it does not control. It is
skipped unless `--realworld` is passed, and never runs in the default CI job.

## Fixture sidecar

Some endpoints need things two qBittorrent containers cannot provide between
them. Only the last row below is currently exercised; the others are recorded
as the gap they are:

| need | status |
|---|---|
| a second peer | the seeder container — **covered** |
| `.torrent` over HTTP | not covered; `torrents/add` is tested by file and magnet |
| RSS feed XML | not covered; the `rss` scope is shape-checked only |
| tracker announce | not covered; the swarm runs trackerless |

`search/*` is the exception: it needs an installed plugin and outbound internet,
which a private network deliberately lacks. Those endpoints are **shape-checked
only** against a recorded response and marked as such in the coverage ledger, so
the claim stays honest. (The official `qbittorrent-nox` image does ship
`python3`, so plugins can run if we later accept a network-dependent tier.)

## Scenarios

Named behaviours, each a test:

- **lifecycle** — add stopped → start → completes → lands in `stoppedUP` with
  `max_seeding_time=0`; then the same with `setForceStart` on, asserting it
  does *not* stop, which is the trap we hit.
- **dead swarm** — stop the seeder mid-download, assert `availability` converges
  to `progress` and the health verdict reports stuck rather than slow.
- **queued is not dead** — queue a torrent behind the active limit, assert
  `availability == 0` while `state == queuedDL`, and that the health check does
  *not* call it dead. This encodes the over-deletion bug directly.
- **relocate** — `setLocation` on a partial torrent, poll until `save_path`
  changes *and* the bytes exist, then `recheck` and assert progress is preserved.
- **graft** — copy an identical file into a different torrent's folder, recheck,
  assert the recovered percentage, and assert a *size mismatch* is rejected.
- **categories** — category save paths with `autoTMM`, including that changing a
  category moves data when `category_changed_tmm_enabled` is set.
- **destructive guards** — `delete` without `delete_files` leaves files;
  `qbt_call` requires `confirm` for `destructive=True` endpoints and refuses
  every `mutating=True` endpoint under `--read-only`; `setPreferences` rejects
  blocklisted WebUI/auth keys.
- **blocklist integrity** — every blocklisted preference key must exist in the
  server's own `app/preferences`, and the real host-header key must be refused.
  A misspelled entry guards nothing, which is exactly what happened.

Auth dialects, version gating and Host-header rejection are *measured* rather
than asserted: `tests/contract/probe_auth.py` records each server's behaviour
and `compat.py` carries the result. They are not yet contract tests, and the
compatibility claims rest on the matrix passing, not on a named scenario.
- **progress 1.0 with files deselected** — set one file of a pack to priority 0,
  let it finish, assert it reaches `progress: 1.0` while `size < total_size` and
  `pieces_have < pieces_num`. Found by dogfooding: a live season pack reported
  `progress: 1` holding 3716 of 6516 pieces because four episodes were
  deselected. Any "the content is all on disk, the torrent is safe to delete"
  rule built on `progress` alone is wrong on exactly these.

### Isolation between scenarios

Preferences are server-wide and outlive the test that set them. Deleting the
torrents afterwards does not undo them, so `conftest` snapshots preferences on
both nodes and reverts whatever the test changed.

This is not precautionary. Three scenarios have to set share or queue limits to
provoke their behaviour, and `max_seeding_time=0` left on the *seeder* stops it
the instant a torrent completes. A later test needing a working seeder then
fails with the useless symptom "peers never connected" — passing alone, failing
in the suite. The revert also made the pair run in 13s instead of 101s, because
the time had been spent waiting out timeouts against a seeder that would not
seed.

## Container runtime

Podman locally, Docker on CI. `runtime_exe()` honours `QBT_CONTAINER_RUNTIME`,
then prefers podman, then falls back to docker on `PATH`. Every command the
harness issues — `run`, `rm`, `logs`, `inspect`, `network`, `exec` — is spelled
identically in both CLIs, so discovery is sufficient and no abstraction layer
is warranted.

Hardcoding podman meant the contract job could only ever pass on the author's
machine, since GitHub's runners ship docker and no podman. Verified by running
the full suite with `QBT_CONTAINER_RUNTIME=docker`.

## Running

```sh
uv run pytest tests/unit -q                        # fast, no containers
uv run pytest -m contract tests/contract -q        # containers, ~70s
QBT_TEST_TAG=4.6.7-1 uv run pytest -m contract tests/contract -q
```

`-m 'not contract and not realworld'` is the default in `pyproject.toml`, so a
bare `pytest` never reaches for a container.

Teardown removes containers and volumes unconditionally, including on failure,
so a crashed run does not leave a half-seeded swarm or a stale network behind.
