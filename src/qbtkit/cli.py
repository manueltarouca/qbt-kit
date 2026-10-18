"""The CLI, generated from the spec.

Every endpoint in the spec becomes a subcommand, so coverage of the CLI is
coverage of the API by construction rather than by diligence. `qbt call` is the
raw escape hatch for anything a friendlier command does not reach.
"""

from __future__ import annotations

import functools
import inspect
import json as jsonlib
import sys
from collections.abc import Callable
from typing import Annotated, Any, Optional

import typer

from . import coverage as cov
from . import errors
from .client import Client
from .spec import load_all
from .spec._types import Endpoint, Wire, camel_to_kebab

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Complete CLI for the qBittorrent WebUI API.",
    rich_markup_mode=None,
)

# Mapping from wire encoding to the type the CLI should accept.
PY_TYPE: dict[Wire, Any] = {
    Wire.PLAIN: str,
    Wire.BOOL_STR: bool,
    Wire.INT: int,
    Wire.FLOAT: float,
    Wire.PIPE_LIST: str,  # comma- or pipe-separated on the command line
    Wire.HASHES: str,
    Wire.JSON_BLOB: str,
    Wire.FILE: str,  # a path, read before sending
}

_STATE: dict[str, Any] = {
    "url": None,
    "username": None,
    "password": None,
    "api_key": None,
    "read_only": False,
    "json": False,
}


def _client() -> Client:
    return Client(
        _STATE["url"],
        username=_STATE["username"],
        password=_STATE["password"],
        api_key=_STATE["api_key"],
        read_only=_STATE["read_only"],
    )


def _emit(value: Any) -> None:
    if value is None:
        return
    if _STATE["json"] or isinstance(value, (dict, list)):
        typer.echo(
            jsonlib.dumps(value, indent=2, sort_keys=False)
            if not isinstance(value, bytes)
            else "<binary>"
        )
    elif isinstance(value, bytes):
        sys.stdout.buffer.write(value)
    else:
        typer.echo(value)


def _cli_option_name(param_name: str) -> str:
    """savePath -> --save-path, autoTMM -> --auto-tmm."""
    return "--" + camel_to_kebab(param_name)


