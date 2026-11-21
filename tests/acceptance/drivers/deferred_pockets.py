"""Driver for pockets a step's gate leaves to the loop's checkpoint, on top of the step-loop driver.

A scenario names which pockets the checkout has, which of them a step's change widens, and
whether a pocket's whole suite passes, fails, hangs or holds until it is released. This
driver builds on `step_loop` (the checkout, the plan, the Agent tool's double, the command)
and `pocket_gate` (a pocket's runner configuration, its time bound, a call cut off). It adds:

- a whole-suite test in each pocket that appends its pocket's label to a log outside the
  checkout every time it runs, so a scenario counts whole-suite runs from what ran, never
  from the records the command writes about them;
- the two edits that widen a pocket while leaving it runnable, as the test-scope command
  reads them at the base commit: a change to a pocket's own runner configuration widens
  that pocket alone (`pocket-config-changed`), and a new source module no test reaches
  widens every pocket (`unmapped-path`);
- `next` called again while it answers `gate-running`, within a deadline;
- the blocks of `TEST_RESULTS.md` a call added.

Bound here, because the specification or the base commit fixes them:

- a block's line for a pocket the gate left unrun opens with `Deferred:` and names the
  pocket by its root as the test-scope command names it (`bench`; the root pocket is `.`);
- a call whose runs are still inside their bound prints the error code `gate-running`;
- how long one call waits for its runs is set through `GATE_WAIT_VARIABLE`, the gate's own
  wait at the base commit; a checkpoint run is taken to honour the same wait.

Not yet bound (each raises until a binding step binds it to the designed interface):

- where `status --json` lists the pockets waiting for the checkpoint and their steps;
- where a stop lists the pockets waiting for the checkpoint and their steps.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.acceptance.drivers import step_loop
from tests.acceptance.drivers.pocket_gate import pocket_config
from tests.acceptance.drivers.step_loop import (
    Envelope,
    LoopTask,
    Step,
    Work,
    build_loop,
    git,
    next_action,
    reconciler_verdict,
)

GATE_WAIT_VARIABLE = "PRAXION_STEP_LOOP_GATE_WAIT_SECONDS"
RUN_LOG = "whole-suite-runs.log"  # beside the checkout, never inside it
SETTLE_DEADLINE_SECONDS = 600
SETTLE_PAUSE_SECONDS = 0.5
HOLD_LIMIT_SECONDS = 300

# The root pocket's runner configuration: the step-loop driver's own, with its tests kept
# under `tests/` so the root pocket's whole suite never collects another pocket's tests.
ROOT_CONFIG = (
    '[project]\nname = "loop-widget"\nversion = "0.0.0"\n\n'
    '[tool.pytest.ini_options]\npythonpath = ["."]\ntestpaths = ["tests"]\n'
)


# -- The pockets a checkout has ---------------------------------------------------------------


@dataclass(frozen=True)
class Pocket:
    """A pocket: its root as the test-scope command names it, and a label for its whole suite."""

    root: str  # "." for the root pocket
    label: str  # an identifier: the whole-suite test's name and its log lines carry it

    @property
    def config(self) -> str:
        return "pyproject.toml" if self.root == "." else f"{self.root}/pyproject.toml"

    @property
    def config_text(self) -> str:
        return ROOT_CONFIG if self.root == "." else pocket_config(f"{self.label}-suite")

    @property
    def suite_test(self) -> str:
        directory = "tests" if self.root == "." else f"{self.root}/tests"
        return f"{directory}/test_{self.label}_whole_suite.py"

    @property
    def suite_test_name(self) -> str:
        return f"test_{self.label}_whole_suite_takes_part"


ROOT = Pocket(".", "root")
BENCH = Pocket("bench", "bench")

OUTCOME_BODIES = {
    "passes": "    assert True\n",
    "fails": "    assert 'left red' == 'for the checkpoint'\n",
    "hangs": "    time.sleep(600)\n",
}


def whole_suite_test(pocket: Pocket, log: Path, *, outcome: str, hold: Path | None) -> str:
    """The pocket's whole-suite test: it logs its run, waits while `hold` exists, then ends."""
    return (
        "import time\nfrom pathlib import Path\n\n"
        f"LOG = Path({str(log)!r})\n"
        f"HOLD = {None if hold is None else repr(str(hold))}\n\n\n"
        f"def {pocket.suite_test_name}():\n"
        f"    with LOG.open('a') as out:\n        out.write({pocket.label!r} + '\\n')\n"
        "    if HOLD is not None:\n"
        f"        stop_at = time.monotonic() + {HOLD_LIMIT_SECONDS}\n"
        "        while Path(HOLD).exists() and time.monotonic() < stop_at:\n"
        "            time.sleep(0.2)\n" + OUTCOME_BODIES[outcome]
    )


