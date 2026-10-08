"""The `goal` verb: scaffold a one-step goal plan every existing reader parses, or write nothing.

It writes the plan, a progress file, a task brief, the baseline reading of the goal's check and
deny rules on the protected paths in the repository's local harness settings. A refusal is free:
the options parse once into a `GoalSpec`, the documents and merged settings are composed as text
(the plan is read back by the plan reader), the check runs once, and only then is anything
written. The settings are the repository's, not the task's: their rules bind every session
started in that checkout, so the printed object names the file and warns in a primary checkout.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from _git_runner import GitUnavailableError, run_git
from _goal_record import (
    BASELINE_REQUEST,
    PROGRESS_HEADING,
    entry_path,
    is_protected,
    names_directory,
    protected_set,
)
from _loop_fields import (
    Check,
    Expectation,
    GoalBudget,
    Met,
    UnreadableCheck,
    evaluate_check,
    parse_check_field,
    parse_iterations,
)
from _plan_steps import Implementer, parse_plan_steps
from _repo_root import git_toplevel_from_cwd
from _step_loop_cli import SCHEMA, SUMMARY_PREFIX, CallerError, warning_lines
from _step_loop_files import gate_heading, write_atomic, write_gate_block
from _step_loop_gate import GoalTargets, parse_pytest_summary, render_result_line
from _step_loop_io import OUTER_LOOP_PREFIXES, OutsideRepoError, normalise_path, run_check
from _step_loop_record_gate import RESULTS_FILE, classified

PLAN_FILE, WIP_FILE, BRIEF_FILE = "IMPLEMENTATION_PLAN.md", "WIP.md", "TASK_BRIEF.md"
SETTINGS_FILE = ".claude/settings.local.json"
_TASK_FILES = (PLAN_FILE, WIP_FILE, BRIEF_FILE, RESULTS_FILE)
STEP_ID, TITLE_LIMIT = "1", 60
PRIMARY_CHECKOUT, SETTINGS_NOT_IGNORED = "primary-checkout", "settings-not-ignored"
CHECK_COMPLETES_EARLY = "check-completes-early"
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


@dataclass(frozen=True)
class Baseline:
    """The check run once: the gate block's lines, the tests passing and the targets failing."""

    lines: tuple[str, ...]
    passes: int
    targets: int


@dataclass(frozen=True)
class GoalSpec:
    """A goal as asked for, parsed once; `protect` lists the outer-loop paths first."""

    slug: str
    goal: str
    check: Check
    expects: str
    iterations: int
    paths: tuple[str, ...]
    protect: tuple[str, ...]

    @property
    def title(self) -> str:
        return textwrap.shorten(self.goal, width=TITLE_LIMIT, placeholder="…")


