"""Tests for hooks/inject_subagent_context.py — the single PreToolUse(Agent)
updatedInput emitter (dec-266).

Behavioral specification:

- Host-native subagents (Explore, Plan, general-purpose) receive a compact Praxion
  preamble prepended to their prompt when launched from a Praxion-managed project.
- Praxion-native subagents (praxion:*) are skipped by default for the PREAMBLE ONLY
  (they already encode the behavioral contract in their system prompts).
- Praxion-native subagents receive the preamble when PRAXION_INJECT_NATIVE_SUBAGENTS=1.
- Projects without a .ai-state/ directory receive no preamble (not a Praxion project) —
  this gate is scoped to the preamble only.
- PRAXION_DISABLE_SUBAGENT_INJECT=1 disables the preamble in any project.
- A session inside a *linked* git worktree (`--git-dir` != `--git-common-dir`) gets a
  session-worktree briefing line prepended for EVERY subagent type, praxion:* included —
  no .ai-state/ requirement, no praxion skip.
- A prompt that names an absolute `.claude/worktrees/<name>` path differing from the
  session's own cwd gets a briefed-root line prepended for EVERY subagent type — pure
  text regex, no filesystem walk, no git call.
- At most ONE updatedInput is ever emitted per spawn, composing whichever of the three
  segments (preamble, session-worktree line, briefed-root line) apply; when none apply,
  the hook emits nothing.
- Malformed or empty stdin is tolerated — hook exits 0 without crashing.
- Per-session-id caching: a second call with the same session_id avoids re-statting
  the filesystem for .ai-state/ presence.
- Fast-path (no .ai-state/, no git repo) completes in < 200ms per invocation
  (generous CI bound).

Gate-liveness contract (rules/swe/gate-liveness.md): each of the three composed
segments is its own CODE gate. Every gate below ships a canary (a fixture proving
the segment DOES fire) paired with a suppression case (a fixture proving it does
NOT fire when the triggering condition is absent) — ruling out both "never fires"
and "fires unconditionally" failure modes.

The hook interface contract (stdin/stdout shapes) is documented in SYSTEMS_PLAN.md
§Interfaces → Hook contract — PreToolUse(Agent). Tests use that shape directly.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
MODULE_PATH = HOOKS_DIR / "inject_subagent_context.py"

# ---------------------------------------------------------------------------
# Deferred import pattern — production module may not exist when tests are
# authored.  Import inside each test body so pytest collection succeeds even
# when the file is absent, yielding per-test ImportError (RED state) rather
# than collection-time failure.
# ---------------------------------------------------------------------------


def _load_module():
    """Load inject_subagent_context.py as a module, or raise ImportError."""
    if not MODULE_PATH.exists():
        raise ImportError(
            "hooks/inject_subagent_context.py not found. The production module does not yet exist."
        )
    spec = importlib.util.spec_from_file_location("inject_subagent_context", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError("Could not load spec for inject_subagent_context.py")
    module = importlib.util.module_from_spec(spec)
    # Fresh load each time so monkeypatched env is visible
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# stdin payload builders — canonical shapes from SYSTEMS_PLAN.md §Interfaces
# ---------------------------------------------------------------------------

PREAMBLE_MARKER = "[Praxion process active]"
SESSION_WORKTREE_MARKER = "[Worktree session]"
BRIEFED_ROOT_MARKER = "[Worktree briefing]"
_ORIGINAL_PROMPT = "Research X for the current task."


def _pretooluse_payload(
    subagent_type: str,
    prompt: str = _ORIGINAL_PROMPT,
    cwd: str | None = None,
    session_id: str = "test-session-001",
) -> dict[str, Any]:
    """Build a valid PreToolUse(Agent) stdin payload."""
    return {
        "tool_name": "Agent",
        "tool_input": {
            "subagent_type": subagent_type,
            "prompt": prompt,
        },
        "cwd": cwd or "/tmp/fake-praxion-project",
        "session_id": session_id,
        "transcript_path": "/dev/null",
    }


def _run_hook(
    payload: dict[str, Any] | None,
    env_extra: dict[str, str] | None = None,
    cwd_override: str | None = None,
    raw_stdin: str | None = None,
) -> subprocess.CompletedProcess:
    """Run inject_subagent_context.py as a subprocess with the given payload."""
    env = {**os.environ}
    # Strip all PRAXION_* keys so tests start from a clean slate
    for key in list(env):
        if key.startswith("PRAXION_"):
            del env[key]
    if env_extra:
        env.update(env_extra)
    stdin = raw_stdin if raw_stdin is not None else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(MODULE_PATH)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd_override,
        timeout=10,
    )


def _prompt_that_names(worktree_path: str, note: str = _ORIGINAL_PROMPT) -> str:
    """A prompt whose text names an absolute .claude/worktrees/<name> path."""
    return f"Your target worktree root is {worktree_path}. {note}"


# ---------------------------------------------------------------------------
# Fixtures — plain dirs (preamble gate) and hermetic git repos (worktree gates)
# ---------------------------------------------------------------------------


@pytest.fixture
def praxion_project(tmp_path: Path) -> Path:
    """A temporary directory that looks like a Praxion-managed project.

    Contains a .ai-state/ directory (the preamble's presence signal) but is
    NOT a git repo — isolates preamble behavior from worktree-line behavior.
    """
    ai_state = tmp_path / ".ai-state"
    ai_state.mkdir()
    return tmp_path


@pytest.fixture
def non_praxion_project(tmp_path: Path) -> Path:
    """A temporary directory without .ai-state/ and without git — not a
    Praxion project, no worktree boundary."""
    return tmp_path


@pytest.fixture
def main_repo(tmp_path: Path) -> Path:
    """A real git repo serving as the 'main' (canonical) worktree — no
    .ai-state/, so the preamble gate stays independently closed."""
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
def praxion_main_repo(main_repo: Path) -> Path:
    """The main_repo fixture, additionally marked as a Praxion project."""
    (main_repo / ".ai-state").mkdir()
    return main_repo


@pytest.fixture
def linked_worktree(main_repo: Path, tmp_path: Path) -> Path:
    """A linked worktree created from the main repo — no .ai-state/."""
    wt = tmp_path / "linked"
    subprocess.run(
        ["git", "-C", str(main_repo), "worktree", "add", "-q", str(wt), "-b", "feature"],
        check=True,
    )
    return wt


@pytest.fixture
def praxion_linked_worktree(linked_worktree: Path) -> Path:
    """The linked_worktree fixture, additionally marked as a Praxion project."""
    (linked_worktree / ".ai-state").mkdir()
    return linked_worktree


@pytest.fixture(autouse=True)
def _clear_praxion_env(monkeypatch):
    """Each test starts with no PRAXION_* env vars set."""
    for key in list(os.environ):
        if key.startswith("PRAXION_"):
            monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# Group 1: Preamble — host-native subagent injection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("subagent_type", ["Explore", "Plan", "general-purpose"])
def test_host_native_subagent_receives_preamble_in_praxion_project(
    subagent_type: str, praxion_project: Path
) -> None:
    """Host-native subagents get the Praxion preamble prepended to their prompt."""
    payload = _pretooluse_payload(
        subagent_type=subagent_type,
        cwd=str(praxion_project),
    )
    result = _run_hook(payload)

    assert result.returncode == 0, f"Hook exited non-zero: {result.stderr}"
    assert result.stdout, "Expected updatedInput JSON on stdout"
    output = json.loads(result.stdout)
    updated_prompt = output["hookSpecificOutput"]["updatedInput"]["prompt"]
    assert updated_prompt.startswith(PREAMBLE_MARKER), (
        f"Preamble not prepended for {subagent_type!r}: {updated_prompt[:80]!r}"
    )
    assert _ORIGINAL_PROMPT in updated_prompt, "Original prompt must be preserved after preamble"


def test_preamble_contains_behavioral_contract_keywords(
    praxion_project: Path,
) -> None:
    """Injected preamble includes all four behavioral contract principles."""
    payload = _pretooluse_payload(subagent_type="Explore", cwd=str(praxion_project))
    result = _run_hook(payload)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    prompt = output["hookSpecificOutput"]["updatedInput"]["prompt"]
    for keyword in [
        "Surface Assumptions",
        "Register Objection",
        "Stay Surgical",
        "Simplicity First",
    ]:
        assert keyword in prompt, f"Keyword {keyword!r} missing from preamble"


def test_preamble_contains_return_contract(praxion_project: Path) -> None:
    """Preamble carries the pointer-not-payload return contract for host-native
    agents that have no `## Output` block and do not load the always-on rule."""
    payload = _pretooluse_payload(subagent_type="Explore", cwd=str(praxion_project))
    result = _run_hook(payload)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    prompt = output["hookSpecificOutput"]["updatedInput"]["prompt"]
    for phrase in ["pointer, not a payload", ".ai-work/"]:
        assert phrase in prompt, f"Return-contract phrase {phrase!r} missing"


def test_preamble_length_is_compact(praxion_project: Path) -> None:
    """The injected preamble stays within the ~180 char spec limit."""
    payload = _pretooluse_payload(subagent_type="Explore", cwd=str(praxion_project))
    result = _run_hook(payload)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    prompt = output["hookSpecificOutput"]["updatedInput"]["prompt"]
    # Extract only the prepended preamble (everything before the original prompt)
    preamble = prompt[: prompt.index(_ORIGINAL_PROMPT)]
    assert len(preamble) <= 300, (
        f"Preamble too long ({len(preamble)} chars, spec ~180+separator): {preamble!r}"
    )


def test_output_preserves_subagent_type_unchanged(praxion_project: Path) -> None:
    """The hook returns the subagent_type field unchanged in updatedInput."""
    payload = _pretooluse_payload(subagent_type="Plan", cwd=str(praxion_project))
    result = _run_hook(payload)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    returned_type = output["hookSpecificOutput"]["updatedInput"]["subagent_type"]
    assert returned_type == "Plan"


def test_output_preserves_description_and_other_tool_input_fields(
    praxion_project: Path,
) -> None:
    """The hook must preserve every original tool_input field, not just
    subagent_type and prompt.

    Canary for the host-native spawn breakage: the Agent tool requires a
    `description` field. An earlier version reconstructed tool_input from
    scratch with only subagent_type + prompt, dropping `description` (and
    `model`, `run_in_background`, …), so Explore/Plan/general-purpose spawns
    failed schema validation. This test feeds a payload carrying those extra
    fields and asserts they survive the injection.
    """
    payload = _pretooluse_payload(subagent_type="Explore", cwd=str(praxion_project))
    payload["tool_input"]["description"] = "probe task"
    payload["tool_input"]["model"] = "sonnet"
    payload["tool_input"]["run_in_background"] = True

    result = _run_hook(payload)
    assert result.returncode == 0, f"Hook exited non-zero: {result.stderr}"
    output = json.loads(result.stdout)
    returned = output["hookSpecificOutput"]["updatedInput"]
    assert returned.get("description") == "probe task", (
        "description field dropped — host-native Agent spawns will fail schema validation"
    )
    assert returned.get("model") == "sonnet", "model field dropped"
    assert returned.get("run_in_background") is True, "run_in_background field dropped"
    # And the prompt is still injected
    assert returned["prompt"].startswith(PREAMBLE_MARKER)


def test_output_hook_event_name_is_pretooluse(praxion_project: Path) -> None:
    """The hookEventName field in output is PreToolUse."""
    payload = _pretooluse_payload(subagent_type="Explore", cwd=str(praxion_project))
    result = _run_hook(payload)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["hookSpecificOutput"]["hookEventName"] == "PreToolUse"


# ---------------------------------------------------------------------------
# Group 2: Preamble — Praxion-native subagent skip (default behavior)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subagent_type",
    [
        "praxion:researcher",
        "praxion:implementer",
        "praxion:test-engineer",
        "praxion:systems-architect",
        "praxion:verifier",
    ],
)
def test_praxion_native_subagent_skipped_by_default(
    subagent_type: str, praxion_project: Path
) -> None:
    """Praxion-native agents (praxion:*) produce no injection by default (no
    preamble; not a worktree session; prompt names no worktree)."""
    payload = _pretooluse_payload(subagent_type=subagent_type, cwd=str(praxion_project))
    result = _run_hook(payload)

    assert result.returncode == 0, f"Hook exited non-zero: {result.stderr}"
    # No injection: stdout must be empty (silent pass-through)
    assert result.stdout == "", (
        f"Praxion-native agent {subagent_type!r} should not receive injection "
        f"by default, but got stdout: {result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# Group 3: Preamble — Praxion-native opt-in via PRAXION_INJECT_NATIVE_SUBAGENTS=1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("subagent_type", ["praxion:researcher", "praxion:implementer"])
def test_praxion_native_receives_preamble_when_opt_in_env_set(
    subagent_type: str, praxion_project: Path
) -> None:
    """With PRAXION_INJECT_NATIVE_SUBAGENTS=1, praxion:* agents also get the preamble."""
    payload = _pretooluse_payload(subagent_type=subagent_type, cwd=str(praxion_project))
    result = _run_hook(payload, env_extra={"PRAXION_INJECT_NATIVE_SUBAGENTS": "1"})

    assert result.returncode == 0
    assert result.stdout, "Expected updatedInput JSON when opt-in env is set"
    output = json.loads(result.stdout)
    prompt = output["hookSpecificOutput"]["updatedInput"]["prompt"]
    assert prompt.startswith(PREAMBLE_MARKER), (
        f"Preamble not prepended for {subagent_type!r} with opt-in env set"
    )


def test_praxion_native_injection_opt_in_does_not_affect_host_native(
    praxion_project: Path,
) -> None:
    """Host-native subagents are always injected regardless of the opt-in flag."""
    payload = _pretooluse_payload(subagent_type="Explore", cwd=str(praxion_project))
    # Without opt-in
    result_default = _run_hook(payload)
    assert result_default.returncode == 0
    assert result_default.stdout, "Explore must be injected by default"

    # With opt-in (should also inject)
    result_optin = _run_hook(payload, env_extra={"PRAXION_INJECT_NATIVE_SUBAGENTS": "1"})
    assert result_optin.returncode == 0
    assert result_optin.stdout, "Explore must still be injected with opt-in"


# ---------------------------------------------------------------------------
# Group 4: Preamble — .ai-state/ gate (non-Praxion project → no preamble)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("subagent_type", ["Explore", "Plan", "praxion:researcher"])
def test_no_injection_when_ai_state_absent(subagent_type: str, non_praxion_project: Path) -> None:
    """No injection occurs for any subagent type when .ai-state/ is absent and
    the cwd is not a git repo (none-apply composition case)."""
    payload = _pretooluse_payload(subagent_type=subagent_type, cwd=str(non_praxion_project))
    result = _run_hook(payload)

    assert result.returncode == 0
    assert result.stdout == "", f"No injection expected without .ai-state/; got: {result.stdout!r}"


def test_no_injection_when_cwd_has_no_ai_state_subdirectory(tmp_path: Path) -> None:
    """Even with a valid filesystem path, no preamble if .ai-state/ is missing."""
    # Create unrelated dirs to confirm it's not just "any dir triggers injection"
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    payload = _pretooluse_payload(subagent_type="Plan", cwd=str(tmp_path))
    result = _run_hook(payload)
    assert result.returncode == 0
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# Group 5: Preamble — PRAXION_DISABLE_SUBAGENT_INJECT opt-out
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("subagent_type", ["Explore", "Plan", "general-purpose"])
def test_injection_disabled_when_opt_out_env_set(subagent_type: str, praxion_project: Path) -> None:
    """PRAXION_DISABLE_SUBAGENT_INJECT=1 suppresses the preamble even in Praxion projects."""
    payload = _pretooluse_payload(subagent_type=subagent_type, cwd=str(praxion_project))
    result = _run_hook(payload, env_extra={"PRAXION_DISABLE_SUBAGENT_INJECT": "1"})

    assert result.returncode == 0
    assert result.stdout == "", f"Expected no injection with opt-out flag, got: {result.stdout!r}"


def test_opt_out_also_suppresses_native_opt_in(praxion_project: Path) -> None:
    """PRAXION_DISABLE_SUBAGENT_INJECT takes precedence over PRAXION_INJECT_NATIVE_SUBAGENTS."""
    payload = _pretooluse_payload(subagent_type="praxion:researcher", cwd=str(praxion_project))
    result = _run_hook(
        payload,
        env_extra={
            "PRAXION_DISABLE_SUBAGENT_INJECT": "1",
            "PRAXION_INJECT_NATIVE_SUBAGENTS": "1",
        },
    )
    assert result.returncode == 0
    assert result.stdout == "", "Opt-out must override opt-in"


def test_disable_preamble_flag_does_not_suppress_worktree_line(
    linked_worktree: Path,
) -> None:
    """PRAXION_DISABLE_SUBAGENT_INJECT is scoped to the preamble only — the
    session-worktree line still fires inside a linked worktree."""
    payload = _pretooluse_payload(subagent_type="praxion:implementer", cwd=str(linked_worktree))
    result = _run_hook(payload, env_extra={"PRAXION_DISABLE_SUBAGENT_INJECT": "1"})

    assert result.returncode == 0
    assert result.stdout, "Session-worktree line must still fire"
    output = json.loads(result.stdout)
    prompt = output["hookSpecificOutput"]["updatedInput"]["prompt"]
    assert SESSION_WORKTREE_MARKER in prompt
    assert PREAMBLE_MARKER not in prompt


# ---------------------------------------------------------------------------
# Group 6: Malformed stdin — unconditional exit 0 (fail-open)
# ---------------------------------------------------------------------------


def test_empty_stdin_exits_zero_without_crash() -> None:
    """Empty stdin must not cause an exception — exit 0, no stdout."""
    result = _run_hook(None, raw_stdin="")
    assert result.returncode == 0, f"Expected exit 0, got {result.returncode}: {result.stderr}"
    assert result.stdout == ""


def test_malformed_json_stdin_exits_zero_without_crash() -> None:
    """Malformed JSON on stdin must not crash the hook — exit 0."""
    result = _run_hook(None, raw_stdin="not valid json {{{")
    assert result.returncode == 0, f"Expected exit 0, got {result.returncode}: {result.stderr}"
    assert "Traceback" not in result.stderr


def test_missing_tool_input_field_exits_zero() -> None:
    """Payload missing tool_input must not crash the hook — exit 0."""
    payload = {"tool_name": "Agent", "cwd": "/tmp", "session_id": "s1"}
    result = _run_hook(payload)
    assert result.returncode == 0


def test_missing_subagent_type_field_exits_zero() -> None:
    """Payload missing subagent_type must not crash the hook — exit 0."""
    payload = {
        "tool_name": "Agent",
        "tool_input": {"prompt": "do something"},
        "cwd": "/tmp",
        "session_id": "s1",
    }
    result = _run_hook(payload)
    assert result.returncode == 0


def test_missing_cwd_field_exits_zero() -> None:
    """Payload missing cwd must not crash the hook — exit 0, and neither the
    preamble nor the worktree lines fire without a cwd."""
    payload = {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "Explore", "prompt": "research"},
        "session_id": "s1",
    }
    result = _run_hook(payload)
    assert result.returncode == 0
    assert result.stdout == ""


def test_non_agent_tool_name_exits_zero_silently(praxion_project: Path) -> None:
    """Non-Agent tool_name (e.g. Bash) must exit 0 with no injection."""
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "echo hi"},
        "cwd": str(praxion_project),
        "session_id": "s1",
    }
    result = _run_hook(payload)
    assert result.returncode == 0
    assert result.stdout == ""


def test_tool_input_not_a_dict_exits_zero() -> None:
    """A non-object tool_input must not crash the hook — exit 0."""
    payload = {"tool_name": "Agent", "tool_input": "not-a-dict", "cwd": "/tmp"}
    result = _run_hook(payload)
    assert result.returncode == 0
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# Group 7: Per-session-id caching (preamble .ai-state/ stat cache)
# ---------------------------------------------------------------------------


def test_second_call_same_session_id_still_injects(praxion_project: Path) -> None:
    """Repeated calls with the same session_id still inject correctly.

    The cache is for filesystem stat performance only — it must not suppress
    injection on a second call if the first call determined injection should occur.
    """
    payload = _pretooluse_payload(
        subagent_type="Explore",
        cwd=str(praxion_project),
        session_id="cached-session-xyz",
    )
    for _ in range(2):
        result = _run_hook(payload)
        assert result.returncode == 0
        assert result.stdout, "Injection must fire on each call (same session_id)"
        output = json.loads(result.stdout)
        prompt = output["hookSpecificOutput"]["updatedInput"]["prompt"]
        assert prompt.startswith(PREAMBLE_MARKER)


def test_different_session_ids_both_inject(praxion_project: Path) -> None:
    """Two calls with different session_ids both inject correctly."""
    for session_id in ["session-alpha", "session-beta"]:
        payload = _pretooluse_payload(
            subagent_type="Plan",
            cwd=str(praxion_project),
            session_id=session_id,
        )
        result = _run_hook(payload)
        assert result.returncode == 0
        assert result.stdout, f"Expected injection for {session_id}"


# ---------------------------------------------------------------------------
# Group 8: Latency assertion (fast-path, no .ai-state/, no git repo)
# ---------------------------------------------------------------------------


def test_fast_path_no_ai_state_completes_under_2000ms(
    non_praxion_project: Path,
) -> None:
    """No-.ai-state/, non-git fast-path (skip) completes well within CI bounds.

    Methodology: warm up Python import by loading the module once in a subprocess,
    then time the actual hook execution. 2000ms is a generous CI-safe ceiling —
    the logic path itself (one filesystem stat + failed git subprocess calls for
    the worktree gate) is expected to run in low tens of milliseconds.
    """
    payload = _pretooluse_payload(subagent_type="Explore", cwd=str(non_praxion_project))
    payload_json = json.dumps(payload)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PRAXION_")}

    times: list[float] = []
    for _ in range(5):
        t0 = time.perf_counter()
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH)],
            input=payload_json,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
        assert result.returncode == 0

    best_ms = min(times) * 1000
    assert best_ms < 2000, (
        f"Fast-path hook took {best_ms:.0f}ms (best of 5). "
        "If Python/git startup is unusually slow on this system, consider adjusting."
    )


def test_inject_path_completes_under_2000ms_including_python_startup(
    praxion_project: Path,
) -> None:
    """Injection path completes in < 2000ms including Python startup (CI-safe bound).

    Catches regressions caused by accidental heavy I/O (file reads, network
    calls, heavy imports) in the injection path.
    """
    payload = _pretooluse_payload(subagent_type="Explore", cwd=str(praxion_project))
    payload_json = json.dumps(payload)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PRAXION_")}

    t0 = time.perf_counter()
    result = subprocess.run(
        [sys.executable, str(MODULE_PATH)],
        input=payload_json,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert result.returncode == 0
    assert elapsed_ms < 2000, (
        f"Injection path took {elapsed_ms:.0f}ms (wall-clock including Python startup). "
        "This suggests heavy I/O or imports in the hook script — investigate."
    )


# ---------------------------------------------------------------------------
# Group 9: Module-level importability (structural smoke test)
# ---------------------------------------------------------------------------


def test_module_is_importable_and_has_expected_callable() -> None:
    """The hook module imports cleanly and exposes its main callable.

    Uses deferred import so this test fails with ImportError (RED) before
    the implementer creates the file, and passes (GREEN) after.
    """
    mod = _load_module()
    has_main = hasattr(mod, "main") and callable(mod.main)
    has_run = hasattr(mod, "run") and callable(mod.run)
    assert has_main or has_run, (
        "inject_subagent_context.py must expose a callable `main` or `run` "
        "for testability. If the hook only has __main__ guard, add a main() function."
    )


# ---------------------------------------------------------------------------
# Group 10: Session-worktree line — canary + suppression + all subagent types
# ---------------------------------------------------------------------------


def test_injects_session_worktree_line_from_worktree_cwd(linked_worktree: Path) -> None:
    """Gate-liveness canary: a session cwd inside a linked worktree must inject
    the absolute-path session-worktree line into the spawned subagent's prompt.

    Self-test: if the worktree-detection branch were gutted (always returning
    None), stdout would stay empty and this test would fail — proving the gate
    is not a no-op that only ever passes on the current (non-firing) state.
    """
    payload = _pretooluse_payload(subagent_type="praxion:implementer", cwd=str(linked_worktree))
    result = _run_hook(payload)

    assert result.returncode == 0, f"Hook exited non-zero: {result.stderr}"
    assert result.stdout, "Expected updatedInput JSON on stdout for a worktree cwd"
    output = json.loads(result.stdout)
    updated_prompt = output["hookSpecificOutput"]["updatedInput"]["prompt"]
    assert SESSION_WORKTREE_MARKER in updated_prompt
    assert str(linked_worktree.resolve()) in updated_prompt, (
        "Briefing must name the absolute worktree root"
    )
    assert "absolute paths" in updated_prompt.lower()
    assert "never relative" in updated_prompt.lower() or "relative paths" in updated_prompt.lower()
    assert _ORIGINAL_PROMPT in updated_prompt, "Original prompt must be preserved"


def test_no_session_worktree_line_from_canonical_checkout_cwd(main_repo: Path) -> None:
    """Gate-liveness suppression case: the main (canonical) checkout has no
    worktree boundary to brief — no session-worktree line.

    Paired with the canary above: same hook, same subagent payload shape, the
    only variable is cwd (linked worktree vs main checkout). This rules out a
    hook that fires unconditionally regardless of worktree state.
    """
    payload = _pretooluse_payload(subagent_type="praxion:implementer", cwd=str(main_repo))
    result = _run_hook(payload)

    assert result.returncode == 0
    assert result.stdout == "", (
        f"No injection expected from the main checkout; got: {result.stdout!r}"
    )


def test_no_session_worktree_line_when_cwd_is_not_a_git_repo(tmp_path: Path) -> None:
    """A non-git cwd has no worktree boundary — no injection, fail-open."""
    non_git = tmp_path / "not-a-repo"
    non_git.mkdir()
    payload = _pretooluse_payload(subagent_type="praxion:implementer", cwd=str(non_git))
    result = _run_hook(payload)

    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.parametrize(
    "subagent_type",
    ["praxion:implementer", "praxion:systems-architect", "Explore", "Plan", "general-purpose"],
)
def test_session_worktree_line_injects_for_every_subagent_type(
    subagent_type: str, linked_worktree: Path
) -> None:
    """Unlike the preamble's gate (d), praxion:* agents are NOT skipped for the
    session-worktree line: they are the common case in worktree pipelines
    (EnterWorktree is a Standard/Full requirement), so excluding them would
    leave the most frequent spawn path unmitigated.
    """
    payload = _pretooluse_payload(subagent_type=subagent_type, cwd=str(linked_worktree))
    result = _run_hook(payload)

    assert result.returncode == 0
    assert result.stdout, f"Expected injection for subagent_type={subagent_type!r}"
    output = json.loads(result.stdout)
    assert output["hookSpecificOutput"]["updatedInput"]["subagent_type"] == subagent_type
    assert SESSION_WORKTREE_MARKER in output["hookSpecificOutput"]["updatedInput"]["prompt"]


def test_disable_worktree_flag_suppresses_session_worktree_line(linked_worktree: Path) -> None:
    payload = _pretooluse_payload(subagent_type="praxion:implementer", cwd=str(linked_worktree))
    result = _run_hook(payload, env_extra={"PRAXION_DISABLE_WORKTREE_PATH_BRIEFING": "1"})
    assert result.returncode == 0
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# Group 11: Briefed-root line (td-051 direction) — canary + suppression
# ---------------------------------------------------------------------------


def test_injects_briefed_root_line_when_canonical_session_names_a_worktree(
    main_repo: Path,
) -> None:
    """Gate-liveness canary for the td-051 direction: a CANONICAL session (no
    worktree boundary of its own) briefing an agent INTO a worktree via the
    prompt text must get a deterministic reinforcement line — the exact gap
    that let a doc-engineer commit to the wrong tree despite an absolute-path
    briefing.

    Self-test: if the prompt-regex branch were gutted (always returning None),
    stdout would stay empty (main_repo has no worktree boundary of its own,
    so the session-worktree line does not fire either) and this test would
    fail.
    """
    named_worktree = "/Users/example/project/.claude/worktrees/other-feature"
    payload = _pretooluse_payload(
        subagent_type="praxion:doc-engineer",
        prompt=_prompt_that_names(named_worktree),
        cwd=str(main_repo),
    )
    result = _run_hook(payload)

    assert result.returncode == 0, f"Hook exited non-zero: {result.stderr}"
    assert result.stdout, "Expected updatedInput JSON when prompt names a worktree root"
    output = json.loads(result.stdout)
    updated_prompt = output["hookSpecificOutput"]["updatedInput"]["prompt"]
    assert BRIEFED_ROOT_MARKER in updated_prompt
    assert named_worktree in updated_prompt
    assert SESSION_WORKTREE_MARKER not in updated_prompt, "main_repo has no worktree of its own"
    assert _ORIGINAL_PROMPT in updated_prompt


def test_no_briefed_root_line_when_prompt_names_no_worktree(main_repo: Path) -> None:
    """Suppression case: a canonical session with an ordinary prompt (no
    worktree path named) gets no briefed-root line."""
    payload = _pretooluse_payload(subagent_type="praxion:implementer", cwd=str(main_repo))
    result = _run_hook(payload)
    assert result.returncode == 0
    assert result.stdout == ""


def test_no_briefed_root_line_when_prompt_names_the_sessions_own_root(
    linked_worktree: Path,
) -> None:
    """Suppression case: when the prompt names the SAME worktree root the
    session is already in, the briefed-root line does not duplicate the
    session-worktree line — only one line fires."""
    own_root = str(linked_worktree.resolve())
    payload = _pretooluse_payload(
        subagent_type="praxion:implementer",
        prompt=_prompt_that_names(own_root),
        cwd=str(linked_worktree),
    )
    result = _run_hook(payload)

    assert result.returncode == 0
    assert result.stdout, "Session-worktree line should still fire"
    output = json.loads(result.stdout)
    prompt = output["hookSpecificOutput"]["updatedInput"]["prompt"]
    assert SESSION_WORKTREE_MARKER in prompt
    assert BRIEFED_ROOT_MARKER not in prompt, "Naming the session's own root is not a mismatch"


def test_no_briefed_root_line_when_prompt_names_a_subpath_of_sessions_own_root(
    linked_worktree: Path,
) -> None:
    """A prompt naming a FILE under the session's own worktree root (not just
    the bare root) is still recognized as 'already there' — no duplicate line."""
    sub_path = f"{linked_worktree.resolve()}/src/module.py"
    payload = _pretooluse_payload(
        subagent_type="praxion:implementer",
        prompt=_prompt_that_names(str(linked_worktree.resolve()), note=f"Edit {sub_path}."),
        cwd=str(linked_worktree),
    )
    result = _run_hook(payload)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    prompt = output["hookSpecificOutput"]["updatedInput"]["prompt"]
    assert BRIEFED_ROOT_MARKER not in prompt


@pytest.mark.parametrize(
    "subagent_type",
    ["praxion:implementer", "praxion:doc-engineer", "Explore", "Plan", "general-purpose"],
)
def test_briefed_root_line_injects_for_every_subagent_type(
    subagent_type: str, main_repo: Path
) -> None:
    """No praxion:* skip for the briefed-root line either — symmetric with the
    session-worktree line's all-agent-types contract."""
    named_worktree = "/Users/example/project/.claude/worktrees/other-feature"
    payload = _pretooluse_payload(
        subagent_type=subagent_type,
        prompt=_prompt_that_names(named_worktree),
        cwd=str(main_repo),
    )
    result = _run_hook(payload)
    assert result.returncode == 0
    assert result.stdout, f"Expected injection for subagent_type={subagent_type!r}"
    output = json.loads(result.stdout)
    assert BRIEFED_ROOT_MARKER in output["hookSpecificOutput"]["updatedInput"]["prompt"]


