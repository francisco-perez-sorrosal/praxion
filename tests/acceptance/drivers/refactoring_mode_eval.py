"""Driver for the adherence eval's refactoring-mode tasks, reached from outside its package.

Bound here, through the adherence eval's own driver (`adherence_eval`): the console entry
`praxion-evals-adherence`, its `--dry-run` flag, the stand-in `claude` first on `PATH` that records
any launch instead of starting a paying session, and the dry run's printed lines (one planned
session each, its main-session prompt the argument after `-p`).

Unbound until a binding step ties them to the design (each raises `UnboundDriverError` with the
assumption's words): how a refactoring-mode task's end state is graded, how a paired run of the
move is dry-run, and how the two arms of that run are built.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tests.acceptance.drivers import adherence_eval
from tests.acceptance.drivers.adherence_eval import PlannedSession, RunRequest
from tests.acceptance.drivers.refactoring_delivery import unbound

# The refactoring skill's verification checklist, per role, as the specification states it.
CHECKLIST = {
    "implementer": (
        "the tests still pass",
        "behaviour is unchanged",
        "every call site is re-wired",
        "no dead code remains",
        "no transitional shim remains",
    ),
    "test-engineer": (
        "characterization tests exist before any structural change",
        "characterization tests pin behaviour through the public surface",
    ),
}

ArmKind = Literal["preloaded", "delivered"]


@dataclass(frozen=True)
class DryRun:
    sessions: tuple[PlannedSession, ...]
    launches: int  # sessions the stand-in `claude` saw start
    exit_code: int
    stderr: str


def dry_run(role: str, workspace: Path) -> DryRun:
    """Dry-run the adherence eval for `role` in its `full` arm, as an operator would."""
    fake = adherence_eval.install_fake_claude(workspace)
    request = RunRequest(
        roles=(role,),
        arms=("full",),
        checkout=adherence_eval.checkout_under_test(workspace),
        output=workspace / "results" / "adherence.json",
        dry_run=True,
    )
    result = adherence_eval.run_adherence_eval(request, fake.bin_dir)
    sessions = adherence_eval.planned_sessions(result.stdout) if result.exit_code == 0 else []
    return DryRun(tuple(sessions), len(fake.launches()), result.exit_code, result.stderr)


@dataclass(frozen=True)
class Grade:
    passed: bool


def grade_refactoring_task(
    role: str, workspace: Path, *, broken: str | None, account: str
) -> Grade:
    unbound(
        "One refactoring-mode task of the role is graded from the end state a recorded session "
        "left behind: the task's clean end state, or that end state with exactly the one "
        "checklist item named by `broken` violated; the session's final message is `account`, "
        "which the grade does not take as evidence"
    )


@dataclass(frozen=True)
class PairedSession:
    arm: ArmKind
    task_id: str
    prompt: str


@dataclass(frozen=True)
class PairedDryRun:
    sessions: tuple[PairedSession, ...]
    launches: int


def dry_run_paired_move(role: str, workspace: Path) -> PairedDryRun:
    unbound(
        "A paired run of the move for the role is dry-run through the adherence eval's entry with "
        "its dry-run flag: it names each session it would launch with its arm (the role "
        "preloading the skill as today, or the role after the move receiving it by marked "
        "delivery), its task and its prompt, and launches none"
    )


def build_paired_move_arms(role: str, workspace: Path) -> dict[ArmKind, Path]:
    unbound(
        "The paired run builds one plugin installation per arm: in the preloaded arm the role's "
        "definition preloads the skill as today; in the delivered arm the move is applied"
    )
