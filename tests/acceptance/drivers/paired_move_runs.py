"""Driver for a paired run of the refactoring move, run to its end with every session a stand-in.

A scenario runs the paired run the way an operator does, through the adherence eval's console
entry, started inside a committed checkout of the plugin, with `paired_move_stand_in` first on
`PATH` answering every launch. The stand-in crosses each spawn's hook boundary for real against
the arm copy the session was handed, so what reaches the role is whatever that copy delivers.

Bound here, because the specification, the base commit or a bound driver fixes them:
- the console entry and the options it has at the base (`--role`, `--arm`, `--seed`,
  `--no-judge`, `--max-total-usd`, `--fixture-pages-base-url`, `--dry-run`, `--output`,
  `--continue RUN`, `--close RUN --reason TEXT`, `--calibration`, `--calibration-run RUN`,
  `--report FILE`), reached as `adherence_runs` reaches them;
- the paired run's own options and arm names as the paired dry run binds them
  (`refactoring_mode_eval`): `--axis refactoring-delivery`, `--arm preloaded`, `--arm delivered`;
  the same command without `--dry-run` runs the paired run;
- the committed task data of each role's refactoring pool (`refactoring_mode_eval`);
- the checkout: a committed copy of the plugin (`refactoring_delivery.new_installation`), every
  role put back on trial as `adherence_runs.new_checkout` does, and the canary that removes the
  delivery from it (`refactoring_delivery.remove_delivery`);
- where results land and how the run names the file it wrote (`adherence_runs`), and the report
  (`adherence_scoring.render`), the earlier-runs listing (`adherence_results_wire.earlier_runs`).

Unbound until a binding step ties them to the designed results file and report (each raises
`UnboundDriverError` with the assumption's words): `session_records`, `check_comparisons` and
`unshown_arm_reason`.
"""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers import adherence_eval, adherence_runs, adherence_scoring
from tests.acceptance.drivers import paired_move_stand_in as stand_in
from tests.acceptance.drivers import refactoring_delivery as rd
from tests.acceptance.drivers import refactoring_mode_eval as rme
from tests.acceptance.drivers.kernel_sandbox import UnboundDriverError
from tests.acceptance.drivers.paired_move_stand_in import Ending, Launch, Script

AXIS = rme.AXIS
ARMS = rme.ARM_KINDS  # ("preloaded", "delivered"): before the move, after it
CHECKLIST = rme.CHECKLIST


def unbound(assumption: str) -> UnboundDriverError:
    return UnboundDriverError(f"driver unbound: {assumption}")


# -- The checkout a paired run measures ----------------------------------------------------------


def new_checkout(workspace: Path) -> Path:
    """A committed copy of the plugin, every switched role put back on trial."""
    root = rd.new_installation(workspace / "checkout").root
    for definition in sorted((root / "agents").glob("*.md")):
        text = definition.read_text(encoding="utf-8")
        definition.write_text(
            adherence_runs.OMIT_FLAG_LINE.sub("", text, count=1), encoding="utf-8"
        )
    rme._commit_all(root, "a checkout of the plugin")
    return root


def without_the_delivery(checkout: Path) -> None:
    """The canary, committed: the checkout keeps every other spawn-time delivery."""
    rd.remove_delivery(rd.Installation(checkout))
    adherence_eval._git(checkout, "add", "-A")
    adherence_eval._git(checkout, "commit", "-q", "-m", "remove the refactoring skill's delivery")


def templates(role: str) -> dict[str, Path]:
    return {template.name: template for template in rme.refactoring_templates(role)}


def grading_material(role: str, template: str) -> set[str]:
    """Digests of the files only a template's end states hold: what its grade is decided by."""
    root = templates(role)[template]
    start = set(stand_in.tree_digests(root / "start").values())
    ends = set(stand_in.tree_digests(root / "end_states").values())
    return ends - start


def results_snapshot(checkout: Path) -> dict[str, str]:
    directory = adherence_runs.results_dir(checkout)
    files = sorted(directory.glob("*")) if directory.is_dir() else []
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}


# -- Running it ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class PairedRun:
    exit_code: int
    stdout: str
    stderr: str
    results_path: Path
    launches: tuple[Launch, ...]  # every session the run started, in launch order

    def proofs(self, arm: str) -> list[Launch]:
        return [launch for launch in self.launches if launch.proof and launch.arm == arm]

    def tasks(self, arm: str) -> list[Launch]:
        return [launch for launch in self.launches if not launch.proof and launch.arm == arm]

    @property
    def printed(self) -> str:
        return self.stdout + self.stderr


def _plan_options(checkout: Path, role: str, arms: Sequence[str]) -> list[str]:
    args = [str(checkout), "--role", role, "--axis", AXIS, "--seed", str(adherence_eval.SEED)]
    args.append("--no-judge")
    for arm in arms:
        args += ["--arm", arm]
    return args


def _run_options(checkout: Path, role: str, arms: Sequence[str]) -> list[str]:
    return [
        *_plan_options(checkout, role, arms),
        *("--max-total-usd", str(adherence_runs.NO_SPEND_CAP_USD)),
        *("--fixture-pages-base-url", adherence_runs.UNREACHABLE_PAGES),
    ]