def _friendly_errors(fn: Callable[..., None]) -> Callable[..., None]:
    """Report a dead or refusing server as a message, not a traceback.

    The generated commands already translate QbtError; the hand-written ones
    (`health`, `ready`, `coverage`) did not, so pointing them at a stopped
    server produced a wall of Rich traceback instead of one line saying the
    server could not be reached.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        try:
            fn(*args, **kwargs)
        except errors.QbtError as e:
            typer.secho(str(e), fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from e

    return wrapper


def _make_command(ep: Endpoint):  # noqa: ANN202 - returns a generated function
    """Build a typer command whose signature mirrors the endpoint's params."""

    def run(**kwargs: Any) -> None:
        confirm = bool(kwargs.pop("confirm", False))
        payload: dict[str, Any] = {}
        for p in ep.params:
            value = kwargs.get(p.name)
            if value is None:
                continue
            if p.wire is Wire.FILE:
                with open(value, "rb") as fh:
                    value = fh.read()
            elif p.wire in (Wire.PIPE_LIST,):
                value = [v for v in str(value).replace("|", ",").split(",") if v]
            payload[p.name] = value
        try:
            with _client() as client:
                _emit(client.call_endpoint(ep, confirm=confirm, **payload))
        except errors.ConfirmationRequired:
            typer.secho(
                f"{ep.path} is destructive. Re-run with --confirm to proceed.",
                fg=typer.colors.YELLOW,
                err=True,
            )
            raise typer.Exit(2) from None
        except errors.QbtError as e:
            typer.secho(str(e), fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from None

    params: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {}
    for p in ep.params:
        py = PY_TYPE[p.wire]
        opt = typer.Option(
            _cli_option_name(p.name), help=p.summary or f"{p.name} ({p.wire.value})"
        )
        # Build the type outside the subscript: a conditional inside
        # Annotated[...] is not a valid type expression.
        base = py if p.required else Optional[py]  # noqa: UP045
        ann = Annotated[base, opt]
        annotations[p.name] = ann
        params.append(
            inspect.Parameter(
                p.name,
                inspect.Parameter.KEYWORD_ONLY,
                default=... if p.required else None,
                annotation=ann,
            )
        )
    if ep.destructive:
        ann = Annotated[bool, typer.Option("--confirm", help="required: this is destructive")]
        annotations["confirm"] = ann
        params.append(
            inspect.Parameter(
                "confirm", inspect.Parameter.KEYWORD_ONLY, default=False, annotation=ann
            )
        )

    # typer reads the signature and annotations to build options; both are set
    # dynamically because the spec, not this module, decides what they are.
    setattr(run, "__signature__", inspect.Signature(params))  # noqa: B010
    run.__annotations__ = annotations
    run.__name__ = ep.cli_command.replace("-", "_")
    run.__doc__ = ep.summary
    return run


def _build() -> dict[str, typer.Typer]:
    """One sub-app per scope, one command per endpoint."""
    subs: dict[str, typer.Typer] = {}
    for ep in load_all():
        sub = subs.get(ep.scope)
        if sub is None:
            sub = typer.Typer(
                no_args_is_help=True, rich_markup_mode=None, help=f"The {ep.scope} scope."
            )
            subs[ep.scope] = sub
            app.add_typer(sub, name=ep.scope)
        sub.command(ep.cli_command, help=ep.summary)(_make_command(ep))
    return subs


SUBS = _build()


@app.callback()
def main(
    url: Annotated[Optional[str], typer.Option("--url", envvar="QBT_URL")] = None,  # noqa: UP045
    username: Annotated[str | None, typer.Option("--username", envvar="QBT_USERNAME")] = None,
    password: Annotated[str | None, typer.Option("--password", envvar="QBT_PASSWORD")] = None,
    api_key: Annotated[Optional[str], typer.Option("--api-key", envvar="QBT_API_KEY")] = None,  # noqa: UP045
    read_only: Annotated[bool, typer.Option("--read-only", envvar="QBT_READ_ONLY")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Credentials resolve from flags, then the environment, then the Keychain."""
    _STATE.update(
        url=url,
        username=username,
        password=password,
        api_key=api_key,
        read_only=read_only,
        json=json_out,
    )


@app.command()
def doctor() -> None:
    """Report server version, auth mode and endpoint availability."""
    try:
        with _client() as c:
            v = c.version
            typer.echo(f"  url          {c.url}")
            typer.echo(f"  webapi       {'.'.join(map(str, v))}")
            typer.echo(f"  auth mode    {c.auth_mode}")
            eps = load_all()
            unavailable = [e.path for e in eps if not e.available_on(v)]
            typer.echo(
                f"  endpoints    {len(eps) - len(unavailable)}/{len(eps)} "
                f"available on this server"
            )
            for path in unavailable:
                typer.echo(f"               unavailable: {path}")
    except errors.HostHeaderRejected as e:
        typer.secho(f"  {e}", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(1) from None
    except errors.QbtError as e:
        typer.secho(f"  {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from None


@app.command("call")
def raw_call(
    path: Annotated[str, typer.Argument(help="scope/name, e.g. torrents/info")],
    param: Annotated[
        list[str] | None,
        typer.Option(
            "--param",
            "-p",
            help="key=value, repeatable",
        ),
    ] = None,
    confirm: Annotated[bool, typer.Option("--confirm")] = False,
) -> None:
    """Call any endpoint directly. Safety gates still apply."""
    kwargs: dict[str, Any] = {}
    for item in param or []:
        if "=" not in item:
            typer.secho(
                f"--param must be key=value, got {item!r}", fg=typer.colors.RED, err=True
            )
            raise typer.Exit(2)
        k, v = item.split("=", 1)
        kwargs[k] = v
    try:
        with _client() as c:
            _emit(c.call(path, confirm=confirm, **kwargs))
    except errors.QbtError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from None


@app.command()
def coverage(target: str = cov.DEFAULT_TARGET) -> None:
    """Print the endpoint coverage ledger."""
    try:
        ledger = cov.build(target)
    except cov.UnknownTarget as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    print(cov.render(ledger))
    if ledger.phantoms:
        raise typer.Exit(1)


# Not generated from the spec: these answer questions rather than wrapping one
# endpoint. They exist because the raw numbers mislead — see swarm_health.
# Release folders routinely carry .nfo and .txt spam beside the media; the
# question "is this ready to import" is about the media only.
MEDIA_EXT = frozenset(
    {".mkv", ".mp4", ".avi", ".m4v", ".ts", ".flac", ".mp3", ".m4b", ".m4a", ".opus", ".webm"}
)
NOT_CONNECTED = frozenset(
    {
        "queuedDL",
        "queuedUP",
        "checkingDL",
        "checkingUP",
        "metaDL",
        "forcedMetaDL",
        "allocating",
        "checkingResumeData",
        "moving",
    }
)


@app.command()
@_friendly_errors
def health(
    include_complete: Annotated[bool, typer.Option("--include-complete")] = False,
) -> None:
    """Judge whether each torrent can actually finish.

    `availability` is how many complete copies exist across reachable peers. When
    it does not exceed `progress`, no peer holds the missing pieces and the
    download can never complete, however long it waits. Queued torrents are
    reported separately because they show availability 0 for not being connected
    yet, which is not the same as being dead.
    """
    with _client() as c:
        rows = c.call("torrents/info")
    stuck: list[dict[str, Any]] = []
    healthy: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    done: list[dict[str, Any]] = []
    for t in rows:
        gap = t["availability"] - t["progress"]
        if t["progress"] >= 1.0:
            done.append(t)
        elif t["state"] in NOT_CONNECTED:
            pending.append(t)
        elif gap > 0.05:
            healthy.append(t)
        else:
            stuck.append(t)

    if _STATE["json"]:
        typer.echo(
            jsonlib.dumps(
                {
                    "stuck": [_h(t) for t in stuck],
                    "healthy": [_h(t) for t in healthy],
                    "not_connected": [_h(t) for t in pending],
                    "complete": [_h(t) for t in done] if include_complete else len(done),
                },
                indent=2,
            )
        )
        return

    def show(label: str, group: list[dict[str, Any]]) -> None:
        if not group:
            return
        held = sum(t["completed"] for t in group)
        typer.echo(f"\n{label} ({len(group)}, holding {held / 2**30:.2f} GiB)")
        for t in sorted(group, key=lambda x: -x["progress"]):
            need = (t["size"] - t["completed"]) / 2**20
            typer.echo(
                f"  {t['progress'] * 100:6.2f}%  avail={t['availability']:7.3f}"
                f"  needs {need:8.0f} MiB  {t['name'][:52]}"
            )

    show("STUCK — no reachable peer has the missing pieces", stuck)
    show("HEALTHY — still progressing", healthy)
    show("NOT YET CONNECTED — cannot be judged", pending)
    if include_complete:
        show("COMPLETE", done)
    else:
        typer.echo(f"\ncomplete: {len(done)}")


def _h(t: dict[str, Any]) -> dict[str, Any]:
    return {
        k: t[k]
        for k in (
            "name",
            "hash",
            "state",
            "progress",
            "availability",
            "size",
            "completed",
            "num_seeds",
            "num_complete",
        )
    }


@app.command()
@_friendly_errors
def ready(
    idle_minutes: Annotated[int, typer.Option("--idle-minutes")] = 15,
) -> None:
    """List downloads that are complete and settled enough to move.

    Completeness is judged per file from the Web UI, which is live. Reading
    qBittorrent's on-disk resume data instead lags by `save_resume_data_interval`
    — 60 minutes by default — so a torrent finished in the last hour looks
    unfinished there.
    """
    import os
    import time

    with _client() as c:
        rows = c.call("torrents/info")
        out: list[dict[str, Any]] = []
        for t in rows:
            if t["progress"] < 1.0:
                continue
            # A finished torrent whose data is gone has already been imported and
            # is just lingering in the queue. Without this check the list fills
            # up with things that were moved into the library hours ago — the
            # hand-rolled predecessor of this command got that right and the
            # first version of this one did not.
            if not os.path.exists(t["content_path"]):
                continue
            files = c.call("torrents/files", hash=t["hash"])
            wanted = [f for f in files if f["priority"]]
            if not wanted or any(f["progress"] < 1.0 for f in wanted):
                continue
            # Report the media files, not the torrent: a pack with most episodes
            # deselected is "ready" only for the ones actually wanted.
            present = [
                f
                for f in wanted
                if os.path.splitext(f["name"])[1].lower() in MEDIA_EXT
                and os.path.exists(os.path.join(t["save_path"], f["name"]))
            ]
            if not present:
                continue
            idle = (time.time() - t["last_activity"]) / 60 if t["last_activity"] else 1e6
            out.append(
                {
                    "name": t["name"],
                    "hash": t["hash"],
                    "size_gib": round(t["size"] / 2**30, 2),
                    "idle_minutes": round(idle),
                    "save_path": t["save_path"],
                    "state": t["state"],
                    "files": [f["name"] for f in present],
                    "settled": idle >= idle_minutes,
                }
            )
    if _STATE["json"]:
        typer.echo(jsonlib.dumps({"ready": out}, indent=2))
        return
    settled = [r for r in out if r["settled"]]
    typer.echo(f"READY ({len(settled)} settled, {len(out) - len(settled)} too recent)")
    for r in sorted(out, key=lambda x: -x["size_gib"]):
        mark = "" if r["settled"] else f"  (only idle {r['idle_minutes']} min, wait)"
        typer.echo(
            f"  {r['size_gib']:7.2f} GiB  idle {r['idle_minutes']:5d} min  "
            f"{r['name'][:56]}{mark}"
        )
    if not out:
        typer.echo("  nothing finished")
