"""Characterization tests for the plan `Files:` reader (``scripts/_plan_steps.py``).

The reader moved out of the reconciler unchanged; these pin the shapes the
reconciler suite relies on directly against the new module, so the reader keeps
its grammar when the reconciler stops being its only caller. The reader is pure:
every case passes document text, never a path.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _plan_steps as plan_steps  # noqa: E402

STEP = "Step "


def heading(number: str, title: str = "t") -> str:
    """A plan step heading as the step-document readers key it."""
    return f"### {STEP}{number}: {title}\n"


def label(number: str) -> str:
    return f"{STEP}{number}"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("`src/a.py`, `src/b.py`", ["src/a.py", "src/b.py"]),
        ("src/a.py, src/b.py", ["src/a.py", "src/b.py"]),
        ("src/a.py src/b.py", ["src/a.py", "src/b.py"]),
        ("src/a.py (see .ai-work/x/WIP.md, n/a)", ["src/a.py"]),
        ("`src/a.py`.", ["src/a.py"]),
        ("`scripts/a.py`, `.ai-work/slug/WIP.md`", ["scripts/a.py"]),
        ("`scripts/*.py`, `docs/guide.md`", ["scripts/*.py", "docs/guide.md"]),
        ("Makefile", []),
        ("`src/pkg/`", []),
        ("none", []),
        ("n/a (docs only)", []),
        ("** none", []),
        ("", []),
    ],
)
def test_split_files_admits_only_declared_paths(raw, expected):
    assert plan_steps.split_files(raw) == expected


@pytest.mark.parametrize(
    ("candidate", "admitted"),
    [
        ("src/a.py", True),
        ("setup.cfg", True),
        ("Makefile", False),
        ("src/pkg/", False),
        (".ai-work/slug/WIP.md", False),
        ("has space.py", False),
        ("a;b.py", False),
    ],
)
def test_is_admitted_file_requires_a_path_shaped_non_bookkeeping_token(candidate, admitted):
    assert plan_steps.is_admitted_file(candidate) is admitted


def test_scan_step_files_associates_each_files_line_with_its_step():
    text = heading("1") + "**Files**: `src/a.py`, `src/b.py`\n" + heading("2") + "Files: src/c.py\n"
    assert plan_steps.scan_step_files(text) == {
        label("1"): ["src/a.py", "src/b.py"],
        label("2"): ["src/c.py"],
    }


def test_scan_step_files_ignores_a_files_line_before_any_step():
    assert plan_steps.scan_step_files("**Files**: `src/a.py`\n" + heading("1")) == {}


def test_scan_step_files_reads_the_label_without_regard_to_case_or_bold():
    text = heading("1") + "files: src/a.py\n" + heading("2") + "**Files:** src/b.py\n"
    assert plan_steps.scan_step_files(text) == {
        label("1"): ["src/a.py"],
        label("2"): ["src/b.py"],
    }


def test_scan_step_files_follows_a_trailing_comma_over_wrapped_lines():
    text = heading("1") + "**Files**: `src/a.py`,\n`src/b.py`,\n`src/c.py`\nprose line\n"
    assert plan_steps.scan_step_files(text) == {label("1"): ["src/a.py", "src/b.py", "src/c.py"]}


def test_a_trailing_comma_never_swallows_the_following_step_heading():
    text = heading("1") + "**Files**: src/a.py,\n" + heading("2") + "**Files**: src/b.py\n"
    assert plan_steps.scan_step_files(text) == {
        label("1"): ["src/a.py"],
        label("2"): ["src/b.py"],
    }


def test_a_lettered_addendum_heading_is_its_own_step():
    text = heading("1") + "**Files**: src/a.py\n" + heading("1b") + "**Files**: src/b.py\n"
    assert plan_steps.scan_step_files(text) == {
        label("1"): ["src/a.py"],
        label("1b"): ["src/b.py"],
    }


def test_a_checklist_step_line_opens_a_step_for_a_wip_document():
    text = f"- [ ] {STEP}3: do it\n  **Files**: src/a.py\n"
    assert plan_steps.scan_step_files(text) == {label("3"): ["src/a.py"]}


def test_repeated_files_lines_for_one_step_accumulate():
    text = heading("1") + "**Files**: src/a.py\n**Files**: src/b.py\n"
    assert plan_steps.scan_step_files(text) == {label("1"): ["src/a.py", "src/b.py"]}


def test_collect_files_value_returns_the_joined_value_and_the_next_unread_index():
    lines = ["src/a.py,", "src/b.py", "after"]
    assert plan_steps.collect_files_value(lines[0], lines, 0) == ("src/a.py, src/b.py", 2)


def test_the_module_does_no_io():
    source = (SCRIPT_DIR / "_plan_steps.py").read_text(encoding="utf-8")
    for forbidden in ("subprocess", "open(", "read_text", "pathlib", "os."):
        assert forbidden not in source
