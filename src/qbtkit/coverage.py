"""The endpoint coverage ledger.

This lives in the package rather than in `tools/` because `qbt coverage` is a
documented command and the ledger is the evidence behind the project's central
claim. Shelling out to a script in the repo meant the command worked from a
checkout and failed from an installed wheel — silently, with exit code 0.

The inventories ship as package data for the same reason: they are no longer
only a build-time artifact, they are what the command reads at runtime.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

from qbtkit.spec import load_all

INVENTORY_DIR = pathlib.Path(__file__).resolve().parent / "inventory"
DEFAULT_TARGET = "release-5.2.3"


class UnknownTarget(LookupError):
    """No committed inventory for that reference."""


@dataclass
class Ledger:
    target: str
    total: int
    specced: int
    untestable: int
    phantoms: list[str]
    scopes: list[dict] = field(default_factory=list)

    @property
    def percent(self) -> float:
        return 100.0 * self.specced / self.total if self.total else 0.0

    def as_dict(self) -> dict:
        return {
            "target": self.target,
            "total": self.total,
            "specced": self.specced,
            "phantoms": self.phantoms,
            "scopes": self.scopes,
        }


def available_targets() -> list[str]:
    return sorted(p.stem for p in INVENTORY_DIR.glob("*.json"))


def load_inventory(ref: str) -> dict[str, set[str]]:
    path = INVENTORY_DIR / f"{ref}.json"
    if not path.exists():
        raise UnknownTarget(
            f"no inventory for {ref!r}; have {', '.join(available_targets()) or 'none'}"
        )
    doc = json.loads(path.read_text())
    by_scope: dict[str, set[str]] = {}
    for e in doc["endpoints"]:
        by_scope.setdefault(e["scope"], set()).add(e["name"])
    return by_scope


def build(target: str = DEFAULT_TARGET) -> Ledger:
    inv = load_inventory(target)
    endpoints = load_all()
    spec_by_scope: dict[str, set[str]] = {}
    for e in endpoints:
        spec_by_scope.setdefault(e.scope, set()).add(e.name)

    # Phantoms: specced but not present upstream. These would silently inflate
    # the numerator, so they are an error rather than a note.
    phantoms = sorted(
        f"{scope}/{name}"
        for scope, names in spec_by_scope.items()
        for name in names - inv.get(scope, set())
    )
    scopes = [
        {
            "scope": scope,
            "total": len(inv[scope]),
            "specced": len(inv[scope] & spec_by_scope.get(scope, set())),
            "missing": sorted(inv[scope] - spec_by_scope.get(scope, set())),
        }
        for scope in sorted(inv, key=lambda s: -len(inv[s]))
    ]
    return Ledger(
        target=target,
        total=sum(len(v) for v in inv.values()),
        specced=sum(len(inv[s] & spec_by_scope.get(s, set())) for s in inv),
        untestable=sum(1 for e in endpoints if e.untestable),
        phantoms=phantoms,
        scopes=scopes,
    )


def bar(done: int, total: int, width: int = 20) -> str:
    if total == 0:
        return "·" * width
    filled = round(width * done / total)
    return "█" * filled + "░" * (width - filled)


def render(ledger: Ledger) -> str:
    out = [f"qbt-kit coverage — target {ledger.target}\n"]
    out.append(f"  {'scope':16s} {'n':>4} {'spec':>6}  progress")
    for row in ledger.scopes:
        n, have = row["total"], row["specced"]
        out.append(f"  {row['scope']:16s} {n:4d} {have:6d}  {bar(have, n)}  {have}/{n}")
    out.append(f"  {'':16s} {'----':>4}")
    out.append(
        f"  {'TOTAL':16s} {ledger.total:4d} {ledger.specced:6d}  "
        f"{bar(ledger.specced, ledger.total)}  {ledger.percent:.1f}%"
    )
    out.append(
        f"\n  specced            {ledger.specced:3d}/{ledger.total}  {ledger.percent:5.1f}%"
    )
    out.append(
        f"  marked untestable  {ledger.untestable:3d}       (reason recorded per endpoint)"
    )
    if ledger.phantoms:
        out.append(f"\n  !! {len(ledger.phantoms)} specced endpoint(s) do not exist upstream:")
        out.extend(f"     {p}" for p in ledger.phantoms)
    return "\n".join(out)