def test_disable_worktree_flag_suppresses_briefed_root_line(main_repo: Path) -> None:
    named_worktree = "/Users/example/project/.claude/worktrees/other-feature"
    payload = _pretooluse_payload(
        subagent_type="praxion:implementer",
        prompt=_prompt_that_names(named_worktree),
        cwd=str(main_repo),
    )
    result = _run_hook(payload, env_extra={"PRAXION_DISABLE_WORKTREE_PATH_BRIEFING": "1"})
    assert result.returncode == 0
    assert result.stdout == ""


def test_briefed_root_and_session_worktree_lines_both_fire_on_worktree_mismatch(
    linked_worktree: Path,
) -> None:
    """A session already inside worktree A, whose prompt names a DIFFERENT
    worktree B, gets BOTH lines: its own session-worktree boundary and the
    mismatch reinforcement for the named target."""
    other_worktree = "/Users/example/project/.claude/worktrees/other-feature"
    payload = _pretooluse_payload(
        subagent_type="praxion:implementer",
        prompt=_prompt_that_names(other_worktree),
        cwd=str(linked_worktree),
    )
    result = _run_hook(payload)

    assert result.returncode == 0
    output = json.loads(result.stdout)
    prompt = output["hookSpecificOutput"]["updatedInput"]["prompt"]
    assert SESSION_WORKTREE_MARKER in prompt
    assert BRIEFED_ROOT_MARKER in prompt
    assert str(linked_worktree.resolve()) in prompt
    assert other_worktree in prompt


