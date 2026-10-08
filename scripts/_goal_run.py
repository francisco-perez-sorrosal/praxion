"""The terminal form of the goal loop: what `run` checks before it starts a worker, and the
line it prints for each iteration.

`run` is the driver's own `drive` loop with a `HeadlessWorker` behind the `Spawner` seam, so
this module holds no loop. A refusal here is a `CallerError` raised before any worker starts;
a worker that could not be started is raised after the loop returns, naming its cause. The
driver passes its `drive` in and calls this module, never the other way round, because the
driver started as a script is `__main__` and a fresh `import step_loop` would be a second copy.

Runs on the plain `python3` the scripts are invoked with, so no `X | Y` at runtime.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from _goal_record import protected_set
from _goal_scaffold import SETTINGS_FILE
from _goal_scaffold import _deny_rule as deny_rule  # noqa: PLC2701 -- one rule, one spelling
from _goal_worker import HeadlessWorker, resolver_invocation, shell_rule
from _goal_worker import _return_types as spawn_return_types  # noqa: PLC2701
from _loop_fields import Check, GoalBudget
from _plan_steps import PlanStep
from _step_loop_cli import SUMMARY_PREFIX, CallerError
from _step_loop_files import WORKER_STEM, NoWorkerResult, WorkerEnd, read_worker_end

SHORT_SHA = 7
SUCCESS = "success"
NOT_STARTED_CODE = "worker-not-started"
_LEDGER_SEPARATOR = "; "
_NOT_KEPT = "not kept: "
STARTED_SUFFIX = ".started"


def _refuse(why: str, fix: str) -> CallerError:
    return CallerError("usage", f"run failed because {why}. To fix: {fix}.")


# --- Before any worker ------------------------------------------------------------------------


def start_worker(
    steps: Sequence[PlanStep], repo: Path, directory: Path, args: argparse.Namespace
) -> MarkedWorker:
    """The worker for the plan's goal step, or the refusal that spares a paid start."""
    goal = next((s for s in steps if isinstance(s.bound, GoalBudget)), None)
    if goal is None:
        raise _refuse(
            "the plan has no goal step, a step with an Iterations: line",
            "scaffold one with the goal verb",
        )
    if not isinstance(goal.check, Check):
        raise _refuse(f"step {goal.id} has no readable Check: line", "write the goal's check")
    if args.max_turns < 1 or args.max_budget_usd <= 0:
        raise _refuse("--max-turns and --max-budget-usd must be positive", "give a bound above 0")
    try:
        shell_rule(goal.check.command)
    except ValueError as error:
        raise _refuse(str(error), "state the check as one pytest command") from error
    missing = missing_deny_rules(goal, repo)
    if missing:
        raise _refuse(
            f"{SETTINGS_FILE} lacks the deny rule for {', '.join(missing)}",
            "scaffold the goal with the goal verb, or add the rules there",
        )
    resolver = resolver_invocation(sys.argv[0], os.environ.get("PATH", ""))
    return MarkedWorker(
        HeadlessWorker(
            repo, directory, goal.check.command, resolver, args.max_turns, args.max_budget_usd
        )
    )


@dataclass(frozen=True)
class MarkedWorker:
    """The headless worker behind a start marker, `WORKER_<request>.started`, written before
    its process is launched. A request that comes again with no worker file was only previewed
    (a `next` wrote its attempt) when it has no marker, and starts fresh; with a marker its
    worker may have run, so it is not started a second time."""

    inner: HeadlessWorker

    def spawn(self, request: Mapping[str, Any]) -> Any:
        directory, name = self.inner.task_dir, request["id"]
        if read_worker_end(directory, name) is not None:  # the file answers; no process starts
            return self.inner.spawn(request)
        marker = directory / f"{WORKER_STEM}_{name}{STARTED_SUFFIX}"
        if request.get("reissued") and marker.exists():
            return spawn_return_types()[1](
                "a reissued request has a start marker and no worker file, so its worker may"
                " have run"
            )
        marker.write_text(f"{name}\n", encoding="utf-8")
        outcome = self.inner.spawn({**request, "reissued": False})
        if read_worker_end(directory, name) is None:  # the process never ran: nothing to guard
            marker.unlink(missing_ok=True)
        return outcome


