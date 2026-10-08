"""Tests for hooks/_agent_transcript.py -- the one reader of a subagent's own transcript.

Three layers: the pure parse (text in, reading out), the locator (files in a temporary config
directory), and a contract against the step-loop driver's double, which leaves a transcript in
each of its three states (ended, running, unreadable). The reader must read what the double
leaves the way the double says it left it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS_DIR))

import _agent_transcript as transcript  # noqa: E402
from _agent_transcript import (  # noqa: E402
    Calling,
    Final,
    Missing,
    Read,
    Unreadable,
    locate,
    parse_transcript,
    read_transcript,
    request_count,
)


def _load_driver():
    """The acceptance driver, loaded by path: `tests` names a regular package under `fitness/`
    when that suite shares the process, and the driver imports nothing from the repository."""
    path = HOOKS_DIR.parent / "tests" / "acceptance" / "drivers" / "step_loop.py"
    spec = importlib.util.spec_from_file_location("step_loop_driver_under_contract", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


driver = _load_driver()
SANDBOX_PROJECT_DIR = driver.SANDBOX_PROJECT_DIR
SANDBOX_SESSION = driver.SANDBOX_SESSION
Step = driver.Step
build_loop = driver.build_loop
leave_agent_transcript = driver.leave_agent_transcript
new_agent_id = driver.new_agent_id

REQUEST_ID = "s1-a1-implement"
AGENT_ID = "a1b2c3d4e5f60718"
SESSION_ID = "session-under-test"
PROMPT = f"Task slug: loop-task\nSpawn request: {REQUEST_ID}\nRead the prompt file first."


def _user(content) -> dict:
    return {"type": "user", "message": {"role": "user", "content": content}}


def _assistant(request_id, *blocks) -> dict:
    message = {"role": "assistant", "content": list(blocks)}
    return {"type": "assistant", "requestId": request_id, "message": message}


def _text(text: str) -> dict:
    return {"type": "text", "text": text}


def _tool(name: str, **tool_input) -> dict:
    return {"type": "tool_use", "name": name, "input": tool_input}


def _jsonl(*entries) -> str:
    return "\n".join(json.dumps(entry) for entry in entries) + "\n"


def _parse(*entries):
    return parse_transcript(_jsonl(*entries))


# -- parse: counting -----------------------------------------------------------------------


def test_an_empty_transcript_reads_as_no_requests_and_no_last_turn():
    assert parse_transcript("") == Read(
        requests=0, first_user_text="", last_turn=None, malformed=False
    )


def test_requests_are_the_distinct_request_ids_over_assistant_records():
    reading = _parse(
        _user(PROMPT),
        _assistant("r1", _text("looking")),
        _assistant("r1", _tool("Bash")),
        _user([{"type": "tool_result"}]),
        _assistant("r2", _text("more")),
        _assistant("r2", _tool("Edit")),
        _assistant("r3", _text("done")),
    )

    assert reading.requests == 3


def test_blank_lines_are_not_records_and_do_not_make_the_transcript_unreadable():
    text = _jsonl(_user(PROMPT)) + "\n   \n" + _jsonl(_assistant("r1", _text("hi")))

    assert parse_transcript(text).requests == 1


@pytest.mark.parametrize(
    "broken",
    [
        _assistant(None, _text("no id")),
        {"type": "assistant", "requestId": "", "message": {"content": []}},
        {"type": "assistant", "requestId": "r9", "message": "not an object"},
        {"type": "assistant", "requestId": "r9"},
    ],
)
def test_an_assistant_record_without_a_usable_id_makes_the_count_unknown_not_guessed(broken):
    reading = _parse(_assistant("r1", _text("fine")), broken)

    assert (reading.requests, reading.malformed) == (None, True)


def test_the_last_turn_of_a_malformed_transcript_comes_from_its_well_formed_requests():
    reading = _parse(_assistant("r1", _text("last good")), _assistant(None, _tool("Bash")))

    assert reading.last_turn == Final("last good")


def test_a_read_cannot_claim_a_count_and_a_malformed_record_together():
    with pytest.raises(ValueError, match="request count is unknown"):
        Read(requests=3, first_user_text="", last_turn=None, malformed=True)


# -- parse: the last turn ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("blocks", "expected"),
    [
        ([_text("All done. [COMPLETE]")], Final("All done. [COMPLETE]")),
        ([_text("first"), _text("second")], Final("first\nsecond")),
        ([_text("editing"), _tool("Bash")], Calling("Bash")),
        ([_tool("Read"), _tool("Edit")], Calling("Edit")),
        ([_text("saying"), _tool("SubagentHandback", message="the result")], Final("the result")),
        ([_tool("SubagentHandback")], Final("")),
        ([_tool("SubagentHandback", message=7)], Final("")),
    ],
)
def test_the_last_turn_is_final_text_or_the_tool_the_agent_is_calling(blocks, expected):
    reading = _parse(_assistant("r1", _text("earlier"), _tool("Bash")), _assistant("r2", *blocks))

    assert reading.last_turn == expected


def test_a_handback_arriving_as_a_tool_input_that_is_not_an_object_reads_as_empty_final():
    entry = _assistant("r1", {"type": "tool_use", "name": "SubagentHandback", "input": "text"})

    assert _parse(entry).last_turn == Final("")


def test_a_last_request_spread_over_records_is_read_as_one_turn():
    reading = _parse(
        _assistant("r1", _tool("Bash")),
        _assistant("r2", _text("words")),
        _assistant("r2", _tool("Edit")),
    )

    assert reading.last_turn == Calling("Edit")


def test_assistant_content_given_as_a_bare_string_reads_as_text():
    reading = _parse({"type": "assistant", "requestId": "r1", "message": {"content": "plain"}})

    assert reading.last_turn == Final("plain")


# -- parse: the first user text ------------------------------------------------------------


@pytest.mark.parametrize(
    "content",
    [PROMPT, [_text(PROMPT)], [{"type": "tool_result"}, _text(PROMPT)]],
)
def test_the_first_user_text_is_the_prompt_whatever_shape_the_content_has(content):
    assert _parse(_user(content)).first_user_text == PROMPT


def test_the_first_user_text_skips_user_records_that_hold_no_text():
    reading = _parse(_user([{"type": "tool_result"}]), _user(PROMPT), _user("a later message"))

    assert reading.first_user_text == PROMPT


def test_text_a_hook_prepended_stays_in_front_of_the_prompt():
    prepended = "Hook says hello.\n" + PROMPT

    assert f"Spawn request: {REQUEST_ID}" in _parse(_user(prepended)).first_user_text


# -- parse: unreadable ---------------------------------------------------------------------


def test_a_non_json_line_before_the_final_entry_is_unreadable_with_the_final_entry_ok():
    text = _jsonl(_user(PROMPT)) + "{cut off mid-flush\n" + _jsonl(_assistant("r1", _text("end")))

    assert parse_transcript(text) == Unreadable(lines_ok=2, last_ok=True)


def test_a_cut_off_final_line_is_unreadable_with_the_final_entry_not_ok():
    text = _jsonl(_user(PROMPT), _assistant("r1", _tool("Bash"))) + '{"type": "assist'

    assert parse_transcript(text) == Unreadable(lines_ok=2, last_ok=False)


@pytest.mark.parametrize("not_an_object", ["[1, 2]", "null", '"text"', "7"])
def test_a_line_that_is_json_but_not_an_object_is_unreadable(not_an_object):
    assert parse_transcript(not_an_object + "\n") == Unreadable(lines_ok=0, last_ok=False)


# -- locate and read -----------------------------------------------------------------------


def _file_at(directory: Path, agent_id: str = AGENT_ID, body: str = "") -> Path:
    path = directory / f"agent-{agent_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body or _jsonl(_user(PROMPT)), encoding="utf-8")
    return path


def _subagents(config: Path, project: str = "-proj", session: str = SESSION_ID) -> Path:
    return config / "projects" / project / session / "subagents"


def test_an_agent_is_found_beside_the_parent_transcript_when_the_session_is_known(tmp_path):
    expected = _file_at(tmp_path / "elsewhere" / SESSION_ID / "subagents")
    parent = tmp_path / "elsewhere" / "parent.jsonl"

    found = locate(
        AGENT_ID, session_id=SESSION_ID, transcript_path=str(parent), config=tmp_path / "none"
    )

    assert found == expected


def test_a_workflow_spawn_is_found_one_level_deeper(tmp_path):
    expected = _file_at(_subagents(tmp_path) / "workflows" / "run-1")

    assert locate(AGENT_ID, config=tmp_path) == expected


def test_a_direct_file_wins_over_a_workflow_file_in_the_same_directory(tmp_path):
    direct = _file_at(_subagents(tmp_path))
    _file_at(_subagents(tmp_path) / "workflows" / "run-1")

    assert locate(AGENT_ID, config=tmp_path) == direct


def test_an_agent_is_found_by_id_across_project_and_session_directories(tmp_path):
    _file_at(_subagents(tmp_path, "-proj-a", "s1"), agent_id="other0000")
    expected = _file_at(_subagents(tmp_path, "-proj-b", "s2"))

    assert locate(AGENT_ID, config=tmp_path) == expected


def test_a_known_session_that_misses_falls_back_to_the_search_by_id(tmp_path):
    expected = _file_at(_subagents(tmp_path))
    parent = tmp_path / "nowhere" / "parent.jsonl"

    found = locate(
        AGENT_ID, session_id="other-session", transcript_path=str(parent), config=tmp_path
    )

    assert found == expected


def test_the_config_directory_comes_from_the_environment_when_none_is_passed(tmp_path, monkeypatch):
    expected = _file_at(_subagents(tmp_path))
    monkeypatch.setenv(transcript.CONFIG_DIR_VARIABLE, str(tmp_path))

    assert locate(AGENT_ID) == expected


def test_the_config_directory_defaults_to_the_claude_directory_of_the_home(tmp_path, monkeypatch):
    expected = _file_at(_subagents(tmp_path / ".claude"))
    monkeypatch.delenv(transcript.CONFIG_DIR_VARIABLE, raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert locate(AGENT_ID) == expected


@pytest.mark.parametrize("not_an_id", ["", "*", "../escape", "a/b", "a b", "agent-*"])
def test_a_string_that_is_not_an_agent_id_is_never_searched_for(tmp_path, not_an_id):
    _file_at(_subagents(tmp_path), agent_id="x")

    assert locate(not_an_id, config=tmp_path) is None


def test_a_directory_named_like_a_transcript_is_not_a_transcript(tmp_path):
    (_subagents(tmp_path) / f"agent-{AGENT_ID}.jsonl").mkdir(parents=True)

    assert locate(AGENT_ID, config=tmp_path) is None


def test_no_file_reads_as_missing():
    assert read_transcript(None) == Missing()


def test_a_file_reads_through_the_same_parse(tmp_path):
    body = _jsonl(_user(PROMPT), _assistant("r1", _text("done")))
    path = _file_at(tmp_path, body=body)

    assert read_transcript(path) == parse_transcript(body)


def test_a_file_that_cannot_be_opened_is_unreadable_rather_than_an_error(tmp_path, monkeypatch):
    path = _file_at(tmp_path)

    def refuse(self, *args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_text", refuse)

    assert read_transcript(path) == Unreadable(lines_ok=0, last_ok=False)


def test_bytes_that_are_not_utf8_are_replaced_not_raised(tmp_path):
    path = _file_at(tmp_path)
    path.write_bytes(path.read_bytes() + b"\xff\xfe\n")

    assert isinstance(read_transcript(path), Unreadable)


# -- contract: the reader agrees with the driver's double -----------------------------------


def _driver_request() -> dict:
    return {"id": REQUEST_ID, "kind": "implement", "step": "1", "agent_call": {"prompt": PROMPT}}


def _leave(tmp_path, **kwargs):
    task = build_loop(tmp_path, Step("1"))
    agent_id = new_agent_id()
    leave_agent_transcript(task, _driver_request(), agent_id, **kwargs)
    return task, agent_id


def _read_the_way_the_hook_does(task, agent_id):
    config = task.sandbox_home / ".claude"
    parent = config / "projects" / SANDBOX_PROJECT_DIR / f"{SANDBOX_SESSION}.jsonl"
    found = locate(agent_id, session_id=SANDBOX_SESSION, transcript_path=str(parent))
    return found, read_transcript(found)


def test_the_reader_reads_an_ended_transcript_as_final_text_with_every_request_counted(
    tmp_path, monkeypatch
):
    task, agent_id = _leave(tmp_path, requests=7, final_text="All done. [COMPLETE]", ended=True)
    monkeypatch.setenv(transcript.CONFIG_DIR_VARIABLE, str(task.sandbox_home / ".claude"))

    reading = read_transcript(locate(agent_id))

    assert reading == Read(
        requests=7, first_user_text=PROMPT, last_turn=Final("All done. [COMPLETE]"), malformed=False
    )


def test_the_reader_reads_a_running_transcript_as_a_tool_call_below_the_cap(tmp_path):
    task, agent_id = _leave(tmp_path, requests=4, final_text="Still editing.", ended=False)

    found, reading = _read_the_way_the_hook_does(task, agent_id)

    assert found.name == f"agent-{agent_id}.jsonl"
    assert reading == Read(
        requests=4, first_user_text=PROMPT, last_turn=Calling("Bash"), malformed=False
    )


def test_the_reader_reads_an_unreadable_transcript_as_a_bad_line_before_an_ok_final_entry(
    tmp_path,
):
    task, agent_id = _leave(
        tmp_path, requests=5, final_text="[COMPLETE]", ended=True, readable=False
    )

    _, reading = _read_the_way_the_hook_does(task, agent_id)

    assert isinstance(reading, Unreadable)
    assert reading.last_ok is True
    assert reading.lines_ok > 0


def test_an_agent_the_double_never_spawned_reads_as_missing_in_the_same_sandbox(
    tmp_path, monkeypatch
):
    task, _ = _leave(tmp_path, requests=2, final_text="Done.", ended=True)
    monkeypatch.setenv(transcript.CONFIG_DIR_VARIABLE, str(task.sandbox_home / ".claude"))

    assert read_transcript(locate(new_agent_id())) == Missing()


# -- one count of an agent's requests ------------------------------------------------------

LINE_BREAKS_BEYOND_NEWLINE = ["\u2028", "\u2029", "\x0b", "\x0c", "\x1c", "\x85"]


def _verbatim_jsonl(*entries) -> str:
    """JSON Lines the way a record with a raw separator inside a string is written."""
    return "\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n"


@pytest.mark.parametrize("separator", LINE_BREAKS_BEYOND_NEWLINE)
def test_a_line_break_other_than_newline_inside_a_string_stays_inside_its_record(separator):
    prompt, reply = f"before{separator}after", f"one{separator}two"
    text = _verbatim_jsonl(_user(prompt), _assistant("r1", _text(reply)))

    reading = parse_transcript(text)

    assert reading == Read(
        requests=1, first_user_text=prompt, last_turn=Final(reply), malformed=False
    )


def test_only_a_newline_ends_a_record():
    text = (
        '{"type": "user", "message": {"content": "a"}}\n{"type": "assistant",\n"requestId": "r1"}'
    )

    assert isinstance(parse_transcript(text), Unreadable)


@pytest.mark.parametrize("requests", [0, 1, 5])
def test_the_count_of_a_clean_transcript_is_its_distinct_requests(requests):
    records = [_assistant(f"r{n}", _text("turn")) for n in range(requests)]

    assert request_count(_parse(_user(PROMPT), *records)) == requests


def test_a_repeated_line_or_request_does_not_raise_the_count():
    records = [_assistant("r1", _text("a")), _assistant("r2", _tool("Bash"))]

    assert request_count(_parse(*records, *records, records[0])) == 2


def test_a_malformed_assistant_record_gives_no_count():
    assert (
        request_count(_parse(_assistant("r1", _text("ok")), _assistant(None, _text("x")))) is None
    )


def test_a_partial_transcript_with_a_cut_off_line_gives_no_count():
    text = _jsonl(_assistant("r1", _text("ok"))) + '{"type": "assistant", "requestId": "r2", "mess'

    assert request_count(parse_transcript(text)) is None


@pytest.mark.parametrize("reading", [Missing(), Unreadable(lines_ok=3, last_ok=True)])
def test_a_transcript_that_was_not_read_gives_no_count(reading):
    assert request_count(reading) is None


def test_the_count_of_a_file_is_the_count_of_its_text(tmp_path):
    body = _jsonl(_user(PROMPT), _assistant("r1", _text("a")), _assistant("r2", _text("b")))

    assert request_count(read_transcript(_file_at(tmp_path, body=body))) == request_count(
        parse_transcript(body)
    )


def test_a_search_confined_to_the_session_does_not_look_in_other_projects(tmp_path):
    _file_at(_subagents(tmp_path, "-proj-b", "s2"))

    assert locate(AGENT_ID, config=tmp_path, search_all=False) is None


def test_a_search_confined_to_the_session_still_finds_the_agent_beside_the_parent(tmp_path):
    expected = _file_at(tmp_path / "elsewhere" / SESSION_ID / "subagents")
    parent = tmp_path / "elsewhere" / "parent.jsonl"

    found = locate(AGENT_ID, session_id=SESSION_ID, transcript_path=str(parent), search_all=False)

    assert found == expected
