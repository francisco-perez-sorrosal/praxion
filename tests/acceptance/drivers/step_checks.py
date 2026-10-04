"""Driver for the pipeline reconciler's judgment of plan steps that may declare a completion check.

A scenario names only what varies per step: whether the step declares a `Check:`
(a command plus the counts its `Result:` line must show, and a `pending=` count
where acceptance tests fall due), whether its declared files changed, whether
`WIP.md` claims it done, its recorded `Result:` line, its attempt count and an
optional `[BLOCKED]` replan marking. This driver builds everything else -- a git
checkout whose step files changed after the base commit, the plan, the progress
file and the step's `TEST_RESULTS.md` section, in the shapes the planning
templates document -- and asks the reconciler (`scripts/reconcile_pipeline_state.py`)
for its per-step verdicts, the same way `/resume-pipeline` does.

The bound part is everything that exists at the base commit: legacy plan, progress
and result shapes, and the reconciler's command line and its `step`, `verdict`
and `evidence` fields. The unbound part raises until a binding step connects it
to the designed surface: how a `Check:` is written in a plan step, how an attempt
count and a replan marking are written in `WIP.md`, and how a verdict names its
deciding criterion, its outcome source and the attempt count.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
RECONCILER = REPO_ROOT / "scripts" / "reconcile_pipeline_state.py"
SLUG = "check-step"
DEFAULT_COMMAND = "uv run pytest tests -q --tb=short -rf"
GREEN = "Result: pass=4 fail=0 skip=0"

# Verdicts `/resume-pipeline` answers with an automatic re-spawn of the step's agent.
AUTO_RESUME_VERDICTS = frozenset({"mismatch", "partial", "in-flight"})
_RECONCILER_VERDICT_EXITS = (0, 1, 2)  # clean, recovery needed, needs a human; 3 is an error


class UnboundDriverError(NotImplementedError):
    """Raised by a driver hook not yet bound to the designed surface."""


class Criterion(Enum):
    CHECK = "the step's declared completion check"
    FALLBACK = "the existing evidence: declared files changed plus green tests"
    NONE = "no evidence exists yet"


class OutcomeSource(Enum):
    RUN = "the declared command was run"
    RECORDED = "a result recorded for the step was read"


@dataclass(frozen=True)
class Check:
    """A step's declared completion check: a command and the counts its `Result:` must show."""

    command: str
    passed: int
    failed: int = 0
    skipped: int = 0
    pending: int | None = None  # declared only where the step makes acceptance tests due


UNREADABLE_CHECK = "unreadable"


@dataclass(frozen=True)
class StepSetup:
    number: str
    title: str
    files_changed: bool = True
    claimed_done: bool = True
    result: str | None = GREEN  # the step's recorded `Result:` line; None records no run for it
    check: Check | str | None = None  # a Check, UNREADABLE_CHECK, or no declared check
    tag: str | None = None  # e.g. "mutation: on"
    mutation_line: str | None = None
    attempt: int | None = None
    blocked_for_replan: str | None = None  # WIP marks the step [BLOCKED] with this replan request

    @property
    def files(self) -> tuple[str, ...]:
        return (f"src/step{self.number}.py",)

    @property
    def recorded_command(self) -> str:
        return self.check.command if isinstance(self.check, Check) else DEFAULT_COMMAND


@dataclass(frozen=True)
class PipelineTask:
    root: Path
    slug: str
    base: str


@dataclass(frozen=True)
class StepVerdict:
    raw: dict[str, Any]

    @property
    def verdict(self) -> str:
        return str(self.raw["verdict"])

    @property
    def evidence(self) -> str:
        return str(self.raw.get("evidence", ""))

    @property
    def criterion(self) -> Criterion:
        return _criterion_of(self.raw)

    @property
    def criterion_label(self) -> str:
        return _criterion_label_of(self.raw)

    @property
    def outcome_source(self) -> OutcomeSource | None:
        return _outcome_source_of(self.raw)

    @property
    def attempt(self) -> int | None:
        return _attempt_of(self.raw)


