"""Driver for the per-role adoption ledger (`.ai-state/kernel_adoption.yaml`).

Scenarios describe a role's record in the specification's terms: its status
(trial, switched or held), the moment the record began, the adherence runs of that
role in order, the startup probe's readings of its first request before and after,
the user's ratification of the flip rule and of the flip, and, for a held role, the
reason its trial closed without a flip. A held role re-opened is a new trial: its
record starts at the re-opening, and the spawns made while it was held come before
that start. Scenarios date the hold an hour back, so the hold, the spawns made while
held and the re-opening are distinct instants at the ledger's whole-second resolution.
The hooks read and write the ledger's wire
shape (`version: 1`, `roles`, and `eligible` while the roles are not pinned apart; a
held row carries `reason`); a missing ledger reads as empty.

Which ledger a spawn outside the Praxion checkout reads is an open question; the
scenarios provisionally write the running plugin's own ledger.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from tests.acceptance.drivers.kernel_sandbox import ADOPTION_LEDGER, PILOT_ROLES, commit_paths

ELIGIBILITY_PIN = "scripts/kernel_eligibility.py"  # where the eligible roles live once pinned

ADHERENCE_ENTRY = "praxion-evals-adherence"
REQUIRED_PAIRS = 20
TRIAL_SINCE = "2026-10-12"
HELD_REASON = "the flip rule did not pass on the role's last run; a calibration run comes first"
HELD_FOR = timedelta(hours=1)  # how long before its re-opening a scenario's role was held


@dataclass(frozen=True)
class AdherenceRun:
    run_id: str
    complete_pairs: int
    passes_flip_rule: bool
    entry: str = ADHERENCE_ENTRY


@dataclass(frozen=True)
class AdoptionRecord:
    role: str
    status: str  # "trial" | "switched" | "held"
    runs: tuple[AdherenceRun, ...] = ()  # every adherence run of the role, in order
    probe_before_tokens: int | None = None
    probe_after_tokens: int | None = None
    flip_rule_ratified: bool = False
    flip_ratified: bool = False
    reason: str | None = None  # why a held trial closed without a flip; None writes no reason
    since: str | None = (
        TRIAL_SINCE  # when the record (a trial, or a re-opened one) began; None writes none
    )


def at_trial(role: str) -> AdoptionRecord:
    return AdoptionRecord(role, "trial")


def held(
    role: str, runs: tuple[AdherenceRun, ...] = (), reason: str | None = HELD_REASON
) -> AdoptionRecord:
    """A trial closed without a flip: its runs kept in order, and (by default) its reason."""
    return AdoptionRecord(role, "held", runs=runs, reason=reason)


def ledger_instant(moment: datetime) -> str:
    """`moment` as the ledger writes an instant: ISO 8601 in UTC, whole seconds."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def commit_hold(root: Path, record: AdoptionRecord, held_for: timedelta = HELD_FOR) -> datetime:
    """Commit `record`, a held one, as a hold made `held_for` ago; return the hold's moment."""
    hold = datetime.now(UTC) - held_for
    _write(root, [record])
    commit_paths(root, "ledger: the role held", ADOPTION_LEDGER, at=hold)
    return hold


def reopened_now() -> str:
    """The start of a trial re-opened at this moment: the re-opening itself.

    Truncated to the ledger's whole seconds, so every spawn made after the re-opening
    falls at or after the start.
    """
    return ledger_instant(datetime.now(UTC))


def reopened_after(moment: datetime) -> str:
    """The start of a trial re-opened right after `moment`: the first whole second past it.

    Whatever happened by `moment` (a spawn made while the role was held) then comes
    before the start, at any resolution a reader compares instants at.
    """
    return ledger_instant(moment.replace(microsecond=0) + timedelta(seconds=1))


def start_before_the_reopening(kind: str, hold: datetime) -> str:
    """A start a re-opened trial records that falls before its re-opening."""
    starts = {
        "the first trial's start kept": TRIAL_SINCE,
        "a start inside the held period": ledger_instant(hold + HELD_FOR / 2),
    }
    return starts[kind]


STARTS_BEFORE_THE_REOPENING = ("the first trial's start kept", "a start inside the held period")


def start_out_of_bounds(kind: str) -> str | None:
    """A start a re-opened trial may not record: none, one not after the hold, or a future one."""
    starts = {
        "no start": None,
        "the first trial's start kept": TRIAL_SINCE,
        "a start after the re-opening": ledger_instant(datetime.now(UTC) + HELD_FOR),
    }
    return starts[kind]


STARTS_OUT_OF_BOUNDS = ("no start", "the first trial's start kept", "a start after the re-opening")


def runs_of(role: str, count: int) -> tuple[AdherenceRun, ...]:
    """`count` recorded runs of `role`, none of which passes the flip rule."""
    return tuple(AdherenceRun(f"{role}-run-{n}", 12, False) for n in range(1, count + 1))


def full_switch_record(role: str) -> AdoptionRecord:
    """Every element a flip needs: an earlier run, then a passing run of enough pairs."""
    return AdoptionRecord(
        role,
        "switched",
        runs=(
            AdherenceRun(f"{role}-run-1", 12, False),
            AdherenceRun(f"{role}-run-2", REQUIRED_PAIRS + 4, True),
        ),
        probe_before_tokens=31_000,
        probe_after_tokens=22_000,
        flip_rule_ratified=True,
        flip_ratified=True,
    )