def build_pocket_loop(
    workspace: Path,
    *steps: Step,
    pockets: tuple[Pocket, ...] = (ROOT, BENCH),
    outcomes: dict[str, str] | None = None,
    holds: dict[str, Path] | None = None,
    base_files: dict[str, str] | None = None,
) -> LoopTask:
    """A step-loop checkout whose base commit holds `pockets`, each with its whole-suite test.

    `outcomes` maps a pocket's label to how its whole-suite test ends (`passes` by default,
    `fails` or `hangs`); `holds` maps a label to a file whose existence makes the test wait.
    """
    log = run_log_path(workspace)
    files: dict[str, str] = {ROOT.config: ROOT.config_text}
    for pocket in pockets:
        files[pocket.config] = pocket.config_text
        files[pocket.suite_test] = whole_suite_test(
            pocket,
            log,
            outcome=(outcomes or {}).get(pocket.label, "passes"),
            hold=(holds or {}).get(pocket.label),
        )
    return build_loop(workspace, *steps, base_files={**files, **(base_files or {})})


# -- What a step changes ----------------------------------------------------------------------


def config_edit(pocket: Pocket, note: str) -> tuple[str, str]:
    """An edit of the pocket's own runner configuration that leaves it runnable."""
    return pocket.config, pocket.config_text + f"# {note}\n"


def unreached_module(step_id: str) -> str:
    return f"src/unreached_by_any_test_{step_id}.py"


def widening_step(step_id: str, *pockets: Pocket, **step_fields: Any) -> Step:
    """A step whose declared files include each named pocket's runner configuration."""
    return Step(step_id, more_files=tuple(p.config for p in pockets), **step_fields)


def widening_work(step_id: str, *pockets: Pocket, **work_fields: Any) -> Work:
    """The step's own pair of files, plus an edit of each named pocket's configuration."""
    edits = tuple(config_edit(p, f"settled by step {step_id}") for p in pockets)
    return Work(other_edits=edits, **work_fields)


def everywhere_step(step_id: str, **step_fields: Any) -> Step:
    """A step whose declared files include a source module no test reaches."""
    return Step(step_id, more_files=(unreached_module(step_id),), **step_fields)


def everywhere_work(step_id: str, **work_fields: Any) -> Work:
    """The step's own pair of files, plus a new source module no test reaches."""
    return Work(other_edits=((unreached_module(step_id), "UNREACHED = True\n"),), **work_fields)


# -- What ran ---------------------------------------------------------------------------------


def run_log_path(workspace: Path) -> Path:
    return workspace / RUN_LOG


def whole_suite_runs(task: LoopTask, pocket: Pocket) -> int:
    """How many times the pocket's whole-suite test has run since the checkout was built."""
    log = task.root.parent / RUN_LOG
    if not log.exists():
        return 0
    return log.read_text(encoding="utf-8").splitlines().count(pocket.label)


def wait_for_whole_suite_run(task: LoopTask, pocket: Pocket, *, deadline_seconds: float) -> None:
    stop_at = time.monotonic() + deadline_seconds
    while time.monotonic() < stop_at:
        if whole_suite_runs(task, pocket) >= 1:
            return
        time.sleep(0.2)
    raise AssertionError(f"the {pocket.root} whole suite did not start in {deadline_seconds} s")


# -- Calling the command ----------------------------------------------------------------------


def is_gate_running(envelope: Envelope) -> bool:
    return envelope.outcome == "error" and (envelope.error or {}).get("code") == "gate-running"


def next_until_settled(
    task: LoopTask, *, deadline_seconds: float = SETTLE_DEADLINE_SECONDS
) -> Envelope:
    """`next`, made again while it answers `gate-running`, as the orchestrator is told to."""
    stop_at = time.monotonic() + deadline_seconds
    while True:
        asked = next_action(task)
        if not is_gate_running(asked):
            return asked
        if time.monotonic() > stop_at:
            raise AssertionError(f"`next` still answered gate-running after {deadline_seconds} s")
        time.sleep(SETTLE_PAUSE_SECONDS)


