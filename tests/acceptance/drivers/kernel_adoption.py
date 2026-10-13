"""Driver for the per-role adoption ledger (`.ai-state/kernel_adoption.yaml`), not yet bound.

Scenarios describe a role's record in the specification's terms: its status
(trial or switched), the adherence runs of that role in order, the startup probe's
readings of its first request before and after, and the user's ratification of the
flip rule and of the flip. The file's shape is designed later; the hooks raise
until a binding step writes it.

Which ledger a spawn outside the Praxion checkout reads is an open question; the
scenarios provisionally write the running plugin's own ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from tests.acceptance.drivers.kernel_sandbox import UnboundDriverError

ADHERENCE_ENTRY = "praxion-evals-adherence"
REQUIRED_PAIRS = 20


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


def record(root: Path, *records: AdoptionRecord) -> None:
    raise UnboundDriverError(
        "writing a role's adoption record (status, adherence runs in order, startup "
        "readings before and after, ratifications) into the adoption ledger is not designed yet"
    )


def switched_roles(root: Path) -> set[str]:
    raise UnboundDriverError("reading which roles the adoption ledger records as switched")