def switched_without_record(role: str) -> AdoptionRecord:
    """Status switched, nothing else: what the hook reads, never what a flip needs."""
    return AdoptionRecord(role, "switched")


def lacking(record: AdoptionRecord, element: str) -> AdoptionRecord:
    """`record` with one required element missing or short."""
    passing = record.runs[-1]
    variants = {
        "no adherence run": replace(record, runs=()),
        "a passing run under twenty pairs": replace(
            record, runs=(*record.runs[:-1], replace(passing, complete_pairs=REQUIRED_PAIRS - 1))
        ),
        "no run that passes the flip rule": replace(
            record, runs=tuple(replace(r, passes_flip_rule=False) for r in record.runs)
        ),
        "a passing run from another eval": replace(
            record, runs=(*record.runs[:-1], replace(passing, entry="praxion-evals-live"))
        ),
        "no startup reading before": replace(record, probe_before_tokens=None),
        "no startup reading after": replace(record, probe_after_tokens=None),
        "no ratification of the flip rule": replace(record, flip_rule_ratified=False),
        "no ratification of the flip": replace(record, flip_ratified=False),
        "status still trial": replace(record, status="trial"),
    }
    return variants[element]


MISSING_ELEMENTS = (
    "no adherence run",
    "a passing run under twenty pairs",
    "no run that passes the flip rule",
    "a passing run from another eval",
    "no startup reading before",
    "no startup reading after",
    "no ratification of the flip rule",
    "no ratification of the flip",
    "status still trial",
)


def _run_row(run: AdherenceRun) -> dict:
    return {
        "id": run.run_id,
        "complete_pairs": run.complete_pairs,
        "passes_flip_rule": run.passes_flip_rule,
        "entry": run.entry,
    }


def _passing_run_id(runs: tuple[AdherenceRun, ...]) -> str | None:
    """The run a flip rests on: the last run that passes the rule, else the last run."""
    passing = [r for r in runs if r.passes_flip_rule]
    chosen = passing or list(runs)
    return chosen[-1].run_id if chosen else None


def _record_row(record: AdoptionRecord) -> dict:
    row: dict = {"status": record.status}
    if record.since is not None:
        row["since"] = record.since
    row["runs"] = [_run_row(r) for r in record.runs]
    if record.reason is not None:
        row["reason"] = record.reason
    if record.status == "switched":
        passing = _passing_run_id(record.runs)
        extras = {
            "passing_run": passing,
            "probe_before_tokens": record.probe_before_tokens,
            "probe_after_tokens": record.probe_after_tokens,
        }
        row.update({k: v for k, v in extras.items() if v is not None})
        row["flip_rule_ratified"] = record.flip_rule_ratified
        row["flip_ratified"] = record.flip_ratified
    return row


def _load(root: Path) -> dict:
    path = root / ADOPTION_LEDGER
    ledger = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None
    ledger = ledger or {}
    ledger.setdefault("version", 1)
    if not (root / ELIGIBILITY_PIN).is_file():
        ledger.setdefault("eligible", list(PILOT_ROLES))  # until the roles are pinned apart
    ledger.setdefault("roles", {})
    return ledger


def record(root: Path, *records: AdoptionRecord) -> None:
    """Write each role's record into the ledger, replacing that role's earlier one.

    A role's status moves one step per commit, and only along absent -> trial, then
    trial -> switched, trial -> held, or held -> trial (a re-opened trial). A switched
    or held record is therefore reached the way the rule prescribes: the role's trial
    row (a held role's with the runs it keeps) is committed first, on its own, so the
    record the scenario leaves uncommitted is one step from the parent commit's ledger.
    """
    switched = [at_trial(each.role) for each in records if each.status == "switched"]
    closed = [
        replace(each, status="trial", reason=None) for each in records if each.status == "held"
    ]
    if switched or closed:
        commit_records(root, *switched, *closed)
    _write(root, records)


def commit_records(root: Path, *records: AdoptionRecord) -> None:
    """Write `records` and commit the ledger without the gate: the parent of the move under test."""
    _write(root, records)
    commit_paths(root, "ledger: the records before the move", ADOPTION_LEDGER)


def rewrite(root: Path, *records: AdoptionRecord) -> None:
    """Write `records` exactly as given, uncommitted: the move the commit gate judges."""
    _write(root, records)


def move(
    root: Path, role: str, before: AdoptionRecord | None, after: AdoptionRecord | None
) -> None:
    """Commit `before` as `role`'s record, then leave `after` uncommitted for the gate.

    None stands for no record: absent at the parent commit, or removed by the move.
    """
    _write(root, [before] if before else [], drop=role)
    commit_paths(root, "ledger: the record before the move", ADOPTION_LEDGER)
    _write(root, [after] if after else [], drop=role)


def _write(root: Path, records: Sequence[AdoptionRecord], drop: str | None = None) -> None:
    ledger = _load(root)
    ledger["roles"].pop(drop, None)
    for each in records:
        ledger["roles"][each.role] = _record_row(each)
    path = root / ADOPTION_LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(ledger, sort_keys=False), encoding="utf-8")


def switched_roles(root: Path) -> set[str]:
    roles = _load(root)["roles"] or {}
    return {role for role, row in roles.items() if (row or {}).get("status") == "switched"}
