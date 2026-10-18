# Security

## Reporting a vulnerability

Please report privately through
[GitHub's security advisories](https://github.com/manueltarouca/qbt-kit/security/advisories/new)
rather than opening a public issue. Include what an attacker gains and the
smallest reproduction you have; a proof-of-concept is welcome but not required.

Expect an acknowledgement within a few days. This is a personal project, not a
funded one, so please size your expectations accordingly — but anything that
lets a caller delete data or escape a gate will be treated as urgent.

## What this tool holds

qbt-kit authenticates to a qBittorrent WebUI with either an API key
(qBittorrent 5.2+) or a username and password. **qBittorrent has no OAuth**, so
there is no short-lived token to delegate: the secret is long-lived and grants
full control of the torrent client, including where it writes files.

Credentials resolve from flags, then the environment, then the macOS Keychain.
Prefer the Keychain. An MCP client's `env` block is plaintext and frequently
committed, so if you use it, reference a variable rather than pasting a secret.

Two deliberate behaviours:

- **Credentials are never printed.** Startup reports the *source* of the
  credential, never its value. `httpx` DEBUG logging would print `Authorization`
  and `Cookie` headers, so each client attaches a filter that drops any record
  carrying them.
- **`app/preferences` is redacted.** qBittorrent returns its own API key and
  several passwords in that response. Both the `preferences` tool and the raw
  `qbt_call` strip them, because returning a secret into a model's context puts
  it in transcripts and logs that no later instruction can recall.

## Threat model for the MCP server

The MCP server is driven by a language model, which may be acting on text it
read somewhere — a torrent name, an RSS title, a web page. Treat tool arguments
as untrusted and assume the model can be talked into asking for anything the
API allows. The gates are therefore code, not prompt text:

- Destructive endpoints require explicit `confirm`; `delete_files` is never
  implied.
- `--read-only` / `QBT_READ_ONLY=1` refuses every mutating endpoint, **including
  through `qbt_call`**, so the escape hatch cannot be used to escape the gate.
- `app/setPreferences` refuses keys that would lock you out, expose the WebUI,
  or execute code — notably `autorun_program`, which runs an arbitrary command
  on torrent events. There is no override. A contract test asserts every
  blocklisted key exists in the server's own preferences, because a misspelled
  entry silently guards nothing.

What the gates do **not** protect against: a caller with legitimate confirmation
deleting data they meant to keep, and anything qBittorrent itself permits once a
preference has been set outside this tool.

## Transports

`qbt-mcp` speaks stdio by default, which is the safe choice: the server is a
child process of the client and nothing listens on a socket. The `sse` and
`streamable-http` transports expose an **unauthenticated** control surface
carrying your qBittorrent credentials — the MCP SDK binds them to `127.0.0.1`,
so reaching them means reaching your machine, but do not forward those ports or
bind them to an external interface.

## Supply chain

Runtime dependencies are deliberately few — `httpx` and `typer`, plus `mcp` and
`pydantic` for the optional server — and each is justified in
[`docs/dependencies.md`](docs/dependencies.md). Releases are built and published
by GitHub Actions through PyPI trusted publishing, so no long-lived PyPI token
exists to steal.
