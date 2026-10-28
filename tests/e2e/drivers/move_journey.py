"""A move run, end to end, that spends nothing: stand-in main sessions over planted records.

The operator's journey crosses the console entry, the `claude` binary it launches each task's
main session through, the fixture repository the session works in, and the results files and
run index it writes. This driver points the entry at a narrowed checkout (`move_eval`), puts a
stand-in `claude` first on PATH, runs floor and paired runs, and hands back what each run
launched and wrote.

The stand-in plays a headless main session the way the harness would present one to the
runner, and is unbound until a binding step ties it to the designed session record: per
launch it learns the arm and task the runner launched, leaves in the session's own record the
arrivals the arm owes (or what the scenario scripts instead), acts in the task's fixture as
scripted (a conforming commit of the named files, or a violating one), or fails with an
identical infrastructure error, and records the launch: its arm, task, working directory and
prompt. No real `claude` ever starts; the run carries a dummy credential.
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from tests.acceptance.drivers import adherence_eval
from tests.acceptance.drivers.move_eval import (
    FIRST_MOVE,
    Arm,
    CliResult,
    MoveRun,
    RunKind,
    run_move,
    unbound,
)

Ending = Literal[
    "conforming",  # commits exactly the named files with a well-formed message
    "violating",  # stages every change at once and commits with a malformed message
    "violating the message only",  # commits the named files with a malformed message
    "kernel never arrived",  # a lean session whose resident kernel is absent from its record
    "infrastructure error",  # exits non-zero with the same error text every time
]


@dataclass(frozen=True)
class Script:
    """What the stand-in does for each session: by arm, then by the arm's nth launch (1-based)."""

    default: Ending = "conforming"
    by_arm: Mapping[Arm, Ending] = field(default_factory=dict)
    by_launch: Mapping[tuple[Arm, int], Ending] = field(default_factory=dict)


@dataclass(frozen=True)
class MoveLaunch:
    arm: Arm
    task_id: str
    cwd: Path
    prompt: str


@dataclass(frozen=True)
class StandIn:
    root: Path

    @property
    def bin_dir(self) -> Path:
        return self.root / "bin"

    def launches(self) -> list[MoveLaunch]:
        unbound(
            "the move stand-in reads back each launch it answered, with its arm, task, working"
            " directory and prompt"
        )

    def rescript(self, script: Script) -> None:
        unbound("the move stand-in can be handed a new script between runs")


def install_stand_in(workspace: Path, script: Script) -> StandIn:
    unbound(
        "a stand-in claude answers each main session of a move run as the harness would: it"
        " learns the arm and task the runner launched, leaves in the session's own record the"
        " arrivals that arm owes, acts in the task's fixture as scripted, and records the launch"
    )


def results_dir(checkout: Path) -> Path:
    return checkout / ".ai-state" / "eval_ledger" / "adherence"


def _results_files(checkout: Path) -> set[Path]:
    return {p for p in results_dir(checkout).glob("*.json") if p.name != "index.json"}


@dataclass(frozen=True)
class RunOutcome:
    cli: CliResult
    launches: tuple[MoveLaunch, ...]  # the launches this invocation made
    written: tuple[Path, ...]  # results files this invocation added

    @property
    def results(self) -> Path:
        (only,) = self.written
        return only

    def describe(self) -> str:
        return f"exit {self.cli.exit_code}; stderr: {self.cli.stderr[-1500:]}"


def run(
    stand_in: StandIn,
    checkout: Path,
    kind: RunKind,
    *,
    max_tasks: int,
    floor_citation: Path | None = None,
    stop_count: int | None = None,
    move: str = FIRST_MOVE,
    declared=None,
) -> RunOutcome:
    """Launch one floor or paired run of `move` with the stand-in, and say what it did."""
    request = MoveRun(
        move,
        checkout,
        kind=kind,
        max_tasks=max_tasks,
        floor_citation=floor_citation,
        stop_count=stop_count,
        declared=declared,
    )
    return observe(stand_in, checkout, lambda: run_move(request, stand_in.bin_dir))


def observe(stand_in: StandIn, checkout: Path, invoke) -> RunOutcome:
    """Run `invoke` and report the launches and results files it added."""
    files_before, launched_before = _results_files(checkout), len(stand_in.launches())
    cli = invoke()
    launches = tuple(stand_in.launches()[launched_before:])
    written = tuple(sorted(_results_files(checkout) - files_before))
    return RunOutcome(cli, launches, written)


def copy_checkout(checkout: Path, workspace: Path) -> Path:
    """An independent copy of a checkout and every results file it holds, for one scenario."""
    target = workspace / "checkout-copy"
    shutil.copytree(checkout, target, symlinks=True)
    return target


def commit_change(checkout: Path, relpath: str, text: str) -> None:
    """Change one file of the checkout and commit it, as a maintainer would between runs."""
    (checkout / relpath).write_text(text, encoding="utf-8")
    adherence_eval._git(checkout, "add", "--", relpath)
    adherence_eval._git(checkout, "commit", "-q", "-m", f"Change {relpath}")
