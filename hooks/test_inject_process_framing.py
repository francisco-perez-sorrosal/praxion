"""Tests for hooks/inject_process_framing.py — UserPromptSubmit hook.

Verifies the four fast-skip paths and the injection path:

  - Fast-skip when .ai-state/ is absent (non-Praxion project)
  - Fast-skip when PRAXION_DISABLE_PROCESS_INJECT=1 is set
  - Fast-skip when the last transcript turn is from assistant (continuation)
  - Fast-skip when prompt is short (<60 chars) and has no question mark
  - Fast-skip when prompt matches the trivial-pattern regex (yes/no/ok/go/run etc.)
  - Injection path: compact additionalContext emitted on a non-trivial first turn
  - Injection content: structural assertions (tier-selector + rule-inheritance keywords)
  - Token budget: additionalContext value is under 50 tokens
  - Malformed stdin: exits 0 without crashing
  - Boundary: prompt exactly 60 chars with no '?' is still a short reply (no injection)
  - Boundary: prompt exactly 60 chars with '?' gets injection (question gets framing)

Tests use deferred imports (``_load_module()`` inside each test body) so pytest
can collect and report per-test RED/GREEN rather than a collection-time failure
while the production module does not yet exist.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
HOOK_SCRIPT_PATH = HOOKS_DIR / "inject_process_framing.py"


# ---------------------------------------------------------------------------
# Deferred loader — imports inside each test body for RED/GREEN per-test
# ---------------------------------------------------------------------------


def _load_module():
    """Load inject_process_framing.py as a module inside a test body.

    Returns the module so callers can call the main entry point.
    Raises ImportError / ModuleNotFoundError when the module does not yet exist
    — that is the expected RED state during concurrent BDD/TDD execution.
    """
    spec = importlib.util.spec_from_file_location("inject_process_framing", HOOK_SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(
            f"Cannot load {HOOK_SCRIPT_PATH}. The production module does not yet exist."
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Each test starts with PRAXION_DISABLE_PROCESS_INJECT unset."""
    monkeypatch.delenv("PRAXION_DISABLE_PROCESS_INJECT", raising=False)


def _make_payload(
    prompt: str,
    cwd: str,
    transcript_path: str = "/tmp/fake_transcript.jsonl",
) -> dict:
    """Build a minimal UserPromptSubmit payload dict."""
    return {
        "hookEventName": "UserPromptSubmit",
        "prompt": prompt,
        "cwd": cwd,
        "transcript_path": transcript_path,
    }


def _run_hook(module, payload: dict, *, stdin_json: str | None = None) -> dict | None:
    """Call the hook's main entry point with a payload dict.

    Returns parsed JSON output if the hook emitted any, or None for silent
    no-op (empty / whitespace output).  Raises SystemExit when the hook
    calls sys.exit with a non-zero code.
    """
    import io

    raw_stdin = stdin_json if stdin_json is not None else json.dumps(payload)

    captured_output = io.StringIO()
    with (
        patch.object(sys, "stdin", io.StringIO(raw_stdin)),
        patch.object(sys, "stdout", captured_output),
    ):
        try:
            module.main()
        except SystemExit as exc:
            if exc.code not in (None, 0):
                raise
    output = captured_output.getvalue().strip()
    if not output:
        return None
    return json.loads(output)


# ---------------------------------------------------------------------------
# Fast-skip: non-Praxion project (no .ai-state/ in cwd)
# ---------------------------------------------------------------------------


def test_non_praxion_project_emits_no_framing(tmp_path, monkeypatch):
    """When cwd has no .ai-state/ directory, the hook exits 0 with no output."""
    module = _load_module()
    monkeypatch.chdir(tmp_path)
    payload = _make_payload(
        prompt="Implement the new authentication module with JWT tokens and refresh logic",
        cwd=str(tmp_path),
    )
    result = _run_hook(module, payload)
    assert result is None, (
        f"Hook must emit no output when .ai-state/ is absent (non-Praxion project). Got: {result}"
    )


# ---------------------------------------------------------------------------
# Fast-skip: disable flag
# ---------------------------------------------------------------------------


def test_disable_flag_suppresses_injection(tmp_path, monkeypatch):
    """When PRAXION_DISABLE_PROCESS_INJECT=1 is set, the hook exits 0 with no output."""
    module = _load_module()
    ai_state = tmp_path / ".ai-state"
    ai_state.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAXION_DISABLE_PROCESS_INJECT", "1")
    payload = _make_payload(
        prompt="Design the full microservices migration plan with API gateway patterns",
        cwd=str(tmp_path),
    )
    result = _run_hook(module, payload)
    assert result is None, (
        f"Hook must be silent when PRAXION_DISABLE_PROCESS_INJECT=1. Got: {result}"
    )


# ---------------------------------------------------------------------------
# Fast-skip: continuation turn (last transcript turn is assistant)
# ---------------------------------------------------------------------------


