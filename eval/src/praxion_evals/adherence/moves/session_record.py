"""A main session's own record, read once into ordered events or refused as unreadable.

This is the only reader of the raw record: the take proof and the trigger record consume the
events it returns and never touch the file. The record is the harness's JSONL (one JSON object
per line); the events are the three things a score needs, in the order the record gives them:

- ``Arrival``: text that entered the session, by a hook (``hook_additional_context``, whose
  ``hookEvent`` names the channel), as an eager instruction file (``instructions``) or as a lazy
  rule load (``nested_memory``);
- ``ToolUse``: a tool call the session composed;
- ``ToolResult``: what that call printed, which is where a gate's refusal reads.

A record that cannot say what arrived is ``Unreadable`` with the reason, never an empty
success: a line that is not a JSON object, a known record or attachment of a shape no reader
knows, or a record showing no arrival at session start (a harness that does not record arrivals
at all). The shapes are the harness's as probed (Claude Code 2.1.302) and as the move stand-in
plants them; a version that writes them differently reads as unreadable, so it is never scored
from a mis-parse.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SESSION_START_ORIGINS = ("SessionStart", "instructions")
HOOK_ATTACHMENT = "hook_additional_context"
INSTRUCTION_ATTACHMENTS = ("instructions", "nested_memory")
ATTACHMENT_TEXT_KEYS = ("content", "rawContent")


@dataclass(frozen=True)
class Arrival:
    origin: str  # the hook event, or the attachment type of a file the harness loaded
    text: str
    tool_use_id: str | None = None  # the call a tool hook fired for, when the record names it

    @property
    def at_session_start(self) -> bool:
        return self.origin in SESSION_START_ORIGINS


@dataclass(frozen=True)
class ToolUse:
    id: str
    name: str
    command: str | None  # a shell call's command
    file_path: str | None  # a file tool's target


@dataclass(frozen=True)
class ToolResult:
    tool_use_id: str
    text: str


Event = Arrival | ToolUse | ToolResult


@dataclass(frozen=True)
class Parsed:
    events: tuple[Event, ...]

    @property
    def arrivals(self) -> tuple[Arrival, ...]:
        return tuple(event for event in self.events if isinstance(event, Arrival))


@dataclass(frozen=True)
class Unreadable:
    reason: str  # a standalone sentence: why no arrival can be read from the record

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("an unreadable record gives its reason")


SessionEvents = Parsed | Unreadable


class _MalformedError(ValueError):
    """A record of a kind this reader knows, in a shape it does not."""


def parse(path: Path) -> SessionEvents:
    """The record at ``path`` as ordered events, or why it cannot be read."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return Unreadable(f"the session record at {path} cannot be read: {error}")
    try:
        events = tuple(_events(text))
    except _MalformedError as error:
        return Unreadable(f"the session record at {path} is not one this reader knows: {error}")
    parsed = Parsed(events)
    if not any(arrival.at_session_start for arrival in parsed.arrivals):
        return Unreadable(
            f"the session record at {path} shows no arrival at session start, so it cannot say"
            " what the session was given"
        )
    return parsed


def _events(text: str) -> Iterator[Event]:
    # Split on a newline alone: a record holds no raw newline, but its strings can hold U+2028.
    for number, line in enumerate(text.split("\n"), start=1):
        if line.strip():
            yield from _record_events(number, _record(number, line))


def _record(number: int, line: str) -> dict[str, Any]:
    try:
        record = json.loads(line)
    except json.JSONDecodeError as error:
        raise _MalformedError(f"line {number} is not JSON ({error.msg})") from error
    if not isinstance(record, dict):
        raise _MalformedError(f"line {number} is not a JSON object")
    return record


def _record_events(number: int, record: dict[str, Any]) -> Iterator[Event]:
    try:
        match record.get("type"):
            case "attachment":
                yield from _arrival(record.get("attachment"))
            case "assistant":
                yield from _tool_uses(record)
            case "user":
                yield from _tool_results(record)
    except _MalformedError as error:
        raise _MalformedError(f"line {number}: {error}") from error


def _arrival(attachment: object) -> Iterator[Arrival]:
    if not isinstance(attachment, dict):
        raise _MalformedError("an attachment record carries no attachment object")
    kind = attachment.get("type")
    if kind == HOOK_ATTACHMENT:
        origin = attachment.get("hookEvent")
        if not isinstance(origin, str) or not origin:
            raise _MalformedError("a hook context names no hook event")
    elif kind in INSTRUCTION_ATTACHMENTS:
        origin = kind
    else:
        return  # an attachment that delivers no text to the session
    use_id = attachment.get("toolUseID")
    yield Arrival(origin, _attachment_text(attachment), use_id if isinstance(use_id, str) else None)


def _attachment_text(attachment: dict[str, Any]) -> str:
    for key in ATTACHMENT_TEXT_KEYS:
        if key in attachment:
            return _text(attachment[key])
    raise _MalformedError(f"a {attachment['type']} attachment carries no {ATTACHMENT_TEXT_KEYS[0]}")


def _tool_uses(record: dict[str, Any]) -> Iterator[ToolUse]:
    for block in _blocks(record, "tool_use"):
        use_id, name, tool_input = block.get("id"), block.get("name"), block.get("input")
        if not (isinstance(use_id, str) and isinstance(name, str) and isinstance(tool_input, dict)):
            raise _MalformedError("a tool call carries no id, name and input")
        command, file_path = tool_input.get("command"), tool_input.get("file_path")
        yield ToolUse(
            use_id,
            name,
            command if isinstance(command, str) else None,
            file_path if isinstance(file_path, str) else None,
        )


def _tool_results(record: dict[str, Any]) -> Iterator[ToolResult]:
    for block in _blocks(record, "tool_result"):
        use_id = block.get("tool_use_id")
        if not isinstance(use_id, str):
            raise _MalformedError("a tool result names no call")
        yield ToolResult(use_id, _text(block.get("content", "")))


def _blocks(record: dict[str, Any], kind: str) -> Iterator[dict[str, Any]]:
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):  # a prompt's content can be a plain string: no block to read
        yield from (b for b in content if isinstance(b, dict) and b.get("type") == kind)


def _text(content: object) -> str:
    """Text held as a string, or as a list of strings and ``{"text": ...}`` blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_text_part(part) for part in content)
    raise _MalformedError(f"text is held as a string or a list, not {type(content).__name__}")


def _text_part(part: object) -> str:
    if isinstance(part, str):
        return part
    if isinstance(part, dict) and isinstance(part.get("text"), str):
        return part["text"]
    raise _MalformedError("a part of the text is neither a string nor a text block")
