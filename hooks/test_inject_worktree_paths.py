"""Tests for hooks/inject_worktree_paths.py — PreToolUse(Agent) worktree-path briefing.

Gate-liveness contract (rules/swe/gate-liveness.md): this is a CODE gate mitigating
td-034's residual exposure (relative-path writes + subagent cwd-bifurcation inside a
linked worktree). It ships a canary — a worktree-cwd fixture that asserts the briefing
line IS injected — paired with a suppression test — a canonical (main-checkout) cwd
fixture that asserts NO injection occurs — plus a fail-open test on malformed stdin.
A gate that fires unconditionally, or never fires at all, is indistinguishable from no
gate; the two fixtures below prove it discriminates on the one condition that matters.

Behavioral specification:

- A session whose cwd resolves inside a *linked* git worktree gets a briefing line
  prepended to every spawned Agent subagent's prompt: the absolute worktree root plus
  an "absolute paths only, never relative" instruction.
- A session whose cwd is the *main* checkout (or not a git repo at all) gets no
  injection — nothing to brief.
- Applies to ALL subagent types, i-am:* and host-native alike — no gate (d)-style skip.
- PRAXION_DISABLE_WORKTREE_PATH_BRIEFING=1 disables injection even inside a worktree.
- Malformed or empty stdin, non-Agent tool_name, missing cwd — all tolerated, exit 0.
- Every other tool_input field (description, model, run_in_background, …) survives
  the injection untouched — the same updatedInput envelope contract as
  inject_subagent_context.py.

Hermetic-git-repo pattern (template: hooks/test_worktree_guard.py): every worktree
fixture is a real temporary git repo + a real `git worktree add` linked worktree.
Subprocess harness (template: hooks/test_inject_subagent_context.py /
hooks/test_worktree_guard.py): the hook is invoked as a real subprocess with a JSON
payload on stdin, mirroring exactly how Claude Code dispatches PreToolUse(Agent).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

MODULE_PATH = Path(__file__).resolve().parent / "inject_worktree_paths.py"

_ORIGINAL_PROMPT = "Implement Step 3 of the plan."


# ---------------------------------------------------------------------------
# Fixtures — real git repos, mirroring hooks/test_worktree_guard.py
# ---------------------------------------------------------------------------


@pytest.fixture
def main_repo(tmp_path: Path) -> Path:
    """A real git repo serving as the 'main' (canonical) worktree."""
    repo = tmp_path / "main"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "test"], check=True)
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True)
    return repo


@pytest.fixture
def linked_worktree(main_repo: Path, tmp_path: Path) -> Path:
    """A linked worktree created from the main repo."""
    wt = tmp_path / "linked"
    subprocess.run(
        ["git", "-C", str(main_repo), "worktree", "add", "-q", str(wt), "-b", "feature"],
        check=True,
    )
    return wt


# ---------------------------------------------------------------------------
# Hook invocation helpers
# ---------------------------------------------------------------------------


def _agent_payload(
    prompt: str = _ORIGINAL_PROMPT,
    subagent_type: str = "i-am:implementer",
    cwd: str | None = None,
) -> dict[str, Any]:
    return {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": subagent_type, "prompt": prompt},
        "cwd": cwd,
        "session_id": "test-session-001",
    }


def _run_hook(
    payload: dict[str, Any] | None,
    cwd: Path,
    raw_stdin: str | None = None,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke inject_worktree_paths.py as a subprocess with a JSON payload on stdin."""
    import os

    env = {k: v for k, v in os.environ.items() if not k.startswith("PRAXION_")}
    if env_extra:
        env.update(env_extra)
    stdin = raw_stdin if raw_stdin is not None else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(MODULE_PATH)],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=10,
    )


# ---------------------------------------------------------------------------
# Canary: worktree-cwd fixture must fire
# ---------------------------------------------------------------------------


def test_injects_briefing_line_from_worktree_cwd(linked_worktree: Path) -> None:
    """Gate-liveness canary: a session cwd inside a linked worktree must inject
    the absolute-path briefing line into the spawned subagent's prompt.

    Self-test: if the worktree-detection branch were gutted (always returning
    None), stdout would stay empty and this test would fail — proving the gate
    is not a no-op that only ever passes on the current (non-firing) state.
    """
    payload = _agent_payload(cwd=str(linked_worktree))
    result = _run_hook(payload, linked_worktree)

    assert result.returncode == 0, f"Hook exited non-zero: {result.stderr}"
    assert result.stdout, "Expected updatedInput JSON on stdout for a worktree cwd"
    output = json.loads(result.stdout)
    updated_prompt = output["hookSpecificOutput"]["updatedInput"]["prompt"]
    assert (
        str(linked_worktree.resolve()) in updated_prompt
    ), "Briefing must name the absolute worktree root"
    assert "absolute paths" in updated_prompt.lower()
    assert "never relative" in updated_prompt.lower() or "relative paths" in updated_prompt.lower()
    assert _ORIGINAL_PROMPT in updated_prompt, "Original prompt must be preserved"


# ---------------------------------------------------------------------------
# Suppression: canonical (main-checkout) cwd fixture must NOT fire
# ---------------------------------------------------------------------------


