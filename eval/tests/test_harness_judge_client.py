"""Behavioral tests for JudgeClient auth-mode selection and schema enforcement.

All production imports are deferred inside each test body so pytest collection
succeeds before the harness package exists (RED-state handshake).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Helper: a minimal JSON-schema that judge() must validate against
# ---------------------------------------------------------------------------

_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["PASS", "WARN", "FAIL"]},
        "findings": {"type": "array", "items": {"type": "string"}},
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": ["verdict", "findings", "score"],
}


# ---------------------------------------------------------------------------
# select_judge_client: env-detection factory
# ---------------------------------------------------------------------------


def test_oauth_token_selects_agent_sdk_client(monkeypatch):
    """When CLAUDE_CODE_OAUTH_TOKEN is set, factory returns AgentSdkJudgeClient."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok_test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from praxion_evals.harness.judge_client import AgentSdkJudgeClient, select_judge_client

    client = select_judge_client()
    assert isinstance(client, AgentSdkJudgeClient)


def test_api_key_only_selects_messages_api_client(monkeypatch):
    """When only ANTHROPIC_API_KEY is set, factory returns MessagesApiJudgeClient."""
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk_test")

    from praxion_evals.harness.judge_client import MessagesApiJudgeClient, select_judge_client

    client = select_judge_client()
    assert isinstance(client, MessagesApiJudgeClient)


def test_oauth_wins_when_both_env_vars_set(monkeypatch):
    """When both env vars are set, CLAUDE_CODE_OAUTH_TOKEN takes precedence."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok_test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk_test")

    from praxion_evals.harness.judge_client import AgentSdkJudgeClient, select_judge_client

    client = select_judge_client()
    assert isinstance(client, AgentSdkJudgeClient), (
        "OAuth token must win over API key when both are present"
    )


def test_neither_env_var_raises_runtime_error_naming_both(monkeypatch):
    """When neither env var is set, factory raises RuntimeError naming both vars."""
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    import pytest
    from praxion_evals.harness.judge_client import select_judge_client

    with pytest.raises(RuntimeError) as exc_info:
        select_judge_client()

    msg = str(exc_info.value)
    assert "CLAUDE_CODE_OAUTH_TOKEN" in msg, "Error must name the OAuth token env var"
    assert "ANTHROPIC_API_KEY" in msg, "Error must name the API key env var"


# ---------------------------------------------------------------------------
# AgentSdkJudgeClient: schema enforcement via mocked SDK
# ---------------------------------------------------------------------------


def test_agent_sdk_client_returns_valid_judge_verdict(monkeypatch):
    """AgentSdkJudgeClient.judge() with a mocked query returns a JudgeVerdict."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok_test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    # Stub out the claude_agent_sdk dependency so the test runs without the real SDK.
    import types

    fake_sdk = types.ModuleType("claude_agent_sdk")

    # The structured_output on the result message
    fake_result = types.SimpleNamespace(
        structured_output={"verdict": "PASS", "findings": ["looks good"], "score": 90}
    )
    # query() is async; wrap in a coroutine

    async def _fake_query(*_args, **_kwargs):
        yield fake_result

    fake_sdk.query = _fake_query  # type: ignore[attr-defined]
    fake_sdk.ClaudeAgentOptions = lambda **kw: types.SimpleNamespace(**kw)  # type: ignore[attr-defined]

    import sys

    sys.modules.setdefault("claude_agent_sdk", fake_sdk)

    from praxion_evals.harness.judge_client import AgentSdkJudgeClient
    from praxion_evals.harness.schemas import JudgeVerdict

    client = AgentSdkJudgeClient()
    verdict = client.judge(
        rubric="Is this good?",
        artifact="Some text.",
        schema=_VERDICT_SCHEMA,
    )

    assert isinstance(verdict, JudgeVerdict)
    assert verdict.verdict in ("PASS", "WARN", "FAIL")
    assert isinstance(verdict.findings, tuple)
    assert isinstance(verdict.score, int)


