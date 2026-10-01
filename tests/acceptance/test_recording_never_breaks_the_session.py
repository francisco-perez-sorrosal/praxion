"""Recording and attribution never fail a spawn, a resume or a tool call.

Whatever arrives on stdin for the agent lifecycle events and for the `Agent`
and `SendMessage` tool events, and even when the log cannot be written, every
hook registered for the event exits with status 0, and what can still be
recorded is recorded.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from tests.acceptance.drivers.observation_harness import (
    LOG_NAME,
    STATE_DIR,
    HookHarness,
    Session,
    log_rows,
    new_checkout,
)

SESSION_ID = "5e551011-0000-4000-8000-00000000d004"
AGENT_ID = "agent-one"
AGENT_TYPE = "praxion:implementer"
SPAWN_PROMPT = "Task slug: sturdy-pipeline\n\nImplement the parser."


def _base(event: str, root: Path) -> dict:
    return {
        "session_id": SESSION_ID,
        "cwd": str(root),
        "hook_event_name": event,
        "transcript_path": str(root.parent / "session.jsonl"),
    }


def _subagent_start(root: Path) -> dict:
    return {**_base("SubagentStart", root), "agent_id": AGENT_ID, "agent_type": AGENT_TYPE}


def _subagent_stop(root: Path) -> dict:
    return {
        **_base("SubagentStop", root),
        "agent_id": AGENT_ID,
        "agent_type": AGENT_TYPE,
        "agent_transcript_path": str(root.parent / "agent.jsonl"),
    }


def _agent_input(prompt: object = SPAWN_PROMPT) -> dict:
    return {
        "prompt": prompt,
        "subagent_type": AGENT_TYPE,
        "description": "spawn",
        "run_in_background": False,
    }


def _pre_agent(root: Path, prompt: object = SPAWN_PROMPT) -> dict:
    return {
        **_base("PreToolUse", root),
        "tool_name": "Agent",
        "tool_input": _agent_input(prompt),
        "tool_use_id": "toolu_sturdy_001",
    }


def _post_agent(root: Path, response: object = None, prompt: object = SPAWN_PROMPT) -> dict:
    default = {"agentId": AGENT_ID, "status": "completed", "prompt": prompt}
    return {
        **_pre_agent(root, prompt),
        "hook_event_name": "PostToolUse",
        "tool_response": default if response is None else response,
    }


def _pre_send(root: Path) -> dict:
    return {
        **_base("PreToolUse", root),
        "tool_name": "SendMessage",
        "tool_input": {"to": AGENT_ID, "message": "Continue."},
        "tool_use_id": "toolu_sturdy_002",
    }


def _post_send(root: Path, response: object = None) -> dict:
    return {
        **_pre_send(root),
        "hook_event_name": "PostToolUse",
        "tool_response": {"resumedAgentId": AGENT_ID} if response is None else response,
    }


def _without(payload: dict, *keys: str) -> dict:
    return {k: v for k, v in payload.items() if k not in keys}


def _with_tool_input(payload: dict, tool_input: object) -> dict:
    return {**payload, "tool_input": tool_input}


# Every well-formed payload whose event the malformed variants below target.
WELL_FORMED = {
    "SubagentStart": _subagent_start,
    "SubagentStop": _subagent_stop,
    "PreToolUse-Agent": _pre_agent,
    "PostToolUse-Agent": _post_agent,
    "PreToolUse-SendMessage": _pre_send,
    "PostToolUse-SendMessage": _post_send,
}

NOT_A_JSON_OBJECT = ["", "this is not json", "[1, 2, 3]", '"a string"', "null", '{"cut": ']


def _deliver(harness: HookHarness, root: Path, event_key: str, payload: object, raw: str | None):
    event = event_key.split("-")[0]
    matching = WELL_FORMED[event_key](root)
    if raw is None:
        return harness.deliver(event, payload, process_cwd=root)
    return harness.deliver(event, matching, raw_stdin=raw, process_cwd=root)


@pytest.fixture
def recording_checkout(tmp_path: Path) -> Path:
    return new_checkout(tmp_path / "proj")


@pytest.fixture
def harness(tmp_path: Path) -> HookHarness:
    return HookHarness(tmp_path / "harness")


# -- Malformed or incomplete payloads ------------------------------------------


@pytest.mark.parametrize("raw", NOT_A_JSON_OBJECT, ids=repr)
@pytest.mark.parametrize("event_key", sorted(WELL_FORMED))
def test_every_hook_exits_zero_when_the_payload_is_not_a_json_object(
    recording_checkout: Path, harness: HookHarness, event_key: str, raw: str
) -> None:
    delivery = _deliver(harness, recording_checkout, event_key, None, raw)

    assert delivery.exits, f"no hook is registered for {event_key}"
    assert delivery.failures() == []


@pytest.mark.parametrize("event_key", sorted(WELL_FORMED))
def test_every_hook_exits_zero_when_the_payload_has_no_cwd(
    recording_checkout: Path, harness: HookHarness, event_key: str
) -> None:
    payload = _without(WELL_FORMED[event_key](recording_checkout), "cwd")

    delivery = _deliver(harness, recording_checkout, event_key, payload, None)

    assert delivery.failures() == []


INCOMPLETE = {
    "start-without-agent-id": ("SubagentStart", lambda r: _without(_subagent_start(r), "agent_id")),
    "start-without-agent-type": (
        "SubagentStart",
        lambda r: _without(_subagent_start(r), "agent_type"),
    ),
    "stop-without-agent-id": ("SubagentStop", lambda r: _without(_subagent_stop(r), "agent_id")),
    "stop-without-transcript": (
        "SubagentStop",
        lambda r: _without(_subagent_stop(r), "agent_transcript_path"),
    ),
    "agent-call-without-input": (
        "PreToolUse-Agent",
        lambda r: _without(_pre_agent(r), "tool_input"),
    ),
    "agent-call-input-not-an-object": (
        "PreToolUse-Agent",
        lambda r: _with_tool_input(_pre_agent(r), "Implement the parser."),
    ),
    "agent-result-without-response": (
        "PostToolUse-Agent",
        lambda r: _without(_post_agent(r), "tool_response"),
    ),
    "agent-result-without-agent-id": (
        "PostToolUse-Agent",
        lambda r: _post_agent(r, {"status": "completed", "prompt": SPAWN_PROMPT}),
    ),
    "agent-result-without-tool-use-id": (
        "PostToolUse-Agent",
        lambda r: _without(_post_agent(r), "tool_use_id"),
    ),
    "send-without-input": (
        "PreToolUse-SendMessage",
        lambda r: _without(_pre_send(r), "tool_input"),
    ),
    "send-result-without-resumed-id": ("PostToolUse-SendMessage", lambda r: _post_send(r, {})),
}


@pytest.mark.parametrize("case", sorted(INCOMPLETE))
def test_every_hook_exits_zero_when_the_payload_is_incomplete(
    recording_checkout: Path, harness: HookHarness, case: str
) -> None:
    event_key, build = INCOMPLETE[case]

    delivery = _deliver(harness, recording_checkout, event_key, build(recording_checkout), None)

    assert delivery.failures() == []


NOT_AN_OBJECT = ["the agent finished", ["agentId", AGENT_ID], 42, True]


@pytest.mark.parametrize("response", NOT_AN_OBJECT, ids=repr)
@pytest.mark.parametrize("event_key", ["PostToolUse-Agent", "PostToolUse-SendMessage"])
def test_every_hook_exits_zero_when_the_tool_response_is_not_an_object(
    recording_checkout: Path, harness: HookHarness, event_key: str, response: object
) -> None:
    payload = {**WELL_FORMED[event_key](recording_checkout), "tool_response": response}

    delivery = _deliver(harness, recording_checkout, event_key, payload, None)

    assert delivery.failures() == []


NOT_TEXT = [42, None, ["Task slug:", "x"], {"text": "Task slug: x"}]

# The Agent tool events that carry the prompt: the call, and the result, which
# repeats it in both the input and the response.
PROMPT_CARRIERS = {
    "PreToolUse-Agent": lambda root, prompt: _pre_agent(root, prompt),
    "PostToolUse-Agent": lambda root, prompt: _post_agent(root, prompt=prompt),
}


@pytest.mark.parametrize("prompt", NOT_TEXT, ids=repr)
@pytest.mark.parametrize("event_key", sorted(PROMPT_CARRIERS))
def test_every_hook_exits_zero_when_the_prompt_is_not_text(
    recording_checkout: Path, harness: HookHarness, event_key: str, prompt: object
) -> None:
    payload = PROMPT_CARRIERS[event_key](recording_checkout, prompt)

    delivery = _deliver(harness, recording_checkout, event_key, payload, None)

    assert delivery.failures() == []


# -- What can still be recorded is recorded -----------------------------------


def test_a_spawn_whose_result_is_garbled_still_records_its_start_and_stop(
    recording_checkout: Path, harness: HookHarness
) -> None:
    session = Session(harness, SESSION_ID, recording_checkout)
    tool_use_id, tool_input = session.agent_call(SPAWN_PROMPT, AGENT_TYPE)
    session.subagent_start(AGENT_ID, AGENT_TYPE)
    session.subagent_stop(AGENT_ID, AGENT_TYPE)

    session.tool_event(
        "PostToolUse", "Agent", tool_input, tool_use_id, tool_response="the agent finished"
    )

    recorded = [
        r["event_type"]
        for r in log_rows(recording_checkout / STATE_DIR)
        if r.get("agent_id") == AGENT_ID
    ]
    assert {"agent_start", "agent_stop"} <= set(recorded), recorded
    assert session.hook_failures() == []


# -- An unwritable log ----------------------------------------------------------


def _log_path_is_a_directory(root: Path) -> None:
    (root / STATE_DIR / LOG_NAME).mkdir()


def _state_directory_is_read_only(root: Path) -> None:
    state = root / STATE_DIR
    state.chmod(stat.S_IRUSR | stat.S_IXUSR)


@pytest.mark.parametrize(
    "make_unwritable",
    [_log_path_is_a_directory, _state_directory_is_read_only],
    ids=["log-path-is-a-directory", "state-directory-read-only"],
)
def test_every_hook_exits_zero_when_the_log_cannot_be_written(
    recording_checkout: Path, harness: HookHarness, make_unwritable
) -> None:
    make_unwritable(recording_checkout)
    session = Session(harness, SESSION_ID, recording_checkout)

    try:
        session.spawn_foreground(SPAWN_PROMPT, AGENT_ID, AGENT_TYPE)
        session.resume(AGENT_ID, AGENT_TYPE)
    finally:
        os.chmod(recording_checkout / STATE_DIR, stat.S_IRWXU)

    assert session.hook_failures() == []
