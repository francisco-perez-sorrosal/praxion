"""Locating and reading the spawned role's own transcript, where its spawn's hook output lands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from praxion_evals.adherence.transcript import (
    EndedOnItsOwn,
    RoleTranscript,
    StoppedAtCap,
    TranscriptRead,
    TranscriptUnread,
    Unknown,
    read_role_transcript,
    role_ending,
    spawned_agent_id,
    transcript_dir_name,
    transcript_path,
)

AGENT = "a2450d924b822afe6"
SESSION = "75f0dd28-ee1f-4d69-93f0-a069e860527f"
CWD = "/private/tmp/run.x/s-1/repo"
ATTACHMENT = {"type": "hook_additional_context", "hookEvent": "SubagentStart", "content": []}
# A real 10-turn role stopped at its cap: records 1 and 10 verbatim from Claude Code 2.1.293
# (`claude -p`, agent `turn-probe`, `maxTurns: 10`), turns 2 to 9 repeating turn 1's shape.
STOPPED_AT_CAP = (
    Path(__file__).parent / "fixtures" / "role_transcripts" / "turn_probe_stopped_at_cap.jsonl"
)


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

    found = read_role_transcript(tmp_path, CWD, SESSION, AGENT)

    assert isinstance(found, TranscriptRead)
    assert found.path == path
    assert found.attachments == (ATTACHMENT,)


def test_a_transcript_that_does_not_exist_is_reported_with_its_path(tmp_path):
    expected = transcript_path(tmp_path, CWD, SESSION, AGENT)

    found = read_role_transcript(tmp_path, CWD, SESSION, AGENT)

    assert found == TranscriptUnread(f"the role's transcript at {expected} was not found")


def test_the_project_directory_turns_every_non_alphanumeric_character_into_a_dash():
    # A macOS TMPDIR holds underscores; the harness names the directory with dashes for them too.
    cwd = "/private/var/folders/x5/pt_h187j3px6_b1dh6fc74kr0000gn/T/praxion-evals-adherence-60q9z5xi/s-1/repo"

    path = transcript_path(Path("/cfg"), cwd, SESSION, AGENT)

    assert (
        path.parts[3]
        == "-private-var-folders-x5-pt-h187j3px6-b1dh6fc74kr0000gn-T-praxion-evals-adherence-60q9z5xi-s-1-repo"
    )


@pytest.mark.parametrize(
    ("cwd", "named"),
    [
        (
            "/private/tmp/claude-501/-Users-fperez-dev-praxion/ad40a83d/scratchpad/naming probe_a+b \u00f1",
            "-private-tmp-claude-501--Users-fperez-dev-praxion-ad40a83d-scratchpad-naming-probe-a-b--",
        ),
        (
            "/Users/fperez/dev/praxion/.claude/worktrees/lean-spawn-continuation",
            "-Users-fperez-dev-praxion--claude-worktrees-lean-spawn-continuation",
        ),
        ("/Users/me/repo2", "-Users-me-repo2"),
        ("/srv//repo", "-srv--repo"),
    ],
    ids=["recorded: odd characters", "recorded: dots", "all ASCII", "empty segment"],
)
def test_the_directory_name_has_one_dash_for_each_character_that_is_not_a_letter_or_digit(
    cwd, named
):
    assert transcript_dir_name(cwd) == named


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


def _turn(number: int, *, calls_tool: bool = True) -> list[str]:
    """One request of the role: an assistant record, and the tool result when it called a tool."""
    block = {"type": "tool_use", "name": "Bash"} if calls_tool else {"type": "text", "text": "done"}
    assistant = {
        "type": "assistant",
        "requestId": f"req_{number}",
        "message": {"content": [block]},
    }
    result = {"type": "user", "message": {"content": [{"type": "tool_result"}]}}
    return [json.dumps(assistant)] + ([json.dumps(result)] if calls_tool else [])


def _read(config_dir: Path, text: str) -> RoleTranscript:
    path = transcript_path(config_dir, CWD, SESSION, AGENT)
    path.parent.mkdir(parents=True)
    path.write_text(text)
    return read_role_transcript(config_dir, CWD, SESSION, AGENT)


def _read_lines(config_dir: Path, lines: list[str]) -> RoleTranscript:
    return _read(config_dir, "\n".join(lines) + "\n")


def test_a_recorded_role_that_ran_ten_tool_turns_under_a_cap_of_ten_stopped_at_it(tmp_path):
    found = _read(tmp_path, STOPPED_AT_CAP.read_text())

    assert role_ending(found, cap=10) == StoppedAtCap(turns=10, cap=10)


def test_a_role_whose_last_request_is_text_ended_on_its_own_before_its_cap(tmp_path):
    found = _read_lines(tmp_path, [*_turn(1), *_turn(2), *_turn(3, calls_tool=False)])

    assert role_ending(found, cap=10) == EndedOnItsOwn(turns=3)


def test_a_role_that_answered_in_text_on_its_cap_request_ended_on_its_own(tmp_path):
    found = _read_lines(tmp_path, [*_turn(1), *_turn(2, calls_tool=False)])

    assert role_ending(found, cap=2) == EndedOnItsOwn(turns=2)


def test_several_records_of_one_request_count_as_one_turn(tmp_path):
    thinking = {"type": "assistant", "requestId": "req_1", "message": {"content": []}}
    found = _read_lines(tmp_path, [json.dumps(thinking), *_turn(1), *_turn(2, calls_tool=False)])

    assert role_ending(found, cap=5) == EndedOnItsOwn(turns=2)


def test_a_missing_transcript_leaves_the_ending_unknown_with_the_reason_it_was_missing(tmp_path):
    missing = read_role_transcript(tmp_path, CWD, SESSION, AGENT)

    assert role_ending(missing, cap=10) == Unknown(
        f"the role's transcript at {transcript_path(tmp_path, CWD, SESSION, AGENT)} was not found"
    )


def test_a_torn_last_line_leaves_the_ending_unknown_for_the_request_it_may_hide(tmp_path):
    torn = '{"type": "assistant", "requestId": "req_3", "mess'
    found = _read(tmp_path, "\n".join([*_turn(1), *_turn(2), torn]))

    ending = role_ending(found, cap=2)

    assert isinstance(ending, Unknown)
    assert "torn" in ending.reason


def test_without_a_cap_the_ending_is_unknown_however_many_turns_were_taken(tmp_path):
    found = _read_lines(tmp_path, [*_turn(1), *_turn(2)])

    assert role_ending(found, cap=None) == Unknown(
        "no turn cap is known for the role to judge its turns against"
    )


def test_more_requests_than_the_cap_mean_the_role_was_resumed_and_the_ending_is_unknown(tmp_path):
    found = _read_lines(tmp_path, [*_turn(1), *_turn(2), *_turn(3, calls_tool=False)])

    ending = role_ending(found, cap=2)

    assert isinstance(ending, Unknown)
    assert "3 requests, more than the 2-turn cap" in ending.reason


def test_a_last_tool_call_short_of_the_cap_is_not_read_as_a_stop_at_it(tmp_path):
    found = _read_lines(tmp_path, [*_turn(1), *_turn(2)])

    ending = role_ending(found, cap=10)

    assert isinstance(ending, Unknown)
    assert "other than its turn cap" in ending.reason


def test_an_assistant_record_without_a_request_id_leaves_the_ending_unknown(tmp_path):
    nameless = {"type": "assistant", "message": {"content": []}}
    found = _read_lines(tmp_path, [*_turn(1), json.dumps(nameless)])

    ending = role_ending(found, cap=1)

    assert isinstance(ending, Unknown)
    assert "no request id" in ending.reason


def test_a_transcript_holding_no_request_of_the_role_leaves_the_ending_unknown(tmp_path):
    found = _read_lines(tmp_path, [json.dumps({"type": "attachment", "attachment": ATTACHMENT})])

    assert isinstance(role_ending(found, cap=10), Unknown)


def test_a_line_separator_inside_a_record_does_not_tear_it(tmp_path):
    spoken = {
        "type": "assistant",
        "requestId": "req_1",
        "message": {"content": [{"type": "text", "text": "one two"}]},
    }
    found = _read(tmp_path, json.dumps(spoken, ensure_ascii=False) + "\n")

    assert role_ending(found, cap=3) == EndedOnItsOwn(turns=1)