def test_no_injection_from_canonical_checkout_cwd(main_repo: Path) -> None:
    """Gate-liveness suppression case: the main (canonical) checkout has no
    worktree boundary to brief — no injection, silent pass-through.

    Paired with the canary above: same hook, same subagent payload shape, the
    only variable is cwd (linked worktree vs main checkout). This rules out a
    hook that fires unconditionally regardless of worktree state.
    """
    payload = _agent_payload(cwd=str(main_repo))
    result = _run_hook(payload, main_repo)

    assert result.returncode == 0
    assert (
        result.stdout == ""
    ), f"No injection expected from the main checkout; got: {result.stdout!r}"


def test_no_injection_when_cwd_is_not_a_git_repo(tmp_path: Path) -> None:
    """A non-git cwd has no worktree boundary — no injection, fail-open."""
    non_git = tmp_path / "not-a-repo"
    non_git.mkdir()
    payload = _agent_payload(cwd=str(non_git))
    result = _run_hook(payload, non_git)

    assert result.returncode == 0
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# Applies to ALL subagent types — no i-am:* skip gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subagent_type",
    ["i-am:implementer", "i-am:systems-architect", "Explore", "Plan", "general-purpose"],
)
def test_injects_for_every_subagent_type(subagent_type: str, linked_worktree: Path) -> None:
    """Unlike inject_subagent_context.py's gate (d), i-am:* agents are NOT skipped:
    they are the common case in worktree pipelines (EnterWorktree is a Standard/Full
    requirement), so excluding them would leave the most frequent spawn path
    unmitigated.
    """
    payload = _agent_payload(subagent_type=subagent_type, cwd=str(linked_worktree))
    result = _run_hook(payload, linked_worktree)

    assert result.returncode == 0
    assert result.stdout, f"Expected injection for subagent_type={subagent_type!r}"
    output = json.loads(result.stdout)
    assert output["hookSpecificOutput"]["updatedInput"]["subagent_type"] == subagent_type


# ---------------------------------------------------------------------------
# updatedInput envelope contract — no wrapper key, other fields preserved
# ---------------------------------------------------------------------------


def test_updated_input_is_the_tool_input_object_directly(linked_worktree: Path) -> None:
    """Harness contract: updatedInput's value IS the replacement tool-input params
    object directly — never wrapped in an envelope key such as {"tool_input": ...}.
    """
    payload = _agent_payload(cwd=str(linked_worktree))
    result = _run_hook(payload, linked_worktree)

    assert result.returncode == 0
    output = json.loads(result.stdout)
    updated = output["hookSpecificOutput"]["updatedInput"]
    assert "tool_input" not in updated, "updatedInput must not be wrapped in a tool_input envelope"
    assert "prompt" in updated
    assert "subagent_type" in updated


def test_preserves_other_tool_input_fields(linked_worktree: Path) -> None:
    """description/model/run_in_background must survive the injection untouched —
    mirroring the schema-validation breakage inject_subagent_context.py hit when it
    once reconstructed tool_input from scratch instead of preserving unknown fields.
    """
    payload = _agent_payload(cwd=str(linked_worktree))
    payload["tool_input"]["description"] = "implement step 3"
    payload["tool_input"]["model"] = "sonnet"
    payload["tool_input"]["run_in_background"] = True

    result = _run_hook(payload, linked_worktree)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    updated = output["hookSpecificOutput"]["updatedInput"]
    assert updated["description"] == "implement step 3"
    assert updated["model"] == "sonnet"
    assert updated["run_in_background"] is True


# ---------------------------------------------------------------------------
# Opt-out
# ---------------------------------------------------------------------------


def test_disable_flag_suppresses_injection_inside_worktree(linked_worktree: Path) -> None:
    payload = _agent_payload(cwd=str(linked_worktree))
    result = _run_hook(
        payload,
        linked_worktree,
        env_extra={"PRAXION_DISABLE_WORKTREE_PATH_BRIEFING": "1"},
    )
    assert result.returncode == 0
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# Non-Agent tool_name / missing fields
# ---------------------------------------------------------------------------


def test_non_agent_tool_name_exits_zero_silently(linked_worktree: Path) -> None:
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "echo hi"},
        "cwd": str(linked_worktree),
    }
    result = _run_hook(payload, linked_worktree)
    assert result.returncode == 0
    assert result.stdout == ""


def test_missing_cwd_exits_zero_without_injection(linked_worktree: Path) -> None:
    payload = {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "i-am:implementer", "prompt": _ORIGINAL_PROMPT},
    }
    result = _run_hook(payload, linked_worktree)
    assert result.returncode == 0
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# Fail-open on malformed / empty stdin
# ---------------------------------------------------------------------------


def test_malformed_stdin_never_raises(linked_worktree: Path) -> None:
    result = _run_hook(None, linked_worktree, raw_stdin="not-json{{{")
    assert result.returncode == 0, "malformed stdin must never cause a non-zero exit"
    assert "Traceback" not in result.stderr


def test_empty_stdin_exits_zero_without_crash(linked_worktree: Path) -> None:
    result = _run_hook(None, linked_worktree, raw_stdin="")
    assert result.returncode == 0


def test_missing_tool_input_exits_zero(linked_worktree: Path) -> None:
    payload = {"tool_name": "Agent", "cwd": str(linked_worktree)}
    result = _run_hook(payload, linked_worktree)
    assert result.returncode == 0
