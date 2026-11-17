#!/usr/bin/env python3
"""The step-loop driver: the command that tells an orchestrator which agent to start next.

    step_loop.py next   <slug> [--repo-root DIR] [--worktree-root DIR] [--base-ref REF]
    step_loop.py record <slug> --request ID (--agent-id ID --marker MARKER [--session-exited]
                        | --not-started REASON)
    step_loop.py status <slug> [--json]
    step_loop.py goal   <slug> --goal S --check C --expects E --paths P... [--protect P...]
                        --iterations N
    step_loop.py run    <slug> [--repo-root DIR] [--worktree-root DIR] [--base-ref REF]
                        [--max-turns T (40)] [--max-budget-usd X (2.00)]

`next` reads the plan, `WIP.md`, the iteration ledger, the light-review files and the task brief,
asks the reconciler for ground truth and prints the loop's one next action. `record` takes back
what an agent left. `status` reports without writing. `goal` scaffolds a one-step goal plan in
the repository it is run from (no location options) and prints `{"schema", "slug", "files",
"warnings"}`, or refuses and writes nothing. `run` repeats `next`, a fresh headless `claude -p`
worker (each bounded by `--max-turns` and `--max-budget-usd`) and `record` until the outcome is
not a spawn, then prints that envelope. It prints a stderr line per iteration (commit or why
none, turns, cost, denials), and every command it prints carries the base and roots it was
given. Exit 4, no worker started: no goal step, no deny rule in `.claude/settings.local.json`
for a protected path, or a worker that cannot start. There are exactly these five verbs.

Defaults: `--repo-root` is the git top level of the current directory, `--worktree-root` (the
root holding `.ai-work/`) is `--repo-root`, `--base-ref` is the merge-base with the default
branch. `IMPLEMENTATION_PLAN.md` and `WIP.md` must exist; `TASK_BRIEF.md` is optional.

stdout: `next`, `record` and `run` print one JSON envelope on one line, errors included (one
constructor per outcome in `_step_loop_cli.py`; `record` adds `recorded` unless it is an error).
`status` prints a table, or with `--json` its own object.
stderr: lines that begin `step_loop: ` (a summary, warnings, and the stop block on a stop).

Outcome and exit code: spawn, withdrawn or complete 0; needs-human 2 (a stalled goal among its
causes); budget-exhausted 3; an error 4, or 1 for the code `internal`. `withdrawn` is printed by
`record --not-started` alone: it carries `recorded` and a `then` naming `next`, and no request.
Outcome precedence: complete, then needs-human, then budget-exhausted, then spawn. Error codes:
usage, missing-artifact, request-not-pending, not-started-but-ran, agent-not-found,
agent-not-for-request, agent-running, gate-running, record-running, worker-not-started (`run`),
internal.

Guarantees:
* A spawn that is new has its attempt written to `WIP.md` (`- Attempts: Step <id> count=<n>
  request=<id>`) and its prompt file `PROMPT_<id>.md` written before it is printed; an
  implement request counts an attempt, a review or revise request leaves the count alone. The
  same write gives a step that `WIP.md` does not list its checklist line (`- [ ] Step <id>:
  <title>`), in front of the first later step's, so the reconciler judges it.
* `next` twice with no `record` between prints the same request, `reissued` false and then
  true, and the second call writes nothing. A stop repeats byte for byte.
* No request exceeds the attempt cap. A stop leaves `HANDOFF.md` whose section 2 names it.
* `record` gates, commits and records an ended agent's return once per request (see
  `_step_loop_record.py`); a request neither pending nor recorded is refused (exit 4). A call
  holds an OS lock on `gate/<request>/record.lock` for its whole run, so a second `record` of
  the same request started meanwhile is refused (`record-running`, exit 4) and writes nothing.
* At most one request is out. `record --not-started` takes the outstanding request back whatever
  the plan now says and issues none, so between it and the `next` its `then` names no request is
  out and a plan block may be amended; left alone, that `next` issues the same attempt again.
  A `next` made while a request is out and the plan issues another first stops
  (`request-outstanding`) naming the request and the record call that takes it back.

Every command a call prints (`then`, a stop's `resume`, the handoff's next action, the status
table's last line) echoes how this command was started, `step_loop.py` when its directory is a
`PATH` entry, else `python3 scripts/step_loop.py`, and ends with the `--repo-root`,
`--worktree-root` and `--base-ref` options that call was given, so a printed command run as
printed reads the same repository and base.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol, Union

import _goal_run
import _step_loop_cli as cli
import _step_loop_record as rec
from _goal_record import protected_set
from _goal_scaffold import scaffold
from _handoff_inputs import HandoffError, resolve_base_ref
from _loop_fields import GoalBudget, OutstandingAttempt, parse_attempts
from _plan_steps import PlanStep, parse_plan_steps
from _repo_root import git_toplevel_from_cwd
from _step_loop_action import CHECK_CANNOT_COLLECT, Complete, Spawn, Stop, issuable_action
from _step_loop_cli import CallerError
from _step_loop_files import (
    iteration_patches,
    latest_gate_evidence,
    latest_reading,
    snapshot_requests,
    with_attempts_line,
    with_checklist_line,
    write_atomic,
    write_prompt,
    write_stop_handoff,
)
from _step_loop_io import commits_touching, paths_differing_from_head
from _step_loop_record_gate import GATE_DIRECTORY, RESULTS_FILE, check_collects
from _step_loop_recording import RecordRunningError, holding_record
from _step_loop_render import (
    GoalState,
    Invocation,
    PromptInputs,
    SpawnRequest,
    render_prompt,
    spawn_request,
    stop_next_action,
    stop_stderr,
)
from _step_loop_state import (
    STEP_LABEL,
    LoopInputs,
    Marked,
    request_kind,
    review_range,
    series_states,
    step_cap,
    wants_outside_work,
    work_start,
)
from iteration_ledger import read_ledger
from reconcile_pipeline_state import reconcile

PLAN_FILE, WIP_FILE, BRIEF_FILE, HANDOFF_FILE = (
    "IMPLEMENTATION_PLAN.md",
    "WIP.md",
    "TASK_BRIEF.md",
    "HANDOFF.md",
)
REVIEW_FILE = "LIGHT_REVIEW_step-{}.md"
HANDOFF_NOT_WRITTEN = "handoff-not-written"


@dataclass(frozen=True)
class Reply:
    """What one call prints: the envelope (or status object), stderr lines, an optional table."""

    doc: Mapping[str, Any]
    lines: tuple[str, ...] = ()
    table: str | None = None  # printed in place of the JSON line when not None

    @property
    def exit(self) -> int:
        return cli.exit_code(self.doc)

    @property
    def stdout(self) -> str:
        return json.dumps(self.doc) + "\n" if self.table is None else self.table


@dataclass(frozen=True)
class Task:
    """Everything one call reads, by value."""

    slug: str
    repo: Path
    work: Path
    dir: Path
    base_ref: str
    wip_text: str
    brief_text: str
    inputs: LoopInputs


# --- Reading the task -------------------------------------------------------------------------


def read_task(args: argparse.Namespace) -> Task:
    repo = Path(args.repo_root).resolve() if args.repo_root else git_toplevel_from_cwd()
    if repo is None:
        raise CallerError("usage", "No repository was found. To fix: pass --repo-root.")
    work = Path(args.worktree_root).resolve() if args.worktree_root else repo
    directory = work / ".ai-work" / args.slug
    plan_text, wip_text = _required(directory / PLAN_FILE), _required(directory / WIP_FILE)
    steps = parse_plan_steps(plan_text)
    ledger = read_ledger(directory)
    attempts = parse_attempts(wip_text, ledger.requests)
    reviews = {
        step.id: path.read_text("utf-8")
        for step in steps
        if (path := directory / REVIEW_FILE.format(step.id)).is_file()
    }
    base_ref = args.base_ref or resolve_base_ref(repo)
    verdicts = reconcile(args.slug, repo, base_ref, state_root=work, include_untracked=True)
    snapshots = snapshot_requests(directory)
    inputs = LoopInputs.read(
        steps, attempts.counts, ledger.records, verdicts, reviews, attempts.unnamed, snapshots
    )
    inputs = replace(inputs, uncommitted=uncommitted_files(repo, inputs))
    inputs = replace(inputs, outside_work=outside_work(repo, inputs, base_ref))
    brief = directory / BRIEF_FILE
    brief_text = brief.read_text("utf-8") if brief.is_file() else ""
    return Task(args.slug, repo, work, directory, base_ref, wip_text, brief_text, inputs)


# Where the pipeline and the hooks write on their own, so a path under them is no attempt's edit.
PIPELINE_STATE = (".ai-work/", ".ai-state/observations")


STATE_FILES = ".ai-state/"  # committed project state, as likely to be dirty as it is unrelated


def uncommitted_files(repo: Path, inputs: LoopInputs) -> dict[str, tuple[str, ...]]:
    """What each marked step left behind: every path of the tree that differs from HEAD, tracked
    or not, bar the pipeline's own state. A marked return commits and restores nothing, and a
    [CONFLICT] is most often an edit outside the step's files, so the stop names them all for
    the person who takes the work over. A step's own files come first and the committed state
    last, so the few names a stop spells out are the ones that matter."""
    states = series_states(inputs)
    marked = [step for step in inputs.steps if isinstance(states[step.id], Marked)]
    if not marked:
        return {}
    left = tuple(
        path
        for path in paths_differing_from_head(repo, ["."])
        if not path.startswith(PIPELINE_STATE)
    )
    if not left:
        return {}
    return {step.id: _own_files_first(left, step.files) for step in marked}


def _own_files_first(paths: tuple[str, ...], own: tuple[str, ...]) -> tuple[str, ...]:
    """`paths` with those a step's Files: names first and the committed state last."""

    def rank(path: str) -> int:
        if any(path == name or path.startswith(f"{name.rstrip('/')}/") for name in own):
            return 0
        return 2 if path.startswith(STATE_FILES) else 1

    return tuple(sorted(paths, key=rank))


