"""The gate phase of `record`: run the derived scope and the step's `Check:`, write one block,
and read the reconciler's verdict as if the request were recorded.

Both runs land in one `TEST_RESULTS.md` block that ends on the deciding line. An ordinary step's
block already written for the request is read back instead of run again, so a call cut off
part-way completes when run again. A goal step's is never read back: the scope and the check run
and the block is rewritten, whoever wrote the earlier one, because a worker that can write the task
directory could forge a green block. Running again is safe for a goal iteration, whose effects are
idempotent without the reuse: an applied commit is recognised by its trailer and an applied unkept
judgement by its patch. A red run fails the attempt whatever the check's expectations say: the
check grammar has no error key, so a run red only by errors would otherwise meet it.

The reconciler reads a step's latest block for its `Mutation:` line, so the block carries the
step's latest earlier one, set before the `Result:` lines to keep the deciding line last. A derived
scope the resolver answers `nothing-to-run` (documents, say) contributes no run: the `Check:`
decides, and a step with no check reads as unverifiable, which is red.
"""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from _loop_fields import Check, GoalBudget
from _plan_steps import PlanStep
from _step_loop_files import gate_heading, write_gate_block
from _step_loop_gate import (
    GateRun,
    GoalTargets,
    Ownership,
    PendingRule,
    classify_run,
    gate_result_lines,
    parse_pytest_summary,
    render_result_line,
)
from _step_loop_io import (
    CommandRun,
    ScopeUnresolved,
    paths_differing_from_head,
    run_check,
    run_derived_scope,
)
from _step_loop_state import VERIFIED, LoopInputs, bare_id, is_done, series_states
from _step_schema import (
    GREEN,
    Counts,
    NoRun,
    parse_result_line,
    render_mutation_line,
    split_step_blocks,
    step_mutation_reading,
)
from reconcile_pipeline_state import reconcile

RESULTS_FILE = "TEST_RESULTS.md"
RED_RUN_VERDICT = "mismatch"  # the reconciler's word for evidence that contradicts the claim
NOTHING_RAN = "the step declares no check and none of its declared files changed"
NOTHING_SELECTED = "the step declares no check and the test scope selects no test"
NOTHING_TO_RUN = "nothing-to-run"  # the resolver's decision when no test is needed
SCOPE_COMMAND = "resolve_test_scope.py"
_HEADING_PREFIX, _RESULT_PREFIX = "## ", "Result:"


class TaskView(Protocol):
    """What `record` reads of the task: where it lives and the loop's inputs, by value."""

    @property
    def slug(self) -> str: ...
    @property
    def repo(self) -> Path: ...
    @property
    def work(self) -> Path: ...
    @property
    def dir(self) -> Path: ...
    @property
    def base_ref(self) -> str: ...
    @property
    def inputs(self) -> LoopInputs: ...


@dataclass(frozen=True)
class Gate:
    """The gate block's body, deciding `Result:` line last, and whether any run was red."""

    body: tuple[str, ...]
    red: bool

    @property
    def deciding(self) -> str:
        return self.body[-1]


def run_gate(task: TaskView, step: PlanStep, request: str) -> Gate:
    """The request's gate: an ordinary step's is read back from its block when written; else
    (and always for a goal step) the runs are made and the block written now."""
    results = task.dir / RESULTS_FILE
    goal = isinstance(step.bound, GoalBudget)
    written = None if goal else recorded_gate(results, gate_heading(step.id, request))
    if written is not None:
        return written
    states = series_states(task.inputs)
    done = frozenset(step_id for step_id, state in states.items() if is_done(state))
    ownership = Ownership(step.id, {s.id: s.read_only for s in task.inputs.steps}, done)
    changed = paths_differing_from_head(task.repo, step.files) if step.files else ()
    if goal:
        scope, check = goal_runs(task.repo, step, changed)
    else:
        scope = scope_run(task.repo, changed, ownership) if changed else None
        check = check_run(task.repo, step, ownership)
    runs = tuple(run for run in (scope, check) if run is not None)
    if not runs:
        runs = (GateRun("", NoRun(NOTHING_SELECTED if changed else NOTHING_RAN)),)
    if check is None:
        lines = tuple(render_result_line(run) for run in runs)
    else:
        lines = gate_result_lines(scope, check)
    commands = tuple(f"Command: `{run.command}`" for run in runs if run.command)
    body = (*commands, *carried_mutation(results, step.id), *lines)
    write_gate_block(results, step.id, request, body)
    return Gate(body, any(run.red for run in runs))


def goal_runs(
    repo: Path, step: PlanStep, changed: Sequence[str]
) -> tuple[GateRun | None, GateRun | None]:
    """A goal step's derived-scope run and check run, the check run first.

    The check's own failing nodes are the goal's targets: both runs pend them and nothing
    else, so a failure the goal did not ask to fix keeps the iteration red. The check's
    run decides the targets, which is why it cannot wait behind the scope's.
    """
    targets = GoalTargets(frozenset())
    check: GateRun | None
    if isinstance(step.check, Check):
        ran = run_check(repo, step.check.command)
        summary = None if ran.problem is not None else parse_pytest_summary(ran.output)
        targets = GoalTargets(frozenset(summary.failed_ids if summary else ()))
        check = classified(ran, targets, step.check.command)
    else:
        check = check_run(repo, step, targets)
    return (scope_run(repo, changed, targets) if changed else None), check