# ---------------------------------------------------------------------------
# Group 12: Composition matrix — preamble / worktree-line-only / briefed-root-
# only / combos / none-apply
# ---------------------------------------------------------------------------


def test_composition_preamble_only(praxion_project: Path) -> None:
    """Praxion project, non-git cwd, host-native agent: preamble fires alone."""
    payload = _pretooluse_payload(subagent_type="Explore", cwd=str(praxion_project))
    result = _run_hook(payload)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    prompt = output["hookSpecificOutput"]["updatedInput"]["prompt"]
    assert PREAMBLE_MARKER in prompt
    assert SESSION_WORKTREE_MARKER not in prompt
    assert BRIEFED_ROOT_MARKER not in prompt


def test_composition_session_worktree_line_only_no_preamble_for_iam_agent(
    linked_worktree: Path,
) -> None:
    """praxion agent in a worktree session (no .ai-state/, not opted in): the
    session-worktree line fires, but the preamble does NOT — praxion:* agents
    are skipped by default and this worktree has no .ai-state/ either way."""
    payload = _pretooluse_payload(subagent_type="praxion:implementer", cwd=str(linked_worktree))
    result = _run_hook(payload)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    prompt = output["hookSpecificOutput"]["updatedInput"]["prompt"]
    assert SESSION_WORKTREE_MARKER in prompt
    assert PREAMBLE_MARKER not in prompt
    assert BRIEFED_ROOT_MARKER not in prompt


