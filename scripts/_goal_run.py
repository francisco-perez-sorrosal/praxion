"""The terminal form of the goal loop: what `run` checks before it starts a worker, and the
line it prints for each iteration.

`run` is the driver's own `drive` loop with a `HeadlessWorker` behind the `Spawner` seam, so
this module holds no loop. A refusal here is a `CallerError` raised before any worker starts;
a worker that could not be started is raised after the loop returns, naming its cause. The
driver calls this module and never the other way round: the driver started as a script is
`__main__`, and a fresh `import step_loop` here would be a second copy of it.

Runs on the plain `python3` the scripts are invoked with, so no `X | Y` at runtime.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from _goal_record import KEPT_WORDS, judgement_words, protected_set
from _goal_record import is_protected as is_covered
from _goal_scaffold import PLAN_FILE, SETTINGS_FILE, WIP_FILE, edit_rule, settings_tracked
from _goal_scaffold import edit_rule as deny_rule
from _goal_worker import _READ_TOOLS as READ_TOOLS  # the worker holds these: a rule adds nothing
from _goal_worker import HeadlessWorker, resolver_invocation, shell_rule
from _loop_fields import Check, GoalBudget
from _plan_steps import PlanStep, parse_plan_steps
from _step_loop_cli import SUMMARY_PREFIX, CallerError, error_line, warning_lines
from _step_loop_files import (
    STARTED_SUFFIX as STARTED_SUFFIX,  # re-exported: callers name the marker by this suffix
)
from _step_loop_files import (
    NoWorkerResult,
    WorkerEnd,
    read_worker_end,
    worker_marker_path,
    worker_result_path,
)
from _step_loop_io import GitCommandError, paths_differing_from_head

SHORT_SHA = 7
SUCCESS = "success"
NOT_STARTED_CODE = "worker-not-started"
MIN_BUDGET_USD = 0.01  # the smallest the worker's `.2f` bound still states
MAX_NAMED_PATHS = 5  # a message names this many changed paths, then counts the rest
USER_SETTINGS = "settings.json"
PROJECT_SETTINGS = ".claude/settings.json"
CONFIG_DIR_VARIABLE = "CLAUDE_CONFIG_DIR"
_RULE_RE = re.compile(r"(?P<tool>[^()\s]+)(?:\((?P<pattern>.*)\))?", re.DOTALL)
_PATH_RULE_TOOLS = ("Write", "MultiEdit", "NotebookEdit")  # accepted, never consulted
_WIDE_PATTERNS = ("", "*", ":*")


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
    if (
        args.max_turns < 1
        or not math.isfinite(args.max_budget_usd)
        or (args.max_budget_usd < MIN_BUDGET_USD)
    ):
        raise _refuse(
            f"--max-turns must be 1 or more and --max-budget-usd {MIN_BUDGET_USD} or more",
            "give bounds the worker can run within",
        )
    try:
        shell_rule(goal.check.command)
    except ValueError as error:
        raise _refuse(str(error), "state the check as one pytest command") from error
    resolver = resolver_invocation(sys.argv[0], os.environ.get("PATH", ""))
    guard = Preconditions(goal, repo, directory, (goal.check.command, resolver))
    standing = guard.standing()
    if standing.failures:
        raise _refuse(
            "; ".join(f.cause for f in standing.failures),
            "; ".join(f.fix for f in standing.failures),
        )
    return MarkedWorker(
        HeadlessWorker(
            repo,
            directory,
            goal.check.command,
            resolver,
            args.max_turns,
            args.max_budget_usd,
            writable=writable_rules(goal.files, repo, directory),
            denied=standing.denied,
        ),
        guard,
    )


@dataclass(frozen=True)
class MarkedWorker:
    """The headless worker behind a start marker, written before its process is launched.
    A request that comes again with no worker file was only previewed (a `next` wrote its
    attempt) when it has no marker, and starts fresh; with a marker its worker may have run, so
    it is not started a second time. A worker file that holds no result is a process that ended
    without one and whose request was withdrawn (the next `next` issues the same request again,
    reissued): that is the retry, and the old file and marker go first.

    Every new process is first checked against `guard`, as the files stand at that moment: a
    failure withdraws the request, so no worker is paid for, and the process that does start is
    denied what that moment's inherited pre-approvals call for."""

    inner: HeadlessWorker
    guard: Preconditions | None = None

    def spawn(self, request: Mapping[str, Any]) -> Any:
        directory, name = self.inner.task_dir, request["id"]
        reissued = bool(request.get("reissued"))
        marker = worker_marker_path(directory, name)
        found = read_worker_end(directory, name)
        if isinstance(found, NoWorkerResult):
            worker_result_path(directory, name).unlink(missing_ok=True)
            marker.unlink(missing_ok=True)
            found = None
        if found is not None or (reissued and marker.exists()):
            return self.inner.spawn(request)  # answers from its file, or refuses a reissue
        worker = self.inner
        if self.guard is not None:
            standing = self.guard.standing()
            if standing.failures:
                return self.inner.not_started("; ".join(f.said() for f in standing.failures))
            worker = replace(self.inner, denied=standing.denied)
        marker.write_text(f"{name}\n", encoding="utf-8")
        try:
            return worker.spawn({**request, "reissued": False})
        finally:  # no worker file: the process never ran or was interrupted, nothing to guard
            if read_worker_end(directory, name) is None:
                marker.unlink(missing_ok=True)

    def reporter(self) -> Reporter:
        """The `observe` callback for this worker's run, aware of the goal step's `Files:`."""
        if self.guard is None:
            return Reporter(self.inner.task_dir)
        return Reporter(self.inner.task_dir, self.inner.repo, self.guard.goal.files)


