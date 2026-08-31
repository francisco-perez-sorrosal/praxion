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

**Coverage note (td-147):** subprocess-driven tests measure zero coverage
under pytest-cov (see `skills/testing-strategy/references/python-testing.md`
§ Subprocess-Driven Tests Measure Zero Coverage) -- no `COVERAGE_PROCESS_START`
reaches the spawned process. The bulk of this file therefore drives
`_process()`/`main()` in-process (module loaded via `importlib`, stdin/stderr
monkeypatched); the `runpy.run_path(..., run_name="__main__")` tests exercise
the real `if __name__ == "__main__":` guard, including its fail-open wrapper.
A handful of subprocess tests are kept at the bottom as an end-to-end contract
proof (real argv, real stdin, real exit code) -- they are not expected to move
the coverage number.
"""

from __future__ import annotations

import importlib.util
import io
import json
import runpy
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
) -> dict:
    return {
        "tool_name": tool_name,
        "cwd": cwd,
        "session_id": "s1",
        "tool_input": {
            "subagent_type": subagent_type,
            "description": "design",
            "prompt": prompt,
        },
    }


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo standing in for a pipeline worktree."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".ai-state").mkdir()
    (tmp_path / ".ai-work" / "auth-flow").mkdir(parents=True)
    return tmp_path


def _drive_process(module, payload: dict, monkeypatch: pytest.MonkeyPatch) -> str:
    """Call `_process()` in-process, capturing what it writes to stderr."""
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", buf)
    module._process(payload)
    return buf.getvalue()


def _drive_main(module, payload_text: str, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    """Call `main()` in-process, capturing stdout and stderr."""
    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload_text))
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    module.main()
    return out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# Canary -- the gate bites on the bad input (in-process)
# ---------------------------------------------------------------------------


def test_canary_fires_when_brief_missing(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """THE canary: architect spawn, slug present, TASK_BRIEF.md absent."""
    assert not (repo / ".ai-work" / "auth-flow" / "TASK_BRIEF.md").exists()
    m = _load_module()

    stderr = _drive_process(m, _payload(cwd=str(repo)), monkeypatch)

    assert ADVISORY_PREFIX in stderr, (
        "the gate did not bite: a systems-architect spawn for slug `auth-flow` "
        "with no .ai-work/auth-flow/TASK_BRIEF.md produced no advisory"
    )
    assert ".ai-work/auth-flow/TASK_BRIEF.md" in stderr


def test_canary_fires_for_implementation_planner(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    m = _load_module()
    stderr = _drive_process(
        m, _payload(subagent_type="praxion:implementation-planner", cwd=str(repo)), monkeypatch
    )
    assert ADVISORY_PREFIX in stderr


def test_canary_fires_for_task_alias_and_bare_agent_name(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    m = _load_module()
    stderr = _drive_process(
        m,
        _payload(subagent_type="systems-architect", cwd=str(repo), tool_name="Task"),
        monkeypatch,
    )
    assert ADVISORY_PREFIX in stderr


def test_canary_fires_when_ai_work_slug_dir_does_not_exist_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """First spawn of a pipeline: `.ai-work/<slug>/` has not been created yet."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    m = _load_module()
    stderr = _drive_process(m, _payload(cwd=str(tmp_path)), monkeypatch)
    assert ADVISORY_PREFIX in stderr


# ---------------------------------------------------------------------------
# Suppression -- the gate stays quiet when it should (in-process)
# ---------------------------------------------------------------------------