def test_composition_briefed_root_only_canonical_session_names_worktree(
    non_praxion_project: Path,
) -> None:
    """The td-051 canary in composition-matrix form: a non-Praxion, non-git
    session (no preamble, no session-worktree boundary) whose prompt names a
    worktree root gets ONLY the briefed-root line."""
    named_worktree = "/Users/example/project/.claude/worktrees/other-feature"
    payload = _pretooluse_payload(
        subagent_type="Explore",
        prompt=_prompt_that_names(named_worktree),
        cwd=str(non_praxion_project),
    )
    result = _run_hook(payload)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    prompt = output["hookSpecificOutput"]["updatedInput"]["prompt"]
    assert BRIEFED_ROOT_MARKER in prompt
    assert PREAMBLE_MARKER not in prompt
    assert SESSION_WORKTREE_MARKER not in prompt


def test_composition_preamble_plus_session_worktree_line(
    praxion_linked_worktree: Path,
) -> None:
    """Praxion project inside a linked worktree, host-native agent: preamble
    AND session-worktree line both fire."""
    payload = _pretooluse_payload(subagent_type="Explore", cwd=str(praxion_linked_worktree))
    result = _run_hook(payload)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    prompt = output["hookSpecificOutput"]["updatedInput"]["prompt"]
    assert PREAMBLE_MARKER in prompt
    assert SESSION_WORKTREE_MARKER in prompt
    assert BRIEFED_ROOT_MARKER not in prompt


