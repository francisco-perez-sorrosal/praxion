#!/usr/bin/env python3
"""The step-loop driver: the command that tells an orchestrator which agent to start next.

    step_loop.py next   <slug> [--repo-root DIR] [--worktree-root DIR] [--base-ref REF]
    step_loop.py record <slug> --request ID (--agent-id ID --marker MARKER | --not-started REASON)
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

Outcome and exit code: spawn or complete 0; needs-human 2 (a stalled goal among its causes);
budget-exhausted 3; an error 4, or 1 for the code `internal`. Outcome precedence: complete, then
needs-human, then budget-exhausted, then spawn. Error codes: usage, missing-artifact,
request-not-pending, not-started-but-ran, agent-not-found, agent-not-for-request, agent-running,
worker-not-started (`run`), internal.

Guarantees:
* A spawn that is new has its attempt written to `WIP.md` (`- Attempts: Step <id> count=<n>
  request=<id>`) and its prompt file `PROMPT_<id>.md` written before it is printed; an
  implement request counts an attempt, a review or revise request leaves the count alone.
* `next` twice with no `record` between prints the same request, `reissued` false and then
  true, and the second call writes nothing. A stop repeats byte for byte.
* No request exceeds the attempt cap. A stop leaves `HANDOFF.md` whose section 2 names it.
* `record` gates, commits and records an ended agent's return once per request (see
  `_step_loop_record.py`); a request neither pending nor recorded is refused (exit 4).

`then` and a stop's `resume` echo how this command was started: `step_loop.py` when its
directory is a `PATH` entry, else `python3 scripts/step_loop.py`.
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
from _handoff_inputs import resolve_base_ref
from _loop_fields import GoalBudget, OutstandingAttempt, parse_attempts
from _plan_steps import PlanStep, parse_plan_steps
from _repo_root import git_toplevel_from_cwd
from _step_loop_action import Complete, Spawn, Stop, issuable_action
from _step_loop_cli import CallerError
from _step_loop_files import (
    iteration_patches,
    latest_reading,
    set_attempts_line,
    snapshot_requests,
    write_prompt,
    write_stop_handoff,
)
from _step_loop_io import paths_differing_from_head
from _step_loop_record_gate import RESULTS_FILE
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
from _step_loop_state import LoopInputs, request_kind, review_range, series_states, step_cap
from iteration_ledger import read_ledger
from reconcile_pipeline_state import reconcile

PLAN_FILE, WIP_FILE, BRIEF_FILE, HANDOFF_FILE = (
    "IMPLEMENTATION_PLAN.md",
    "WIP.md",
    "TASK_BRIEF.md",
    "HANDOFF.md",
)
REVIEW_FILE = "LIGHT_REVIEW_step-{}.md"


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
    brief = directory / BRIEF_FILE
    brief_text = brief.read_text("utf-8") if brief.is_file() else ""
    return Task(args.slug, repo, work, directory, base_ref, wip_text, brief_text, inputs)


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
    lines = cli.warning_lines(frame.warnings)
    if isinstance(action, Spawn):
        return _issue(task, action, frame, invoke)
    if isinstance(action, Complete):
        line = cli.complete_line(task.inputs.steps, counts)
        return Reply(cli.complete_envelope(frame), (line, *lines))
    view = cli.stop_view(action, task.slug, invoke)
    write_stop_handoff(task.slug, task.work, stop_next_action(view), action.cause, task.base_ref)
    doc = cli.stop_envelope(frame, action, invoke, task.dir / HANDOFF_FILE)
    return Reply(doc, (stop_stderr(view), *lines))


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
    set_attempts_line(task.dir / WIP_FILE, action.step.id, OutstandingAttempt(count, key.id))


def run_status(task: Task, args: argparse.Namespace, invoke: Invocation) -> Reply:
    inputs, action = task.inputs, issuable_action(task.inputs)
    stop = None
    lines: tuple[str, ...] = ()
    if isinstance(action, Stop):
        stop = cli.stop_object(task.slug, action, invoke, task.dir / HANDOFF_FILE)
        lines = (stop_stderr(cli.stop_view(action, task.slug, invoke)),)
    status = cli.status_object(task.slug, inputs, series_states(inputs), action, stop)
    if args.json:
        return Reply(status, lines)
    table = cli.status_table(status, cli.next_line(task.slug, action, invoke), inputs.steps)
    return Reply(status, lines, table)


def run_record(task: Task, args: argparse.Namespace, invoke: Invocation) -> Reply:
    try:
        rec.require_known(task.inputs, args.request)
        took = rec.take_back(task, args.request, args.agent_id, args.marker)
    except rec.RecordRefusedError as refused:
        raise CallerError(refused.code, refused.message, cli.iterations_of(task.inputs)) from None
    return run_next(read_task(args), args, invoke, took)


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
        message = "step_loop failed because of an unexpected error. To fix: read stderr."
        reply = _failure(args, cli.INTERNAL, message, None)
        return replace(reply, lines=(*reply.lines, traceback.format_exc().rstrip()))


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
    """Relay `next` and `record` through `spawner` until the outcome is not a spawn, or until a
    request never started (the withdrawal's envelope returns: whether to retry is the caller's).

    With `echo` every command a call prints ends with `location`; `observe` hears each
    request, the spawner's return and the envelope its `record` printed, once per record."""
    shown = tuple(location) if echo else ()
    doc = execute(["next", slug, *location], echo=shown).doc
    while doc["outcome"] == "spawn" and doc.get("recorded", {}).get("stop_reason") != "not-started":
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
    reporter = _goal_run.Reporter(task.dir)
    location = _goal_run.location(task.repo, task.base_ref, args)
    doc = drive(worker, args.slug, location, echo=True, observe=reporter)
    if doc["outcome"] == "spawn":  # the loop ends on a spawn only when its worker never started
        raise reporter.refusal()
    return Reply(doc)


def main(argv: Sequence[str] | None = None) -> int:
    reply = execute(sys.argv[1:] if argv is None else argv)
    sys.stdout.write(reply.stdout)
    for line in reply.lines:
        print(line, file=sys.stderr)
    return reply.exit


if __name__ == "__main__":
    sys.exit(main())
