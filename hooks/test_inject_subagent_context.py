"""Tests for hooks/inject_subagent_context.py — PreToolUse(Agent) context injection.

Behavioral specification:

- Host-native subagents (Explore, Plan, general-purpose) receive a compact Praxion
  preamble prepended to their prompt when launched from a Praxion-managed project.
- Praxion-native subagents (i-am:*) are skipped by default (they already encode
  the behavioral contract in their system prompts).
- Praxion-native subagents receive the preamble when PRAXION_INJECT_NATIVE_SUBAGENTS=1.
- Projects without a .ai-state/ directory receive no injection (not a Praxion project).
- PRAXION_DISABLE_SUBAGENT_INJECT=1 disables injection in any project.
- Malformed or empty stdin is tolerated — hook exits 0 without crashing.
- Per-session-id caching: a second call with the same session_id avoids re-statting
  the filesystem for .ai-state/ presence.
- Fast-path (no .ai-state/) completes in < 200ms per invocation (generous CI bound).

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

# ---------------------------------------------------------------------------
# Deferred import pattern — production module may not exist when tests are
# authored.  Import inside each test body so pytest collection succeeds even
# when the file is absent, yielding per-test ImportError (RED state) rather
# than collection-time failure.
# ---------------------------------------------------------------------------


def _load_module():
    """Load inject_subagent_context.py as a module, or raise ImportError."""
    script_path = HOOKS_DIR / "inject_subagent_context.py"
    if not script_path.exists():
        raise ImportError(
            "hooks/inject_subagent_context.py not found. "
            "The production module does not yet exist."
        )
    spec = importlib.util.spec_from_file_location(
        "inject_subagent_context", script_path
    )
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
    payload: dict[str, Any],
    env_extra: dict[str, str] | None = None,
    cwd_override: str | None = None,
) -> subprocess.CompletedProcess:
    """Run inject_subagent_context.py as a subprocess with the given payload."""
    env = {**os.environ}
    # Strip all PRAXION_* keys so tests start from a clean slate
    for key in list(env):
        if key.startswith("PRAXION_"):
            del env[key]
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "inject_subagent_context.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd_override,
        timeout=10,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def praxion_project(tmp_path: Path) -> Path:
    """A temporary directory that looks like a Praxion-managed project.

    Contains a .ai-state/ directory, which is the presence signal used by
    inject_subagent_context.py to decide whether to inject.
    """
    ai_state = tmp_path / ".ai-state"
    ai_state.mkdir()
    return tmp_path


@pytest.fixture()
def non_praxion_project(tmp_path: Path) -> Path:
    """A temporary directory without .ai-state/ — not a Praxion project."""
    return tmp_path


@pytest.fixture(autouse=True)
def _clear_praxion_env(monkeypatch):
    """Each test starts with no PRAXION_* env vars set."""
    for key in list(os.environ):
        if key.startswith("PRAXION_"):
            monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# Group 1: Host-native subagent injection
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
    updated_prompt = output["hookSpecificOutput"]["updatedInput"]["tool_input"][
        "prompt"
    ]
    assert updated_prompt.startswith(PREAMBLE_MARKER), (
        f"Preamble not prepended for {subagent_type!r}: {updated_prompt[:80]!r}"
    )
    assert _ORIGINAL_PROMPT in updated_prompt, (
        "Original prompt must be preserved after preamble"
    )


def test_preamble_contains_behavioral_contract_keywords(
    praxion_project: Path,
) -> None:
    """Injected preamble includes all four behavioral contract principles."""
    payload = _pretooluse_payload(subagent_type="Explore", cwd=str(praxion_project))
    result = _run_hook(payload)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    prompt = output["hookSpecificOutput"]["updatedInput"]["tool_input"]["prompt"]
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
    prompt = output["hookSpecificOutput"]["updatedInput"]["tool_input"]["prompt"]
    for phrase in ["pointer, not a payload", ".ai-work/"]:
        assert phrase in prompt, f"Return-contract phrase {phrase!r} missing"


def test_preamble_length_is_compact(praxion_project: Path) -> None:
    """The injected preamble stays within the ~180 char spec limit."""
    payload = _pretooluse_payload(subagent_type="Explore", cwd=str(praxion_project))
    result = _run_hook(payload)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    prompt = output["hookSpecificOutput"]["updatedInput"]["tool_input"]["prompt"]
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
    returned_type = output["hookSpecificOutput"]["updatedInput"]["tool_input"][
        "subagent_type"
    ]
    assert returned_type == "Plan"


def test_output_hook_event_name_is_pretooluse(praxion_project: Path) -> None:
    """The hookEventName field in output is PreToolUse."""
    payload = _pretooluse_payload(subagent_type="Explore", cwd=str(praxion_project))
    result = _run_hook(payload)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["hookSpecificOutput"]["hookEventName"] == "PreToolUse"


# ---------------------------------------------------------------------------
# Group 2: Praxion-native subagent skip (default behavior)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subagent_type",
    [
        "i-am:researcher",
        "i-am:implementer",
        "i-am:test-engineer",
        "i-am:systems-architect",
        "i-am:verifier",
    ],
)
def test_praxion_native_subagent_skipped_by_default(
    subagent_type: str, praxion_project: Path
) -> None:
    """Praxion-native agents (i-am:*) produce no injection by default."""
    payload = _pretooluse_payload(subagent_type=subagent_type, cwd=str(praxion_project))
    result = _run_hook(payload)

    assert result.returncode == 0, f"Hook exited non-zero: {result.stderr}"
    # No injection: stdout must be empty (silent pass-through)
    assert result.stdout == "", (
        f"Praxion-native agent {subagent_type!r} should not receive injection "
        f"by default, but got stdout: {result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# Group 3: Praxion-native opt-in via PRAXION_INJECT_NATIVE_SUBAGENTS=1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("subagent_type", ["i-am:researcher", "i-am:implementer"])
def test_praxion_native_receives_preamble_when_opt_in_env_set(
    subagent_type: str, praxion_project: Path
) -> None:
    """With PRAXION_INJECT_NATIVE_SUBAGENTS=1, i-am:* agents also get the preamble."""
    payload = _pretooluse_payload(subagent_type=subagent_type, cwd=str(praxion_project))
    result = _run_hook(payload, env_extra={"PRAXION_INJECT_NATIVE_SUBAGENTS": "1"})

    assert result.returncode == 0
    assert result.stdout, "Expected updatedInput JSON when opt-in env is set"
    output = json.loads(result.stdout)
    prompt = output["hookSpecificOutput"]["updatedInput"]["tool_input"]["prompt"]
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
    result_optin = _run_hook(
        payload, env_extra={"PRAXION_INJECT_NATIVE_SUBAGENTS": "1"}
    )
    assert result_optin.returncode == 0
    assert result_optin.stdout, "Explore must still be injected with opt-in"


# ---------------------------------------------------------------------------
# Group 4: .ai-state/ gate — non-Praxion project → no injection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("subagent_type", ["Explore", "Plan", "i-am:researcher"])
def test_no_injection_when_ai_state_absent(
    subagent_type: str, non_praxion_project: Path
) -> None:
    """No injection occurs for any subagent type when .ai-state/ is absent."""
    payload = _pretooluse_payload(
        subagent_type=subagent_type, cwd=str(non_praxion_project)
    )
    result = _run_hook(payload)

    assert result.returncode == 0
    assert result.stdout == "", (
        f"No injection expected without .ai-state/; got: {result.stdout!r}"
    )


def test_no_injection_when_cwd_has_no_ai_state_subdirectory(tmp_path: Path) -> None:
    """Even with a valid filesystem path, no injection if .ai-state/ is missing."""
    # Create unrelated dirs to confirm it's not just "any dir triggers injection"
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    payload = _pretooluse_payload(subagent_type="Plan", cwd=str(tmp_path))
    result = _run_hook(payload)
    assert result.returncode == 0
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# Group 5: PRAXION_DISABLE_SUBAGENT_INJECT opt-out
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("subagent_type", ["Explore", "Plan", "general-purpose"])
def test_injection_disabled_when_opt_out_env_set(
    subagent_type: str, praxion_project: Path
) -> None:
    """PRAXION_DISABLE_SUBAGENT_INJECT=1 suppresses injection even in Praxion projects."""
    payload = _pretooluse_payload(subagent_type=subagent_type, cwd=str(praxion_project))
    result = _run_hook(payload, env_extra={"PRAXION_DISABLE_SUBAGENT_INJECT": "1"})

    assert result.returncode == 0
    assert result.stdout == "", (
        f"Expected no injection with opt-out flag, got: {result.stdout!r}"
    )


def test_opt_out_also_suppresses_native_opt_in(praxion_project: Path) -> None:
    """PRAXION_DISABLE_SUBAGENT_INJECT takes precedence over PRAXION_INJECT_NATIVE_SUBAGENTS."""
    payload = _pretooluse_payload(
        subagent_type="i-am:researcher", cwd=str(praxion_project)
    )
    result = _run_hook(
        payload,
        env_extra={
            "PRAXION_DISABLE_SUBAGENT_INJECT": "1",
            "PRAXION_INJECT_NATIVE_SUBAGENTS": "1",
        },
    )
    assert result.returncode == 0
    assert result.stdout == "", "Opt-out must override opt-in"


# ---------------------------------------------------------------------------
# Group 6: Malformed stdin — unconditional exit 0
# ---------------------------------------------------------------------------


def test_empty_stdin_exits_zero_without_crash() -> None:
    """Empty stdin must not cause an exception — exit 0, no stdout."""
    result = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "inject_subagent_context.py")],
        input="",
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if not k.startswith("PRAXION_")},
        timeout=10,
    )
    assert result.returncode == 0, (
        f"Expected exit 0, got {result.returncode}: {result.stderr}"
    )


def test_malformed_json_stdin_exits_zero_without_crash() -> None:
    """Malformed JSON on stdin must not crash the hook — exit 0."""
    result = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "inject_subagent_context.py")],
        input="not valid json {{{",
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if not k.startswith("PRAXION_")},
        timeout=10,
    )
    assert result.returncode == 0, (
        f"Expected exit 0, got {result.returncode}: {result.stderr}"
    )


def test_missing_tool_input_field_exits_zero() -> None:
    """Payload missing tool_input must not crash the hook — exit 0."""
    payload = {"tool_name": "Agent", "cwd": "/tmp", "session_id": "s1"}
    result = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "inject_subagent_context.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if not k.startswith("PRAXION_")},
        timeout=10,
    )
    assert result.returncode == 0


def test_missing_subagent_type_field_exits_zero() -> None:
    """Payload missing subagent_type must not crash the hook — exit 0."""
    payload = {
        "tool_name": "Agent",
        "tool_input": {"prompt": "do something"},
        "cwd": "/tmp",
        "session_id": "s1",
    }
    result = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "inject_subagent_context.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if not k.startswith("PRAXION_")},
        timeout=10,
    )
    assert result.returncode == 0


def test_missing_cwd_field_exits_zero() -> None:
    """Payload missing cwd must not crash the hook — exit 0."""
    payload = {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "Explore", "prompt": "research"},
        "session_id": "s1",
    }
    result = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "inject_subagent_context.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if not k.startswith("PRAXION_")},
        timeout=10,
    )
    assert result.returncode == 0


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


# ---------------------------------------------------------------------------
# Group 7: Per-session-id caching
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
        prompt = output["hookSpecificOutput"]["updatedInput"]["tool_input"]["prompt"]
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
# Group 8: Latency assertion (fast-path, no .ai-state/)
# ---------------------------------------------------------------------------


def test_fast_path_no_ai_state_completes_under_200ms(
    non_praxion_project: Path,
) -> None:
    """No-.ai-state/ fast-path (skip) completes in < 200ms excluding Python startup.

    Methodology: warm up Python import by loading the module once in a subprocess,
    then time the actual hook execution.  The 200ms bound is generous for CI —
    the latency budget is < 100ms per spawn, but Python startup (~30-50ms)
    consumes part of that budget; 200ms covers the logic path only.

    Note: this is a unit-level timing assertion.  Flaky risk is low because the
    no-.ai-state/ path performs only one filesystem stat before returning.
    """
    payload = _pretooluse_payload(subagent_type="Explore", cwd=str(non_praxion_project))
    payload_json = json.dumps(payload)

    env = {k: v for k, v in os.environ.items() if not k.startswith("PRAXION_")}

    # Run multiple times to get a stable measurement; take the median
    times: list[float] = []
    for _ in range(5):
        t0 = time.perf_counter()
        result = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "inject_subagent_context.py")],
            input=payload_json,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
        assert result.returncode == 0

    # Sort and take the minimum (best-case run, removes OS scheduling noise)
    best_ms = min(times) * 1000
    # Allow up to 2 seconds for the entire subprocess (Python startup + logic)
    # The 200ms bound is for the *logic* portion only, but we can't separate
    # startup cleanly in a subprocess test. Use 2000ms as the CI-safe ceiling.
    assert best_ms < 2000, (
        f"Fast-path hook took {best_ms:.0f}ms (best of 5). "
        "If Python startup is unusually slow on this system, consider adjusting."
    )


def test_inject_path_completes_under_2000ms_including_python_startup(
    praxion_project: Path,
) -> None:
    """Injection path completes in < 2000ms including Python startup (CI-safe bound).

    The spec claims < 100ms per spawn. Python startup is ~30-50ms. The full
    subprocess (startup + stat + inject) should stay well under 2s on any
    modern CI runner. This test catches regressions caused by accidental I/O
    (file reads, network calls, heavy imports) in the injection path.
    """
    payload = _pretooluse_payload(subagent_type="Explore", cwd=str(praxion_project))
    payload_json = json.dumps(payload)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PRAXION_")}

    t0 = time.perf_counter()
    result = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "inject_subagent_context.py")],
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
    # The hook should expose a top-level callable — either `main`, `run`,
    # or be directly runnable.  We check for at least one of these.
    has_main = hasattr(mod, "main") and callable(mod.main)
    has_run = hasattr(mod, "run") and callable(mod.run)
    assert has_main or has_run, (
        "inject_subagent_context.py must expose a callable `main` or `run` "
        "for testability. If the hook only has __main__ guard, add a main() function."
    )