def test_composition_preamble_plus_briefed_root_line(praxion_main_repo: Path) -> None:
    """Praxion project, canonical (non-worktree) session, host-native agent,
    prompt names a different worktree: preamble AND briefed-root line both
    fire; the session-worktree line does not (main_repo has no boundary)."""
    named_worktree = "/Users/example/project/.claude/worktrees/other-feature"
    payload = _pretooluse_payload(
        subagent_type="Explore",
        prompt=_prompt_that_names(named_worktree),
        cwd=str(praxion_main_repo),
    )
    result = _run_hook(payload)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    prompt = output["hookSpecificOutput"]["updatedInput"]["prompt"]
    assert PREAMBLE_MARKER in prompt
    assert BRIEFED_ROOT_MARKER in prompt
    assert SESSION_WORKTREE_MARKER not in prompt


def test_composition_none_apply_yields_no_output(non_praxion_project: Path) -> None:
    """Non-Praxion, non-git cwd, praxion agent, ordinary prompt: none of the
    three conditions hold — the hook emits nothing at all."""
    payload = _pretooluse_payload(subagent_type="praxion:implementer", cwd=str(non_praxion_project))
    result = _run_hook(payload)
    assert result.returncode == 0
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# Group 13: updatedInput envelope contract — direct object, no wrapper key
# ---------------------------------------------------------------------------


