"""Safety gates. These protect the user from the tool, so they get their own file.

The review of the first plan found that gating only the curated MCP tools left
the raw escape hatch reaching every destructive endpoint ungated. The gates
therefore live in the client, which both the CLI and MCP go through.
"""

from __future__ import annotations

import pytest

from qbtkit import errors
from qbtkit.client import Client, encode
from qbtkit.spec import load_all
from qbtkit.spec._types import Wire
from qbtkit.spec.app import LOCKOUT_KEYS


def _client(*, read_only: bool = False) -> Client:
    # Port 1 is unreachable on purpose: every gate below must fire before any
    # request is attempted, so these stay fast and offline.
    return Client("http://127.0.0.1:1", username="u", password="p", read_only=read_only)


def test_destructive_requires_confirm() -> None:
    c = _client()
    with pytest.raises(errors.ConfirmationRequired):
        c.call("torrents/delete", hashes="all", deleteFiles=True)


def test_read_only_refuses_mutations() -> None:
    c = _client(read_only=True)
    with pytest.raises(errors.ReadOnly):
        c.call("torrents/stop", hashes="all")


def test_read_only_allows_reads() -> None:
    """A read in read-only mode must fail on transport, not on the gate."""
    c = _client(read_only=True)
    with pytest.raises(errors.QbtError) as excinfo:
        c.call("torrents/info")
    assert not isinstance(excinfo.value, errors.ReadOnly)


@pytest.mark.parametrize("key", sorted(LOCKOUT_KEYS))
def test_setpreferences_refuses_lockout_keys(key: str) -> None:
    """Writing any of these severs the connection or weakens security.

    A model asked to 'change the download limit' must not be able to set
    `web_ui_password` in the same call.
    """
    c = _client()
    with pytest.raises(errors.BlockedParameter) as excinfo:
        c.call("app/setPreferences", json={key: "x", "dl_limit": 1024})
    assert key in str(excinfo.value)


def test_setpreferences_allows_ordinary_keys() -> None:
    c = _client()
    with pytest.raises(errors.QbtError) as excinfo:
        c.call("app/setPreferences", json={"dl_limit": 1024, "max_active_downloads": 5})
    assert not isinstance(excinfo.value, errors.BlockedParameter)


def test_shutdown_is_destructive_and_untestable() -> None:
    ep = next(e for e in load_all() if e.path == "app/shutdown")
    assert ep.destructive and ep.mutating
    assert ep.untestable, "shutdown must declare why it is not contract-tested"


def test_api_key_endpoints_are_destructive() -> None:
    """Rotating or deleting the key locks out anyone authenticating with it."""
    for path in ("app/rotateAPIKey", "app/deleteAPIKey"):
        ep = next(e for e in load_all() if e.path == path)
        assert ep.destructive, f"{path} should require confirmation"


def test_endpoints_named_path_do_not_collide_with_call() -> None:
    """Several endpoints take a parameter called `path`.

    `Client.call(path, ...)` names its own first argument the same thing, so
    without positional-only parameters `call("rss/addFolder", path="x")` raises
    TypeError for multiple values. Guard against the signature regressing.
    """
    import inspect

    sig = inspect.signature(Client.call)
    kind = sig.parameters["path"].kind
    assert kind is inspect.Parameter.POSITIONAL_ONLY, (
        "Client.call's `path` must be positional-only so endpoints may use "
        "`path` as a parameter name"
    )
    colliding = [e.path for e in load_all() if any(p.name == "path" for p in e.params)]
    assert colliding, "expected some endpoints to take a `path` parameter"
    c = _client()
    for path in colliding:
        with pytest.raises(errors.QbtError):  # transport, not TypeError
            c.call(path, path="irrelevant")


