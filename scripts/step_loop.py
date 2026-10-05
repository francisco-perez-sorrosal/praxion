#!/usr/bin/env python3
"""The step-loop driver: the command that tells an orchestrator which agent to start next.

    step_loop.py next   <slug> [--repo-root DIR] [--worktree-root DIR] [--base-ref REF]
    step_loop.py record <slug> --request ID (--agent-id ID --marker MARKER | --not-started REASON)
    step_loop.py status <slug> [--json]

`next` reads the plan, `WIP.md`, the iteration ledger, the light-review files and the task brief,
asks the reconciler for ground truth and prints the loop's one next action. `record` takes back
what an agent left. `status` reports without writing. There are exactly these three verbs.

Defaults: `--repo-root` is the git top level of the current directory, `--worktree-root` (the
root holding `.ai-work/`) is `--repo-root`, `--base-ref` is the merge-base with the default
branch. `IMPLEMENTATION_PLAN.md` and `WIP.md` must exist; `TASK_BRIEF.md` is optional.

stdout: `next` and `record` print one JSON envelope on one line, errors included:
`schema`, `outcome`, `slug`, then `request` and `then` for a spawn, `recorded` for a `record`
that is not an error, `stop` for a needs-human or budget-exhausted outcome, `error` for an
error, `iterations` (`used`, `budget`) on every outcome but a usage or missing-artifact error,
and `warnings`. `status` prints a table, or with `--json` its own object.
stderr: lines that begin `step_loop: ` (a summary, warnings, and the stop block on a stop).

Outcome and exit code: spawn or complete 0; needs-human 2; budget-exhausted 3; an error 4, or 1
for the code `internal`. Outcome precedence: complete, then needs-human, then budget-exhausted,
then spawn. Error codes: usage, missing-artifact, request-not-pending, not-started-but-ran,
agent-not-found, agent-not-for-request, agent-running, internal.

Guarantees:
* A spawn that is new has its attempt written to `WIP.md` (`- Attempts: Step <id> count=<n>
  request=<id>`) and its prompt file `PROMPT_<id>.md` written before it is printed; an
  implement request counts an attempt, a review or revise request leaves the count alone.
* `next` twice with no `record` between prints the same request, `reissued` false and then
  true, and the second call writes nothing. A stop repeats byte for byte.
* No request exceeds the attempt cap. A stop leaves `HANDOFF.md` whose section 2 names it.
* A request that is neither pending nor recorded is refused (exit 4, `request-not-pending`).

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
from typing import Any, NoReturn, Protocol, Union

import _step_loop_cli as cli
from _handoff_inputs import resolve_base_ref
from _loop_fields import ATTEMPT_CAP, OutstandingAttempt, parse_attempts
from _plan_steps import parse_plan_steps
from _repo_root import git_toplevel_from_cwd
from _step_loop_action import Complete, Spawn, Stop, next_action
from _step_loop_files import set_attempts_line, write_prompt, write_stop_handoff
from _step_loop_io import paths_differing_from_head
from _step_loop_render import (
    PromptInputs,
    SpawnRequest,
    render_prompt,
    spawn_request,
    stop_next_action,
    stop_stderr,
)
from _step_loop_state import LoopInputs, request_kind, series_states
from iteration_ledger import read_ledger
from reconcile_pipeline_state import reconcile

PLAN_FILE, WIP_FILE, BRIEF_FILE, HANDOFF_FILE = (
    "IMPLEMENTATION_PLAN.md",
    "WIP.md",
    "TASK_BRIEF.md",
    "HANDOFF.md",
)
REVIEW_FILE = "LIGHT_REVIEW_step-{}.md"
VERBS = ("next", "record", "status")
MARKERS = ("complete", "blocked", "conflict", "partial", "none")


class CallerError(Exception):
    """A call the driver refuses: it names its code, says how to fix it, and wrote nothing."""

    def __init__(self, code: str, message: str, counts: cli.Iterations | None = None) -> None:
        super().__init__(message)
        self.code, self.message, self.counts = code, message, counts


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
    wip_text: str
    brief_text: str
    inputs: LoopInputs


# --- The command line -------------------------------------------------------------------------


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise CallerError(
            "usage",
            f"The arguments could not be read because {message}. To fix: see {self.prog} --help.",
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="step_loop.py", description=__doc__)
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    verbs = parser.add_subparsers(dest="verb", required=True, metavar="{" + ",".join(VERBS) + "}")
    for verb in VERBS:
        sub = verbs.add_parser(verb)
        sub.add_argument("slug", help="task slug under .ai-work/<slug>/")
        sub.add_argument("--repo-root", help="git repo root (default: from git)")
        sub.add_argument("--worktree-root", help="root holding .ai-work/ (default: --repo-root)")
        sub.add_argument("--base-ref", help="git ref the reconciler diffs against")
    verbs.choices["status"].add_argument("--json", action="store_true", help="print the object")
    record = verbs.choices["record"]
    record.add_argument("--request", required=True, help="the pending request's id")
    record.add_argument("--agent-id", help="the agentId the Agent tool result carries")
    record.add_argument("--marker", choices=MARKERS, help="the agent's terminal marker")
    record.add_argument("--not-started", metavar="REASON", help="the Agent call never started")
    return parser


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    args = _build_parser().parse_args(argv)
    if args.verb == "record":
        relayed = args.agent_id is not None or args.marker is not None
        if relayed == (args.not_started is not None):
            problem = "give --agent-id with --marker, or --not-started, and not both"
        elif relayed and not (args.agent_id and args.marker):
            problem = "--agent-id and --marker go together, and the id is not empty"
        elif args.not_started is not None and not args.not_started.strip():
            problem = "--not-started needs a reason"
        else:
            return args
        _Parser(prog="step_loop.py record").error(problem)
    return args


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
    verdicts = reconcile(args.slug, repo, args.base_ref or resolve_base_ref(repo), state_root=work)
    inputs = LoopInputs.read(
        steps, attempts.counts, ledger.records, verdicts, reviews, attempts.unnamed
    )
    brief = directory / BRIEF_FILE
    brief_text = brief.read_text("utf-8") if brief.is_file() else ""
    return Task(args.slug, repo, work, directory, wip_text, brief_text, inputs)


def _required(path: Path) -> str:
    if not path.is_file():
        raise CallerError(
            "missing-artifact",
            f"step_loop failed because {path} does not exist. "
            "To fix: create it, or pass --worktree-root for the checkout that holds it.",
        )
    return path.read_text("utf-8")


# --- The verbs --------------------------------------------------------------------------------


def run_next(task: Task, args: argparse.Namespace, invoke: str) -> Reply:
    action, counts = next_action(task.inputs), cli.iterations_of(task.inputs)
    if isinstance(action, Spawn):
        return _issue(task, action, counts, invoke)
    if isinstance(action, Complete):
        frame = cli.Frame(task.slug, counts)
        return Reply(cli.complete_envelope(frame), (cli.complete_line(task.inputs.steps, counts),))
    view = cli.stop_view(action, task.slug, invoke)
    write_stop_handoff(task.slug, task.work, stop_next_action(view))
    doc = cli.stop_envelope(cli.Frame(task.slug, counts), action, invoke, task.dir / HANDOFF_FILE)
    return Reply(doc, (stop_stderr(view),))


def _issue(task: Task, action: Spawn, counts: cli.Iterations, invoke: str) -> Reply:
    request = spawn_request(task.slug, action.step, action.key, ATTEMPT_CAP, str(task.dir))
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
    lines = (cli.spawn_line(request, counts), *cli.warning_lines(warnings))
    return Reply(cli.spawn_envelope(cli.Frame(task.slug, counts, warnings), request, invoke), lines)


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
    )


def _write_ahead(task: Task, action: Spawn) -> None:
    """Count the attempt in `WIP.md` before its request is printed.

    The count is the attempt's number within its series, so a fresh series after a plan
    revision restarts at 1 whatever the old line said; a review or revise request has no
    attempt of its own and keeps the count of the line it follows.
    """
    key, existing = action.key, task.inputs.attempts.get(action.step.id)
    count = key.attempt if key.kind == "implement" or existing is None else existing.count
    set_attempts_line(task.dir / WIP_FILE, action.step.id, OutstandingAttempt(count, key.id))


def run_status(task: Task, args: argparse.Namespace, invoke: str) -> Reply:
    inputs, action = task.inputs, next_action(task.inputs)
    stop = None
    lines: tuple[str, ...] = ()
    if isinstance(action, Stop):
        stop = cli.stop_object(task.slug, action, invoke, task.dir / HANDOFF_FILE)
        lines = (stop_stderr(cli.stop_view(action, task.slug, invoke)),)
    status = cli.status_object(task.slug, inputs, series_states(inputs), action, stop)
    if args.json:
        return Reply(status, lines)
    return Reply(status, lines, cli.status_table(status, _next_line(task, action, invoke)))


def _next_line(task: Task, action: Union[Spawn, Complete, Stop], invoke: str) -> str:  # noqa: UP007
    if isinstance(action, Spawn) and action.reissued:
        return f"the Agent call for {action.key.id} is pending; record it when it ends"
    if isinstance(action, Spawn):
        return f"run `{invoke} next {task.slug}` to start {action.key.id}"
    if isinstance(action, Complete):
        return "every step is done"
    return f"stopped ({action.cause}): {action.evidence}"


def run_record(task: Task, args: argparse.Namespace, invoke: str) -> Reply:
    pending = sorted(
        a.request for a in task.inputs.attempts.values() if isinstance(a, OutstandingAttempt)
    )
    recorded = {record.request for record in task.inputs.records}
    if args.request not in (*pending, *recorded):
        state = f"the pending request is {pending[0]}" if pending else "none is pending"
        raise CallerError(
            "request-not-pending",
            f"record failed because {args.request} is neither pending nor recorded ({state})."
            " To fix: record the pending request, or run next to get one.",
            cli.iterations_of(task.inputs),
        )
    raise NotImplementedError("record gates a returned attempt in the next increment")


_VERBS: Mapping[str, Callable[[Task, argparse.Namespace, str], Reply]] = {
    "next": run_next,
    "record": run_record,
    "status": run_status,
}


# --- One call, and the loop a test drives -------------------------------------------------------


def execute(argv: Sequence[str]) -> Reply:
    """Run one call; every failure becomes the one envelope its code names."""
    args = None
    try:
        args = _parse(argv)
        invoke = cli.invocation(sys.argv[0], os.environ.get("PATH", ""))
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


def drive(spawner: Spawner, slug: str, location: Sequence[str] = ()) -> Mapping[str, Any]:
    """Relay `next` and `record` through `spawner` until the outcome is not a spawn."""
    doc = execute(["next", slug, *location]).doc
    while doc["outcome"] == "spawn":
        request = doc["request"]
        returned = spawner.spawn(request)
        if isinstance(returned, AgentRan):
            relay = ["--agent-id", returned.agent_id, "--marker", returned.marker]
        else:
            relay = ["--not-started", returned.reason]
        doc = execute(["record", slug, "--request", request["id"], *relay, *location]).doc
    return doc


def main(argv: Sequence[str] | None = None) -> int:
    reply = execute(sys.argv[1:] if argv is None else argv)
    sys.stdout.write(reply.stdout)
    for line in reply.lines:
        print(line, file=sys.stderr)
    return reply.exit


if __name__ == "__main__":
    sys.exit(main())
