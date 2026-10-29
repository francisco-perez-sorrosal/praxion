"""A main session's record is read once into ordered events, and a record that cannot say what
arrived is unreadable with the reason, never an empty success."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from praxion_evals.adherence.moves import session_record
from praxion_evals.adherence.moves.session_record import (
    Delivery,
    Parsed,
    ToolResult,
    ToolUse,
    Unreadable,
)

Entry = Mapping[str, Any]


def hook_context(event: str, text: str, **extra: Any) -> Entry:
    attachment = {"type": "hook_additional_context", "hookEvent": event, "content": [text]}
    return {"type": "attachment", "attachment": {**attachment, **extra}}


def instructions(*texts: str) -> Entry:
    files = [
        {"path": f"/work/rule-{n}.md", "type": "Project", "content": t} for n, t in enumerate(texts)
    ]
    return {"type": "attachment", "attachment": {"type": "instructions", "files": files}}


def lazy_rule(text: str) -> Entry:
    file = {"path": "/work/rules/x.md", "type": "Project", "content": text, "globs": ["x/**"]}
    attachment = {"type": "nested_memory", "path": file["path"], "content": file}
    return {"type": "attachment", "attachment": attachment}


def tool_call(use_id: str, name: str, tool_input: Mapping[str, Any]) -> Entry:
    block = {"type": "tool_use", "id": use_id, "name": name, "input": tool_input}
    return {"type": "assistant", "message": {"role": "assistant", "content": [block]}}


def tool_output(use_id: str, content: Any) -> Entry:
    block = {"type": "tool_result", "tool_use_id": use_id, "content": content}
    return {"type": "user", "message": {"role": "user", "content": [block]}}


def prompt(text: str) -> Entry:
    return {"type": "user", "message": {"role": "user", "content": text}}


def write_record(path: Path, entries: Sequence[Entry]) -> Path:
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
    return path


def parsed(path: Path) -> Parsed:
    events = session_record.parse(path)
    assert isinstance(events, Parsed), events
    return events


def unreadable(path: Path) -> Unreadable:
    events = session_record.parse(path)
    assert isinstance(events, Unreadable), events
    return events


def test_events_come_back_in_the_order_the_record_gives_them(tmp_path):
    path = write_record(
        tmp_path / "s.jsonl",
        [
            hook_context("SessionStart", "start text"),
            prompt("Commit the notes."),
            hook_context("PreToolUse", "use text", toolUseID="toolu_1"),
            tool_call("toolu_1", "Bash", {"command": "git commit -m x"}),
            tool_output("toolu_1", [{"type": "text", "text": "[main 1a2b] x"}]),
        ],
    )

    assert parsed(path).events == (
        Delivery("SessionStart", "start text"),
        Delivery("PreToolUse", "use text", tool_use_id="toolu_1"),
        ToolUse("toolu_1", "Bash", "git commit -m x", None),
        ToolResult("toolu_1", "[main 1a2b] x"),
    )


def test_a_file_tool_call_keeps_its_target(tmp_path):
    path = write_record(
        tmp_path / "s.jsonl",
        [
            hook_context("SessionStart", "start"),
            tool_call("toolu_1", "Write", {"file_path": "/work/.ai-state/decisions/x.md"}),
        ],
    )

    assert parsed(path).events[-1] == ToolUse(
        "toolu_1", "Write", None, "/work/.ai-state/decisions/x.md"
    )


def test_instruction_files_and_lazy_rule_loads_arrive_as_the_harness_names_them(tmp_path):
    path = write_record(
        tmp_path / "s.jsonl",
        [
            instructions("eager rule text", "second file"),
            lazy_rule("lazy"),
        ],
    )

    arrivals = parsed(path).deliveries

    assert [(a.origin, a.text, a.at_session_start) for a in arrivals] == [
        ("instructions", "eager rule text\nsecond file", True),
        ("nested_memory", "lazy", False),
    ]


def test_records_that_deliver_no_text_are_not_events(tmp_path):
    path = write_record(
        tmp_path / "s.jsonl",
        [
            hook_context("SessionStart", "start"),
            {"type": "attachment", "attachment": {"type": "hook_success", "hookName": "x"}},
            {"type": "system", "subtype": "init"},
            prompt("hello"),
        ],
    )

    assert parsed(path).events == (Delivery("SessionStart", "start"),)


def test_a_tool_result_part_without_text_is_skipped_not_refused(tmp_path):
    parts = [{"type": "tool_reference", "tool_name": "Bash"}, {"type": "image", "source": {}}]
    path = write_record(
        tmp_path / "s.jsonl",
        [
            hook_context("SessionStart", "start"),
            tool_output("toolu_1", [*parts, {"type": "text", "text": "found"}]),
        ],
    )

    assert parsed(path).events[-1] == ToolResult("toolu_1", "found")


def test_a_tool_result_given_as_a_plain_string_is_read(tmp_path):
    path = write_record(
        tmp_path / "s.jsonl",
        [hook_context("SessionStart", "start"), tool_output("toolu_1", "refused: no")],
    )

    assert parsed(path).events[-1] == ToolResult("toolu_1", "refused: no")


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("not a session record\n{\x00 neither is this\n", "line 1 is not JSON"),
        ('{"type": "system"}\n[1, 2]\n', "line 2 is not a JSON object"),
    ],
)
def test_lines_that_are_not_json_objects_make_the_record_unreadable(tmp_path, content, reason):
    path = tmp_path / "s.jsonl"
    path.write_text(content, encoding="utf-8")

    assert reason in unreadable(path).reason


def test_a_record_of_a_later_harness_showing_no_session_start_arrival_is_unreadable(tmp_path):
    path = write_record(
        tmp_path / "s.jsonl",
        [
            {"type": "session-v9", "version": "99.0.0", "payload": "opaque"},
            {"type": "attachments-v9", "version": "99.0.0", "blob": "b64:AAAA"},
        ],
    )

    assert "no arrival at session start" in unreadable(path).reason


def test_a_record_with_only_later_arrivals_is_unreadable_not_empty(tmp_path):
    path = write_record(tmp_path / "s.jsonl", [hook_context("PreToolUse", "use text")])

    assert isinstance(session_record.parse(path), Unreadable)


def test_an_empty_record_is_unreadable_not_an_empty_success(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text("", encoding="utf-8")

    assert isinstance(session_record.parse(path), Unreadable)


def test_a_missing_record_is_unreadable_naming_the_path(tmp_path):
    path = tmp_path / "gone.jsonl"

    assert str(path) in unreadable(path).reason


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "attachment", "attachment": {"type": "hook_additional_context", "content": ["x"]}},
        {"type": "attachment", "attachment": {"type": "instructions"}},
        {"type": "attachment", "attachment": {"type": "instructions", "files": [{"path": "x"}]}},
        {"type": "attachment", "attachment": {"type": "nested_memory", "content": {"a": 1}}},
        {"type": "attachment", "attachment": {"type": "nested_memory", "content": "bare"}},
        {
            "type": "user",
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": "t", "content": [{"x": 1}]}]
            },
        },
        {"type": "attachment"},
        {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {}}]},
        },
        {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "content": "no call named"}]},
        },
    ],
    ids=[
        "hook-without-event",
        "instructions-without-files",
        "instructions-file-without-text",
        "lazy-load-without-file-text",
        "lazy-load-as-bare-text",
        "result-part-of-no-known-shape",
        "attachment-without-object",
        "call-without-id",
        "result-without-call",
    ],
)
def test_a_known_record_in_a_shape_no_reader_knows_makes_the_record_unreadable(tmp_path, bad):
    path = write_record(tmp_path / "s.jsonl", [hook_context("SessionStart", "start"), bad])

    assert "line 2" in unreadable(path).reason


def test_an_unreadable_record_gives_its_reason():
    with pytest.raises(ValueError, match="reason"):
        Unreadable(" ")