def scope_run(repo: Path, changed: Sequence[str], rule: PendingRule) -> GateRun | None:
    """The derived scope of `changed`, every invocation it lists merged into one run; None when
    the resolver decides no test is needed (a run that failed is red, a run never asked is not)."""
    resolved = run_derived_scope(repo, changed)
    if isinstance(resolved, ScopeUnresolved):
        why = resolved.resolver.problem or f"exit {resolved.resolver.returncode}"
        return GateRun(SCOPE_COMMAND, NoRun(f"the test scope did not resolve ({why})"))
    if not resolved.runs:
        if resolved.decision == NOTHING_TO_RUN:
            return None
        return GateRun(SCOPE_COMMAND, NoRun("the test scope selects no test"))
    return merge_runs(tuple(classified(run, rule) for run in resolved.runs))


def carried_mutation(results: Path, step_id: str) -> tuple[str, ...]:
    """The step's latest `Mutation:` line, to repeat in the gate block (empty when it has none).

    A later block of the step supersedes an earlier one in the reconciler's reading, so the
    driver's block repeats the implementer's line rather than hide it.
    """
    text = results.read_text(encoding="utf-8") if results.is_file() else ""
    reading = step_mutation_reading(step_id, split_step_blocks(text))
    return () if reading is None else (render_mutation_line(reading),)


def check_run(repo: Path, step: PlanStep, rule: PendingRule) -> GateRun | None:
    if step.check is None:
        return None
    if not isinstance(step.check, Check):
        return GateRun("Check:", NoRun(f"the Check: line cannot be read: {step.check.reason}"))
    return classified(run_check(repo, step.check.command), rule, step.check.command)


def classified(run: CommandRun, rule: PendingRule, command: str = "") -> GateRun:
    """One finished command's run as the gate reads it; one that never exited is no run."""
    shown = command or shlex.join(run.argv)
    if run.problem is not None:
        return GateRun(shown, NoRun(f"the run {run.problem}"))
    return classify_run(shown, run.output, rule)


def merge_runs(runs: Sequence[GateRun]) -> GateRun:
    """One run from several: counts summed and nodes joined, each run having been read on its
    own (one invocation's count line never applies to another's nodes); any no-run is no run."""
    command = " ; ".join(run.command for run in runs)
    absent = [run.counts.rationale for run in runs if isinstance(run.counts, NoRun)]
    if absent or not runs:
        return GateRun(command, NoRun("; ".join(absent) or "nothing ran"))
    counts = [cast(Counts, run.counts) for run in runs]
    total = Counts(
        passed=sum(c.passed for c in counts),
        failed=sum(c.failed for c in counts),
        skipped=sum(c.skipped for c in counts),
        errors=sum(c.errors for c in counts),
    )
    failed = tuple(node for run in runs for node in run.failed_ids)
    pending = tuple(dict.fromkeys(node for run in runs for node in run.pending_ids))
    return GateRun(command, total, failed, pending)


def recorded_gate(results: Path, heading: str) -> Gate | None:
    """The gate block already written for the request, read back, or None."""
    lines = results.read_text(encoding="utf-8").splitlines() if results.is_file() else []
    if heading not in lines:
        return None
    start = lines.index(heading) + 1
    end = next(
        (i for i in range(start, len(lines)) if lines[i].startswith(_HEADING_PREFIX)), len(lines)
    )
    body = tuple(line for line in lines[start:end] if line.strip())
    read = [parse_result_line(line) for line in body if line.startswith(_RESULT_PREFIX)]
    red = any(not (isinstance(one, Counts) and one.status == GREEN) for one in read)
    return Gate(body, red) if read and body[-1].startswith(_RESULT_PREFIX) else None


def read_verdict(task: TaskView, step_id: str, request: str, gate: Gate) -> dict[str, Any]:
    """The reconciler's verdict once the request is recorded; never verified on a red run."""
    verdicts = reconcile(
        task.slug,
        task.repo,
        task.base_ref,
        state_root=task.work,
        assume_recorded=frozenset({request}),
        include_untracked=True,
    )
    own = next((v for v in verdicts if bare_id(str(v["step"])) == step_id), None)
    verdict = {"verdict": "unknown", "decided_by": "none", **(own or {})}
    if gate.red and verdict["verdict"] == VERIFIED:
        verdict["verdict"] = RED_RUN_VERDICT
    return verdict


def add_refusal(task: TaskView, step_id: str, request: str, gate: Gate, failure: str) -> Gate:
    """The gate block with a last line saying no commit holds the work, and why."""
    line = render_result_line(GateRun("", NoRun(failure)))
    if gate.deciding == line:
        return gate
    body = (*gate.body, line)
    write_gate_block(task.dir / RESULTS_FILE, step_id, request, body)
    return Gate(body, True)
