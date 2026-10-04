"""Driver for the pipeline's iteration ledger: one record per implementer return.

A scenario appends iteration records to a task's working directory and reads
them back through the ledger's one parser. The ledger is a JSON Lines file named
`ITERATION_LEDGER.jsonl` in the task directory, written and read by the library
`scripts/iteration_ledger.py`. This driver maps between the plain values below
(which a scenario sees) and the library's record, so a scenario never depends on
the on-disk shape. The library is imported inside the bound functions: the
scenario file collects before the library exists, and each scenario then fails on
the missing module rather than on a collection error.
"""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import ModuleType

from tests.acceptance.drivers.step_checks import REPO_ROOT, Criterion

SLUG = "ledger-task"
STEP_NUMBER = "1"
LEDGER_FILE = "ITERATION_LEDGER.jsonl"
STEP_LABEL = "Step "


class StopReason(Enum):
    COMPLETED = "returned complete"
    TURN_CAP = "stopped at its turn cap"
    BLOCKED = "returned blocked"
    NO_MARKER = "returned with no recognized terminal marker"


@dataclass(frozen=True)
class IterationRecord:
    step: str
    attempt: int
    agent_id: str
    verdict: str
    criterion: Criterion
    test_result: str  # the step's recorded `Result:` line
    commit: str | None  # None states that no commit holds the step's work
    stop_reason: StopReason


@dataclass(frozen=True)
class Finding:
    record_position: int  # 1-based position, in append order, of the record that breaks the shape
    message: str


@dataclass(frozen=True)
class LedgerReading:
    records: tuple[IterationRecord, ...]
    findings: tuple[Finding, ...]


# The library writes closed vocabularies as plain words; these tables are the mapping.
_STOP_REASON_WORD = {
    StopReason.COMPLETED: "completed",
    StopReason.TURN_CAP: "turn-cap",
    StopReason.BLOCKED: "blocked",
    StopReason.NO_MARKER: "no-marker",
}
_STOP_REASON_BY_WORD = {word: reason for reason, word in _STOP_REASON_WORD.items()}
_DECIDED_BY_WORD = {
    Criterion.CHECK: "check",
    Criterion.FALLBACK: "fallback",
    Criterion.NONE: "none",
}
_CRITERION_BY_WORD = {word: criterion for criterion, word in _DECIDED_BY_WORD.items()}


def _library() -> ModuleType:
    """The ledger library; scripts import their siblings by bare name, so `scripts/` joins the path."""
    scripts_dir = str(REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    return importlib.import_module("iteration_ledger")


def _to_library_record(library: ModuleType, record: IterationRecord):
    return library.IterationRecord(
        step=f"{STEP_LABEL}{record.step}",
        attempt=record.attempt,
        agent_id=record.agent_id,
        verdict=record.verdict,
        decided_by=_DECIDED_BY_WORD[record.criterion],
        test_result=record.test_result,
        commit=record.commit,
        stop_reason=_STOP_REASON_WORD[record.stop_reason],
    )


def _from_library_record(raw) -> IterationRecord:
    return IterationRecord(
        step=raw.step.removeprefix(STEP_LABEL),
        attempt=raw.attempt,
        agent_id=raw.agent_id,
        verdict=raw.verdict,
        criterion=_CRITERION_BY_WORD[raw.decided_by],
        test_result=raw.test_result,
        commit=raw.commit,
        stop_reason=_STOP_REASON_BY_WORD[raw.stop_reason],
    )


def task_dir(workspace: Path) -> Path:
    """An empty task working directory holding a minimal `WIP.md`."""
    directory = workspace / ".ai-work" / SLUG
    directory.mkdir(parents=True)
    step = f"Step {STEP_NUMBER}"
    (directory / "WIP.md").write_text(
        f"# WIP: ledger task\n\n## Current Step\n\n{step} of 1: Write the widget\n\n"
        "## Status\n\n[IN-PROGRESS] - Step underway\n\n## Progress\n\n"
        f"- [ ] {step}: Write the widget\n\n## Blockers\n\nNone\n",
        encoding="utf-8",
    )
    return directory


def append_record(directory: Path, record: IterationRecord) -> None:
    """Append `record` to the task's iteration ledger, as its writer does."""
    library = _library()
    library.append_record(directory, _to_library_record(library, record))


def append_malformed_record(directory: Path) -> None:
    """Append one record that breaks the documented shape: every key but its verdict."""
    line = {
        "v": 1,
        "recorded_at": "2026-10-04T17:39Z",
        "step": f"{STEP_LABEL}{STEP_NUMBER}",
        "attempt": 1,
        "agent_id": "c0ffee1234",
        "decided_by": "check",
        "test_result": "Result: pass=4 fail=0 skip=0",
        "commit": None,
        "stop_reason": "completed",
    }
    with (directory / LEDGER_FILE).open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps(line) + "\n")


def create_empty_ledger(directory: Path) -> None:
    """Create the ledger with no records in it."""
    (directory / LEDGER_FILE).write_text("", encoding="utf-8")


def read_ledger(directory: Path) -> LedgerReading:
    """Read the task's ledger through its one parser: records in order, plus shape findings."""
    reading = _library().read_ledger(directory)
    return LedgerReading(
        records=tuple(_from_library_record(raw) for raw in reading.records),
        findings=tuple(Finding(f.position, f.reason) for f in reading.findings),
    )


def ledger_artifact_name() -> str:
    """The name under which the project's artifact registry lists the iteration ledger."""
    return LEDGER_FILE