def test_updated_input_is_the_tool_input_object_directly(linked_worktree: Path) -> None:
    """Harness contract: updatedInput's value IS the replacement tool-input
    params object directly — never wrapped in an envelope key such as
    {"tool_input": ...}."""
    payload = _pretooluse_payload(subagent_type="praxion:implementer", cwd=str(linked_worktree))
    result = _run_hook(payload)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    updated = output["hookSpecificOutput"]["updatedInput"]
    assert "tool_input" not in updated, "updatedInput must not be wrapped in a tool_input envelope"
    assert "prompt" in updated
    assert "subagent_type" in updated


def test_worktree_lines_preserve_other_tool_input_fields(linked_worktree: Path) -> None:
    """description/model/run_in_background must survive the worktree-line
    injection untouched — the same field-preservation contract as the
    preamble path."""
    payload = _pretooluse_payload(subagent_type="praxion:implementer", cwd=str(linked_worktree))
    payload["tool_input"]["description"] = "implement step 3"
    payload["tool_input"]["model"] = "sonnet"
    payload["tool_input"]["run_in_background"] = True

    result = _run_hook(payload)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    updated = output["hookSpecificOutput"]["updatedInput"]
    assert updated["description"] == "implement step 3"
    assert updated["model"] == "sonnet"
    assert updated["run_in_background"] is True