def scaffold(args: argparse.Namespace) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Write the goal plan the options ask for and return the object to print and the lines for
    standard error; or refuse, writing nothing."""
    repo = git_toplevel_from_cwd()
    if repo is None:
        _refuse("no repository was found", "run it from the repository root")
    spec = parse_spec(args, repo)
    task = repo / ".ai-work" / spec.slug
    if (task / PLAN_FILE).exists():
        _refuse(f"{task / PLAN_FILE} already exists", "pick another slug, or remove that plan")
    plan = _plan_text(spec)
    _require_reads_back(spec, plan)
    settings = repo / SETTINGS_FILE
    rules = tuple(edit_rule(entry, repo) for entry in protected_set(spec.protect))
    merged = _merged_settings(settings, rules)
    baseline = _baseline(repo, spec)
    task.mkdir(parents=True, exist_ok=True)
    write_atomic(task / PLAN_FILE, plan)
    write_atomic(task / WIP_FILE, _wip_text(spec))
    write_atomic(task / BRIEF_FILE, _brief_text(spec))
    write_gate_block(task / RESULTS_FILE, STEP_ID, BASELINE_REQUEST, baseline.lines)
    settings.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(settings, json.dumps(merged, indent=2) + "\n")
    return _report(repo, spec, baseline)


def _refuse(why: str, fix: str) -> NoReturn:
    raise CallerError("usage", f"goal failed because {why}. To fix: {fix}.")


def parse_spec(args: argparse.Namespace, repo: Path) -> GoalSpec:
    """The options as a `GoalSpec`; a call that could not be scaffolded safely is refused."""
    if not _SLUG_RE.match(args.slug):
        _refuse(f"the slug {args.slug!r} is no directory name", "use letters, digits, - and _")
    goal = _one_line(args.goal, "--goal")
    expects = _one_line(args.expects, "--expects")
    check = _check(_one_line(args.check, "--check"), expects)
    iterations = parse_iterations(args.iterations)
    if not isinstance(iterations, int):
        _refuse(
            f"--iterations {args.iterations!r} is not a whole number of at least 1",
            "give the number of iterations the loop may spend, such as 5",
        )
    paths = _paths(args.paths or (), repo)
    if not paths:
        _refuse("no --paths were given, so no iteration could change anything", "name the files")
    protect = tuple(
        sorted(
            _paths(args.protect or (), repo), key=lambda p: not p.startswith(OUTER_LOOP_PREFIXES)
        )
    )
    guarded = protected_set(protect)
    inside = next((path for path in paths if is_protected(path, guarded)), None)
    if inside is not None:
        _refuse(
            f"the --paths entry {inside} is under a protected path, so the goal could never be met",
            "move it out of the protected set, or drop it from --protect",
        )
    return GoalSpec(args.slug, goal, check, expects, iterations, paths, protect)


def _one_line(text: str, option: str) -> str:
    one = " ".join(text.split())
    if not one or "\n" in text.strip():
        _refuse(f"{option} is empty or spans lines", f"give {option} one sentence")
    return one


def _check(command: str, expects: str) -> Check:
    read = parse_check_field(f"Check: `{command}` expects {expects}")
    try:
        shlex.split(command)
    except ValueError as unsplit:
        read = UnreadableCheck(str(unsplit), command)
    if not isinstance(read, Check):
        why = getattr(read, "reason", "it is no check")
        _refuse(
            f"the check and what it expects are not in the check grammar ({why})",
            "give --check a command without a backtick and --expects like pass=3 fail=0",
        )
    return read


def _paths(raw: tuple[str, ...], repo: Path) -> tuple[str, ...]:
    try:
        return tuple(dict.fromkeys(normalise_path(path, repo) for path in raw))
    except OutsideRepoError as outside:
        _refuse(str(outside), "name paths inside the repository")


def _plan_text(spec: GoalSpec) -> str:
    fields = [
        "**Assignee**: implementer",
        "**Files**: " + ", ".join(f"`{path}`" for path in spec.paths),
        "**Read-only**: " + (", ".join(f"`{path}`" for path in spec.protect) or "none"),
        f"**Check**: `{spec.check.command}` expects {spec.expects}",
        f"**Iterations**: {spec.iterations}",
        "**Done when**: the check is met and no protected path changed",
    ]
    return "\n".join([f"# Plan: {spec.slug}", "", f"### Step {STEP_ID}: {spec.title}", "", *fields,
                      "", spec.goal, ""])  # fmt: skip


def _wip_text(spec: GoalSpec) -> str:
    return (
        f"# WIP: {spec.slug}\n\n## Progress\n\n- [ ] Step {STEP_ID}: {spec.title}\n\n"
        f"{PROGRESS_HEADING}\n"
    )


def _brief_text(spec: GoalSpec) -> str:
    guards = [
        f"- `{entry}` is read-only: a change there stops the loop"
        for entry in protected_set(spec.protect)
    ]
    return "\n".join([f"# Task Brief: {spec.slug}", "", "## Key Signals", "", f"- {spec.goal}", "",
                      "## Health Guards", "", *guards, ""])  # fmt: skip


def _require_reads_back(spec: GoalSpec, plan: str) -> None:
    """Refuse a plan the plan reader would read differently from what was asked."""
    expected = (spec.paths, spec.protect, spec.check, GoalBudget(spec.iterations), Implementer())
    read = tuple(
        (s.files, s.read_only, s.check, s.bound, s.assignee) for s in parse_plan_steps(plan)
    )
    if read != (expected,):
        _refuse(
            "the plan would not read back as given",
            "paths hold only letters, digits and . / _ - ; each --protect entry holds a /; "
            "--goal is a sentence that is no field or step line",
        )


def _baseline(repo: Path, spec: GoalSpec) -> Baseline:
    """The check run once: the gate block that reads as the goal's unmet start, and its counts."""
    command = spec.check.command
    ran = run_check(repo, command)
    if ran.problem is not None:
        _refuse(f"the check did not finish ({ran.problem})", "make the check run to its end")
    summary = parse_pytest_summary(ran.output)
    if summary is None:
        _refuse(
            "the check's output holds no pytest summary line, so the gate could never read it",
            "use a pytest command that prints its summary, without -q -q",
        )
    run = classified(ran, GoalTargets(frozenset(summary.failed_ids)), command)
    body = (f"Command: `{command}`", render_result_line(run))
    block = "\n".join([gate_heading(STEP_ID, BASELINE_REQUEST), "", *body])
    if isinstance(evaluate_check(spec.check, STEP_ID, block), Met):
        _refuse(
            "the check already meets what it expects, so no iteration could complete it",
            "state a goal the check does not yet meet",
        )
    return Baseline(body, summary.counts.passed, run.pending)