# --- What must hold before every worker --------------------------------------------------------


@dataclass(frozen=True)
class Failure:
    """One precondition that does not hold: what is wrong and what to do about it."""

    cause: str
    fix: str

    def said(self) -> str:
        return f"{self.cause}; to fix: {self.fix}"


@dataclass(frozen=True)
class Standing:
    """The preconditions as the files stand at one moment: what fails, and the deny rules that
    neutralise the inherited pre-approvals."""

    failures: tuple[Failure, ...]
    denied: tuple[str, ...]


@dataclass(frozen=True)
class Preconditions:
    """What `run` holds true before each worker, read from the files each time it is asked:
    the goal's protected paths are denied, no inherited pre-approval is beyond neutralising,
    the tree holds no change outside the goal step's `Files:` and the task directory, and the
    plan still holds the goal step's block as `run` found it."""

    goal: PlanStep
    repo: Path
    directory: Path
    commands: tuple[str, str]  # the check and the test-scope resolver the worker may run

    def standing(self) -> Standing:
        denied, refused = _inherited_denials(self.repo, self.commands)
        failures = (
            *_missing_rules(self.goal, self.repo),
            *refused,
            *_outside_files(self.goal, self.repo, self.directory),
            *_edited_plan(self.goal, self.directory),
        )
        return Standing(failures, denied)


def _missing_rules(goal: PlanStep, repo: Path) -> tuple[Failure, ...]:
    missing = missing_deny_rules(goal, repo)
    if not missing:
        return ()
    return (
        Failure(
            f"{SETTINGS_FILE} lacks the deny rule for {', '.join(missing)}",
            "scaffold the goal with the goal verb, or add the rules there",
        ),
    )


def _outside_files(goal: PlanStep, repo: Path, directory: Path) -> tuple[Failure, ...]:
    try:
        stray = changed_outside_files(repo, directory, goal.files)
    except (GitCommandError, OSError) as error:
        return (Failure(f"the tree cannot be read ({error})", "make the repository readable"),)
    others = tuple(path for path in stray if path != SETTINGS_FILE)
    ignore_fix = (
        f"stop tracking {SETTINGS_FILE} with git rm --cached, add it to .gitignore, and commit"
        " both changes"
        if settings_tracked(repo)
        else f"add {SETTINGS_FILE} to .gitignore and commit the ignore change"
    )
    unignored = (
        Failure(
            f"git does not ignore {SETTINGS_FILE}, which holds the worker's deny rules", ignore_fix
        ),
    )
    changed = (
        Failure(
            f"the tree holds changes outside step {goal.id}'s Files: and the task directory:"
            f" {_named(others)}",
            "commit or remove those changes, or add those paths to the step's Files:",
        ),
    )
    return (unignored if SETTINGS_FILE in stray else ()) + (changed if others else ())