def planned_tasks(workspace: Path, checkout: Path, role: str) -> tuple[str, ...]:
    """The distinct tasks the paired run's dry run plans for `role`, in planned order.

    A dry run that fails plans nothing, so a scenario reads the failure as an empty plan and
    states it; nothing here raises during a fixture.
    """
    root = adherence_runs._fresh_directory(workspace, "paired-dry-run")
    tripwire = adherence_eval.install_tripwire(root)
    output = ["--output", str(root / "dry" / "adherence.json"), "--dry-run"]
    done = adherence_runs._console(
        checkout, tripwire.bin_dir, [*_plan_options(checkout, role, ARMS), *output]
    )
    if done.returncode != 0 or tripwire.starts():
        return ()
    sessions = adherence_eval.planned_sessions(done.stdout)
    return tuple(dict.fromkeys(s.task_id for s in sessions))


def run_paired(
    workspace: Path,
    checkout: Path,
    role: str,
    script: Script | None = None,
    *,
    arms: Sequence[str] = ARMS,
    extra_args: Sequence[str] = (),
) -> PairedRun:
    """The paired run of the move for `role`, as the operator starts it, every session a stand-in."""
    root = adherence_runs._fresh_directory(workspace, "paired-stand-in")
    claude = stand_in.install(
        root / "claude",
        version=adherence_eval.FAKE_CLAUDE_VERSION,
        role=role,
        templates=templates(role),
        script=script or Script(),
    )
    directory = adherence_runs.results_dir(checkout)
    before = set(directory.glob("*.json")) if directory.is_dir() else set()
    args = [*_run_options(checkout, role, arms), *extra_args]
    done = adherence_runs._console(checkout, claude.bin_dir, args)
    return PairedRun(
        exit_code=done.returncode,
        stdout=done.stdout,
        stderr=done.stderr,
        results_path=adherence_runs._results_path(checkout, before, done.stdout),
        launches=claude.launches(),
    )


def every_session_ends_in(text: str) -> Script:
    """Every task session in either arm ends in an error result carrying `text`."""
    return Script(default=Ending(error=text))


def stopped_paired_run(workspace: Path, checkout: Path, role: str) -> PairedRun:
    """A paired run asked to stop, as any run stops, on a streak of one error kind in both arms.

    Whether it stopped is the scenario's to assert (`assert_stopped`), never this fixture's.
    """
    return run_paired(workspace, checkout, role, every_session_ends_in(credit_exhausted()))


def assert_stopped(run: PairedRun) -> None:
    assert run.exit_code == adherence_runs.INCOMPLETE_EXIT, (
        f"the paired run did not stop: exit {run.exit_code}\n{run.printed[-2000:]}"
    )
    assert run.results_path.is_file(), f"the stopped run wrote no results: {run.printed[-2000:]}"


def credit_exhausted() -> str:
    return adherence_runs.credit_exhausted().result_text


def close(workspace: Path, checkout: Path, results_path: Path, reason: str) -> int:
    return adherence_runs.close_run(workspace, checkout, results_path, reason).exit_code


def report(workspace: Path, results_path: Path) -> adherence_scoring.Rendering:
    return adherence_scoring.render(results_path, workspace / "report")


def head(checkout: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=checkout, capture_output=True, text=True, check=True
    ).stdout.strip()


# -- Readings of what the run wrote (unbound) ----------------------------------------------------


@dataclass(frozen=True)
class SessionRecord:
    arm: str  # "preloaded" or "delivered"
    task_id: str
    refactoring_checks: Mapping[str, bool]  # checklist item, in the spec's wording -> passed
    ordinary_checks: Mapping[str, bool]  # the role's ordinary check -> passed
    skill_arrived_its_arm_way: bool  # by preload in `preloaded`, by delivery in `delivered`


def session_records(results_path: Path, role: str) -> tuple[SessionRecord, ...]:
    """Each task session the paired run scored for `role`, as its results file records it."""
    raise unbound(
        "the paired run's results file records, for each scored task session of a role, its arm, "
        "its task id, the outcome of each refactoring checklist item and of each ordinary check "
        "of the role, and whether the refactoring skill reached the role by its arm's own way"
    )


@dataclass(frozen=True)
class CheckComparison:
    before_passed: int  # tasks run in both arms that the arm before the move passed
    after_passed: int  # the same tasks the arm after the move passed
    tasks_in_both: int
    evidence_enough: bool  # the report says the run holds enough evidence to judge the check


def check_comparisons(report_text: str, role: str) -> Mapping[str, CheckComparison]:
    """Each check's comparison of the arm after the move with the arm before it, for `role`."""
    raise unbound(
        "the paired run's report states, for each role and each check (each refactoring "
        "checklist item in the spec's wording, each ordinary check by name), how many of the "
        "tasks run in both arms each arm passed, and whether the run holds enough evidence to "
        "judge the check"
    )


def unshown_arm_reason(report_text: str, role: str, arm: str) -> str | None:
    """Why the report says `arm` could not be shown to receive the skill its own way, if it says so."""
    raise unbound(
        "the paired run's report names an arm whose marked spawn could not be shown to hold the "
        "refactoring skill exactly once by its own way, and says why"
    )
