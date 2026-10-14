"""Locating and reading the spawned role's own transcript, where its spawn's hook output lands."""

from __future__ import annotations

import json
from pathlib import Path

from praxion_evals.adherence.transcript import (
    TranscriptRead,
    TranscriptUnread,
    read_role_transcript,
    spawned_agent_id,
    transcript_path,
)

AGENT = "a2450d924b822afe6"
SESSION = "75f0dd28-ee1f-4d69-93f0-a069e860527f"
CWD = "/private/tmp/run.x/s-1/repo"
ATTACHMENT = {"type": "hook_additional_context", "hookEvent": "SubagentStart", "content": []}


def test_the_agent_id_is_read_from_a_synchronous_results_trailer():
    result = f"The findings.\nagentId: {AGENT} (use SendMessage to resume)\n<usage>9</usage>"

    assert spawned_agent_id(result) == AGENT


def test_the_agent_id_is_read_from_a_background_launch_stub():
    stub = f"Async agent launched successfully. (internal)\nagentId: {AGENT} (internal ID)"

    assert spawned_agent_id(stub) == AGENT


def test_a_spawn_result_without_a_trailer_or_with_no_result_names_no_agent():
    assert spawned_agent_id("The findings.") is None
    assert spawned_agent_id(None) is None


def test_the_transcript_lives_under_the_cwd_named_with_every_slash_and_dot_a_dash(tmp_path):
    path = transcript_path(tmp_path, CWD, SESSION, AGENT)

    project = "-private-tmp-run-x-s-1-repo"
    assert path == tmp_path / "projects" / project / SESSION / "subagents" / f"agent-{AGENT}.jsonl"


def test_only_attachment_records_are_read_and_a_torn_last_line_is_skipped(tmp_path):
    path = transcript_path(tmp_path, CWD, SESSION, AGENT)
    path.parent.mkdir(parents=True)
    lines = [
        json.dumps({"type": "user", "message": {}}),
        json.dumps({"type": "attachment", "attachment": ATTACHMENT}),
        json.dumps(["not", "a", "record"]),
        '{"type": "attachment", "attach',
    ]
    path.write_text("\n".join(lines))

    assert read_role_transcript(tmp_path, CWD, SESSION, AGENT) == TranscriptRead(
        path, (ATTACHMENT,)
    )


def test_a_transcript_that_does_not_exist_is_reported_with_its_path(tmp_path):
    expected = transcript_path(tmp_path, CWD, SESSION, AGENT)

    found = read_role_transcript(tmp_path, CWD, SESSION, AGENT)

    assert found == TranscriptUnread(f"the role's transcript at {expected} was not found")


def test_a_transcript_path_that_cannot_be_read_is_reported_as_unreadable(tmp_path):
    transcript_path(tmp_path, CWD, SESSION, AGENT).mkdir(parents=True)

    found = read_role_transcript(tmp_path, CWD, SESSION, AGENT)

    assert isinstance(found, TranscriptUnread)
    assert "could not be read" in found.reason


def test_without_a_session_id_the_transcript_cannot_be_located(tmp_path: Path):
    found = read_role_transcript(tmp_path, CWD, None, AGENT)

    assert found == TranscriptUnread(
        "the stream reports no session id to find the role's transcript by"
    )