@dataclass(frozen=True)
class Reconciliation:
    exit_code: int
    steps: dict[str, StepVerdict] = field(default_factory=dict)

    def step(self, number: str) -> StepVerdict:
        key = f"Step {number}"
        if key not in self.steps:
            raise AssertionError(f"the reconciler judged no {key!r}: {sorted(self.steps)}")
        return self.steps[key]


# -- Unbound hooks: the designed surface ------------------------------------------


def check_field(check: Check) -> str:
    """The plan-step line(s) declaring `check`, in the designed `Check:` grammar."""
    raise UnboundDriverError(
        "unbound: a plan step declares its completion check in a `Check:` field naming the "
        "command, the pass/fail/skip counts its `Result:` line must show and, where acceptance "
        "tests fall due, the expected `pending=` count -- bind this to the designed grammar"
    )


def unreadable_check_field() -> str:
    """A `Check:` field the plan reader cannot read: the designed label with a garbled value."""
    raise UnboundDriverError(
        "unbound: a plan step carries a `Check:` field whose value the plan reader cannot "
        "read -- bind this to the designed label with a value outside its grammar"
    )


def progress_entry(
    number: str, title: str, done: bool, attempt: int | None, blocked_for_replan: str | None
) -> str:
    """The step's `WIP.md` checklist entry, with its attempt count and replan marking if any."""
    if attempt is None and blocked_for_replan is None:
        return f"- [{'x' if done else ' '}] Step {number}: {title}"
    raise UnboundDriverError(
        "unbound: `WIP.md` records a step's attempt number (and, after the attempt cap, a "
        "`[BLOCKED]` marking with a replan request) -- bind this to the designed entry shape"
    )


def _criterion_of(raw: dict[str, Any]) -> Criterion:
    raise UnboundDriverError(
        "unbound: each reconciler verdict names the criterion that decided it -- the declared "
        "check, the fallback evidence, or none -- bind this to the designed verdict field"
    )


def _criterion_label_of(raw: dict[str, Any]) -> str:
    raise UnboundDriverError(
        "unbound: the text by which a verdict names its deciding criterion -- bind this to "
        "the designed verdict field"
    )


def _outcome_source_of(raw: dict[str, Any]) -> OutcomeSource | None:
    raise UnboundDriverError(
        "unbound: a check-decided verdict says whether its outcome came from running the "
        "declared command or from a result recorded for the step -- bind this to the designed "
        "verdict field"
    )


def _attempt_of(raw: dict[str, Any]) -> int | None:
    raise UnboundDriverError(
        "unbound: the reconciler shows each step's attempt count beside its verdict, and none "
        "when WIP.md records none -- bind this to the designed verdict field"
    )


# -- Bound: building the task ------------------------------------------------------


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Check Acceptance",
            "-c",
            "user.email=check-acceptance@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            *args,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
        env=_clean_env(),
    )
    return result.stdout.strip()


def _plan_block(step: StepSetup) -> str:
    lines = [
        f"### Step {step.number}: {step.title}",
        "",
        f"**Implementation**: Write `{step.files[0]}`.",
        "**Files**: " + ", ".join(f"`{f}`" for f in step.files),
    ]
    if step.tag is not None:
        lines.append(step.tag)
    if isinstance(step.check, Check):
        lines.append(check_field(step.check))
    elif step.check == UNREADABLE_CHECK:
        lines.append(unreadable_check_field())
    lines.append(f"**Done when**: `{step.files[0]}` exists.")
    return "\n".join(lines) + "\n"


def _plan(steps: tuple[StepSetup, ...]) -> str:
    return (
        "# Plan: stepwise widget\n\n## Goal\n\nBuild the widget in steps.\n\n## Steps\n\n"
        + "\n".join(_plan_block(s) for s in steps)
    )


