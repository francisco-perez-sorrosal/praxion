"""Shared builders for the `extract_spec.py` test modules (not a test module; never collected).

`test_extract_spec.py` (extraction, `--check`, exit codes, root resolution) and
`test_extract_spec_lint.py` (the design-vocabulary lint) both build the same
plan/brief projects and run the command the same way; this holds that once.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
SCRIPT = SCRIPTS_DIR / "extract_spec.py"
sys.path.insert(0, str(SCRIPTS_DIR))

import extract_spec as es  # noqa: E402

SLUG = "demo-task"
EXTRACT_NAME = "SPEC_EXTRACT.md"


def req_id(number: int) -> str:
    """Requirement id built at run time so no id literal sits in the test files."""
    return f"REQ-{number:02d}"


def make_plan(
    *,
    acceptance: str = "- [ ] A customer who asks for a refund gets the money back.\n",
    behavior: str | None = None,
    extra: str = "",
) -> str:
    """A plan holding spec sections and design sections, all spec text plain."""
    if behavior is None:
        behavior = (
            "### Observable Surface\n\n"
            "- `extract_spec.py` -- the command\n\n"
            f"### {req_id(1)}: Refunds are returned\n\n"
            "**When** a customer asks for a refund\n"
            "**the system** returns the money\n"
            "**so that** trust is kept.\n"
        )
    return (
        "# Plan: Demo\n\n"
        "## Goal\n\nGoal text.\n\n"
        f"## Acceptance Criteria\n\n{acceptance}\n"
        f"## Behavioral Specification\n\n{behavior}\n"
        "## Architecture\n\nDESIGNMARKER the adapter layer lives in scripts/x.py\n\n"
        "## Risk Assessment\n\nRISKMARKER\n" + extra
    )


BRIEF = (
    "# Task Brief\n\n"
    "## Key Signals\n\nSIGNALMARKER users want refunds.\n\n"
    "## Scope\n\nSCOPEMARKER touches billing.\n"
)


def make_project(
    root: Path, plan: str | None = None, brief: str | None = BRIEF, slug: str = SLUG
) -> Path:
    """Create `.ai-work/<slug>/` under `root`; returns the task directory."""
    task_dir = root / ".ai-work" / slug
    task_dir.mkdir(parents=True)
    (task_dir / "SYSTEMS_PLAN.md").write_text(make_plan() if plan is None else plan)
    if brief is not None:
        (task_dir / "TASK_BRIEF.md").write_text(brief)
    return task_dir


def run_main(root: Path, *flags: str, slug: str = SLUG) -> int:
    return es.main([slug, "--repo-root", str(root), *flags])


def extract_path(root: Path) -> Path:
    return root / ".ai-work" / SLUG / EXTRACT_NAME


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=cwd
    )