def outside_work(repo: Path, inputs: LoopInputs, base_ref: str) -> dict[str, tuple[str, ...]]:
    """The commits made outside the loop that hold a reviewed step's work, for each step due a
    light review whose series committed nothing: every commit that touched the step's files
    since its work began (the last commit recorded before the step, else the pipeline base)."""
    states = series_states(inputs)
    found = {}
    for step in inputs.steps:
        if wants_outside_work(inputs, step, states[step.id]):
            since = work_start(inputs, step) or base_ref
            if commits := commits_touching(repo, since, step.files):
                found[step.id] = commits
    return found


def _required(path: Path) -> str:
    if not path.is_file():
        raise CallerError(
            "missing-artifact",
            f"step_loop failed because {path} does not exist. "
            "To fix: create it, or pass --worktree-root for the checkout that holds it.",
        )
    return path.read_text("utf-8")


# --- The verbs --------------------------------------------------------------------------------


def run_next(
    task: Task, args: argparse.Namespace, invoke: Invocation, took: rec.Taken | None = None
) -> Reply:
    """The next action, carrying what a `record` took back."""
    action, counts = issuable_action(task.inputs), cli.iterations_of(task.inputs)
    frame = cli.Frame(task.slug, counts, *((took.warnings, took.recorded) if took else ()))
    if isinstance(action, Spawn):
        action = _first_request_refused(task, action) or action
    if isinstance(action, Spawn):
        return _issue(task, action, frame, invoke)
    if isinstance(action, Complete):
        line = cli.complete_line(task.inputs.steps, counts)
        return Reply(cli.complete_envelope(frame), (line, *cli.warning_lines(frame.warnings)))
    view = cli.stop_view(action, task.slug, invoke)
    try:
        write_stop_handoff(
            task.slug,
            task.work,
            stop_next_action(view),
            action.cause,
            task.base_ref,
            same_action=cli.same_next_action,
        )
    except HandoffError as refused:  # a stop for a human stays one, whatever sits at HANDOFF.md
        frame = frame._replace(
            warnings=(
                *frame.warnings,
                (HANDOFF_NOT_WRITTEN, f"{refused}. To fix: rename it, then call next again."),
            )
        )
    doc = cli.stop_envelope(frame, action, invoke, task.dir / HANDOFF_FILE)
    return Reply(doc, (stop_stderr(view), *cli.warning_lines(frame.warnings)))


