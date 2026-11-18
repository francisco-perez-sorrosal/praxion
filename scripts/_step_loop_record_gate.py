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

import math
import os
import re
import shlex
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol, cast

from _loop_fields import Check, GoalBudget
from _plan_steps import PlanStep
from _step_loop_files import gate_heading, write_atomic, write_gate_block
from _step_loop_gate import (
    GateRun,
    GoalTargets,
    Ownership,
    PendingRule,
    classify_run,
    collected,
    gate_result_lines,
    parse_pytest_summary,
    render_result_line,
)
from _step_loop_io import (
    CommandRun,
    PocketScope,
    ScopeRuns,
    ScopeUnresolved,
    check_pocket,
    head_sha,
    paths_differing_from_head,
    repository_pocket,
    run_bounded_check,
    run_check,
    run_derived_scope,
)
from _step_loop_ownership import repository_form
from _step_loop_pocket_runs import (
    CutOff,
    Finished,
    NotStarted,
    Observed,
    StillRunning,
    failed_node_ids,
    files_with_outcomes,
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
GATE_DIRECTORY = "gate"  # under the task directory: one subdirectory of run logs per request
COMMAND_FILE = "command.txt"  # beside a request's run logs: the check's whole command
COMMAND_LINE_MAX_CHARS = 200  # keeps a green block inside its ceiling whatever the check's length
COMMAND_LINE_OPENING, COMMAND_LINE_CLOSING = "Command: `", "`"
GATE_WAIT_VARIABLE = "PRAXION_STEP_LOOP_GATE_WAIT_SECONDS"
DEFAULT_GATE_WAIT_SECONDS = 480.0  # under the skill's 600 s ceiling on one `record` call
FAILED_LINES_SHOWN = 20
DERIVED_FILES_SHOWN = 3  # declared files the `Derived from:` line names, the rest only counted
DERIVED_NAMES_MAX_CHARS = 200  # keeps a green block inside its ceiling whatever the path lengths
SHORT_SHA_LENGTH = 7
CHECK_OUTPUT = "the Check: run's output"  # where a check's failures beyond the list were shown
_MORE_FAILURES = "…"
COLLECT_ONLY = "--collect-only"
COLLECTION_LINES_SHOWN = 5  # last lines of a refused collection that a stop's evidence quotes
# A collection takes seconds; a hung one is doubt, not a stop. The bound is charged after the gate's
# wait inside one call, so the two together stay well under the 600 s a caller's shell allows.
COLLECTION_TIMEOUT_SECONDS = 30.0
_SHELL_OPERATORS = frozenset({"|", "&&", "||", ";"})
_QUIETEST_RE = re.compile(r"^-q{2,}$")  # `-qq` makes pytest print no summary at all
_RUNNERS = frozenset({"uv", "poetry", "pdm", "pixi", "hatch", "rye"})
_RUNNER_VALUE_OPTIONS = frozenset(  # the options of `uv run` that take the next word as a value
    {"--with", "-w", "--with-editable", "--project", "--directory", "--python", "-p", "--package"}
)
_INTERPRETER_PREFIXES = ("python", "pypy")
_ENV_ASSIGNMENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
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


class GateStillRunningError(Exception):
    """The scope has a run still inside its bound after the call's budget. Nothing was written:
    the same `record` run again attaches to it."""

    def __init__(self, pockets: tuple[str, ...]) -> None:
        super().__init__(f"still running: {', '.join(pockets)}")
        self.pockets = pockets


def gate_wait_seconds() -> float:
    """The most one `record` call waits for the scope's runs, from the environment (a value that
    is not a finite number: the default, so no setting can make one call wait without end)."""
    raw = os.environ.get(GATE_WAIT_VARIABLE, "").strip()
    try:
        seconds = float(raw) if raw else DEFAULT_GATE_WAIT_SECONDS
    except ValueError:
        return DEFAULT_GATE_WAIT_SECONDS
    return max(seconds, 0.0) if math.isfinite(seconds) else DEFAULT_GATE_WAIT_SECONDS


@dataclass(frozen=True)
class ScopeReading:
    """What the derived scope showed, as the block carries it.

    `deciding` is the scope's own verdict: the counts of every run when all finished, otherwise a
    red no-run saying which did not. `kept` holds the counts of the runs that did finish beside
    such a verdict. `scopes` are the `Scope:` lines of the pockets that finished, `cut_offs` the
    runs that outlived their bound and `failures` the nodes that failed, as the repository names
    them, with `where` their runs' logs are kept.
    """

    deciding: GateRun
    kept: tuple[GateRun, ...] = ()
    cut_offs: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()
    where: str = ""
    scopes: tuple[str, ...] = ()

    @property
    def notes(self) -> tuple[str, ...]:
        """The `Cut off:` and `Failed:` lines."""
        return (*self.cut_offs, *failure_lines(self.failures, self.where))


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
    run_dir = task.dir / GATE_DIRECTORY / request
    give_up_at = time.time() + gate_wait_seconds()
    if goal:
        scope, check = goal_runs(task.repo, run_dir, step, changed, give_up_at)
    else:
        scope = scope_run(task.repo, run_dir, changed, ownership, give_up_at) if changed else None
        check = check_run(task.repo, run_dir, step, ownership, give_up_at)
    runs = tuple(run for run in (scope and scope.deciding, check) if run is not None)
    if not runs:
        runs = (GateRun("", NoRun(NOTHING_SELECTED if changed else NOTHING_RAN)),)
    if check is None:
        lines = tuple(render_result_line(run) for run in runs)
    else:
        lines = gate_result_lines(scope and scope.deciding, check)
    # The scope's runs are summarised, their argv being the first line of each log; the check's
    # own command is the plan's one and is named in full, in the block or in the file it points at.
    derived = (derived_from(task.repo, changed),) if scope else ()
    command = command_lines(task, run_dir, request, check)
    kept = tuple(finished_line(run) for run in (scope.kept if scope else ()))
    summary = (*(scope.scopes if scope else ()), *derived)
    body = (
        *summary,
        *command,
        *evidence_lines(scope, check),
        *carried_mutation(results, step.id),
        *kept,
        *lines,
    )
    write_gate_block(results, step.id, request, body)
    return Gate(body, any(run.red for run in runs))


def command_lines(
    task: TaskView, run_dir: Path, request: str, check: GateRun | None
) -> tuple[str, ...]:
    """The block's `Command:` line for the check. A command too long for the line is cut by fixed
    length to the ceiling, ending on a pointer to a file beside the run logs that holds it whole
    (one line per command, and the file is written before the block is)."""
    if not (check and check.command):
        return ()
    line = f"{COMMAND_LINE_OPENING}{check.command}{COMMAND_LINE_CLOSING}"
    if len(line) <= COMMAND_LINE_MAX_CHARS:
        return (line,)
    pointer = f".ai-work/{task.slug}/{GATE_DIRECTORY}/{request}/{COMMAND_FILE}"
    run_dir.mkdir(parents=True, exist_ok=True)
    write_atomic(run_dir / COMMAND_FILE, check.command + "\n")
    return (_cut_command_line(line, pointer),)


def _cut_command_line(line: str, pointer: str) -> str:
    """`line` cut to end on `pointer`; a pointer too long for the ceiling keeps its tail."""
    head, tail = " ... (whole command: ", f"){COMMAND_LINE_CLOSING}"
    room = COMMAND_LINE_MAX_CHARS - len(COMMAND_LINE_OPENING) - len(head) - len(tail)
    if len(pointer) > room:
        pointer = "…" + pointer[len(pointer) - room + 1 :]
    ending = f"{head}{pointer}{tail}"
    return line[: COMMAND_LINE_MAX_CHARS - len(ending)] + ending


def evidence_lines(scope: ScopeReading | None, check: GateRun | None) -> tuple[str, ...]:
    """The `Cut off:` lines and one bounded `Failed:` list for the scope's failures, then the
    check's: the next attempt's prompt reads one pointer to the failures the list has no room for."""
    cut_offs = scope.cut_offs if scope else ()
    failures = (*(scope.failures if scope else ()), *(check.failed_ids if check else ()))
    where = scope.where if scope and scope.where else CHECK_OUTPUT
    return (*cut_offs, *failure_lines(tuple(dict.fromkeys(failures)), where))


def finished_line(run: GateRun) -> str:
    """The counts of runs that finished beside one that did not, in a form that is no `Result:`
    line: the block keeps one deciding `Result:` line per run, and a red block stays red."""
    return render_result_line(run).replace(_RESULT_PREFIX, "Finished:", 1)


def derived_from(repo: Path, changed: Sequence[str]) -> str:
    """The line saying which declared files the scope was derived from, and against what: the
    first few by name, the rest counted."""
    names: list[str] = []
    for path in changed[:DERIVED_FILES_SHOWN]:
        if len(", ".join([*names, path])) > DERIVED_NAMES_MAX_CHARS:
            break
        names.append(path)
    unnamed = len(changed) - len(names)
    listed = ", ".join([*names, f"+{unnamed} more"] if unnamed else names)
    return (
        f"Derived from: {len(changed)} declared files ({listed}) "
        f"differing from {head_sha(repo)[:SHORT_SHA_LENGTH]}"
    )


def goal_runs(
    repo: Path, run_dir: Path, step: PlanStep, changed: Sequence[str], give_up_at: float
) -> tuple[ScopeReading | None, GateRun | None]:
    """A goal step's derived-scope run and check run, the check run first.

    The check's own failing nodes are the goal's targets: both runs pend them and nothing
    else, so a failure the goal did not ask to fix keeps the iteration red. The check's
    run decides the targets, which is why it cannot wait behind the scope's.
    """
    targets = GoalTargets(frozenset())
    check: GateRun | None
    if isinstance(step.check, Check):
        ran = bounded_check(repo, run_dir, step.check.command, give_up_at)
        summary = None if ran.problem is not None else parse_pytest_summary(ran.output)
        targets = GoalTargets(frozenset(summary.failed_ids if summary else ()))
        check = classified(ran, targets, step.check.command)
    else:
        check = check_run(repo, run_dir, step, targets, give_up_at)
    scope = scope_run(repo, run_dir, changed, targets, give_up_at) if changed else None
    return scope, check


def scope_run(
    repo: Path,
    run_dir: Path,
    changed: Sequence[str],
    rule: PendingRule,
    give_up_at: float | None = None,
) -> ScopeReading | None:
    """The derived scope of `changed`, every invocation it lists run and read; None when the
    resolver decides no test is needed (a run that failed is red, a run never asked is not).
    The runs are waited for until `give_up_at`, by default the call's gate wait from now."""
    deadline = time.time() + gate_wait_seconds() if give_up_at is None else give_up_at
    resolved = run_derived_scope(repo, changed, run_dir, os.environ, deadline)
    if isinstance(resolved, ScopeUnresolved):
        why = resolved.resolver.problem or f"exit {resolved.resolver.returncode}"
        return ScopeReading(
            GateRun(SCOPE_COMMAND, NoRun(f"the test scope did not resolve ({why})"))
        )
    if not resolved.pockets:
        if resolved.decision == NOTHING_TO_RUN:
            return None
        return ScopeReading(GateRun(SCOPE_COMMAND, NoRun("the test scope selects no test")))
    running = tuple(
        pocket.pocket
        for pocket in resolved.pockets
        if any(isinstance(run, StillRunning) for run in pocket.runs)
    )
    if running:
        raise GateStillRunningError(running)
    return read_scope(resolved, rule, repo)


@dataclass(frozen=True)
class _RunReading:
    """One invocation's run as the gate reads it: the counts of a run that finished, else why it
    is red; the failures it showed that this step answers for."""

    command: str
    finished: GateRun | None = None
    reason: str = ""
    cut_off: str = ""
    failures: tuple[str, ...] = ()


def read_scope(resolved: ScopeRuns, rule: PendingRule, repo: Path) -> ScopeReading:
    """Every run of a derived scope that lists any, read on its own: the deciding verdict, the
    counts of the runs that finished and the `Cut off:` and `Failed:` lines."""
    observed = [(pocket.pocket, run) for pocket in resolved.pockets for run in pocket.runs]
    pocket_readings = [
        [read_observed(pocket.pocket, run, rule) for run in pocket.runs]
        for pocket in resolved.pockets
    ]
    readings = [reading for one in pocket_readings for reading in one]
    command = " ; ".join(reading.command for reading in readings if reading.command)
    finished = [reading.finished for reading in readings if reading.finished is not None]
    reasons = [reading.reason for reading in readings if reading.reason]
    failures = tuple(dict.fromkeys(node for reading in readings for node in reading.failures))
    cut_offs = dict.fromkeys(f"Cut off: {r.cut_off}" for r in readings if r.cut_off)
    scopes = tuple(line for line in map(scope_line, resolved.pockets, pocket_readings) if line)
    merged = merge_finished(finished) if finished else None
    where = _log_directory(repo, observed)
    if merged is not None and not reasons:
        return ScopeReading(merged, (), tuple(cut_offs), failures, where, scopes)
    deciding = GateRun(command, NoRun("; ".join(reasons) or "nothing ran"))
    return ScopeReading(
        deciding, (merged,) if merged else (), tuple(cut_offs), failures, where, scopes
    )


def scope_line(pocket: PocketScope, readings: Sequence[_RunReading]) -> str | None:
    """`Scope: <pocket> files=<n> tests=<n> <narrow|widened>` for a pocket whose runs all
    finished (the others are named by their `Cut off:` or deciding line); None otherwise. The
    files are the resolver's list, or, for a pocket that ran its whole suite, those its log shows;
    a count nobody knows is left out."""
    runs = [reading.finished for reading in readings]
    if any(run is None for run in runs):
        return None
    counts = [cast(Counts, cast(GateRun, run).counts) for run in runs]
    tests = sum(c.passed + c.failed + c.skipped + c.errors for c in counts)
    tests += sum(cast(GateRun, run).pending for run in runs)
    logs = [run.output for run in pocket.runs if isinstance(run, Finished)]
    files = pocket.listed_test_files or sum(files_with_outcomes(log) for log in logs)
    named = f" files={files}" if files else ""
    return (
        f"Scope: {pocket.pocket}{named} tests={tests} {'widened' if pocket.widened else 'narrow'}"
    )


def read_observed(pocket: str, observed: Observed, rule: PendingRule) -> _RunReading:
    rule = _asked_in(rule, pocket)
    if isinstance(observed, Finished):
        command = shlex.join(observed.argv)
        run = classify_run(command, observed.output, rule)
        if isinstance(run.counts, NoRun):
            seen = _unanswered(observed.output, rule)
            why = f"{pocket}: {run.counts.rationale}"
            return _RunReading(command, reason=why, failures=_in_pocket(pocket, seen))
        run = _in_repository(pocket, run)
        if observed.returncode != 0 and not run.red and not run.pending_ids:
            # A runner that exits non-zero with no failure to show is not a pass.
            why = f"{pocket}: exited {observed.returncode} with no failure reported"
            return _RunReading(command, finished=run, reason=why)
        return _RunReading(command, finished=run, failures=run.failed_ids)
    if isinstance(observed, CutOff):
        bound = observed.bound
        cut = f"{pocket} after {bound.seconds:g}s ({bound.source})"
        seen = _unanswered(observed.output, rule, observed.failed_seen)
        return _RunReading(
            shlex.join(observed.argv), reason=f"{pocket} cut off after {bound.seconds:g}s "
            f"({bound.source})", cut_off=cut, failures=_in_pocket(pocket, seen),
        )  # fmt: skip
    if isinstance(observed, NotStarted):
        seen = _unanswered(observed.output, rule)
        why = f"{pocket} did not run ({observed.reason})"
        return _RunReading("", reason=why, failures=_in_pocket(pocket, seen))
    elapsed, bound = f"{observed.elapsed:.0f}", f"{observed.bound.seconds:g}"
    return _RunReading("", reason=f"{pocket} still running after {elapsed}s (bound {bound}s)")


def _in_pocket(pocket: str, nodes: Sequence[str]) -> tuple[str, ...]:
    return tuple(repository_form(pocket, node) for node in nodes)


def _in_repository(pocket: str, run: GateRun) -> GateRun:
    """`run` with every node id as the repository names it, so the runs of two pockets merge
    without one pocket's id standing for the same relative id of another."""
    failed, pending = _in_pocket(pocket, run.failed_ids), _in_pocket(pocket, run.pending_ids)
    return replace(run, failed_ids=failed, pending_ids=pending)


def _asked_in(rule: PendingRule, pocket: str) -> PendingRule:
    """`rule` asked about the ids of `pocket`'s runs; a rule that knows no pockets is asked as is."""
    return rule.in_pocket(pocket) if isinstance(rule, Ownership) else rule


def _unanswered(log: str, rule: PendingRule, known: Sequence[str] = ()) -> tuple[str, ...]:
    """The failures a log streamed (or `known` already) that no later step owns."""
    nodes = known or failed_node_ids(log)
    return tuple(node for node in nodes if not rule.is_pending(node))


def failure_lines(failures: Sequence[str], where: str) -> tuple[str, ...]:
    """A `Failed:` line for each of the first failures, then one saying how many more and where."""
    shown = [f"Failed: {node}" for node in failures[:FAILED_LINES_SHOWN]]
    more = len(failures) - FAILED_LINES_SHOWN
    if more > 0:
        shown.append(f"Failed: {_MORE_FAILURES} {more} more in {where}")
    return tuple(shown)


def _log_directory(repo: Path, observed: Sequence[tuple[str, Observed]]) -> str:
    """Where the request's run logs live, as the repository names it; empty when no run has a log."""
    logs = [run.log_path for _, run in observed if isinstance(run, (Finished, CutOff))]
    if not logs:
        return ""
    directory = logs[0].parent
    return str(directory.relative_to(repo)) if directory.is_relative_to(repo) else str(directory)


def carried_mutation(results: Path, step_id: str) -> tuple[str, ...]:
    """The step's latest `Mutation:` line, to repeat in the gate block (empty when it has none).

    A later block of the step supersedes an earlier one in the reconciler's reading, so the
    driver's block repeats the implementer's line rather than hide it.
    """
    text = results.read_text(encoding="utf-8") if results.is_file() else ""
    reading = step_mutation_reading(step_id, split_step_blocks(text))
    return () if reading is None else (render_mutation_line(reading),)


def check_run(
    repo: Path, run_dir: Path, step: PlanStep, rule: PendingRule, give_up_at: float
) -> GateRun | None:
    if step.check is None:
        return None
    if not isinstance(step.check, Check):
        return GateRun("Check:", NoRun(f"the Check: line cannot be read: {step.check.reason}"))
    ran = bounded_check(repo, run_dir, step.check.command, give_up_at)
    pocket = repository_pocket(repo, check_pocket(ran.argv))
    run = classified(ran, _asked_in(rule, pocket), step.check.command)
    return _in_repository(pocket, run)


def check_collects(repo: Path, step: PlanStep) -> str | None:
    """Why the step's `Check:` cannot collect (the command and what collection printed), else None.

    The check is run as written with `--collect-only` added, in the foreground under its pocket's
    bound, so interpreter, directory and plugins are the gate's own. It cannot collect when it
    exits non-zero without a collection summary (a missing plugin, an option pytest does not
    know): a path that is not there yet, or a module that fails to import, still print one, and
    the step may be the one that writes them. Doubt is never a stop: a run that never exited, a
    check that is not plain pytest words (another runner, a shell operator that pytest would be
    handed as an argument) and a run that exited 0 read as collecting.
    """
    if not isinstance(step.check, Check) or not _is_plain_pytest(step.check.command):
        return None
    command = step.check.command
    ran = run_check(repo, f"{command} {COLLECT_ONLY}", COLLECTION_TIMEOUT_SECONDS)
    if ran.problem is not None or ran.returncode == 0:
        return None
    if collected(ran.output):
        return None
    shown = [line.strip() for line in ran.output.splitlines() if line.strip()]
    printed = "; ".join(shown[-COLLECTION_LINES_SHOWN:]) or f"exit {ran.returncode}, no output"
    return f"its Check: `{command}` cannot collect; collection printed: {printed}"


def _is_plain_pytest(command: str) -> bool:
    """Whether `command` runs pytest with a summary the probe can read: no shell operator, no
    verbosity that prints none, and the command itself `pytest` or an interpreter's `-m pytest`,
    straight or after a runner (`uv run` and its options). A word that only names pytest, as an
    argument or an added package, does not count."""
    try:
        words = shlex.split(command)
    except ValueError:
        return False
    if _SHELL_OPERATORS & set(words) or any(_QUIETEST_RE.match(word) for word in words):
        return False
    program = _program_words(words)
    if not program:
        return False
    if Path(program[0]).name == "pytest":
        return True
    if not Path(program[0]).name.startswith(_INTERPRETER_PREFIXES):
        return False
    options = iter(program[1:])
    for option in options:
        if option == "-m":
            return next(options, "") == "pytest"
        if not option.startswith("-"):
            return False
    return False


def _program_words(words: Sequence[str]) -> Sequence[str]:
    """`words` from the program the command runs: past leading `NAME=value` words, and past a
    runner's `run` and the options after it (an option that takes a value takes the next word)."""
    start = next(
        (at for at, word in enumerate(words) if not _ENV_ASSIGNMENT_RE.match(word)), len(words)
    )
    program = words[start:]
    if not program or Path(program[0]).name not in _RUNNERS:
        return program
    if "run" not in program:
        return ()
    rest = iter(program[program.index("run") + 1 :])
    for word in rest:
        if not word.startswith("-"):
            return (word, *rest)
        if word in _RUNNER_VALUE_OPTIONS:
            next(rest, None)
    return ()


def bounded_check(repo: Path, run_dir: Path, command: str, give_up_at: float) -> CommandRun:
    """The step's `Check:` run, detached under its pocket's bound; one still inside its bound
    at `give_up_at` leaves the call with nothing written, for the next call to attach to."""
    ran = run_bounded_check(repo, command, run_dir, os.environ, give_up_at)
    if isinstance(ran, StillRunning):
        raise GateStillRunningError((f"{ran.pocket} (the Check: run)",))
    return ran


def classified(run: CommandRun, rule: PendingRule, command: str = "") -> GateRun:
    """One finished command's run as the gate reads it; one that never exited is no run."""
    shown = command or shlex.join(run.argv)
    if run.problem is not None:
        return GateRun(shown, NoRun(f"the run {run.problem}"))
    return classify_run(shown, run.output, rule)


def merge_finished(runs: Sequence[GateRun]) -> GateRun:
    """One run from several that finished: counts summed and nodes joined, each run having been
    read on its own (one invocation's count line never applies to another's nodes)."""
    command = " ; ".join(run.command for run in runs)
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