def _wip(steps: tuple[StepSetup, ...]) -> str:
    current = steps[-1]
    status = (
        "[COMPLETE] - Step finished" if current.claimed_done else "[IN-PROGRESS] - Step underway"
    )
    entries = "\n".join(
        progress_entry(s.number, s.title, s.claimed_done, s.attempt, s.blocked_for_replan)
        for s in steps
    )
    return (
        "# WIP: stepwise widget\n\n## Current Step\n\n"
        f"Step {current.number} of {len(steps)}: {current.title}\n\n"
        f"## Status\n\n{status}\n\n## Progress\n\n{entries}\n\n## Blockers\n\nNone\n"
    )


def _test_results(steps: tuple[StepSetup, ...]) -> str | None:
    sections = []
    for s in steps:
        if s.result is None:
            continue
        lines = [
            f"## Step {s.number} — {s.title}",
            f"Command: `{s.recorded_command}`",
            s.result,
            "Duration: 0.4s",
        ]
        if s.mutation_line is not None:
            lines.append(s.mutation_line)
        sections.append("\n".join(lines) + "\n")
    return "\n".join(sections) if sections else None


def build_task(workspace: Path, *steps: StepSetup) -> PipelineTask:
    """A checkout holding the given plan steps, their progress claims and recorded runs."""
    root = workspace / "project"
    root.mkdir(parents=True)
    _git(root, "init", "-q")
    (root / ".gitignore").write_text(".ai-work/\n", encoding="utf-8")
    (root / "README.md").write_text("# widget\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    base = _git(root, "rev-parse", "HEAD")

    changed = [s for s in steps if s.files_changed]
    if changed:
        for s in changed:
            for rel in s.files:
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"STEP = {s.number!r}\n", encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "step work")

    task_dir = root / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    (task_dir / "IMPLEMENTATION_PLAN.md").write_text(_plan(steps), encoding="utf-8")
    (task_dir / "WIP.md").write_text(_wip(steps), encoding="utf-8")
    results = _test_results(steps)
    if results is not None:
        (task_dir / "TEST_RESULTS.md").write_text(results, encoding="utf-8")
    return PipelineTask(root=root, slug=SLUG, base=base)


# -- Bound: asking the reconciler --------------------------------------------------


def _run_reconciler(
    task: PipelineTask, reconciler: Path, *, machine: bool
) -> subprocess.CompletedProcess[str]:
    output_flags = ["--json", "--quiet"] if machine else []
    result = subprocess.run(
        [
            sys.executable,
            str(reconciler),
            task.slug,
            "--repo-root",
            str(task.root),
            "--base-ref",
            task.base,
            *output_flags,
        ],
        cwd=task.root,
        capture_output=True,
        text=True,
        timeout=120,
        env=_clean_env(),
    )
    if result.returncode not in _RECONCILER_VERDICT_EXITS:
        raise AssertionError(
            f"the reconciler failed (exit {result.returncode}) instead of judging the steps:\n"
            f"{result.stdout}{result.stderr}"
        )
    return result


def reconcile_raw(task: PipelineTask, reconciler: Path = RECONCILER) -> tuple[int, list[dict]]:
    """The reconciler's exit status and machine-readable verdicts, unparsed."""
    result = _run_reconciler(task, reconciler, machine=True)
    try:
        return result.returncode, json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"the reconciler (exit {result.returncode}) printed no verdict JSON:\n"
            f"{result.stdout}{result.stderr}"
        ) from exc


def reconcile(task: PipelineTask) -> Reconciliation:
    """Ask the reconciler for every step's verdict, as `/resume-pipeline` does."""
    exit_code, verdicts = reconcile_raw(task)
    return Reconciliation(
        exit_code=exit_code, steps={str(v["step"]): StepVerdict(v) for v in verdicts}
    )


def readable_report(task: PipelineTask) -> str:
    """The reconciler's human-readable output for the task."""
    result = _run_reconciler(task, RECONCILER, machine=False)
    return result.stdout + result.stderr


def snapshot_working_tree(root: Path) -> dict[str, bytes]:
    """Every file under `root` outside `.git/`, by relative path, with its bytes."""
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and ".git" not in p.relative_to(root).parts
    }