def limit_call_wait(task: LoopTask, seconds: int) -> None:
    """Make one call wait at most `seconds` for its runs before it answers."""
    task.env[GATE_WAIT_VARIABLE] = str(seconds)


def start_next(task: LoopTask) -> subprocess.Popen[str]:
    """`next` started in a session of its own, so the whole call can be cut off."""
    return subprocess.Popen(
        [
            sys.executable,
            str(step_loop.STEP_LOOP),
            "next",
            task.slug,
            "--repo-root",
            str(task.root),
            "--base-ref",
            task.base,
        ],
        cwd=task.root,
        env=task.env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )


def commit_by_hand(task: LoopTask, rel: str, text: str) -> None:
    """A person's own fix: edit one file and commit it outside the loop."""
    (task.root / rel).write_text(text, encoding="utf-8")
    git(task, "add", "--", rel)
    git(task, "commit", "-qm", "fix by hand")


# -- What the command wrote -------------------------------------------------------------------


def results_text(task: LoopTask) -> str:
    path = task.task_dir / "TEST_RESULTS.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def blocks(text: str) -> list[str]:
    """Every level-2 block of a results file, heading included."""
    return [b for b in re.split(r"(?m)^(?=## )", text) if b.startswith("## ")]


def blocks_added(before: str, after: str) -> list[str]:
    earlier = blocks(before)
    return [b for b in blocks(after) if b not in earlier]


def deferred_lines(block: str) -> list[str]:
    return [line for line in block.splitlines() if line.startswith("Deferred:")]


def lines_naming(block: str, prefix: str, pocket: Pocket) -> list[str]:
    """The block's lines opening with `prefix` that name the pocket by its root."""
    pattern = re.compile(rf"(?<![\w/.-]){re.escape(pocket.root)}(?![\w-])")
    return [line for line in block.splitlines() if line.startswith(prefix) and pattern.search(line)]


def names_pocket(text: str, pocket: Pocket) -> bool:
    """Whether `text` (plain, or a JSON dump with escaped line breaks) names the pocket's root."""
    return lines_naming(text.replace("\\n", "\n"), "", pocket) != []


def blocks_naming(candidates: list[str], pocket: Pocket) -> list[str]:
    """The blocks among `candidates` with a line that names the pocket by its root."""
    return [b for b in candidates if lines_naming(b, "", pocket)]


def lines_after_the_first_result(block: str, prefix: str) -> list[str]:
    """The block's lines opening with `prefix` that come after its first `Result:` line."""
    lines = block.splitlines()
    results = [i for i, line in enumerate(lines) if line.startswith("Result:")]
    start = results[0] if results else len(lines)
    return [line for line in lines[start:] if line.startswith(prefix)]


def last_line(block: str) -> str:
    return [line for line in block.splitlines() if line.strip()][-1]


def without_deferred_lines(text: str) -> str:
    return "".join(
        line for line in text.splitlines(keepends=True) if not line.startswith("Deferred:")
    )


def checklist(task: LoopTask) -> list[str]:
    """WIP.md's checklist lines, ticks included."""
    return [
        line
        for line in task.wip_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("- [")
    ]


def verdicts(task: LoopTask) -> dict[str, tuple[Any, Any]]:
    """Each plan step's reconciler verdict and what decided it."""
    read = {s.id: reconciler_verdict(task, s.id) for s in task.steps}
    return {step: (v.get("verdict"), v.get("decided_by")) for step, v in read.items()}


# -- Not yet bound ----------------------------------------------------------------------------


def waiting_in_status(task: LoopTask) -> dict[str, list[str]]:
    """Each pocket `status --json` lists as waiting, mapped to its waiting steps' ids, sorted."""
    raise NotImplementedError(
        "status in its JSON form does not yet list each pocket that waits for the checkpoint "
        "with the steps whose committed changes reached it since its last green run"
    )


def waiting_named_by_stop(envelope: Envelope) -> dict[str, list[str]]:
    """Each pocket a stop names as waiting, mapped to its waiting steps' ids, sorted."""
    raise NotImplementedError(
        "a stop does not yet list each pocket that waits for the checkpoint with the steps "
        f"whose committed changes reached it since its last green run: {envelope.stop}"
    )
