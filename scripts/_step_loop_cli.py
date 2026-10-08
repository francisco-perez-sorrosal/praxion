"""The command-line layer of the step-loop command: what a call reads, prints and exits with.

The arguments come in through `parse`, which refuses a bad call as a `CallerError`. Then pure:
the loop's decision and its inputs come in; the JSON envelope, its exit code, the stderr
lines and the `status` object and table go out. Nothing here reads a file or the clock, so a
stop repeats byte for byte. An envelope is built only by the four constructors below, one per
kind of outcome, so a field is present exactly when its outcome says it is.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple, NoReturn

from _plan_steps import Implementer, PlanStep
from _step_loop_action import (
    BUDGET_CAUSE,
    Action,
    Complete,
    Spawn,
    Stop,
    iteration_budget,
    iterations_used,
)
from _step_loop_render import Invocation, PriorAttempt, SpawnRequest, StopView
from _step_loop_review import (
    Accepted,
    Due,
    Requested,
    RevisedTwice,
    ReviseDue,
    RevisionFailed,
    Unfinished,
)
from _step_loop_state import (
    EXHAUSTED,
    Exhausted,
    Failed,
    HumanVerdict,
    LoopInputs,
    Marked,
    Running,
    Series,
    Verified,
    spent,
    step_cap,
)
from iteration_ledger import IterationRecord

SCHEMA = 1
SCRIPT = "step_loop.py"
SELF_HOST_INVOCATION = f"python3 scripts/{SCRIPT}"
SUMMARY_PREFIX = "step_loop: "
DASH = "—"
SHORT_SHA = 7
PENDING = "pending"
IN_FLIGHT = "in-flight"
VERBS = ("next", "record", "status")
GOAL_VERB = "goal"
MARKERS = ("complete", "blocked", "conflict", "partial", "none")
RECORD_PLACEHOLDERS = "--agent-id <agentId> --marker <complete|blocked|conflict|partial|none>"
EXIT_BY_OUTCOME = {"spawn": 0, "complete": 0, "needs-human": 2, "budget-exhausted": 3}
EXIT_CALLER_ERROR, EXIT_INTERNAL = 4, 1
INTERNAL = "internal"
_REVIEW_WORDS = {
    Due: "due",
    Requested: "requested",
    Accepted: "accepted",
    ReviseDue: "revise-due",
    RevisedTwice: "revised-twice",
    Unfinished: "unfinished",
    RevisionFailed: "revision-failed",
}
_TABLE_HEADERS = ("STEP", "ASSIGNEE", "VERDICT", "ATTEMPTS", "REVIEW", "COMMIT")
_COLUMN_GAP = "  "

Warnings = Sequence[tuple[str, str]]  # (code, message)


class Iterations(NamedTuple):
    used: int
    budget: int


class Frame(NamedTuple):
    """What every envelope carries besides its outcome's own part."""

    slug: str
    iterations: Iterations | None = None
    warnings: Warnings = ()
    recorded: Mapping[str, Any] | None = None


def iterations_of(inputs: LoopInputs) -> Iterations:
    return Iterations(iterations_used(inputs), iteration_budget(inputs.steps))


# --- The invocation the caller used --------------------------------------------------------


def invocation(argv0: str, path: str) -> str:
    """`step_loop.py` when the script was started through `PATH`, else the checkout's form.

    The script's directory is compared with each `PATH` entry as written (links are not
    resolved), so a managed project, where the installer links the script into a `PATH`
    directory, is told to run the short form and the Praxion checkout is not.
    """
    here = os.path.dirname(os.path.abspath(argv0))
    entries = (os.path.abspath(entry) for entry in path.split(os.pathsep) if entry)
    return SCRIPT if here in entries else SELF_HOST_INVOCATION


# --- The command line -------------------------------------------------------------------------


class CallerError(Exception):
    """A call the driver refuses: it names its code, says how to fix it, and wrote nothing."""

    def __init__(self, code: str, message: str, counts: Iterations | None = None) -> None:
        super().__init__(message)
        self.code, self.message, self.counts = code, message, counts


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise CallerError(
            "usage",
            f"The arguments could not be read because {message}. To fix: see {self.prog} --help.",
        )


def _build_parser(description: str | None) -> argparse.ArgumentParser:
    parser = _Parser(prog=SCRIPT, description=description)
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    offered = (*VERBS, GOAL_VERB)
    verbs = parser.add_subparsers(dest="verb", required=True, metavar="{" + ",".join(offered) + "}")
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
    _add_goal_verb(verbs)
    return parser


