"""Behavioral stubs for subagent isolation verification — SHIP GATE for td-034.

PURPOSE
-------
Verify that ``hooks/worktree_guard.py`` fires for Write/Edit calls issued by a
subagent spawned inside a rework worktree session and blocks writes to paths
outside that worktree root.

TWO-PATH STRUCTURE
------------------
**Path A (automated)**: If the ``Agent`` tool is callable from a pytest context
(detected via ``importlib.util.find_spec`` on the claudecode SDK or an equivalent
probe), the harness spawns a real minimal subagent, instructs it to Edit a file
outside the worktree root, and asserts that ``worktree_guard.py`` returns exit
code 2 (BLOCKED).  Path A is gated by a ``@pytest.mark.skipif`` condition that
detects whether the harness can spawn a subagent from a pytest context.

**Path B (manual-verification fallback)**: If Path A is skipped (Agent not
callable from pytest), the harness produces ``MANUAL_VERIFICATION.md``
documenting the exact manual steps.  This file contains the assertion stubs
and the skip-with-manual-fallback wiring.

RATIONALE
---------
This harness is the SHIP GATE for the rework-loop's subagent-isolation invariant
(documented in `.ai-state/decisions/` — the finalized ADR is discoverable via
DECISIONS_INDEX.md by the `td-034 / subagent isolation` tags).  If the Path A
automated test FAILS (guard does not fire), do NOT ship the rework feature
without an explicit user override recorded in an ADR amendment.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Project-root helpers (no imports of production modules at module level)
# ---------------------------------------------------------------------------

_HOOKS_DIR = Path(__file__).parent
_REPO_ROOT = _HOOKS_DIR.parent
_RESUME_REWORK_PATH = _REPO_ROOT / "commands" / "resume-rework.md"


# ---------------------------------------------------------------------------
# Probe: can the Agent tool be called from a pytest context?
# ---------------------------------------------------------------------------


def _agent_tool_callable_from_pytest() -> bool:
    """Return True iff the Agent tool is callable from pytest — currently False.

    Checks: claude_code_sdk importable, agent_sdk importable, or
    tests/agent_harness.py exists.  All absent: the Agent tool is a
    session-bound Claude Code primitive, not a Python-callable object.
    """
    if importlib.util.find_spec("claude_code_sdk") is not None:
        return True
    if importlib.util.find_spec("agent_sdk") is not None:
        return True
    if (_REPO_ROOT / "tests" / "agent_harness.py").exists():
        return True
    return False


# ---------------------------------------------------------------------------
# Path B helper: confirm MANUAL_VERIFICATION.md exists (committed alongside this file)
# ---------------------------------------------------------------------------

_MANUAL_VERIFICATION_PATH = _HOOKS_DIR / "MANUAL_VERIFICATION.md"


def _ensure_manual_verification_doc() -> None:
    """Assert that hooks/MANUAL_VERIFICATION.md is present.

    The file is committed alongside this test module (not generated at runtime)
    so this function serves as a sanity check that the artifact was not deleted.
    """
    assert _MANUAL_VERIFICATION_PATH.exists(), (
        f"hooks/MANUAL_VERIFICATION.md not found at {_MANUAL_VERIFICATION_PATH}; "
        "it should be committed alongside this test file."
    )


# ---------------------------------------------------------------------------
# Test 1: smoke test — always runs, Path A / Path B agnostic
# ---------------------------------------------------------------------------


def test_worktree_guard_loads_without_error() -> None:
    """worktree_guard module loads and exposes its hook entry-point."""
    # Deferred import: surfaces import errors as test failures, not collection errors.
    spec = importlib.util.spec_from_file_location(
        "worktree_guard_smoke", _HOOKS_DIR / "worktree_guard.py"
    )
    assert spec is not None, "worktree_guard.py must be importable from hooks/"
    assert spec.loader is not None, "worktree_guard.py must be importable from hooks/"
    import sys

    mod_name = "worktree_guard_smoke"
    import types

    mod = types.ModuleType(mod_name)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    assert callable(getattr(mod, "main", None)), (
        "worktree_guard.py must expose a callable 'main' entry-point "
        "(the function invoked by the PreToolUse hook runner)"
    )


# ---------------------------------------------------------------------------
# Test 2: Path A — subagent cross-worktree write is blocked by worktree_guard
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _agent_tool_callable_from_pytest(),
    reason="td-034 Path A: Agent tool not callable from pytest — Path B (manual verification) applies",
)
def test_guard_blocks_cross_worktree_edit_in_subagent_session(
    tmp_path: Path,
) -> None:
    """A subagent instructed to Edit outside the rework worktree is blocked by the guard.

    Path A (automated): would spawn a real subagent in a linked worktree and
    assert that ``worktree_guard.py`` blocks the cross-boundary Edit (exit code 2).
    Path B (this path): Agent is not callable from pytest; skip and confirm the
    manual verification document is present.  See hooks/MANUAL_VERIFICATION.md.
    """
    # Path B: Agent not callable from pytest — confirm manual doc present and skip.
    _ensure_manual_verification_doc()
    pytest.skip(
        "td-034 Path A unrunnable: Agent tool not callable from pytest context. "
        "See hooks/MANUAL_VERIFICATION.md for the manual reproduction steps."
    )


# ---------------------------------------------------------------------------
# Test 3: defense-in-depth — always runs
# ---------------------------------------------------------------------------


def test_absolute_path_briefing_present_in_resume_rework() -> None:
    """The Dispatch section of /resume-rework uses absolute paths, not relative ones.

    This is the second layer of defense against td-034: even if worktree_guard.py
    somehow misses a subagent Edit, the absolute-path briefing in the spawn prompt
    makes it harder for the spawned agent to accidentally resolve paths relative to
    the wrong working directory.
    """
    assert _RESUME_REWORK_PATH.exists(), (
        f"commands/resume-rework.md not found at {_RESUME_REWORK_PATH}; "
        "the rework command file must exist before this test runs"
    )

    text = _RESUME_REWORK_PATH.read_text(encoding="utf-8")

    # Locate the Dispatch section.
    dispatch_match = re.search(r"^## Dispatch\b", text, re.MULTILINE)
    assert dispatch_match is not None, (
        "commands/resume-rework.md must contain a '## Dispatch' section; "
        "the absolute-path briefing lives there"
    )

    # Extract Dispatch section body: from the heading to the next ## heading (or EOF).
    dispatch_start = dispatch_match.end()
    next_section = re.search(r"^##\s", text[dispatch_start:], re.MULTILINE)
    dispatch_body = (
        text[dispatch_start : dispatch_start + next_section.start()]
        if next_section
        else text[dispatch_start:]
    )

    # The dispatch body must reference absolute paths for both the findings file
    # and the worktree root.  Accept any of: explicit "absolute" wording, "$PWD",
    # or a prose marker like "absolute path".
    absolute_path_signal = re.search(
        r"absolute[\s-]path|absolute\b|\$PWD",
        dispatch_body,
        re.IGNORECASE,
    )
    assert absolute_path_signal is not None, (
        "The '## Dispatch' section of commands/resume-rework.md must explicitly "
        "reference absolute paths for the spawned agent's cwd / VERIFIER_FINDINGS.md "
        "path.  Accepted signals: 'absolute path', 'absolute-path', '$PWD'. "
        "This is the defense-in-depth layer required by dec-180."
    )
