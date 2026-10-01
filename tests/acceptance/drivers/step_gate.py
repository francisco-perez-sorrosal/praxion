"""Driver for the pipeline's step-completion judgment on a step tagged for mutation testing.

A scenario names only what varies: the step's mutation tag and the `Mutation:`
lines its recorded test runs carry. This driver builds everything else a step
needs to count as otherwise done -- a git checkout whose step files changed
after the base commit, the plan with the step and its tag, the progress file
with the step checked off, and a green recorded run in the step's
`TEST_RESULTS.md` section, in the shapes the planning templates document -- and
asks the pipeline whether the step may complete and the pipeline advance past it.

Whatever extra evidence the bound judgment needs for an otherwise-done step to
complete belongs in `build_task`, never in a scenario.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers.gate_liveness import UnboundDriverError

SLUG = "liveness-step"
STEP = "1"
STEP_TITLE = "Read the widget file"
STEP_FILES = ("src/widget.py", "tests/test_widget.py")


@dataclass(frozen=True)
class RecordedRun:
    """One recorded test run of the step; `mutation` is its `Mutation:` line, if any."""

    mutation: str | None
    passed: int = 4


@dataclass(frozen=True)
class PipelineTask:
    root: Path
    slug: str
    base: str


@dataclass(frozen=True)
class StepJudgment:
    completes: bool  # the step may be marked complete and the pipeline advance past it
    message: str  # what the judgment says about the step: on a block, the step and why


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Liveness Acceptance",
            "-c",
            "user.email=liveness-acceptance@example.invalid",
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
        env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
    )
    return result.stdout.strip()


def _plan(tag: str | None) -> str:
    tag_line = f"{tag}\n" if tag is not None else ""
    return (
        "# Plan: widget reader\n\n"
        "## Goal\n\nRead the widget file.\n\n"
        "## Steps\n\n"
        f"### Step {STEP}: {STEP_TITLE}\n\n"
        "**Implementation**: Read the widget file from disk.\n"
        f"**Files**: `{STEP_FILES[0]}`, `{STEP_FILES[1]}`\n"
        f"{tag_line}"
        "**Done when**: the widget file is read.\n"
    )


def _wip() -> str:
    return (
        "# WIP: widget reader\n\n"
        "## Current Step\n\n"
        f"Step {STEP} of 1: {STEP_TITLE}\n\n"
        "## Status\n\n[COMPLETE] - Step finished\n\n"
        "## Progress\n\n"
        f"- [x] Step {STEP}: {STEP_TITLE}\n\n"
        "## Blockers\n\nNone\n"
    )


def _test_results(runs: tuple[RecordedRun, ...]) -> str:
    sections = []
    for run in runs:
        lines = [
            f"## Step {STEP} — {STEP_TITLE}",
            "Command: `uv run pytest tests/test_widget.py -q --tb=short -rf`",
            f"Result: pass={run.passed} fail=0 skip=0",
            "Duration: 0.4s",
        ]
        if run.mutation is not None:
            lines.append(run.mutation)
        sections.append("\n".join(lines) + "\n")
    return "\n".join(sections)


def build_task(workspace: Path, *, tag: str | None, runs: tuple[RecordedRun, ...]) -> PipelineTask:
    """A checkout holding one otherwise-done step with the given tag and recorded runs."""
    root = workspace / "project"
    root.mkdir(parents=True)
    _git(root, "init", "-q")
    (root / ".gitignore").write_text(".ai-work/\n", encoding="utf-8")
    (root / "README.md").write_text("# widget\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    base = _git(root, "rev-parse", "HEAD")

    (root / "src").mkdir()
    (root / "src" / "widget.py").write_text(
        "from pathlib import Path\n\n\ndef read_widget(path: Path) -> str:\n"
        "    return path.read_text()\n",
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    (root / "tests" / "test_widget.py").write_text(
        "from src.widget import read_widget\n\n\ndef test_reads(tmp_path):\n"
        "    (tmp_path / 'w').write_text('x')\n"
        "    assert read_widget(tmp_path / 'w') == 'x'\n",
        encoding="utf-8",
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", STEP_TITLE)

    task_dir = root / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    (task_dir / "IMPLEMENTATION_PLAN.md").write_text(_plan(tag), encoding="utf-8")
    (task_dir / "WIP.md").write_text(_wip(), encoding="utf-8")
    (task_dir / "TEST_RESULTS.md").write_text(_test_results(runs), encoding="utf-8")
    return PipelineTask(root=root, slug=SLUG, base=base)


def judge_step(task: PipelineTask, step: str = STEP) -> StepJudgment:
    """Ask the pipeline whether `step` may complete and the pipeline advance past it."""
    raise UnboundDriverError(
        "The pipeline's mechanical step-completion judgment for a step tagged for "
        "mutation testing is not designed yet: given a task's plan, progress file and "
        "recorded test results in a checkout, it reports whether the step may complete "
        "and, when it is blocked, names the step and either the refusal reason or the "
        "missing mutation line."
    )