def edit_rule(entry: str, repo: Path) -> str:
    """An edit rule anchored with `/`: a bare file name would match at any depth."""
    base = entry_path(entry)
    directory = names_directory(entry) or (repo / base).is_dir()
    return f"Edit(/{base}/**)" if directory else f"Edit(/{base})"


def _merged_settings(path: Path, rules: tuple[str, ...]) -> dict[str, Any]:
    """The settings with `rules` appended to `permissions.deny` where absent, all else kept."""
    settings = _read_settings(path)
    permissions, deny = settings.get("permissions", {}), None
    if isinstance(permissions, dict):
        deny = permissions.get("deny", [])
    if not isinstance(deny, list):
        _refuse(f"{path} holds a permissions.deny that is no list", "repair or remove the file")
    added = [rule for rule in dict.fromkeys(rules) if rule not in deny]
    return {**settings, "permissions": {**permissions, "deny": [*deny, *added]}}


def _read_settings(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        loaded = None
    if not isinstance(loaded, dict):
        _refuse(f"{path} is not a JSON object", "repair or remove the file, then run goal again")
    return loaded


def _report(
    repo: Path, spec: GoalSpec, baseline: Baseline
) -> tuple[dict[str, Any], tuple[str, ...]]:
    written = [f".ai-work/{spec.slug}/{name}" for name in _TASK_FILES] + [SETTINGS_FILE]
    warnings = []
    if _in_primary_checkout(repo):
        warnings.append((PRIMARY_CHECKOUT, _PRIMARY_MESSAGE))
    ignored = _git(repo, "check-ignore", "-q", SETTINGS_FILE)
    if ignored is not None and ignored.returncode == 1:
        warnings.append((SETTINGS_NOT_IGNORED, _NOT_IGNORED_MESSAGE))
    early = early_completion_message(spec.check, baseline.passes, baseline.targets)
    if early is not None:
        warnings.append((CHECK_COMPLETES_EARLY, early))
    doc = {
        "schema": SCHEMA,
        "slug": spec.slug,
        "files": written,
        "warnings": [{"code": code, "message": message} for code, message in warnings],
    }
    summary = f"{SUMMARY_PREFIX}scaffolded the goal plan {spec.slug}: {len(written)} files"
    return doc, (summary, *warning_lines(warnings))


_PRIMARY_MESSAGE = (
    f"this is a primary checkout, and the deny rules in {SETTINGS_FILE} bind every session "
    "started in it. To fix: scaffold from a linked worktree, or remove the rules after the run"
)
_NOT_IGNORED_MESSAGE = (
    f"git does not ignore {SETTINGS_FILE}, so the first iteration would stop on it as a "
    "protected change. To fix: add it to .gitignore"
)


def early_completion_message(check: Check, passes: int, targets: int) -> str | None:
    """Why the check could be met with some of the goal's own failing tests still failing, or
    None when its expectation binds every target. Pure in the parsed check and the baseline.

    A goal check's `fail=0` is always met, because the failing tests the goal is working on
    read `pending`; only `pending=0`, or a pass count of every test, says they all pass."""
    wanted = next((e.count for e in check.expectations if e.key == "pass"), 0)
    total = passes + targets
    if targets == 0 or wanted >= total or _binds_pending(check):
        return None
    open_targets = min(targets, total - wanted)
    return (
        f"the check can be met with up to {open_targets} of the {targets} failing tests still "
        "failing: fail=0 is always met, because the goal's own failing tests read pending. "
        f"To fix: expect pending=0, or pass={total}"
    )


def _binds_pending(check: Check) -> bool:
    return Expectation("pending", "=", 0) in check.expectations


def _in_primary_checkout(repo: Path) -> bool:
    """A linked worktree's git directory is not the repository's common one."""
    done = _git(repo, "rev-parse", "--git-dir", "--git-common-dir")
    if done is None or done.returncode != 0:
        return False
    here, common = (repo / line for line in done.stdout.splitlines()[:2])
    return here.resolve() == common.resolve()


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return run_git(repo, *args)
    except GitUnavailableError:
        return None