# ---------------------------------------------------------------------------
# Group 14: In-process unit coverage of the three segment gates
#
# Every group above drives the hook as a subprocess, which is the right shape
# for the stdin/stdout contract but cannot force the branch-level failure modes
# that matter here: git timing out, git missing, `--show-toplevel` answering
# when the dir probes did not, the per-session stat cache actually caching.
# These tests call the functions directly. Each `_load_module()` gets a fresh
# module object, so the module-level `_session_cache` never leaks between tests.
# ---------------------------------------------------------------------------


def _drive_main(payload: object, monkeypatch, raw: str | None = None) -> str:
    """Run main() in-process with the payload on stdin; return stdout."""
    import io

    module = _load_module()
    stdin = raw if raw is not None else json.dumps(payload)
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    module.main()
    return ""


class TestAiStateGateAndCache:
    def test_directory_with_ai_state_is_recognized(self, praxion_project: Path) -> None:
        module = _load_module()
        assert module._has_ai_state(str(praxion_project), "s1") is True

    def test_directory_without_ai_state_is_rejected(self, non_praxion_project: Path) -> None:
        module = _load_module()
        assert module._has_ai_state(str(non_praxion_project), "s1") is False

    def test_second_lookup_for_the_same_session_reuses_the_cached_answer(
        self, praxion_project: Path
    ) -> None:
        """Dense fan-out must not re-stat the filesystem once per spawn."""
        module = _load_module()
        assert module._has_ai_state(str(praxion_project), "sess-cache") is True

        # Removing the directory would flip the real answer; the cache must win.
        (praxion_project / ".ai-state").rmdir()
        assert module._has_ai_state(str(praxion_project), "sess-cache") is True
        assert module._has_ai_state(str(praxion_project), "different-session") is False

    @pytest.mark.parametrize(
        ("subagent_type", "expected"),
        [("praxion:researcher", True), ("Explore", False), ("general-purpose", False), ("", False)],
    )
    def test_praxion_native_detection(self, subagent_type: str, expected: bool) -> None:
        module = _load_module()
        assert module._is_praxion_native(subagent_type) is expected


