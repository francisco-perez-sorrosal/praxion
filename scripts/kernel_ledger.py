"""The adoption ledger: what a role's record of trial and flip evidence means.

`.ai-state/kernel_adoption.yaml` is read through `kernel_model`'s readers; this module holds
what the ledger adds to them, as values whose illegal states cannot be built.

| Invariant                                                        | Enforced by                      |
| ---------------------------------------------------------------- | -------------------------------- |
| a switched record holds every piece of flip evidence             | `Switched.__post_init__`         |
| only an eligible role is switched                                | `_parse_record`                  |
| a role moves only absent -> trial -> switched                    | `ledger_transitions`             |
| a record names when it began, readably, to bound what it judges  | `since_time`, both readers       |
| the spawn hook reads every role's status as PyYAML does          | `hook_misreadings`               |

The ledger has three readers, each for a caller that trusts different things: `load_ledger`
builds the evidence-checked record (the commit gate); `load_adoptions` reads only each
role's status and start (the liveness check); `kernel_model.load_statuses` reads only the
status (the generator). The two lenient readers survive a record the gate is about to refuse.
A fourth reader lives outside this module: the spawn hook scans the ledger's text line by
line, without a YAML parser, so `hook_misreadings` holds its reading to PyYAML's.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any

import kernel_model as km

REQUIRED_PAIRS = 20  # a flip rests on a run of at least this many complete pairs
SWITCHED_FIELDS = tuple(
    "passing_run probe_before_tokens probe_after_tokens flip_rule_ratified flip_ratified".split()
)
_BARE_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_LADDER = (None, "trial", "switched")  # a role stays or climbs one rung: no skipping, no descent
_MAPPING_KEY = re.compile(r"[ \t]*([\w.-]+)[ \t]*:")


@dataclass(frozen=True)
class Run:
    id: str
    complete_pairs: int
    passes_flip_rule: bool
    entry: str


@dataclass(frozen=True)
class Trial:
    role: str
    since: datetime
    runs: tuple[Run, ...]


@dataclass(frozen=True)
class Switched:
    role: str
    since: datetime
    runs: tuple[Run, ...]
    passing_run: str
    probe_before_tokens: int
    probe_after_tokens: int
    flip_rule_ratified: bool
    flip_ratified: bool

    def __post_init__(self) -> None:
        passing = next((run for run in self.runs if run.id == self.passing_run), None)
        gaps = (
            _run_gaps(passing) if passing else [f"cites {self.passing_run!r}, not among its runs"]
        )
        probes = ((n, getattr(self, n)) for n in SWITCHED_FIELDS[1:3])
        gaps += [f"has no positive {n}" for n, v in probes if type(v) is not int or v <= 0]
        gaps += [
            f"lacks the user's {n}" for n in SWITCHED_FIELDS[3:] if getattr(self, n) is not True
        ]
        if gaps:
            raise km.KernelModelError(f"role {self.role}: a switched record " + "; ".join(gaps))


def _run_gaps(run: Run) -> list[str]:
    gaps = []
    if run.complete_pairs < REQUIRED_PAIRS:
        gaps.append(
            f"rests on run {run.id!r} of {run.complete_pairs} pairs (needs {REQUIRED_PAIRS})"
        )
    if not run.passes_flip_rule:
        gaps.append(f"rests on run {run.id!r}, which does not pass the flip rule")
    return gaps


AdoptionRecord = Trial | Switched


@dataclass(frozen=True)
class Ledger:
    eligible: tuple[str, ...]
    records: Mapping[str, AdoptionRecord]


@dataclass(frozen=True)
class Adoption:
    """A role at trial or switched, and the moment its record began: no spawn before it is judged."""

    status: str
    since: datetime


# -- Boundary: the evidence-checked ledger ------------------------------------------


def parse_ledger(raw: Mapping[str, Any], agents: Collection[str]) -> Ledger:
    """The ledger with its evidence: a switched role missing any piece is refused by name."""
    statuses = km.parse_statuses(raw)
    eligible = tuple(km.as_sequence(raw.get("eligible"), "eligible"))
    records = {}
    for role, status in statuses.items():
        if role not in agents:
            raise km.KernelModelError(f"role {role}: no such agent")
        records[role] = _parse_record(role, status, raw["roles"][role], role in eligible)
    return Ledger(eligible, MappingProxyType(records))


def _parse_record(role: str, status: str, row: Mapping[str, Any], eligible: bool) -> AdoptionRecord:
    since = since_time(row.get("since"), role)
    runs = tuple(_parse_run(role, run) for run in km.as_sequence(row.get("runs"), "runs"))
    if status == "trial":
        return Trial(role, since, runs)
    if not eligible:
        raise km.KernelModelError(f"role {role}: is not eligible to be switched")
    missing = [key for key in SWITCHED_FIELDS if row.get(key) is None]
    if missing:
        raise km.KernelModelError(f"role {role}: a switched record lacks {', '.join(missing)}")
    return Switched(role, since, runs, *(row[key] for key in SWITCHED_FIELDS))


def _parse_run(role: str, row: Any) -> Run:
    row = km.as_mapping(row, f"role {role}: a run")
    return Run(
        id=km.as_text(row.get("id"), f"role {role}: run id"),
        complete_pairs=row.get("complete_pairs") or 0,
        passes_flip_rule=row.get("passes_flip_rule") is True,
        entry=row.get("entry") or "",
    )


# -- Boundary: the lenient reader of who is adopted, and since when ----------------------


def parse_adoptions(raw: Mapping[str, Any]) -> Mapping[str, Adoption]:
    """Each role at trial or switched with the moment its record began; nothing else is judged."""
    statuses = km.parse_statuses(raw)
    rows = km.as_mapping(raw.get("roles") or {}, "roles")
    return MappingProxyType(
        {
            role: Adoption(status, since_time(rows[role].get("since"), role))
            for role, status in statuses.items()
        }
    )


def since_time(value: Any, role: str) -> datetime:
    """When a record began, as an aware datetime; the one reader of a record's `since`.

    A moment is itself (a naive one reads as UTC). A bare date is the end of that day in UTC, so
    a role placed at trial mid-day is not judged on that day's earlier spawns; the ledger writer
    records a moment, and a date YAML already parsed reads the same way as one still text.
    """
    if isinstance(value, str):
        value = _iso(value, role)
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time.max, tzinfo=timezone.utc)
    raise km.KernelModelError(f"role {role}: since {value!r} is not a date or a moment")


def _iso(text: str, role: str) -> date | datetime:
    stamp = text.strip()
    if stamp.endswith("Z"):
        stamp = stamp[:-1] + "+00:00"  # `fromisoformat` takes "Z" only from Python 3.11
    try:
        if _BARE_DATE.fullmatch(stamp):
            return date.fromisoformat(stamp)
        return datetime.fromisoformat(stamp)
    except ValueError as exc:
        raise km.KernelModelError(
            f"role {role}: since {text!r} is not an ISO date or moment"
        ) from exc


# -- Pure: the ladder of moves -------------------------------------------------------


def ledger_transitions(
    before: Mapping[str, str] | None, after: Mapping[str, str]
) -> tuple[km.Finding, ...]:
    """Moves between two ledgers' statuses (role -> status) that go anywhere but forward one rung.

    `before` None is no ledger at all: every role in `after` then starts from absent.
    """
    earlier = before or {}
    findings = []
    for role in sorted(set(earlier) | set(after)):
        was, now = earlier.get(role), after.get(role)
        if _LADDER.index(now) - _LADDER.index(was) not in (0, 1):
            move = f"{was or 'absent'} -> {now or 'absent'}"
            findings.append(km.Finding("ledger-transition", f"role {role}", move))
    return tuple(findings)


def hook_misreadings(
    statuses: Mapping[str, str],
    ledger_text: str,
    hook_status: Callable[[str, str], str | None],
) -> tuple[km.Finding, ...]:
    """Each role whose status `hook_status` reads from `ledger_text` otherwise than `statuses`.

    `statuses` is PyYAML's reading of the same text; `hook_status` is the spawn hook's own
    reader, which knows only the generated block shape. Both directions are judged: a record
    in any other layout (deeper indentation, a quoted or flow-style value) parses here and
    injects nothing at spawn, and a record PyYAML discards (a second top-level `roles:` key,
    of which it keeps the last) injects at spawn with no record the gate judged.
    """
    roles = set(statuses) | _mapping_keys(ledger_text)
    return tuple(
        km.Finding(
            "hook-misread",
            f"role {role}",
            f"the spawn hook reads status {read!r} where PyYAML reads {statuses.get(role)!r}: "
            "rewrite the record in the ledger's generated block shape",
        )
        for role in sorted(roles, key=str)
        if (read := hook_status(ledger_text, role)) != statuses.get(role)
    )


def _mapping_keys(text: str) -> frozenset[str]:
    """Every block-mapping key in `text`, at any indentation, line by line as the hook splits it.

    A superset of the roles the spawn hook can answer for: it reads a status only under a key
    line, and its key pattern is one of these.
    """
    return frozenset(
        found.group(1) for line in text.splitlines() if (found := _MAPPING_KEY.match(line))
    )


# -- Edge: files -----------------------------------------------------------------------


def load_ledger(root: Path, agents: Collection[str]) -> Ledger:
    """The evidence-checked ledger; no ledger file is an empty ledger."""
    path = root / km.LEDGER_PATH
    if not path.is_file():
        return Ledger((), MappingProxyType({}))
    return parse_ledger(km.read_yaml(path), agents)


def load_adoptions(root: Path) -> Mapping[str, Adoption]:
    """Who is adopted under `root` and since when; no ledger file adopts nobody."""
    path = root / km.LEDGER_PATH
    return parse_adoptions(km.read_yaml(path)) if path.is_file() else MappingProxyType({})
