# Changelog

Notable changes to qbt-kit. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[semantic](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `qbt-mcp` exited when qBittorrent was unreachable at startup. An MCP client
  launches its servers when the session starts, which for a desktop qBittorrent
  is routinely before the application is running, so the server vanished and
  the client reported only "connection closed" — never the one fact worth
  knowing. A stopped server and an expiring ban are now reported on stderr and
  the tools serve regardless, each reporting the failure per call. Rejected
  credentials and a refused host header stay fatal: they do not fix themselves,
  and since every tool call builds a fresh client that re-POSTs `auth/login`,
  staying up would trip qBittorrent's ban on repeated failed logins and lock
  the user out of the WebUI in their browser too.

## [0.1.1] — 2026-10-18

### Fixed

- The licence badge linked to a relative path, which resolves to nothing on
  PyPI. Badges are now Markdown rather than raw HTML, so no HTML attribute is
  left for a relative target to hide in.
- `uvx qbt-mcp` appeared twice in the README. It resolves to nothing:
  `qbt-mcp` is a console script inside `qbt-kit`, not a package. Both now read
  `uvx --from "qbt-kit[mcp]" qbt-mcp`.

### Added

- The repository is also a plugin marketplace:
  `/plugin install qbt-kit --marketplace manueltarouca/qbt-kit`.

## [0.1.0] — 2026-10-18

First public release.

### Added

- Typed client for the qBittorrent WebUI API covering **all 123 endpoints** of
  qBittorrent 5.2.3, generated from a declarative spec.
- `qbt` CLI with one command per endpoint, plus `doctor`, `health`, `ready`,
  `call` and `coverage`.
- `qbt-mcp`, an MCP server exposing 15 tools — 13 task-shaped plus `qbt_call`
  escape hatch, so the small tool surface stays complete.
- Coverage traceability: endpoint inventories extracted from the qBittorrent
  C++ source per release tag (4.1.9, 4.4.5, 5.2.3, master) with a CI gate that
  fails on both missing and invented endpoints.
- Version compatibility down to 4.4, with a rename table so `torrents/stop`
  resolves to `pause` on servers that predate the rename. 4.1 inventories are
  committed, but 4.4 is the supported floor.
- Safety gates: destructive endpoints require explicit confirmation, a
  read-only mode that holds even through `qbt_call`, and a `setPreferences`
  blocklist covering the WebUI and auth keys that could lock you out.
- Contract test suite driving real qBittorrent containers across 4.6, 5.0, 5.1
  and 5.2, including scenarios reproduced from real incidents.

### Notes

Several behaviours documented here are not in the official wiki, including that
a failed login returns HTTP 200 on qBittorrent ≤5.1, that `app/webapiVersion`
requires authentication, and that a torrent reports `progress: 1.0` while files
set to priority 0 were never downloaded. See the README and `docs/TESTING.md`.
