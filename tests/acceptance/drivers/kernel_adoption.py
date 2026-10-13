"""Driver for the per-role adoption ledger (`.ai-state/kernel_adoption.yaml`).

Scenarios describe a role's record in the specification's terms: its status
(trial or switched), the adherence runs of that role in order, the startup probe's
readings of its first request before and after, and the user's ratification of the
flip rule and of the flip. The hooks read and write the ledger's wire shape (the implementation
plan's "Wire shapes": `version: 1`, `eligible`, `roles`); a missing ledger reads as
empty.

Which ledger a spawn outside the Praxion checkout reads is an open question; the
scenarios provisionally write the running plugin's own ledger.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from tests.acceptance.drivers.kernel_sandbox import ADOPTION_LEDGER, PILOT_ROLES, commit_paths

ADHERENCE_ENTRY = "praxion-evals-adherence"
REQUIRED_PAIRS = 20
TRIAL_SINCE = "2026-10-12"


@dataclass(frozen=True)
class AdherenceRun:
    run_id: str
    complete_pairs: int
    passes_flip_rule: bool
    entry: str = ADHERENCE_ENTRY


@dataclass(frozen=True)
class AdoptionRecord:
    role: str
    status: str  # "trial" | "switched"
    runs: tuple[AdherenceRun, ...] = ()  # every adherence run of the role, in order
    probe_before_tokens: int | None = None
    probe_after_tokens: int | None = None
    flip_rule_ratified: bool = False
    flip_ratified: bool = False


def at_trial(role: str) -> AdoptionRecord:
    return AdoptionRecord(role, "trial")


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
    row: dict = {
        "status": record.status,
        "since": TRIAL_SINCE,
        "runs": [_run_row(r) for r in record.runs],
    }
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
    ledger.setdefault("eligible", list(PILOT_ROLES))
    ledger.setdefault("roles", {})
    return ledger


def record(root: Path, *records: AdoptionRecord) -> None:
    """Write each role's record into the ledger, replacing that role's earlier one.

    A role climbs one rung per commit (absent -> trial -> switched). A switched record
    is therefore reached the way the rule prescribes: the role's trial row is committed
    first, on its own, so the switched record the scenario leaves uncommitted is one
    rung above the parent commit's ledger.
    """
    switched = [each for each in records if each.status == "switched"]
    if switched:
        _write(root, [at_trial(each.role) for each in switched])
        commit_paths(root, "ledger: place the roles at trial", ADOPTION_LEDGER)
    _write(root, records)


def _write(root: Path, records: Sequence[AdoptionRecord]) -> None:
    ledger = _load(root)
    for each in records:
        ledger["roles"][each.role] = _record_row(each)
    path = root / ADOPTION_LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(ledger, sort_keys=False), encoding="utf-8")


def switched_roles(root: Path) -> set[str]:
    roles = _load(root)["roles"] or {}
    return {role for role, row in roles.items() if (row or {}).get("status") == "switched"}