def test_continuation_turn_emits_no_framing(tmp_path, monkeypatch):
    """When the transcript indicates a continuation turn, the hook is silent."""
    module = _load_module()
    ai_state = tmp_path / ".ai-state"
    ai_state.mkdir()
    monkeypatch.chdir(tmp_path)

    # The hook calls _hook_utils.scan_transcript (or an equivalent helper) to
    # detect continuation. We stub the transcript-scan result to signal
    # "continuation" by returning a TranscriptStats-like value that the hook
    # treats as "last turn was assistant / continuation detected".
    #
    # The hook may call scan_transcript() from _hook_utils, or it may directly
    # inspect the last entry in the transcript JSONL. Either way, the test stubs
    # out the detection so it returns a truthy "is continuation" signal, and
    # asserts the hook remains silent.

    continuation_transcript = tmp_path / "transcript.jsonl"
    # Transcript with last role = assistant
    turns = [
        {"type": "human", "message": {"content": "describe the architecture"}},
        {"type": "assistant", "message": {"content": "Sure, here is the overview..."}},
    ]
    continuation_transcript.write_text("\n".join(json.dumps(t) for t in turns) + "\n")

    payload = _make_payload(
        prompt="What about error handling in that component?",
        cwd=str(tmp_path),
        transcript_path=str(continuation_transcript),
    )

    # Stub the transcript scanner so the hook sees "continuation = True"
    # regardless of how it internally detects it.
    with patch(
        "inject_process_framing._is_continuation",
        return_value=True,
        create=True,
    ):
        result = _run_hook(module, payload)

    assert result is None, f"Hook must be silent on continuation turns. Got: {result}"


# ---------------------------------------------------------------------------
# Fast-skip: short reply (< 60 chars, no question mark)
# ---------------------------------------------------------------------------


def test_short_reply_without_question_mark_emits_no_framing(tmp_path, monkeypatch):
    """Prompt < 60 chars with no '?' is a short reply and must not get framing."""
    module = _load_module()
    ai_state = tmp_path / ".ai-state"
    ai_state.mkdir()
    monkeypatch.chdir(tmp_path)
    # 45 chars, no question mark
    short_prompt = "Run the tests and report any failures now"
    assert len(short_prompt) < 60
    assert "?" not in short_prompt
    payload = _make_payload(prompt=short_prompt, cwd=str(tmp_path))
    result = _run_hook(module, payload)
    assert result is None, (
        f"Short reply ({len(short_prompt)} chars, no '?') must not trigger framing. Got: {result}"
    )


def test_prompt_at_60_chars_without_question_mark_emits_no_framing(tmp_path, monkeypatch):
    """Boundary: prompt exactly 60 chars with no '?' still counts as short reply."""
    module = _load_module()
    ai_state = tmp_path / ".ai-state"
    ai_state.mkdir()
    monkeypatch.chdir(tmp_path)
    # Craft a prompt that is exactly 60 characters with no '?'
    boundary_prompt = "a" * 60
    assert len(boundary_prompt) == 60
    assert "?" not in boundary_prompt
    payload = _make_payload(prompt=boundary_prompt, cwd=str(tmp_path))
    result = _run_hook(module, payload)
    assert result is None, (
        f"Prompt at exactly 60 chars (no '?') must not trigger framing. Got: {result}"
    )


# ---------------------------------------------------------------------------
# Fast-skip: trivial pattern regex
# ---------------------------------------------------------------------------


def test_trivial_pattern_emits_no_framing(tmp_path, monkeypatch):
    """Prompts matching the trivial-pattern regex (yes/ok/go/run/do it) get no framing."""
    module = _load_module()
    ai_state = tmp_path / ".ai-state"
    ai_state.mkdir()
    monkeypatch.chdir(tmp_path)

    trivial_prompts = [
        "yes",
        "Yes",
        "YES",
        "ok",
        "Ok",
        "OK",
        "go",
        "Go",
        "run",
        "do it",
    ]
    for prompt_text in trivial_prompts:
        payload = _make_payload(prompt=prompt_text, cwd=str(tmp_path))
        result = _run_hook(module, payload)
        assert result is None, (
            f"Trivial prompt {prompt_text!r} must not trigger framing. Got: {result}"
        )


# ---------------------------------------------------------------------------
# Injection path: non-trivial first turn in a Praxion project
# ---------------------------------------------------------------------------


def test_non_trivial_prompt_emits_additional_context(tmp_path, monkeypatch):
    """Non-trivial prompt in a Praxion project emits additionalContext."""
    module = _load_module()
    ai_state = tmp_path / ".ai-state"
    ai_state.mkdir()
    monkeypatch.chdir(tmp_path)

    payload = _make_payload(
        prompt=(
            "Design and implement a new pipeline for processing customer payment "
            "events including retry logic, idempotency, and dead-letter queue handling"
        ),
        cwd=str(tmp_path),
    )
    result = _run_hook(module, payload)
    assert result is not None, (
        "Non-trivial prompt in Praxion project must emit additionalContext. Got None."
    )
    assert "additionalContext" in result, (
        f"Output must contain 'additionalContext' key. Got keys: {list(result.keys())}"
    )