@pytest.mark.parametrize("falsey", ["false", "False", "FALSE", "0", "no", "off"])
def test_string_false_does_not_become_true(falsey: str) -> None:
    """`deleteFiles=false` from the CLI must not delete the files.

    Every `-p key=value` on `qbt call` arrives as a string, and an agent using
    `qbt_call` can pass one too. Under plain truthiness every non-empty string
    is true, so the one spelling a user reaches for to *protect* their data —
    `deleteFiles=false` — encoded as `true` and wiped it. Booleans crossing a
    text boundary have to be parsed, not evaluated.
    """
    assert encode(Wire.BOOL_STR, falsey) == "false"


@pytest.mark.parametrize("truthy", ["true", "True", "1", "yes", "on"])
def test_string_true_is_still_true(truthy: str) -> None:
    assert encode(Wire.BOOL_STR, truthy) == "true"


def test_real_booleans_are_unaffected() -> None:
    assert encode(Wire.BOOL_STR, True) == "true"
    assert encode(Wire.BOOL_STR, False) == "false"


def test_an_ambiguous_boolean_is_refused_rather_than_guessed() -> None:
    """Guessing here is how `deleteFiles=maybe` silently becomes destructive."""
    with pytest.raises(errors.QbtError, match="boolean"):
        encode(Wire.BOOL_STR, "perhaps")


def test_blocklist_sees_through_a_json_string() -> None:
    """A blocked key hidden in a JSON *string* must still be refused.

    The CLI hands `--json '{...}'` straight through as text, and the gate only
    inspected `dict` values, so the check quietly matched nothing. The request
    then went out double-encoded and qBittorrent ignored it, which hid the hole
    behind a silent no-op: the command appeared to work, changed nothing, and
    reported success. The gate has to understand the wire form the CLI actually
    sends.
    """
    c = Client("http://127.0.0.1:1", username="u", password="p", api_key=None)
    try:
        with pytest.raises(errors.BlockedParameter, match="web_ui_port"):
            c.call("app/setPreferences", json='{"web_ui_port": 9999}')
    finally:
        c.close()


def test_a_blocklisted_param_rejects_a_value_it_cannot_inspect() -> None:
    """If the gate cannot see inside a value, it must refuse, not wave it past."""
    c = Client("http://127.0.0.1:1", username="u", password="p", api_key=None)
    try:
        with pytest.raises(errors.QbtError):
            c.call("app/setPreferences", json="not json at all")
    finally:
        c.close()


def test_a_plain_json_string_still_reaches_the_wire() -> None:
    """Parsing must not break the legitimate case: a safe dict as a string."""
    from qbtkit.client import encode
    from qbtkit.spec._types import Wire

    assert encode(Wire.JSON_BLOB, '{"dl_limit": 22222}') == '{"dl_limit": 22222}'
    assert encode(Wire.JSON_BLOB, {"dl_limit": 22222}) == '{"dl_limit": 22222}'


def test_keychain_can_be_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """A caller that passes explicit credentials must not get ambient ones too.

    The contract tests construct a client with `api_key=None` and a container's
    throwaway username, on the understanding that the author's real credentials
    stay out of the test session. They did not: `None` fell through to the
    Keychain, so a real API key was sent as a Bearer token to every disposable
    container the suite started. Sending a live credential somewhere it was
    never meant to go is worth an explicit off switch.
    """
    import qbtkit.client as mod

    monkeypatch.setattr(mod, "_keychain", lambda *a, **k: "KEYCHAIN-SECRET")
    monkeypatch.delenv("QBT_API_KEY", raising=False)
    monkeypatch.delenv("QBT_PASSWORD", raising=False)

    leaky = Client("http://127.0.0.1:1", username="u", password="p", api_key=None)
    try:
        assert leaky._api_key == "KEYCHAIN-SECRET", "default should still use the Keychain"
    finally:
        leaky.close()

    sealed = Client(
        "http://127.0.0.1:1", username="u", password="p", api_key=None, use_keychain=False
    )
    try:
        assert sealed._api_key is None
        assert sealed._password == "p"
    finally:
        sealed.close()