def _edited_plan(goal: PlanStep, directory: Path) -> tuple[Failure, ...]:
    try:
        steps = parse_plan_steps((directory / PLAN_FILE).read_text("utf-8"))
    except (OSError, ValueError) as error:
        return (Failure(f"{PLAN_FILE} cannot be read ({error})", "restore the plan"),)
    if any(step.id == goal.id and step.digest == goal.digest for step in steps):
        return ()
    return (
        Failure(
            f"{PLAN_FILE} no longer holds step {goal.id} as this run found it",
            "restore the step's block, or run again to take the edited one",
        ),
    )


def changed_outside_files(repo: Path, directory: Path, files: Sequence[str]) -> tuple[str, ...]:
    """The paths that differ from HEAD (untracked ones that are not ignored included) outside
    the given `Files:` entries and the task directory."""
    declared = list(files)
    try:
        declared.append(str(directory.resolve().relative_to(repo.resolve())))
    except ValueError:  # a task directory outside the repository holds no path of its tree
        pass
    return tuple(
        path for path in paths_differing_from_head(repo, ["."]) if not is_covered(path, declared)
    )


def _named(paths: Sequence[str]) -> str:
    shown = ", ".join(paths[:MAX_NAMED_PATHS])
    return (
        shown
        if len(paths) <= MAX_NAMED_PATHS
        else f"{shown} and {len(paths) - MAX_NAMED_PATHS} more"
    )


# --- What the worker may write, and what it would inherit -----------------------------------


def writable_rules(files: Sequence[str], repo: Path, directory: Path) -> tuple[str, ...]:
    """The edit rules the worker is granted: each `Files:` entry, then the task's progress file
    (written as an absolute rule when the task directory lies outside the repository)."""
    root, task = repo.resolve(), directory.resolve()
    try:
        progress = edit_rule(str((task / WIP_FILE).relative_to(root)), repo)
    except ValueError:
        progress = f"Edit(/{task / WIP_FILE})"
    return tuple(dict.fromkeys((*(edit_rule(entry, repo) for entry in files), progress)))


@dataclass(frozen=True)
class Inherited:
    """A rule of some settings file's `permissions.allow`, and the file that holds it."""

    rule: str
    file: Path


def inherited_rules(repo: Path) -> tuple[Inherited, ...]:
    """The allow rules of the user, project and local settings, which the worker loads and
    which `dontAsk` honours as pre-approvals. A file that is missing, unreadable or not a JSON
    object holds no rules."""
    config = os.environ.get(CONFIG_DIR_VARIABLE)
    user = (Path(config) if config else Path.home() / ".claude") / USER_SETTINGS
    files = (user, repo / PROJECT_SETTINGS, repo / SETTINGS_FILE)
    return tuple(Inherited(rule, file) for file in files for rule in _allow_rules(file))


def _allow_rules(file: Path) -> tuple[str, ...]:
    try:
        allow = json.loads(file.read_text("utf-8"))["permissions"]["allow"]
    except (OSError, ValueError, KeyError, TypeError):
        return ()
    return tuple(rule for rule in allow if isinstance(rule, str)) if isinstance(allow, list) else ()


class Treatment(Enum):
    """What `run` does with one inherited allow rule."""

    MIRROR = "mirror"  # the worker gets a deny rule of the same text
    IGNORE = "ignore"  # it grants the worker nothing it could use
    REFUSE = "refuse"  # it cannot be neutralised, so `run` does not start


def classify(rule: str, commands: Sequence[str]) -> Treatment:
    """The treatment of one allow rule, given the check and resolver commands the worker runs.

    A scoped `Bash` rule that cannot approve either command is mirrored; one that could, or
    that covers every command, is refused, as is any rule granting edits at large. A rule of a
    tool the worker is not granted (a web fetch, a search, an agent, an MCP tool) is mirrored.
    A path rule of a tool the harness never consults for paths and a read rule are ignored.

    `Bash(X:*)` and `Bash(X *)` are one rule to the harness, so a rule's head is its pattern up
    to the first `*` without the trailing `:` or space, and both spellings get one treatment."""
    parsed = _RULE_RE.fullmatch(rule)
    if parsed is None:
        return Treatment.IGNORE
    tool, pattern = parsed["tool"], parsed["pattern"]
    if tool == "Edit" or (tool in _PATH_RULE_TOOLS and pattern is None):
        return Treatment.REFUSE
    if tool in _PATH_RULE_TOOLS or tool in READ_TOOLS:
        return Treatment.IGNORE
    if tool != "Bash":
        return Treatment.MIRROR
    head = (pattern or "").partition("*")[0].removesuffix(":").rstrip()
    if pattern in _WIDE_PATTERNS or not head or any(c.startswith(head) for c in commands):
        return Treatment.REFUSE
    return Treatment.MIRROR


