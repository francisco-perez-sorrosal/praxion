"""A judge reply that stops short is named for what stopped it, never read as a malformed one.

The Messages-API route reads the response's ``stop_reason``: a reply cut off at the output cap
carries an incomplete tool input (handling-stop-reasons.md), so its fields are not read. The
Agent-SDK route reads the result message: an error subtype, or a success that carries no
structured output, is a failure the SDK names (agent-sdk/structured-outputs.md § Error handling).
"""

from __future__ import annotations

import sys
import types

import pytest

# Every name is read off the module when a test runs: another test reloads `judge_client`, which
# rebinds its classes, so a name imported at collection would be a class no reply raises.
from praxion_evals.harness import judge_client
from praxion_evals.harness.schemas import JudgeVerdict

SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {"type": "array", "items": {"type": "string"}},
        "verdict": {"type": "string", "enum": ["PASS", "WARN", "FAIL"]},
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": ["findings", "verdict", "score"],
}
COMPLETE = {"findings": ["the ADR states its decision"], "verdict": "PASS", "score": 90}


# -- The Messages-API route -------------------------------------------------------------------------


class _ToolUseBlock:
    def __init__(self, tool_input: dict) -> None:
        self.type = "tool_use"
        self.name = "verdict"
        self.input = tool_input


def _messages_api(monkeypatch, tool_input: dict, stop_reason: str | None) -> dict:
    """Install a fake ``anthropic`` whose reply carries `tool_input` and `stop_reason`; return
    the dict that records the request's keyword arguments."""
    request: dict = {}

    def _create(**kwargs):
        request.update(kwargs)
        return types.SimpleNamespace(content=[_ToolUseBlock(tool_input)], stop_reason=stop_reason)

    fake_types = types.ModuleType("anthropic.types")
    fake_types.ToolUseBlock = _ToolUseBlock  # type: ignore[attr-defined]
    fake = types.ModuleType("anthropic")
    fake.Anthropic = lambda **_kw: types.SimpleNamespace(  # type: ignore[attr-defined]
        messages=types.SimpleNamespace(create=_create)
    )
    fake.types = fake_types  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setitem(sys.modules, "anthropic.types", fake_types)
    return request


@pytest.mark.parametrize(
    "tool_input",
    [{"findings": ["the ADR states"]}, {**COMPLETE, "score": 9}],
    ids=["cut-inside-the-findings", "every-field-present-but-the-score-cut"],
)
@pytest.mark.parametrize("stop_reason", ["max_tokens", "model_context_window_exceeded"])
def test_a_reply_cut_off_at_its_cap_is_named_truncated_and_never_read(
    monkeypatch, tool_input, stop_reason
):
    _messages_api(monkeypatch, tool_input, stop_reason)

    with pytest.raises(judge_client.JudgeReplyTruncatedError, match=f"cut off.*{stop_reason}"):
        judge_client.MessagesApiJudgeClient().judge("rubric", "artifact", SCHEMA)


def test_a_truncated_reply_is_still_a_malformed_reply_to_callers_that_catch_one():
    assert issubclass(judge_client.JudgeReplyTruncatedError, ValueError)


@pytest.mark.parametrize("stop_reason", ["tool_use", None])
def test_a_reply_that_finished_its_tool_call_is_read(monkeypatch, stop_reason):
    _messages_api(monkeypatch, COMPLETE, stop_reason)

    verdict = judge_client.MessagesApiJudgeClient().judge("rubric", "artifact", SCHEMA)

    assert (verdict.verdict, verdict.score) == ("PASS", 90)


def test_the_request_leaves_room_for_a_findings_first_reply(monkeypatch):
    request = _messages_api(monkeypatch, COMPLETE, "tool_use")

    judge_client.MessagesApiJudgeClient().judge("rubric", "artifact", SCHEMA)

    assert request["max_tokens"] == judge_client._JUDGE_MAX_TOKENS
    assert judge_client._JUDGE_MAX_TOKENS >= 4096, "1,024 cut off findings-first replies"


# -- The Agent-SDK route ----------------------------------------------------------------------------


def _agent_sdk(monkeypatch, result: types.SimpleNamespace, *, raise_after: bool = False) -> None:
    """Install a fake ``claude_agent_sdk`` whose query yields `result`, then raises when
    `raise_after` (as a single-shot query does after an error result)."""

    async def _query(*_args, **_kwargs):
        yield types.SimpleNamespace(content=[])  # an assistant message: no structured_output
        yield result
        if raise_after:
            raise RuntimeError("Command failed with exit code 1")

    fake = types.ModuleType("claude_agent_sdk")
    fake.query = _query  # type: ignore[attr-defined]
    fake.ClaudeAgentOptions = lambda **kw: types.SimpleNamespace(**kw)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    monkeypatch.delenv("CLAUDECODE", raising=False)


def _result(**fields) -> types.SimpleNamespace:
    defaults = {"subtype": "success", "stop_reason": "end_turn", "structured_output": None}
    return types.SimpleNamespace(**{**defaults, "errors": None, **fields})


@pytest.mark.parametrize("raise_after", [False, True], ids=["yielded", "then-raised"])
def test_a_run_that_spent_its_structured_output_retries_is_named_by_its_subtype(
    monkeypatch, raise_after
):
    result = _result(
        subtype="error_max_structured_output_retries",
        errors=["output did not match the schema"],
    )
    _agent_sdk(monkeypatch, result, raise_after=raise_after)

    with pytest.raises(ValueError, match="error_max_structured_output_retries.*did not match"):
        judge_client.AgentSdkJudgeClient().judge("rubric", "artifact", SCHEMA)


def test_a_success_that_carries_no_structured_output_is_named_as_such(monkeypatch):
    _agent_sdk(monkeypatch, _result())

    with pytest.raises(ValueError, match="without a structured output"):
        judge_client.AgentSdkJudgeClient().judge("rubric", "artifact", SCHEMA)


def test_a_run_cut_off_at_its_cap_is_named_truncated(monkeypatch):
    _agent_sdk(monkeypatch, _result(stop_reason="max_tokens"))

    with pytest.raises(judge_client.JudgeReplyTruncatedError, match="cut off.*max_tokens"):
        judge_client.AgentSdkJudgeClient().judge("rubric", "artifact", SCHEMA)


def test_a_run_that_returned_its_structured_output_is_read(monkeypatch):
    _agent_sdk(monkeypatch, _result(structured_output=dict(COMPLETE)))

    verdict = judge_client.AgentSdkJudgeClient().judge("rubric", "artifact", SCHEMA)

    assert isinstance(verdict, JudgeVerdict)
    assert (verdict.verdict, verdict.score) == ("PASS", 90)


def test_a_failure_with_no_result_message_propagates_unchanged(monkeypatch):
    async def _query(*_args, **_kwargs):
        raise ConnectionError("the CLI process could not start")
        yield  # pragma: no cover

    fake = types.ModuleType("claude_agent_sdk")
    fake.query = _query  # type: ignore[attr-defined]
    fake.ClaudeAgentOptions = lambda **kw: types.SimpleNamespace(**kw)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    monkeypatch.delenv("CLAUDECODE", raising=False)

    with pytest.raises(ConnectionError, match="could not start"):
        judge_client.AgentSdkJudgeClient().judge("rubric", "artifact", SCHEMA)