def test_agent_sdk_client_raises_on_missing_verdict_field(monkeypatch):
    """AgentSdkJudgeClient.judge() raises ValueError when 'verdict' is absent from output."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok_test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    import sys
    import types

    import pytest

    fake_sdk = types.ModuleType("claude_agent_sdk")
    # Missing 'verdict' field
    fake_result = types.SimpleNamespace(structured_output={"findings": ["ok"], "score": 80})

    async def _fake_query(*_args, **_kwargs):
        yield fake_result

    fake_sdk.query = _fake_query  # type: ignore[attr-defined]
    fake_sdk.ClaudeAgentOptions = lambda **kw: types.SimpleNamespace(**kw)  # type: ignore[attr-defined]
    sys.modules["claude_agent_sdk"] = fake_sdk

    from praxion_evals.harness.judge_client import AgentSdkJudgeClient

    client = AgentSdkJudgeClient()
    with pytest.raises(ValueError, match="verdict"):
        client.judge(rubric="?", artifact="x", schema=_VERDICT_SCHEMA)


# ---------------------------------------------------------------------------
# MessagesApiJudgeClient: schema enforcement via mocked anthropic SDK
# ---------------------------------------------------------------------------


def test_messages_api_client_returns_valid_judge_verdict(monkeypatch):
    """MessagesApiJudgeClient.judge() with a mocked anthropic client returns a JudgeVerdict."""
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk_test")

    import sys
    import types

    # Minimal stub for anthropic.Anthropic().messages.create()
    tool_call_input = {"verdict": "WARN", "findings": ["minor issue"], "score": 65}
    fake_tool_use = types.SimpleNamespace(
        type="tool_use",
        name="verdict",
        input=tool_call_input,
    )
    fake_response = types.SimpleNamespace(content=[fake_tool_use])

    fake_messages = types.SimpleNamespace(create=lambda **_kw: fake_response)
    fake_anthropic_instance = types.SimpleNamespace(messages=fake_messages)

    fake_anthropic_mod = types.ModuleType("anthropic")
    fake_anthropic_mod.Anthropic = lambda **_kw: fake_anthropic_instance  # type: ignore[attr-defined]

    sys.modules["anthropic"] = fake_anthropic_mod

    from praxion_evals.harness.judge_client import MessagesApiJudgeClient
    from praxion_evals.harness.schemas import JudgeVerdict

    client = MessagesApiJudgeClient()
    verdict = client.judge(
        rubric="Rate this.",
        artifact="Some content.",
        schema=_VERDICT_SCHEMA,
    )

    assert isinstance(verdict, JudgeVerdict)
    assert verdict.verdict in ("PASS", "WARN", "FAIL")
    assert isinstance(verdict.findings, tuple)
    assert 0 <= verdict.score <= 100


# ---------------------------------------------------------------------------
# Import isolation: harness.judge_client is importable without claude_agent_sdk
# ---------------------------------------------------------------------------


def test_judge_client_module_importable_without_agent_sdk(monkeypatch):
    """Importing harness.judge_client succeeds even when claude_agent_sdk is absent.

    Only constructing AgentSdkJudgeClient() triggers the lazy import.
    """
    import sys

    # Remove any cached real or fake module so we test the missing-module path.
    sys.modules.pop("claude_agent_sdk", None)

    # The import must not raise; the missing SDK is only relevant at construction time.
    import importlib

    # Force a fresh import (the module may already be cached from prior tests)
    if "praxion_evals.harness.judge_client" in sys.modules:
        importlib.reload(sys.modules["praxion_evals.harness.judge_client"])
    else:
        import praxion_evals.harness.judge_client  # noqa: F401


def test_constructing_agent_sdk_client_without_sdk_raises_import_error(monkeypatch):
    """AgentSdkJudgeClient() raises ImportError (or ModuleNotFoundError) when SDK absent."""
    import sys

    import pytest

    sys.modules.pop("claude_agent_sdk", None)
    # Ensure a future import attempt fails by inserting a sentinel that raises

    # Temporarily prevent the SDK from being found by blocking its import
    original = sys.modules.get("claude_agent_sdk")
    sys.modules["claude_agent_sdk"] = None  # type: ignore[assignment]

    try:
        from praxion_evals.harness.judge_client import AgentSdkJudgeClient

        with pytest.raises((ImportError, ModuleNotFoundError)):
            AgentSdkJudgeClient()
    finally:
        if original is None:
            sys.modules.pop("claude_agent_sdk", None)
        else:
            sys.modules["claude_agent_sdk"] = original