def _inherited_denials(
    repo: Path, commands: Sequence[str]
) -> tuple[tuple[str, ...], tuple[Failure, ...]]:
    """The deny rules that neutralise the inherited pre-approvals, and a failure naming each
    one that cannot be neutralised and its file."""
    treated = [(i, classify(i.rule, commands)) for i in inherited_rules(repo)]
    refused = [f"{i.rule} in {i.file}" for i, treatment in treated if treatment is Treatment.REFUSE]
    denied = tuple(i.rule for i, treatment in treated if treatment is Treatment.MIRROR)
    if not refused:
        return denied, ()
    failure = Failure(
        f"the worker would inherit pre-approvals it must not hold: {'; '.join(refused)}",
        "remove them from those files, or narrow each to a command that is neither the"
        " check nor the test-scope resolver nor a file edit",
    )
    return denied, (failure,)


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
    request could not start (the withdrawal of a request records no iteration). Given the
    repository and the goal step's `Files:`, it also says what a completed run left that no
    commit holds."""

    def __init__(
        self, directory: Path, repo: Path | None = None, files: Sequence[str] = ()
    ) -> None:
        self.directory = directory
        self.repo = repo
        self.files = tuple(files)
        self.not_started = "no reason was given"

    def __call__(self, request: Mapping[str, Any], returned: Any, doc: Mapping[str, Any]) -> None:
        reason = getattr(returned, "reason", None)  # only a `NotStarted` carries one
        if reason is not None:
            self.not_started = reason
        elif "recorded" in doc:  # an `error` envelope recorded nothing
            end = read_worker_end(self.directory, request["id"])
            lines = (iteration_line(request["id"], doc["recorded"], end), *_warnings_of(doc))
            print(*lines, sep="\n", file=sys.stderr, flush=True)

    def closing(self, doc: Mapping[str, Any]) -> tuple[str, ...]:
        """The lines the run ends with on standard error: the refusal an `error` envelope
        carries, where a stop left the task, or the changes outside `Files:` that a completed
        run left uncommitted."""
        if doc.get("outcome") == "error":
            return (error_line(doc["error"]["message"]),)
        stop = doc.get("stop")
        if stop:
            said = f"{SUMMARY_PREFIX}stopped ({stop['cause']}): {stop['evidence']}"
            return (said, f"{SUMMARY_PREFIX}to resume, run: {stop['resume']}")
        if self.repo is None or doc.get("outcome") != "complete":
            return ()
        try:
            stray = changed_outside_files(self.repo, self.directory, self.files)
        except (GitCommandError, OSError) as error:
            unread = (
                f"complete, but the tree could not be read for changes outside Files: ({error})"
            )
            return (f"{SUMMARY_PREFIX}{unread}",)
        if not stray:
            return ()
        left = f"{SUMMARY_PREFIX}complete, but changes outside the goal step's Files: stand"
        return (f"{left} and no commit holds them: {_named(stray)}",)

    def refusal(self) -> CallerError:
        """The error for a loop that ended because a worker could not start."""
        return CallerError(
            NOT_STARTED_CODE,
            f"run failed because a worker could not be started: {self.not_started}.",
        )


def _warnings_of(doc: Mapping[str, Any]) -> list[str]:
    """What the call's reply said on standard error besides the iteration: its warnings."""
    return warning_lines(tuple((w["code"], w["message"]) for w in doc.get("warnings", ())))


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
    """Why nothing was committed: the judgement's own words, and for work it kept but could not
    commit the gate's refusal, else the gate's verdict."""
    gate = recorded.get("gate") or {}
    reason = judgement_words(recorded.get("ledger"))
    if reason == KEPT_WORDS:
        return f"{reason}, but the commit was refused: {gate.get('evidence')}"
    return reason or str(gate.get("verdict"))


def _decimal(cost: float) -> str:
    """The cost as plain decimal text (a float's `repr`, never an exponent)."""
    return format(Decimal(repr(cost)), "f")