def _first_request_refused(task: Task, action: Spawn) -> Stop | None:
    """The stop that keeps a series' first request from going out when its step's `Check:` cannot
    collect: a plan defect no attempt can mend, found before one is spent. A request already out,
    a review, a revision and any later attempt of the series are not asked."""
    key = action.key
    if action.reissued or key.kind != "implement" or key.attempt != 1:
        return None
    why = check_collects(task.repo, action.step)
    if why is None:
        return None
    return Stop(CHECK_CANNOT_COLLECT, action.step.id, f"{STEP_LABEL}{action.step.id}: {why}")


def _issue(task: Task, action: Spawn, frame: cli.Frame, invoke: Invocation) -> Reply:
    cap = step_cap(action.step)
    request = spawn_request(task.slug, action.step, action.key, cap, str(task.dir))
    request = replace(request, reissued=action.reissued)
    path = Path(request.prompt_path)
    warnings: Sequence[tuple[str, str]] = ()
    if not action.reissued:
        text, warnings = render_prompt(_prompt_inputs(task, action, request))
        write_prompt(task.dir, action.key.id, text)
        _write_ahead(task, action)
    elif not path.exists():
        write_prompt(
            task.dir, action.key.id, render_prompt(_prompt_inputs(task, action, request))[0]
        )
    frame = frame._replace(warnings=(*frame.warnings, *warnings))
    lines = (cli.spawn_line(request, frame.iterations), *cli.warning_lines(frame.warnings))
    return Reply(cli.spawn_envelope(frame, request, invoke), lines)


