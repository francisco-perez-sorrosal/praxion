"""Tests for spawn_transcripts.py -- recorded subagent transcripts parsed into spawn values.

The fixtures write the layout Claude Code records (`<session>.jsonl` holding each Agent call and
its result, `<session>/subagents/agent-<id>.jsonl` holding the spawn's own turns), the same shape
the outer-loop driver's `record_sessions` writes.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import spawn_transcripts as st  # noqa: E402

FLOOR_MODEL = "claude-sonnet-5-5"
SESSION = "5e55a1b2-0000-4000-8000-000000000001"


def _call(use_id: str, role: str, prompt: str = "Do the step.", model: str | None = None) -> dict:
    spawn_input = {"subagent_type": f"praxion:{role}", "prompt": prompt}
    if model is not None:
        spawn_input["model"] = model
    block = {"type": "tool_use", "id": use_id, "name": "Agent", "input": spawn_input}
    return {"type": "assistant", "message": {"role": "assistant", "content": [block]}}


def _result(use_id: str, agent_id: str) -> dict:
    block = {"type": "tool_result", "tool_use_id": use_id, "content": f"agentId: {agent_id}"}
    return {
        "type": "user",
        "message": {"role": "user", "content": [block]},
        "toolUseResult": {"status": "completed", "agentId": agent_id},
    }


def _blob_copy(record: dict) -> dict:
    """The `api-request-blob` record Claude Code writes for the same message: same content blocks,
    a different record kind."""
    return {
        "type": "api-request-blob",
        "sessionId": SESSION,
        "hash": "0" * 8,
        "message": record["message"],
    }


def _own_transcript(model: str | None) -> list[dict]:
    reply = {"role": "assistant", "content": [{"type": "text", "text": "Done."}]}
    if model is not None:
        reply["model"] = model
    return [
        {"type": "user", "message": {"role": "user", "content": "Do the step."}},
        {"type": "assistant", "message": reply},
    ]


def _write_lines(path: Path, lines: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(line if isinstance(line, str) else json.dumps(line) for line in lines) + "\n",
        encoding="utf-8",
    )


def _record(
    directory: Path,
    session: str,
    role: str,
    agent_id: str,
    ran_model: str | None = FLOOR_MODEL,
    *,
    prompt: str = "Do the step.",
    model: str | None = None,
) -> None:
    """One session holding one spawn, with its own transcript when it ran on a model."""
    use_id = f"toolu_{agent_id}"
    _write_lines(
        directory / f"{session}.jsonl",
        [_call(use_id, role, prompt, model), _result(use_id, agent_id)],
    )
    if ran_model is not None:
        own = directory / session / "subagents" / f"agent-{agent_id}.jsonl"
        _write_lines(own, _own_transcript(ran_model))


def test_a_spawn_that_passed_no_model_reads_back_with_the_model_it_ran_on(tmp_path):
    _record(tmp_path, SESSION, "implementer", "a1", ran_model=FLOOR_MODEL)

    spawns = st.read_spawns(tmp_path)

    assert spawns == [
        st.Spawn(
            session=SESSION,
            agent_id="a1",
            role="implementer",
            requested_model=None,
            ran_model=FLOOR_MODEL,
            prompt_markers=frozenset(),
        )
    ]


def test_a_per_spawn_model_is_the_requested_model_apart_from_the_ran_model(tmp_path):
    _record(tmp_path, SESSION, "researcher", "a1", ran_model="claude-opus-5-5", model="opus")

    (spawn,) = st.read_spawns(tmp_path)

    assert (spawn.requested_model, spawn.ran_model) == ("opus", "claude-opus-5-5")


def test_prompt_markers_are_the_closed_phrases_the_prompt_states(tmp_path):
    prompt = "Task slug: x\nMode: acceptance-design\ntier: H\nroutine consult"
    _record(tmp_path, SESSION, "test-engineer", "a1", prompt=prompt)

    (spawn,) = st.read_spawns(tmp_path)

    assert spawn.prompt_markers == {"Mode: acceptance-design", "tier: H", "routine"}


@pytest.mark.parametrize(
    "prompt",
    [
        "a tier: High hint",
        "routinely",
        "Mode: acceptance-designs",
        "This is not Mode: light-review work.",
        "The step is tier: H and a routine one.",
        "Task slug: x\n  Mode: light-review",
    ],
)
def test_a_marker_is_matched_as_a_whole_phrase_only(tmp_path, prompt):
    _record(tmp_path, SESSION, "implementer", "a1", prompt=prompt)

    (spawn,) = st.read_spawns(tmp_path)

    assert spawn.prompt_markers == frozenset()


def test_a_parenthesised_hint_at_the_end_of_a_line_is_a_marker(tmp_path):
    _record(tmp_path, SESSION, "implementer", "a1", prompt="Implement the refactor (tier: H)")

    (spawn,) = st.read_spawns(tmp_path)

    assert spawn.prompt_markers == {"tier: H"}


def test_one_agent_call_is_one_spawn_whatever_record_kinds_carry_a_copy_of_it(tmp_path):
    call = _call("toolu_a1", "implementer")
    _write_lines(
        tmp_path / f"{SESSION}.jsonl",
        [call, _blob_copy(call), _result("toolu_a1", "a1"), _blob_copy(call)],
    )

    spawns = st.read_spawns(tmp_path)

    assert [s.agent_id for s in spawns] == ["a1"]


def test_a_driver_pointer_prompt_names_the_request_it_answers(tmp_path):
    prompt = "Task slug: x\nSpawn request: s7-a1-review-r1\nRead PROMPT_s7.md first."
    _record(tmp_path, SESSION, "verifier", "a1", prompt=prompt)

    (spawn,) = st.read_spawns(tmp_path)

    assert spawn.driver_request == "s7-a1-review-r1"


@pytest.mark.parametrize(
    "prompt",
    [
        "Do the step.",
        "Spawn request: s7-a1\nTask slug: x",
        "Task slug: x\nWe answer the Spawn request: s7-a1 today.",
        "Intro\nTask slug: x\nSpawn request: s7-a1",
        "Task slug: x\nNo request here.",
    ],
)
def test_a_prompt_that_is_not_a_driver_pointer_names_no_request(tmp_path, prompt):
    _record(tmp_path, SESSION, "verifier", "a1", prompt=prompt)

    (spawn,) = st.read_spawns(tmp_path)

    assert spawn.driver_request is None


def test_a_spawn_with_no_transcript_of_its_own_has_no_ran_model(tmp_path):
    _record(tmp_path, SESSION, "implementer", "a1", ran_model=None)

    (spawn,) = st.read_spawns(tmp_path)

    assert spawn.ran_model is None


def test_an_own_transcript_with_no_model_on_its_assistant_entries_has_no_ran_model(tmp_path):
    _record(tmp_path, SESSION, "implementer", "a1", ran_model=None)
    own = tmp_path / SESSION / "subagents" / "agent-a1.jsonl"
    _write_lines(own, _own_transcript(None) + _own_transcript(st.SYNTHETIC_MODEL))

    (spawn,) = st.read_spawns(tmp_path)

    assert spawn.ran_model is None


def test_an_unreadable_line_is_skipped_and_the_rest_of_the_session_still_reads(tmp_path):
    _write_lines(
        tmp_path / f"{SESSION}.jsonl",
        [
            '{"type": "assistant", "message": {"content": [{"typ',
            "[1, 2]",
            _call("toolu_a1", "implementer"),
            "not json",
            _result("toolu_a1", "a1"),
        ],
    )
    _write_lines(
        tmp_path / SESSION / "subagents" / "agent-a1.jsonl",
        ["{broken", *_own_transcript(FLOOR_MODEL)],
    )

    (spawn,) = st.read_spawns(tmp_path)

    assert (spawn.agent_id, spawn.ran_model) == ("a1", FLOOR_MODEL)


def test_two_sessions_in_one_directory_keep_their_spawns_apart(tmp_path):
    other = "5e55a1b2-0000-4000-8000-000000000002"
    _record(tmp_path, SESSION, "implementer", "a1", ran_model=FLOOR_MODEL)
    _record(tmp_path, other, "verifier", "a2", ran_model="claude-opus-5-5")

    spawns = st.read_spawns(tmp_path)

    assert [(s.session, s.role, s.agent_id, s.ran_model) for s in spawns] == [
        (SESSION, "implementer", "a1", FLOOR_MODEL),
        (other, "verifier", "a2", "claude-opus-5-5"),
    ]


def test_two_spawns_in_one_session_each_read_their_own_transcript(tmp_path):
    _write_lines(
        tmp_path / f"{SESSION}.jsonl",
        [
            _call("toolu_a1", "implementer"),
            _result("toolu_a1", "a1"),
            _call("toolu_a2", "verifier"),
            _result("toolu_a2", "a2"),
        ],
    )
    subagents = tmp_path / SESSION / "subagents"
    _write_lines(subagents / "agent-a1.jsonl", _own_transcript(FLOOR_MODEL))
    _write_lines(subagents / "agent-a2.jsonl", _own_transcript("claude-opus-5-5"))

    spawns = st.read_spawns(tmp_path)

    assert [(s.agent_id, s.ran_model) for s in spawns] == [
        ("a1", FLOOR_MODEL),
        ("a2", "claude-opus-5-5"),
    ]


def test_a_call_that_names_no_agent_id_or_is_not_a_praxion_agent_is_no_spawn(tmp_path):
    other_tool = _call("toolu_b", "implementer")
    other_tool["message"]["content"][0]["input"]["subagent_type"] = "Explore"
    _write_lines(
        tmp_path / f"{SESSION}.jsonl",
        [
            _call("toolu_a", "implementer"),  # no result: it never ran
            other_tool,
            _result("toolu_b", "b1"),
        ],
    )

    assert st.read_spawns(tmp_path) == []


def test_an_empty_directory_holds_no_spawns(tmp_path):
    assert st.read_spawns(tmp_path) == []


def test_a_spawn_is_a_frozen_value():
    spawn = st.Spawn("s", "a1", "implementer", None, None, frozenset())

    with pytest.raises(dataclasses.FrozenInstanceError):
        spawn.ran_model = "x"  # type: ignore[misc]


def test_floors_are_each_definitions_frontmatter_model_by_agent_name(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "implementer.md").write_text(
        "---\nname: implementer\nmodel: sonnet\n---\nBody\n", encoding="utf-8"
    )
    (agents / "researcher.md").write_text(
        "---\nname: researcher\nmodel: opus  # why\n---\nBody\n", encoding="utf-8"
    )
    (agents / "README.md").write_text("# Agents\n", encoding="utf-8")
    (agents / "no-model.md").write_text("---\nname: no-model\n---\n", encoding="utf-8")

    assert st.read_floors(tmp_path) == {"implementer": "sonnet", "researcher": "opus"}