class TestPreambleSegmentGates:
    def test_host_native_agent_in_a_praxion_project_gets_the_preamble(
        self, praxion_project: Path
    ) -> None:
        module = _load_module()
        assert module._preamble_segment("Explore", str(praxion_project), "s1") == module._PREAMBLE

    def test_disable_flag_suppresses_the_preamble(self, praxion_project: Path, monkeypatch) -> None:
        monkeypatch.setenv("PRAXION_DISABLE_SUBAGENT_INJECT", "1")
        module = _load_module()
        assert module._preamble_segment("Explore", str(praxion_project), "s1") == ""

    def test_empty_cwd_suppresses_the_preamble(self) -> None:
        module = _load_module()
        assert module._preamble_segment("Explore", "", "s1") == ""

    def test_missing_ai_state_suppresses_the_preamble(self, non_praxion_project: Path) -> None:
        module = _load_module()
        assert module._preamble_segment("Explore", str(non_praxion_project), "s1") == ""

    def test_praxion_native_agent_is_skipped_by_default(self, praxion_project: Path) -> None:
        module = _load_module()
        assert module._preamble_segment("praxion:researcher", str(praxion_project), "s1") == ""

    @pytest.mark.parametrize("flag_value", ["1", "true", "YES"])
    def test_praxion_native_opt_in_restores_the_preamble(
        self, praxion_project: Path, monkeypatch, flag_value: str
    ) -> None:
        monkeypatch.setenv("PRAXION_INJECT_NATIVE_SUBAGENTS", flag_value)
        module = _load_module()
        assert module._preamble_segment("praxion:researcher", str(praxion_project), "s1") != ""

    def test_praxion_native_opt_in_ignores_a_non_truthy_value(
        self, praxion_project: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("PRAXION_INJECT_NATIVE_SUBAGENTS", "maybe")
        module = _load_module()
        assert module._preamble_segment("praxion:researcher", str(praxion_project), "s1") == ""


class TestGitProbe:
    def test_successful_probe_returns_stripped_stdout(self, main_repo: Path) -> None:
        module = _load_module()
        assert module._git(main_repo, "rev-parse", "--abbrev-ref", "HEAD")

    def test_non_zero_exit_returns_none(self, tmp_path: Path) -> None:
        module = _load_module()
        plain = tmp_path / "plain"
        plain.mkdir()
        assert module._git(plain, "rev-parse", "--show-toplevel") is None

    def test_empty_stdout_returns_none(self, main_repo: Path) -> None:
        module = _load_module()
        assert module._git(main_repo, "config", "--get", "praxion.absent.key") is None

    def test_timeout_returns_none(self, monkeypatch) -> None:
        module = _load_module()

        def _timeout(*_a, **_k):
            raise subprocess.TimeoutExpired(cmd="git", timeout=3)

        monkeypatch.setattr(module.subprocess, "run", _timeout)
        assert module._git(Path("/tmp"), "rev-parse") is None

    def test_missing_git_binary_returns_none(self, monkeypatch) -> None:
        module = _load_module()

        def _missing(*_a, **_k):
            raise OSError("no git")

        monkeypatch.setattr(module.subprocess, "run", _missing)
        assert module._git(Path("/tmp"), "rev-parse") is None


class TestLinkedWorktreeDetection:
    def test_linked_worktree_resolves_to_its_root(self, linked_worktree: Path) -> None:
        module = _load_module()
        assert module._linked_worktree_root(linked_worktree) == linked_worktree.resolve()

    def test_main_checkout_has_no_boundary_to_brief(self, main_repo: Path) -> None:
        module = _load_module()
        assert module._linked_worktree_root(main_repo) is None

    def test_non_git_directory_fails_open_to_no_briefing(self, tmp_path: Path) -> None:
        module = _load_module()
        assert module._linked_worktree_root(tmp_path) is None

    def test_unresolvable_toplevel_fails_open(self, linked_worktree: Path, monkeypatch) -> None:
        module = _load_module()
        real_git = module._git

        def _no_toplevel(cwd, *args):
            if args[:2] == ("rev-parse", "--show-toplevel"):
                return None
            return real_git(cwd, *args)

        monkeypatch.setattr(module, "_git", _no_toplevel)
        assert module._linked_worktree_root(linked_worktree) is None


class TestBriefedRootDetection:
    def test_named_worktree_differing_from_cwd_is_returned(self) -> None:
        module = _load_module()
        named = "/Users/x/proj/.claude/worktrees/feature-a"
        assert module._briefed_worktree_root(f"Target: {named}", "/Users/x/proj") == named

    def test_trailing_slash_is_normalized_away(self) -> None:
        module = _load_module()
        named = "/Users/x/proj/.claude/worktrees/feature-a"
        assert module._briefed_worktree_root(f"Target: {named}/", "/Users/x/proj") == named

    def test_the_sessions_own_root_is_not_a_mismatch(self) -> None:
        module = _load_module()
        named = "/Users/x/proj/.claude/worktrees/feature-a"
        assert module._briefed_worktree_root(f"Target: {named}", named) is None

    def test_a_cwd_inside_the_named_root_is_not_a_mismatch(self) -> None:
        module = _load_module()
        named = "/Users/x/proj/.claude/worktrees/feature-a"
        assert module._briefed_worktree_root(f"Target: {named}", f"{named}/src") is None

    def test_prompt_naming_no_worktree_yields_none(self) -> None:
        module = _load_module()
        assert module._briefed_worktree_root("Just do the thing.", "/Users/x/proj") is None

    def test_capture_stops_at_the_worktree_name(self) -> None:
        """A file path under the worktree must not sweep extra segments into
        the captured root."""
        module = _load_module()
        prompt = "Edit /Users/x/proj/.claude/worktrees/feature-a/src/mod.py now"
        assert (
            module._briefed_worktree_root(prompt, "/Users/x/proj")
            == "/Users/x/proj/.claude/worktrees/feature-a"
        )


class TestWorktreeSegmentComposition:
    def test_disable_flag_suppresses_both_worktree_lines(
        self, linked_worktree: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("PRAXION_DISABLE_WORKTREE_PATH_BRIEFING", "1")
        module = _load_module()
        assert module._worktree_segments(str(linked_worktree), "anything") == []

    def test_empty_cwd_suppresses_both_worktree_lines(self) -> None:
        module = _load_module()
        assert module._worktree_segments("", "anything") == []

    def test_session_line_only_inside_a_worktree_with_an_ordinary_prompt(
        self, linked_worktree: Path
    ) -> None:
        module = _load_module()
        segments = module._worktree_segments(str(linked_worktree), "do the thing")
        assert len(segments) == 1
        assert SESSION_WORKTREE_MARKER in segments[0]

    def test_both_lines_when_a_worktree_session_names_a_different_worktree(
        self, linked_worktree: Path
    ) -> None:
        module = _load_module()
        other = "/Users/x/proj/.claude/worktrees/other"
        segments = module._worktree_segments(str(linked_worktree), f"target {other}")
        assert [SESSION_WORKTREE_MARKER in s for s in segments].count(True) == 1
        assert [BRIEFED_ROOT_MARKER in s for s in segments].count(True) == 1

    def test_no_segments_for_a_plain_non_git_directory(self, tmp_path: Path) -> None:
        module = _load_module()
        assert module._worktree_segments(str(tmp_path), "do the thing") == []


class TestEmission:
    def test_segments_are_prepended_as_separate_paragraphs(self, capsys) -> None:
        module = _load_module()
        module._emit_updated_input(
            {"subagent_type": "Explore", "description": "probe"}, "ORIGINAL", ["A", "B"]
        )
        output = json.loads(capsys.readouterr().out)
        assert output["hookSpecificOutput"]["updatedInput"]["prompt"] == "A\n\nB\n\nORIGINAL"

    def test_emission_preserves_every_original_tool_input_field(self, capsys) -> None:
        module = _load_module()
        module._emit_updated_input(
            {"subagent_type": "Explore", "description": "probe", "model": "sonnet"}, "P", ["A"]
        )
        updated = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["updatedInput"]
        assert updated["description"] == "probe"
        assert updated["model"] == "sonnet"

    def test_permission_decision_is_allow(self, capsys) -> None:
        module = _load_module()
        module._emit_updated_input({"subagent_type": "Explore"}, "P", ["A"])
        output = json.loads(capsys.readouterr().out)
        assert output["hookSpecificOutput"]["permissionDecision"] == "allow"


class TestProcessAndMainInProcess:
    def test_non_agent_tool_emits_nothing(self, capsys, praxion_project: Path) -> None:
        module = _load_module()
        module._process({"tool_name": "Bash", "cwd": str(praxion_project)})
        assert capsys.readouterr().out == ""

    def test_non_dict_tool_input_emits_nothing(self, capsys) -> None:
        module = _load_module()
        module._process({"tool_name": "Agent", "tool_input": "oops", "cwd": "/tmp"})
        assert capsys.readouterr().out == ""

    def test_no_applicable_segment_emits_nothing(self, capsys, non_praxion_project: Path) -> None:
        module = _load_module()
        module._process(
            {
                "tool_name": "Agent",
                "tool_input": {"subagent_type": "praxion:implementer", "prompt": "go"},
                "cwd": str(non_praxion_project),
                "session_id": "s1",
            }
        )
        assert capsys.readouterr().out == ""

    def test_applicable_segments_are_composed_into_one_emission(
        self, capsys, praxion_linked_worktree: Path
    ) -> None:
        """The composition path end to end: preamble + session-worktree line,
        one updatedInput, original prompt last."""
        module = _load_module()
        module._process(
            {
                "tool_name": "Agent",
                "tool_input": {"subagent_type": "Explore", "prompt": "ORIGINAL"},
                "cwd": str(praxion_linked_worktree),
                "session_id": "s1",
            }
        )
        prompt = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["updatedInput"]["prompt"]
        assert prompt.startswith(PREAMBLE_MARKER)
        assert SESSION_WORKTREE_MARKER in prompt
        assert prompt.endswith("ORIGINAL")

    def test_main_emits_for_an_applicable_payload(self, capsys, monkeypatch, praxion_project: Path):
        _drive_main(
            {
                "tool_name": "Agent",
                "tool_input": {"subagent_type": "Explore", "prompt": "ORIGINAL"},
                "cwd": str(praxion_project),
                "session_id": "s1",
            },
            monkeypatch,
        )
        assert PREAMBLE_MARKER in capsys.readouterr().out

    def test_malformed_stdin_emits_nothing(self, capsys, monkeypatch) -> None:
        _drive_main(None, monkeypatch, raw="{{{ not json")
        assert capsys.readouterr().out == ""

    def test_an_internal_error_is_swallowed_so_the_spawn_is_never_blocked(
        self, capsys, monkeypatch
    ) -> None:
        import io

        module = _load_module()

        def _boom(_payload):
            raise RuntimeError("kaboom")

        monkeypatch.setattr(module, "_process", _boom)
        monkeypatch.setattr(sys, "stdin", io.StringIO('{"tool_name": "Agent"}'))

        module.main()  # must not raise

        assert capsys.readouterr().out == ""