def _prompt_inputs(task: Task, action: Spawn, request: SpawnRequest) -> PromptInputs:
    step, inputs = action.step, task.inputs
    previous = tuple(
        cli.prior_attempt(record)
        for record in inputs.driver_records(step.id)
        if request_kind(record) == "implement"
    )
    return PromptInputs(
        request,
        step,
        str(task.dir),
        brief_text=task.brief_text,
        wip_text=task.wip_text,
        findings_text=inputs.reviews.get(step.id, ""),
        previous=previous,
        gate_evidence=latest_gate_evidence(task.dir / RESULTS_FILE, step.id),
        dirty_files=paths_differing_from_head(task.repo, step.files) if previous else (),
        review_range=review_range(inputs, step),
        goal=_goal_state(task, step) if action.key.kind == "implement" else None,
    )


def _goal_state(task: Task, step: PlanStep) -> GoalState | None:
    """What a goal step's prompt reads from the files; None for an ordinary step."""
    if not isinstance(step.bound, GoalBudget):
        return None
    return GoalState(
        latest_reading(task.dir / RESULTS_FILE, step.id),
        protected_set(step.read_only),
        iteration_patches(task.dir, step.id),
    )


def _write_ahead(task: Task, action: Spawn) -> None:
    """Count the attempt in `WIP.md` before its request is printed: its number within its
    series (a plan revision's fresh series restarts at 1); a review or revise keeps the count."""
    key, existing = action.key, task.inputs.attempts.get(action.step.id)
    count = key.attempt if key.kind == "implement" or existing is None else existing.count
    wip = task.dir / WIP_FILE
    listed = with_checklist_line(wip.read_text("utf-8"), action.step, task.inputs.steps)
    attempt = OutstandingAttempt(count, key.id)
    write_atomic(wip, with_attempts_line(listed, action.step.id, attempt))


def run_status(task: Task, args: argparse.Namespace, invoke: Invocation) -> Reply:
    inputs, action = task.inputs, issuable_action(task.inputs)
    stop = None
    lines: tuple[str, ...] = ()
    if isinstance(action, Stop):
        stop = cli.stop_object(task.slug, action, invoke, task.dir / HANDOFF_FILE)
        lines = (stop_stderr(cli.stop_view(action, task.slug, invoke)),)
    status = cli.status_object(task.slug, inputs, series_states(inputs), action, stop, invoke)
    if args.json:
        return Reply(status, lines)
    table = cli.status_table(status, cli.next_line(task.slug, action, invoke), inputs.steps)
    return Reply(status, lines, table)


def run_record(task: Task, args: argparse.Namespace, invoke: Invocation) -> Reply:
    """Take back a return while holding the request's record lock for the whole call.

    The id is checked as one the loop knows before it names the lock's directory, and the task is
    read again under the lock: a record of the request that ended a moment ago is then a replay,
    never a second record from inputs read before it wrote."""
    try:
        rec.require_known(task.inputs, args.request)
    except rec.RecordRefusedError as refused:
        raise _refusal(task, refused) from None
    try:
        with holding_record(task.dir / GATE_DIRECTORY / args.request):
            return _record_holding_lock(read_task(args), args, invoke)
    except RecordRunningError as running:
        raise cli.record_running(running, cli.iterations_of(task.inputs)) from None


def _record_holding_lock(task: Task, args: argparse.Namespace, invoke: Invocation) -> Reply:
    try:
        rec.require_known(task.inputs, args.request)
        took = rec.take_back(
            task, args.request, args.agent_id, args.marker, session_exited=args.session_exited
        )
    except rec.RecordRefusedError as refused:
        raise _refusal(task, refused) from None
    if args.not_started is not None:  # nothing is issued: the plan may be amended before `next`
        frame = cli.Frame(task.slug, cli.iterations_of(task.inputs), took.warnings, took.recorded)
        doc = cli.withdrawn_envelope(frame, invoke)
        return Reply(doc, (cli.withdrawn_line(args.request, doc["then"]),))
    return run_next(read_task(args), args, invoke, took)


