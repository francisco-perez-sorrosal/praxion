"""Driver for the pipeline's iteration ledger: one record per implementer return.

A scenario appends iteration records to a task's working directory and reads
them back through the ledger's one parser. Where the ledger lives (a file of its
own or a section of `WIP.md`), how a record is written and how the parser reports
a record that breaks the shape are design decisions; every hook below raises
until a binding step connects it to them. Records and findings cross this driver
as the plain values below, so a scenario never depends on the on-disk shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from tests.acceptance.drivers.step_checks import Criterion, UnboundDriverError

SLUG = "ledger-task"
STEP_NUMBER = "1"


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
    raise UnboundDriverError(
        "unbound: an iteration record (step, attempt, agent id, verdict and deciding criterion, "
        "test result line, commit or an explicit none, stop reason) is appended to the task's "
        "ledger in its one documented shape -- bind this to the designed writer"
    )


def append_malformed_record(directory: Path) -> None:
    """Append one record that breaks the documented shape (a record missing its verdict)."""
    raise UnboundDriverError(
        "unbound: a record that breaks the ledger's documented shape can be appended for the "
        "parser to report -- bind this to the designed record shape, minus its verdict"
    )


def create_empty_ledger(directory: Path) -> None:
    """Create the ledger with no records in it."""
    raise UnboundDriverError(
        "unbound: an iteration ledger that exists but holds no records -- bind this to the "
        "designed ledger location"
    )


def read_ledger(directory: Path) -> LedgerReading:
    """Read the task's ledger through its one parser: records in order, plus shape findings."""
    raise UnboundDriverError(
        "unbound: the iteration ledger has one parser that returns every record in append order "
        "and reports each record that breaks the shape with its position -- bind this to it"
    )


def ledger_artifact_name() -> str:
    """The name under which the project's artifact registry lists the iteration ledger."""
    raise UnboundDriverError(
        "unbound: the canonical artifact list names the iteration ledger -- bind this to the "
        "registered name"
    )
