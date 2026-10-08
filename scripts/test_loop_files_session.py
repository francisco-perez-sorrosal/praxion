"""Tests for `read_agent`'s session arm in ``scripts/_step_loop_files.py``.

A request run by a top-level session (not an Agent-tool spawn) leaves its transcript at
``projects/<slug of the repository>/<session id>.jsonl``; the driver's adapter reads that file
when it is given the repository root and no subagent transcript carries the id.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_files as files  # noqa: E402
from _agent_transcript import Final, Missing, Read  # noqa: E402

STEP = "s9"
REQUEST = f"{STEP}-a1-implement"
OTHER_REQUEST = f"{STEP}-a2-implement"
SESSION_ID = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"
REPOSITORY = Path("/work/some.repo")
REPOSITORY_SLUG = "-work-some-repo"
PROMPT = f"Task slug: s\nSpawn request: {REQUEST}\nRead PROMPT_{REQUEST}.md first."


def user(text: str) -> dict:
    return {"type": "user", "message": {"content": text}}


def turn(request_id: str, text: str, tool: str | None = None) -> dict:
    blocks = [{"type": "text", "text": text}]
    blocks += [{"type": "tool_use", "name": tool, "input": {}}] if tool else []
    return {"type": "assistant", "requestId": request_id, "message": {"content": blocks}}


def write_jsonl(path: Path, records: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
    return path


def put_session(config: Path, records: list[dict]) -> Path:
    return write_jsonl(config / "projects" / REPOSITORY_SLUG / f"{SESSION_ID}.jsonl", records)


def put_subagent(config: Path, agent: str, records: list[dict]) -> Path:
    directory = config / "projects" / REPOSITORY_SLUG / "a-session" / "subagents"
    return write_jsonl(directory / f"agent-{agent}.jsonl", records)


FINISHED = [
    user(PROMPT),
    turn("r1", "reading", tool="Read"),
    turn("r1", "reading more"),
    turn("r2", "done\n[COMPLETE]"),
]


def test_a_top_level_session_is_read_for_its_turns_marker_and_end(tmp_path: Path) -> None:
    written = put_session(tmp_path, FINISHED)

    path, reading = files.read_agent(SESSION_ID, config=tmp_path, cwd=REPOSITORY)

    assert (path, isinstance(reading, Read)) == (written, True)
    assert (reading.requests, reading.last_turn) == (2, Final("done\n[COMPLETE]"))


def test_a_session_transcript_names_its_request_as_a_subagents_does(tmp_path: Path) -> None:
    put_session(tmp_path, FINISHED)

    _, reading = files.read_agent(SESSION_ID, config=tmp_path, cwd=REPOSITORY)

    assert files.names_request(reading, REQUEST) is True


def test_a_session_whose_first_message_names_another_request_is_not_this_ones(
    tmp_path: Path,
) -> None:
    put_session(tmp_path, [user(PROMPT.replace(REQUEST, OTHER_REQUEST)), *FINISHED[1:]])

    _, reading = files.read_agent(SESSION_ID, config=tmp_path, cwd=REPOSITORY)

    assert files.names_request(reading, REQUEST) is False


def test_a_subagents_transcript_is_found_and_counted_as_before(tmp_path: Path) -> None:
    written = put_subagent(tmp_path, "a1b2c3", FINISHED)

    path, reading = files.read_agent("a1b2c3", config=tmp_path, cwd=REPOSITORY)

    assert (path, reading.requests) == (written, 2)


def test_the_subagent_arm_comes_first_when_the_id_is_also_a_session_file(tmp_path: Path) -> None:
    subagent = put_subagent(tmp_path, SESSION_ID, FINISHED[:2])
    put_session(tmp_path, FINISHED)

    path, reading = files.read_agent(SESSION_ID, config=tmp_path, cwd=REPOSITORY)

    assert (path, reading.requests) == (subagent, 1)


def test_a_session_is_not_looked_up_when_no_repository_is_given(tmp_path: Path) -> None:
    put_session(tmp_path, FINISHED)

    assert files.read_agent(SESSION_ID, config=tmp_path) == (None, Missing())


def test_an_id_no_file_carries_reads_as_missing_with_the_session_arm_on(tmp_path: Path) -> None:
    put_session(tmp_path, FINISHED)

    assert files.read_agent("nobody", config=tmp_path, cwd=REPOSITORY) == (None, Missing())