def _refusal(task: Task, refused: rec.RecordRefusedError) -> CallerError:
    return CallerError(refused.code, refused.message, cli.iterations_of(task.inputs))


_VERBS: Mapping[str, Callable[[Task, argparse.Namespace, Invocation], Reply]] = {
    "next": run_next,
    "record": run_record,
    "status": run_status,
}


# --- One call, and the loop a test drives -------------------------------------------------------


def execute(argv: Sequence[str], *, echo: Sequence[str] = ()) -> Reply:
    """Run one call; every failure becomes the one envelope its code names. The commands it
    prints end with `echo`, the options this call was given that the person should repeat."""
    args = None
    try:
        args = cli.parse(argv, __doc__)
        program = cli.invocation(sys.argv[0], os.environ.get("PATH", ""))
        invoke = Invocation(program, tuple(echo))
        if args.verb == cli.GOAL_VERB:  # there is no plan to read yet
            return Reply(*scaffold(args))
        if args.verb == cli.RUN_VERB:
            return run_goal(args)
        return _VERBS[args.verb](read_task(args), args, invoke)
    except CallerError as error:
        return _failure(args, error.code, error.message, error.counts)
    except Exception:  # noqa: BLE001 -- the contract: any failure is one internal envelope
        trace = traceback.format_exc().rstrip()  # the envelope carries it: `drive` keeps no lines
        return _failure(args, cli.INTERNAL, f"step_loop failed unexpectedly:\n{trace}", None)


def _failure(
    args: argparse.Namespace | None, code: str, message: str, counts: cli.Iterations | None
) -> Reply:
    slug = getattr(args, "slug", "")
    doc = cli.error_envelope(cli.Frame(slug, counts), code, message)
    human_status = getattr(args, "verb", None) == "status" and not args.json
    return Reply(doc, (cli.error_line(message),), "" if human_status else None)


@dataclass(frozen=True)
class AgentRan:
    """The Agent call started an agent: its id and the terminal marker its final text carried."""

    agent_id: str
    marker: str


@dataclass(frozen=True)
class NotStarted:
    """The Agent call failed before any agent started."""

    reason: str


SpawnReturn = Union[AgentRan, NotStarted]  # noqa: UP007 -- runtime value, 3.9 floor


class Spawner(Protocol):
    """Whatever starts an agent for a request: the orchestrator in life, a double in a test."""

    def spawn(self, request: Mapping[str, Any]) -> SpawnReturn: ...


Observer = Callable[[Mapping[str, Any], SpawnReturn, Mapping[str, Any]], None]


def drive(
    spawner: Spawner,
    slug: str,
    location: Sequence[str] = (),
    *,
    echo: bool = False,
    observe: Observer | None = None,
) -> Mapping[str, Any]:
    """Relay `next` and `record` through `spawner` until the outcome is not a spawn; a request
    that never started ends it on the withdrawal's envelope (whether to retry is the caller's).

    With `echo` every command a call prints ends with `location`; `observe` hears each
    request, the spawner's return and the envelope its `record` printed, once per record."""
    shown = tuple(location) if echo else ()
    doc = execute(["next", slug, *location], echo=shown).doc
    while doc["outcome"] == "spawn":
        request = doc["request"]
        returned = spawner.spawn(request)
        if isinstance(returned, AgentRan):
            relay = ["--agent-id", returned.agent_id, "--marker", returned.marker]
        else:
            relay = ["--not-started", returned.reason]
        doc = execute(
            ["record", slug, "--request", request["id"], *relay, *location], echo=shown
        ).doc
        if observe is not None:
            observe(request, returned, doc)
    return doc


def run_goal(args: argparse.Namespace) -> Reply:
    """The terminal form of the goal loop: `drive` with a headless worker; its last envelope."""
    task = read_task(args)
    worker = _goal_run.start_worker(task.inputs.steps, task.repo, task.dir, args)
    reporter = worker.reporter()
    location = _goal_run.location(task.repo, task.base_ref, args)
    doc = drive(worker, args.slug, location, echo=True, observe=reporter)
    # The loop ends on a withdrawal only when its worker never started.
    if doc["outcome"] == "withdrawn":
        raise reporter.refusal()
    return Reply(doc, reporter.closing(doc))


def main(argv: Sequence[str] | None = None) -> int:
    words = sys.argv[1:] if argv is None else argv
    reply = execute(words, echo=cli.location_echo(words))
    sys.stdout.write(reply.stdout)
    for line in reply.lines:
        print(line, file=sys.stderr)
    return reply.exit


if __name__ == "__main__":
    sys.exit(main())