def _add_goal_verb(verbs: Any) -> None:
    """`goal` takes no location options: it scaffolds in the repository it is run from."""
    goal = verbs.add_parser(GOAL_VERB)
    goal.add_argument("slug", help="task slug under .ai-work/<slug>/")
    goal.add_argument("--goal", required=True, help="the goal, one sentence")
    goal.add_argument("--check", required=True, help="the command whose pytest summary judges it")
    goal.add_argument("--expects", required=True, help="what the check must show, pass=3 fail=0")
    goal.add_argument("--paths", nargs="+", help="the files an iteration may change")
    goal.add_argument("--protect", nargs="+", default=[], help="paths no iteration may change")
    goal.add_argument("--iterations", required=True, help="how many iterations the loop may spend")


def parse(argv: Sequence[str], description: str | None) -> argparse.Namespace:
    """Read one call's arguments; `description` is the help text the entry script carries."""
    args = _build_parser(description).parse_args(argv)
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
        _Parser(prog=f"{SCRIPT} record").error(problem)
    return args


# --- The four constructors, one per kind of outcome ----------------------------------------


def _envelope(frame: Frame, outcome: str, **parts: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {"schema": SCHEMA, "outcome": outcome, "slug": frame.slug, **parts}
    if frame.recorded is not None:
        doc["recorded"] = dict(frame.recorded)
    if frame.iterations is not None:
        doc["iterations"] = {"used": frame.iterations.used, "budget": frame.iterations.budget}
    doc["warnings"] = [{"code": code, "message": message} for code, message in frame.warnings]
    return doc


def spawn_envelope(frame: Frame, request: SpawnRequest, invoke: str | Invocation) -> dict[str, Any]:
    """A request is pending: the Agent call to make and the `record` call that follows it."""
    key, call = request.key, request.agent_call
    shown = {
        "id": key.id,
        "kind": key.kind,
        "step": key.step,
        "attempt": key.attempt,
        "attempt_cap": request.attempt_cap,
        "agent_call": {
            "subagent_type": call.subagent_type,
            "model": call.model,
            "description": call.description,
            "prompt": call.prompt,
        },
        "prompt_path": request.prompt_path,
        "reissued": request.reissued,
    }
    then = Invocation.of(invoke).command(
        "record", frame.slug, "--request", key.id, RECORD_PLACEHOLDERS
    )
    return _envelope(frame, "spawn", request=shown, then=then)


def complete_envelope(frame: Frame) -> dict[str, Any]:
    return _envelope(frame, "complete")


def stop_envelope(
    frame: Frame, stop: Stop, invoke: str | Invocation, handoff: Path
) -> dict[str, Any]:
    """The loop has stopped: `needs-human`, or `budget-exhausted` for the budget cause."""
    outcome = "budget-exhausted" if stop.cause == BUDGET_CAUSE else "needs-human"
    return _envelope(frame, outcome, stop=stop_object(frame.slug, stop, invoke, handoff))


def error_envelope(frame: Frame, code: str, message: str) -> dict[str, Any]:
    return _envelope(frame, "error", error={"code": code, "message": message})


def exit_code(doc: Mapping[str, Any]) -> int:
    """A total function of the outcome and, for an error, its code; an object with no outcome
    (the scaffold `goal` prints) is a success."""
    if "outcome" not in doc:
        return 0
    if doc["outcome"] == "error":
        return EXIT_INTERNAL if doc["error"]["code"] == INTERNAL else EXIT_CALLER_ERROR
    return EXIT_BY_OUTCOME[doc["outcome"]]


# --- A stop and its attempts ----------------------------------------------------------------


def prior_attempt(record: IterationRecord) -> PriorAttempt:
    return PriorAttempt(
        record.attempt,
        record.agent_id,
        record.stop_reason,
        record.turns,
        record.max_turns,
        record.test_result,
        record.commit,
    )


def stop_view(stop: Stop, slug: str, invoke: str | Invocation) -> StopView:
    attempts = tuple(prior_attempt(record) for record in stop.attempts)
    return StopView(stop.cause, stop.step, stop.evidence, attempts, slug, invoke)


def stop_object(slug: str, stop: Stop, invoke: str | Invocation, handoff: Path) -> dict[str, Any]:
    return {
        "cause": stop.cause,
        "step": stop.step,
        "evidence": stop.evidence,
        "attempts": [_attempt_object(record) for record in stop.attempts],
        "replan_request": stop.replan_request,
        "handoff": str(handoff),
        "resume": Invocation.of(invoke).command("next", slug),
    }


def _attempt_object(record: IterationRecord) -> dict[str, Any]:
    return {
        "attempt": record.attempt,
        "agent_id": record.agent_id,
        "stop_reason": record.stop_reason,
        "turns": record.turns,
        "max_turns": record.max_turns,
        "verdict": record.verdict,
        "gate": record.test_result,
        "commit": record.commit,
    }


# --- The stderr lines -----------------------------------------------------------------------


def spawn_line(request: SpawnRequest, counts: Iterations) -> str:
    call, key = request.agent_call, request.key
    if request.reissued:
        return f"{SUMMARY_PREFIX}{call.description} is still pending ({key.id}); reissued, nothing written"
    arrow = f"spawn {call.subagent_type} ({call.model})"
    return (
        f"{SUMMARY_PREFIX}{call.description} → {arrow} · iterations {counts.used}/{counts.budget}"
    )


def complete_line(steps: Sequence[PlanStep], counts: Iterations) -> str:
    driven = sum(isinstance(step.assignee, Implementer) for step in steps)
    return (
        f"{SUMMARY_PREFIX}complete — {driven} of {driven} driven steps verified"
        f" · iterations {counts.used}/{counts.budget}"
    )


def warning_lines(warnings: Warnings) -> list[str]:
    return [f"{SUMMARY_PREFIX}warning: {code} — {message}" for code, message in warnings]


def error_line(message: str) -> str:
    return f"{SUMMARY_PREFIX}error: {message}"


# --- `status` --------------------------------------------------------------------------------


def outcome_of(action: Action) -> str:
    if isinstance(action, Spawn):
        return "spawn"
    if isinstance(action, Complete):
        return "complete"
    return "budget-exhausted" if action.cause == BUDGET_CAUSE else "needs-human"


def status_object(
    slug: str,
    inputs: LoopInputs,
    states: Mapping[str, Series],
    action: Action,
    stop: Mapping[str, Any] | None,
) -> dict[str, Any]:
    pending = action.key.id if isinstance(action, Spawn) and action.reissued else None
    used, budget = iterations_of(inputs)
    return {
        "schema": SCHEMA,
        "slug": slug,
        "outcome": outcome_of(action),
        "pending_request": pending,
        "iterations": {"used": used, "budget": budget},
        "steps": [_step_row(step, states[step.id], inputs) for step in inputs.steps],
        "stop": None if stop is None else dict(stop),
    }


def _step_row(step: PlanStep, state: Series, inputs: LoopInputs) -> dict[str, Any]:
    commits = [r.commit for r in inputs.driver_records(step.id) if r.commit]
    assignee = "implementer" if isinstance(step.assignee, Implementer) else step.assignee.name
    return {
        "step": step.id,
        "assignee": assignee,
        "verdict": _shown_verdict(state, inputs.verdicts.get(step.id, {}).get("verdict", PENDING)),
        "attempts": _attempts_of(state),
        "review": _REVIEW_WORDS.get(type(state.review)) if isinstance(state, Verified) else None,
        "commit": commits[-1][:SHORT_SHA] if commits else None,
    }


def _shown_verdict(state: Series, word: str) -> str:
    """In flight while a request is outstanding; never exhausted for a series still open."""
    if isinstance(state, Running):
        return IN_FLIGHT
    held = isinstance(state, (Exhausted, HumanVerdict))
    return PENDING if word == EXHAUSTED and not held else word


def _attempts_of(state: Series) -> int:
    if isinstance(state, (Running, Verified)):
        return state.n
    if isinstance(state, (Failed, Exhausted, Marked)):
        return spent(state.attempts)
    return 0


def next_line(slug: str, action: Action, invoke: str | Invocation) -> str:
    """The status table's last line: what to run, or what is pending, done or stopped."""
    if isinstance(action, Spawn) and action.reissued:
        return f"the Agent call for {action.key.id} is pending; record it when it ends"
    if isinstance(action, Spawn):
        return f"run `{Invocation.of(invoke).command('next', slug)}` to start {action.key.id}"
    if isinstance(action, Complete):
        return "every step is done"
    return f"stopped ({action.cause}): {action.evidence}"


def status_table(status: Mapping[str, Any], next_line: str, steps: Sequence[PlanStep]) -> str:
    """The human table: a header, one row per plan step, and the next action; a step's
    attempts read against its own bound's cap."""
    caps = {step.id: step_cap(step) for step in steps}
    rows = [
        (
            row["step"],
            row["assignee"],
            row["verdict"],
            f"{row['attempts']}/{caps[row['step']]}" if row["attempts"] else DASH,
            row["review"] or DASH,
            row["commit"] or DASH,
        )
        for row in status["steps"]
    ]
    widths = [max(len(cell) for cell in col) for col in zip(_TABLE_HEADERS, *rows)]  # noqa: B905
    table = [
        _COLUMN_GAP.join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip()  # noqa: B905
        for row in (_TABLE_HEADERS, *rows)
    ]
    used, budget = status["iterations"]["used"], status["iterations"]["budget"]
    head = f"{status['slug']} · iterations {used}/{budget}"
    if status["pending_request"]:
        head += f" · pending {status['pending_request']}"
    return "\n".join([head, *table, f"next: {next_line}"]) + "\n"
