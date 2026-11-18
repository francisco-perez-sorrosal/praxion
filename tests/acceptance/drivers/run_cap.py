"""Driver for the adherence eval's dry run, read for what it says a run's cap must be.

A dry run is started the way an operator starts one, through the console entry, with a `claude`
tripwire first on `PATH`, so a dry run that launched anything is caught. The ordinary comparison
runs from this repository (its default checkout) on two tasks; the paired axis runs from a
committed copy of the plugin before the move (`paired_move_runs.new_checkout`).

Bound here, because the specification or the base commit fixes them: `--dry-run`,
`--session-budget-usd`, `--max-total-usd`, `--axis refactoring-delivery`, the per-session lines on
standard output (one JSON object each, read by `adherence_eval.planned_sessions`), and the
per-role task counts on standard error. What the statement says is read from standard error, the
stream the task counts already use, as numbers and words, never as a fixed sentence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers import adherence_eval, adherence_runs
from tests.acceptance.drivers import paired_move_runs as paired

REPO_ROOT = adherence_eval.REPO_ROOT
ORDINARY_ROLE = "researcher"
PAIRED_ROLE = "implementer"
ORDINARY_TASKS = 2
BASE_SESSION_FIELDS = frozenset({"role", "arm", "task_id", "argv", "env_names"})
# Sessions a run may launch beyond its planned task sessions: at most one proof per arm and role.
EXTRA_SESSIONS_AT_MOST = 4
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


@dataclass(frozen=True)
class DryRun:
    exit_code: int
    stdout: str
    stderr: str
    launched: tuple[str, ...]

    def planned_lines(self) -> list[str]:
        return [line for line in self.stdout.splitlines() if line.strip()]

    def numbers_stated(self) -> list[float]:
        return [float(n) for n in _NUMBER.findall(self.stderr)]


def dry_run(workspace: Path, axis: str, *, budget: float, cap: float | None = None) -> DryRun:
    root = adherence_runs._fresh_directory(workspace, f"dry-run-{axis}")
    tripwire = adherence_eval.install_tripwire(root)
    if axis == "ordinary":
        checkout = REPO_ROOT
        plan = [str(checkout), "--role", ORDINARY_ROLE, "--seed", str(adherence_eval.SEED)]
        plan += ["--no-judge", "--max-tasks", str(ORDINARY_TASKS)]
    else:
        checkout = paired.new_checkout(root)
        plan = paired._plan_options(checkout, PAIRED_ROLE, paired.ARMS)
    options = [*plan, "--dry-run", "--output", str(root / "dry" / "adherence.json")]
    options += ["--session-budget-usd", f"{budget:g}"]
    if cap is not None:
        options += ["--max-total-usd", f"{cap:g}"]
    done = adherence_runs._console(checkout, tripwire.bin_dir, options)
    return DryRun(done.returncode, done.stdout, done.stderr, tuple(tripwire.starts()))


def _stated(numbers: list[float], value: float) -> bool:
    return any(abs(n - value) < 0.005 for n in numbers)


def smallest_cap_stated(run: DryRun, budget: float) -> float | None:
    """The smallest admitting cap the dry run states: a session count it names times the budget."""
    planned = len(run.planned_lines())
    numbers = run.numbers_stated()
    for sessions in range(planned, planned + EXTRA_SESSIONS_AT_MOST + 1):
        if _stated(numbers, sessions) and _stated(numbers, sessions * budget):
            return sessions * budget
    return None