def location(repo: Path, base_ref: str, args: argparse.Namespace) -> tuple[str, ...]:
    """The options every command printed under `run` ends with: the roots as given (the
    repository root as found when it was not given) and the base the loop reads against."""
    options = ("--repo-root", args.repo_root or str(repo), "--base-ref", base_ref)
    return (*options, "--worktree-root", args.worktree_root) if args.worktree_root else options


def missing_deny_rules(goal: PlanStep, repo: Path) -> tuple[str, ...]:
    """The protected paths whose edit rule is absent from the repository's local settings."""
    try:
        settings = json.loads((repo / SETTINGS_FILE).read_text("utf-8"))
        denied = settings["permissions"]["deny"]
    except (OSError, ValueError, KeyError, TypeError):
        denied = []
    if not isinstance(denied, list):
        denied = []
    wanted = {entry: deny_rule(entry, repo) for entry in protected_set(goal.read_only)}
    return tuple(entry for entry, rule in wanted.items() if rule not in denied)


# --- Each iteration's line --------------------------------------------------------------------


class Reporter:
    """The `observe` callback: one stderr line per recorded iteration, and the reason the last
    request could not start (the withdrawal of a request records no iteration)."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.not_started = "no reason was given"

    def __call__(self, request: Mapping[str, Any], returned: Any, doc: Mapping[str, Any]) -> None:
        reason = getattr(returned, "reason", None)  # only a `NotStarted` carries one
        if reason is not None:
            self.not_started = reason
        elif "recorded" in doc:  # an `error` envelope recorded nothing
            end = read_worker_end(self.directory, request["id"])
            print(iteration_line(request["id"], doc["recorded"], end), file=sys.stderr, flush=True)

    def refusal(self) -> CallerError:
        """The error for a loop that ended because a worker could not start."""
        return CallerError(
            NOT_STARTED_CODE,
            f"run failed because a worker could not be started: {self.not_started}."
            " To fix: remove that cause (a worker file in the task directory shows what it"
            " printed), then run it again.",
        )


def iteration_line(
    request: str, recorded: Mapping[str, Any], end: WorkerEnd | NoWorkerResult | None
) -> str:
    """`step_loop: <request> <committed sha|no commit (why)> · <n> turns · cost $<x>`, then the
    permission denials and a non-success subtype when the worker's result reported them."""
    commit = recorded["commit"]
    kept = f"committed {commit[:SHORT_SHA]}" if commit else f"no commit ({_why(recorded)})"
    turns = recorded["turns"]
    parts = [f"{SUMMARY_PREFIX}{request} {kept}", f"{'unknown' if turns is None else turns} turns"]
    if isinstance(end, WorkerEnd):
        parts.append(f"cost ${_decimal(end.cost_usd)}" if end.cost_usd is not None else "cost n/a")
        if end.denials:
            parts.append(f"{end.denials} permission denials")
        if end.subtype != SUCCESS:
            parts.append(f"stopped at {end.subtype}")
    return " · ".join(parts)


def _why(recorded: Mapping[str, Any]) -> str:
    """Why nothing was committed: the judgement's own words, else the gate's verdict."""
    _, _, said = (recorded.get("ledger") or "").partition(_LEDGER_SEPARATOR)
    reason = said.split(_LEDGER_SEPARATOR)[0].removeprefix(_NOT_KEPT)
    return reason or str((recorded.get("gate") or {}).get("verdict"))


def _decimal(cost: float) -> str:
    """The cost as plain decimal text (a float's `repr`, never an exponent)."""
    return format(Decimal(repr(cost)), "f")
