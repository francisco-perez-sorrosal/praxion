"""A main session's own record, read once into ordered events or refused as unreadable.

This is the only reader of the raw record: the take proof and the trigger record consume the
events it returns and never touch the file. The record is the harness's JSONL (one JSON object
per line); the events are the three things a score needs, in the order the record gives them:

- ``Delivery``: text that entered the session, by a hook (``hook_additional_context``, whose
  ``hookEvent`` names the channel), as eager instruction files (``instructions``) or as a lazy
  rule load (``nested_memory``);
- ``ToolUse``: a tool call the session composed;
- ``ToolResult``: what that call printed, which is where a gate's refusal reads.

A record that cannot say what arrived is ``Unreadable`` with the reason, never an empty
success: a line that is not a JSON object, a known record or attachment of a shape no reader
knows, or a record showing no arrival at session start (a harness that does not record arrivals
at all). The shapes are the harness's as read from its own records (Claude Code 2.1.283 to
2.1.312): ``instructions`` holds ``files`` of ``{path, type, content}``, ``nested_memory`` holds
one such file as ``content``, a hook holds ``content`` as text; the move stand-in plants the hook
form. A version that writes them differently reads as unreadable, so it is never scored from a
mis-parse. A part that carries no text (an image, a tool reference) is skipped, not refused.
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


@dataclass(frozen=True)
class Delivery:
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


Event = Delivery | ToolUse | ToolResult


@dataclass(frozen=True)
class Parsed:
    events: tuple[Event, ...]

    @property
    def deliveries(self) -> tuple[Delivery, ...]:
        return tuple(event for event in self.events if isinstance(event, Delivery))


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
    if not any(delivery.at_session_start for delivery in parsed.deliveries):
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
                yield from _delivery(record.get("attachment"))
            case "assistant":
                yield from _tool_uses(record)
            case "user":
                yield from _tool_results(record)
    except _MalformedError as error:
        raise _MalformedError(f"line {number}: {error}") from error


def _delivery(attachment: object) -> Iterator[Delivery]:
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
    yield Delivery(
        origin, _delivered_text(kind, attachment), use_id if isinstance(use_id, str) else None
    )


def _delivered_text(kind: str, attachment: dict[str, Any]) -> str:
    match kind:
        case "instructions":
            files = attachment.get("files")
            if not isinstance(files, list):
                raise _MalformedError("an instructions attachment carries no list of files")
            return "\n".join(_file_text(file) for file in files)
        case "nested_memory":
            return _file_text(attachment.get("content"))
        case _:
            if "content" not in attachment:
                raise _MalformedError(f"a {kind} attachment carries no content")
            return _text(attachment["content"])


def _file_text(file: object) -> str:
    text = file.get("content") if isinstance(file, dict) else None
    if not isinstance(text, str):
        raise _MalformedError("a loaded file carries no text")
    return text


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
    """Text held as a string, or as a list of strings and typed blocks (those without text skipped)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(text for text in map(_text_part, content) if text is not None)
    raise _MalformedError(f"text is held as a string or a list, not {type(content).__name__}")


def _text_part(part: object) -> str | None:
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        if isinstance(part.get("text"), str):
            return part["text"]
        if isinstance(part.get("type"), str):
            return None  # a typed block that carries no text, such as an image or a tool reference
    raise _MalformedError("a part of the text is neither a string nor a typed block")