def test_silent_when_brief_exists(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (repo / ".ai-work" / "auth-flow" / "TASK_BRIEF.md").write_text("# Task Brief\n")
    m = _load_module()
    stderr = _drive_process(m, _payload(cwd=str(repo)), monkeypatch)
    assert stderr == ""


def test_silent_for_non_brief_consuming_stage(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """researcher runs at Lightweight too -- reminding there would misfire."""
    m = _load_module()
    stderr = _drive_process(
        m, _payload(subagent_type="praxion:researcher", cwd=str(repo)), monkeypatch
    )
    assert stderr == ""


def test_silent_when_prompt_carries_no_task_slug(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    m = _load_module()
    stderr = _drive_process(m, _payload(prompt="Design the thing.", cwd=str(repo)), monkeypatch)
    assert stderr == ""


def test_silent_for_non_agent_tool(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    m = _load_module()
    stderr = _drive_process(m, _payload(cwd=str(repo), tool_name="Bash"), monkeypatch)
    assert stderr == ""


def test_silent_when_tool_input_is_not_a_dict(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    m = _load_module()
    payload = _payload(cwd=str(repo))
    payload["tool_input"] = "not-a-dict"
    stderr = _drive_process(m, payload, monkeypatch)
    assert stderr == ""


def test_silent_when_disabled_by_env(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRAXION_DISABLE_TASK_BRIEF_REMINDER", "1")
    m = _load_module()
    stderr = _drive_process(m, _payload(cwd=str(repo)), monkeypatch)
    assert stderr == ""


def test_silent_outside_a_git_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    m = _load_module()
    stderr = _drive_process(m, _payload(cwd=str(tmp_path)), monkeypatch)
    assert stderr == ""


def test_silent_when_git_rev_parse_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`_repo_root` returns None on a non-zero git exit, not just a missing git."""
    m = _load_module()

    class _FakeCompleted:
        returncode = 128
        stdout = ""

    monkeypatch.setattr(m.subprocess, "run", lambda *a, **k: _FakeCompleted(), raising=True)
    stderr = _drive_process(m, _payload(cwd=str(tmp_path)), monkeypatch)
    assert stderr == ""


def test_silent_when_git_binary_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_repo_root` degrades to None when `git` itself cannot be invoked."""
    m = _load_module()

    def _missing_binary(*_a, **_k):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(m.subprocess, "run", _missing_binary, raising=True)
    stderr = _drive_process(m, _payload(cwd=str(tmp_path)), monkeypatch)
    assert stderr == ""


def test_silent_when_git_toplevel_output_is_blank(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A git call that succeeds but prints nothing must not resolve to a truthy root."""
    m = _load_module()

    class _FakeCompleted:
        returncode = 0
        stdout = "\n"

    monkeypatch.setattr(m.subprocess, "run", lambda *a, **k: _FakeCompleted(), raising=True)
    stderr = _drive_process(m, _payload(cwd=str(tmp_path)), monkeypatch)
    assert stderr == ""


# ---------------------------------------------------------------------------
# main() -- stdin parsing, stdout emptiness (in-process)
# ---------------------------------------------------------------------------


def test_main_fires_advisory_on_stderr_and_keeps_stdout_empty(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    m = _load_module()
    out, err = _drive_main(m, json.dumps(_payload(cwd=str(repo))), monkeypatch)
    assert out == "", "stdout must stay empty -- see module docstring"
    assert ADVISORY_PREFIX in err


def test_main_malformed_stdin_is_silent(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    m = _load_module()
    out, err = _drive_main(m, "not json at all", monkeypatch)
    assert out == ""
    assert err == ""


@pytest.mark.parametrize("payload_text", ["[]", "null", '"a bare string"', "123"])
def test_main_well_formed_non_object_payload_is_silent(
    payload_text: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    m = _load_module()
    out, err = _drive_main(m, payload_text, monkeypatch)
    assert out == ""
    assert err == ""


# ---------------------------------------------------------------------------
# Script boundary -- the __main__ guard's fail-open wrapper (runpy)
# ---------------------------------------------------------------------------


class TestHookNeverRaisesIntoTheHarness:
    """The script boundary must swallow everything -- it runs on every spawn."""

    @pytest.mark.parametrize(
        "payload_text",
        ["not-json-at-all", "[]", "null", '"a bare string"', "123", ""],
    )
    def test_hostile_stdin_is_swallowed_at_the_script_boundary(
        self, payload_text: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(payload_text))
        runpy.run_path(str(MODULE_PATH), run_name="__main__")

    def test_an_unexpected_exception_inside_main_does_not_propagate(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A collaborator raising something `_repo_root` does not catch (e.g. a
        `RuntimeError` from `subprocess.run`) must still exit the script cleanly
        -- that is the fail-open wrapper's whole job.
        """
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_payload(cwd=str(repo)))))

        def _boom(*_a, **_k):
            raise RuntimeError("simulated collaborator failure")

        monkeypatch.setattr(subprocess, "run", _boom)

        runpy.run_path(str(MODULE_PATH), run_name="__main__")  # must not raise


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


def test_repo_root_resolves_the_real_toplevel(repo: Path) -> None:
    module = _load_module()
    assert module._repo_root(str(repo)) == repo.resolve() or module._repo_root(str(repo)) == Path(
        str(repo)
    )


# ---------------------------------------------------------------------------
# End-to-end contract proof (subprocess) -- real argv/stdin/exit code.
#
# Kept minimal deliberately: these do not move the coverage number (see the
# module docstring's coverage note) and exist only to prove the script is
# invocable exactly as the harness invokes it.
# ---------------------------------------------------------------------------


def _run_subprocess(payload: dict | str, cwd: Path, env_extra: dict[str, str] | None = None):
    import os

    env = dict(os.environ)
    env.pop("PRAXION_DISABLE_TASK_BRIEF_REMINDER", None)
    if env_extra:
        env.update(env_extra)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(MODULE_PATH)],
        input=text,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=30,
    )


def test_subprocess_contract_fires_and_exits_zero(repo: Path) -> None:
    result = _run_subprocess(_payload(cwd=str(repo)), repo)
    assert result.returncode == 0, "the advisory must never block a spawn"
    assert ADVISORY_PREFIX in result.stderr
    assert result.stdout == ""


def test_subprocess_contract_disabled_by_env_is_silent(repo: Path) -> None:
    result = _run_subprocess(
        _payload(cwd=str(repo)), repo, env_extra={"PRAXION_DISABLE_TASK_BRIEF_REMINDER": "1"}
    )
    assert result.returncode == 0
    assert result.stderr == ""
