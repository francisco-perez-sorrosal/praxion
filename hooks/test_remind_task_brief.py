"""Tests for hooks/remind_task_brief.py -- the TASK_BRIEF advisory.

Gate-liveness contract (rules/swe/gate-liveness.md): a CODE gate must be
proven to *bite*, not merely to pass on the current good state. Every
behavior below therefore ships as a canary/suppression pair -- one fixture
proving the advisory DOES fire on the bad input, one proving it does NOT fire
when the triggering condition is absent -- ruling out both the "never fires"
and the "fires unconditionally" failure modes.

The load-bearing canary is `test_canary_fires_when_brief_missing`: a
`systems-architect` spawn carrying a task slug whose `TASK_BRIEF.md` does not
exist. That is the exact input shape that lapsed 100% of the time before this
hook existed.

The advisory is also asserted to keep stdout empty on every path. That is not
cosmetic: `inject_subagent_context.py` is the single `updatedInput` emitter
registered on the same PreToolUse(Agent|Task) matcher, and a second emitter
on one spawn is a resolved defect this hook must not reintroduce.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
MODULE_PATH = HOOKS_DIR / "remind_task_brief.py"

ADVISORY_PREFIX = "[task-brief-reminder]"


def _load_module():
    """Load remind_task_brief.py as a module, or raise ImportError."""
    if not MODULE_PATH.exists():
        raise ImportError("hooks/remind_task_brief.py not found.")
    spec = importlib.util.spec_from_file_location("remind_task_brief", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError("Could not load spec for remind_task_brief.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payload(
    *,
    subagent_type: str = "praxion:systems-architect",
    prompt: str = "Task slug: auth-flow\n\nDesign the thing.",
    cwd: str,
    tool_name: str = "Agent",
) -> str:
    return json.dumps(
        {
            "tool_name": tool_name,
            "cwd": cwd,
            "session_id": "s1",
            "tool_input": {
                "subagent_type": subagent_type,
                "description": "design",
                "prompt": prompt,
            },
        }
    )


def _run(payload: str, cwd: Path, env_extra: dict[str, str] | None = None):
    """Invoke the hook as the harness does: a subprocess fed JSON on stdin."""
    import os

    env = dict(os.environ)
    env.pop("PRAXION_DISABLE_TASK_BRIEF_REMINDER", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(MODULE_PATH)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=30,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo standing in for a pipeline worktree."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".ai-state").mkdir()
    (tmp_path / ".ai-work" / "auth-flow").mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# Canary -- the gate bites on the bad input
# ---------------------------------------------------------------------------


def test_canary_fires_when_brief_missing(repo: Path) -> None:
    """THE canary: architect spawn, slug present, TASK_BRIEF.md absent."""
    assert not (repo / ".ai-work" / "auth-flow" / "TASK_BRIEF.md").exists()

    result = _run(_payload(cwd=str(repo)), repo)

    assert result.returncode == 0, "the advisory must never block a spawn"
    assert ADVISORY_PREFIX in result.stderr, (
        "the gate did not bite: a systems-architect spawn for slug `auth-flow` "
        "with no .ai-work/auth-flow/TASK_BRIEF.md produced no advisory"
    )
    assert ".ai-work/auth-flow/TASK_BRIEF.md" in result.stderr
    assert result.stdout == "", "stdout must stay empty -- see module docstring"


def test_canary_fires_for_implementation_planner(repo: Path) -> None:
    result = _run(_payload(subagent_type="praxion:implementation-planner", cwd=str(repo)), repo)
    assert ADVISORY_PREFIX in result.stderr


def test_canary_fires_for_task_alias_and_bare_agent_name(repo: Path) -> None:
    result = _run(
        _payload(subagent_type="systems-architect", cwd=str(repo), tool_name="Task"),
        repo,
    )
    assert ADVISORY_PREFIX in result.stderr


def test_canary_fires_when_ai_work_slug_dir_does_not_exist_at_all(tmp_path: Path) -> None:
    """First spawn of a pipeline: `.ai-work/<slug>/` has not been created yet."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    result = _run(_payload(cwd=str(tmp_path)), tmp_path)
    assert ADVISORY_PREFIX in result.stderr


# ---------------------------------------------------------------------------
# Suppression -- the gate stays quiet when it should
# ---------------------------------------------------------------------------


def test_silent_when_brief_exists(repo: Path) -> None:
    (repo / ".ai-work" / "auth-flow" / "TASK_BRIEF.md").write_text("# Task Brief\n")
    result = _run(_payload(cwd=str(repo)), repo)
    assert result.stderr == ""
    assert result.stdout == ""


def test_silent_for_non_brief_consuming_stage(repo: Path) -> None:
    """researcher runs at Lightweight too -- reminding there would misfire."""
    result = _run(_payload(subagent_type="praxion:researcher", cwd=str(repo)), repo)
    assert result.stderr == ""


def test_silent_when_prompt_carries_no_task_slug(repo: Path) -> None:
    result = _run(_payload(prompt="Design the thing.", cwd=str(repo)), repo)
    assert result.stderr == ""


def test_silent_for_non_agent_tool(repo: Path) -> None:
    result = _run(_payload(cwd=str(repo), tool_name="Bash"), repo)
    assert result.stderr == ""


def test_silent_when_disabled_by_env(repo: Path) -> None:
    result = _run(
        _payload(cwd=str(repo)),
        repo,
        env_extra={"PRAXION_DISABLE_TASK_BRIEF_REMINDER": "1"},
    )
    assert result.stderr == ""


def test_silent_outside_a_git_repo(tmp_path: Path) -> None:
    result = _run(_payload(cwd=str(tmp_path)), tmp_path)
    assert result.returncode == 0
    assert result.stderr == ""


def test_malformed_stdin_exits_zero_silently(repo: Path) -> None:
    result = _run("not json at all", repo)
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


# ---------------------------------------------------------------------------
# Unit-level contract
# ---------------------------------------------------------------------------


def test_slug_regex_accepts_backticked_form() -> None:
    module = _load_module()
    assert module.TASK_SLUG_RE.search("Task slug: `auth-flow`").group(1) == "auth-flow"
    assert module.TASK_SLUG_RE.search("Task slug: auth-flow\n").group(1) == "auth-flow"


def test_namespaced_subagent_type_is_normalized() -> None:
    module = _load_module()
    assert module._normalize_stage("praxion:systems-architect") == "systems-architect"
    assert module._normalize_stage("systems-architect") == "systems-architect"