def test_injection_content_references_tier_selector(tmp_path, monkeypatch):
    """Injected additionalContext mentions the tier selector (process framing)."""
    module = _load_module()
    ai_state = tmp_path / ".ai-state"
    ai_state.mkdir()
    monkeypatch.chdir(tmp_path)

    payload = _make_payload(
        prompt=(
            "Refactor the authentication module to support multi-tenant SSO with "
            "backward compatibility for existing session tokens"
        ),
        cwd=str(tmp_path),
    )
    result = _run_hook(module, payload)
    assert result is not None
    context = result.get("additionalContext", "")
    # The spec says ~120-char reminder of tier selector + rule-inheritance.
    # We check for the concepts without hardcoding exact wording so the
    # implementer has freedom to craft the exact phrasing.
    context_lower = context.lower()
    tier_selector_mentioned = any(
        kw in context_lower for kw in ("tier", "pipeline", "process", "praxion")
    )
    assert tier_selector_mentioned, (
        f"additionalContext must reference the tier selector or Praxion process. Got: {context!r}"
    )


def test_injection_content_references_rule_inheritance(tmp_path, monkeypatch):
    """Injected additionalContext mentions rule-inheritance or behavioral contract."""
    module = _load_module()
    ai_state = tmp_path / ".ai-state"
    ai_state.mkdir()
    monkeypatch.chdir(tmp_path)

    payload = _make_payload(
        prompt=(
            "Implement the data export feature with CSV and JSON formats, "
            "pagination support, and rate limiting per organization"
        ),
        cwd=str(tmp_path),
    )
    result = _run_hook(module, payload)
    assert result is not None
    context = result.get("additionalContext", "")
    context_lower = context.lower()
    inheritance_mentioned = any(
        kw in context_lower
        for kw in (
            "behavioral contract",
            "contract",
            "delegation",
            "subagent",
            "rule-inheritance",
            "rule inheritance",
        )
    )
    assert inheritance_mentioned, (
        "additionalContext must reference rule-inheritance or behavioral contract. "
        f"Got: {context!r}"
    )


def test_injection_content_stays_within_token_budget(tmp_path, monkeypatch):
    """additionalContext value is under 50 tokens (≈180 bytes at 3.6 bytes/token)."""
    module = _load_module()
    ai_state = tmp_path / ".ai-state"
    ai_state.mkdir()
    monkeypatch.chdir(tmp_path)

    payload = _make_payload(
        prompt=(
            "Plan and execute the full infrastructure migration from monolith to "
            "microservices, covering service decomposition, API gateway, and CI/CD"
        ),
        cwd=str(tmp_path),
    )
    result = _run_hook(module, payload)
    assert result is not None
    context = result.get("additionalContext", "")
    # Conservative token estimate: bytes / 3.6. The spec states < 50 tokens.
    # 50 tokens × 3.6 bytes/token = 180 bytes ceiling.
    byte_count = len(context.encode("utf-8"))
    token_estimate = byte_count / 3.6
    assert token_estimate < 50, (
        f"additionalContext token estimate is {token_estimate:.1f} (>{50}). "
        f"Content ({byte_count} bytes): {context!r}"
    )


# ---------------------------------------------------------------------------
# Boundary: short prompt WITH question mark gets framing
# ---------------------------------------------------------------------------


def test_prompt_at_60_chars_with_question_mark_emits_framing(tmp_path, monkeypatch):
    """Boundary: prompt exactly 60 chars WITH '?' is a question and gets framing."""
    module = _load_module()
    ai_state = tmp_path / ".ai-state"
    ai_state.mkdir()
    monkeypatch.chdir(tmp_path)
    # Craft a prompt exactly 60 chars ending with '?'
    # "What is the recommended architecture for this system now?" = 57 chars, pad to 60
    boundary_prompt = "What is the recommended architecture for this system now?  ?"
    # Trim/adjust to hit exactly 60 chars while keeping '?'
    # Let's be explicit: 59 'a' chars + '?'
    boundary_prompt = "a" * 59 + "?"
    assert len(boundary_prompt) == 60
    assert "?" in boundary_prompt
    payload = _make_payload(prompt=boundary_prompt, cwd=str(tmp_path))
    result = _run_hook(module, payload)
    assert result is not None, "Prompt at exactly 60 chars with '?' must trigger framing. Got None."
    assert "additionalContext" in result, f"Expected additionalContext in output. Got: {result}"


# ---------------------------------------------------------------------------
# Unconditional exit 0 on malformed stdin
# ---------------------------------------------------------------------------


def test_malformed_stdin_exits_zero_without_output(tmp_path, monkeypatch):
    """Malformed JSON stdin must not crash the hook — exits 0 with no output."""
    module = _load_module()
    monkeypatch.chdir(tmp_path)
    result = _run_hook(module, payload={}, stdin_json="not valid json at all {{{{")
    assert result is None, (
        f"Malformed stdin must produce no output (exit 0 silently). Got: {result}"
    )
