"""The one reader of a subagent's own transcript.

Claude Code files it at `<session dir>/<session id>/subagents/agent-<agent id>.jsonl` (an
Agent-tool spawn) or under `subagents/workflows/<run>/` (a Workflow-tool spawn). The step-loop
driver's adapter (has the agent ended? how many requests?) and the turn-budget reminder hook (how
many requests so far?) must agree on what it says, so both read it here. `locate` finds it by
session and agent id, else by agent id across every project directory under the config directory
(`search_all=False` keeps a hot caller to the session's own directory); `locate_session` finds
a top-level session's own transcript, which is not a subagent's. A transcript is JSON Lines
split on `"\n"` alone: a record holds no raw newline, but its strings can hold U+2028 and U+2029,
which `str.splitlines()` would cut at. It reads as:

  * `Missing` -- no such file (not flushed yet, or an id from another config directory);
  * `Unreadable(lines_ok, last_ok)` -- a line is not a JSON object, so nothing is trusted:
    `lines_ok` lines parsed and `last_ok` says whether the final one did (a cut-off flush);
  * `Read(requests, first_user_text, last_turn, malformed)` -- every line parsed. `requests`
    counts distinct `requestId` values over assistant records (one API request spans several
    records) and is `None` exactly when an assistant record lacks an id: never guessed.
    `last_turn` is the last well-formed request: `Final(text)` when it holds no tool call,
    `Calling(tool)` when it ends on one; a `SubagentHandback` call hands the result back, so it
    reads as `Final(message)`.

`request_count` is the one definition of an agent's count of requests, read by the step-loop
driver, the turn-budget reminder and the context instrument alike: the `requests` of a `Read`,
`None` for anything else, so a reader that cannot parse a transcript gives no count.

Stdlib only and 3.9-safe: the hook runs under whatever interpreter the harness finds."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Union

CONFIG_DIR_VARIABLE = "CLAUDE_CONFIG_DIR"
HANDBACK_TOOL = "SubagentHandback"

# An agent id becomes part of a glob pattern; anything else is not an id.
_AGENT_ID = re.compile(r"[A-Za-z0-9_-]+")


@dataclass(frozen=True)
class Final:
    text: str


@dataclass(frozen=True)
class Calling:
    tool: str


LastTurn = Union[Final, Calling]  # noqa: UP007 -- runtime value, 3.9 floor


@dataclass(frozen=True)
class Missing:
    """No transcript file exists for the agent."""


@dataclass(frozen=True)
class Unreadable:
    """A line is not a JSON object; `lines_ok` parsed, `last_ok` says if the final one did."""

    lines_ok: int
    last_ok: bool


@dataclass(frozen=True)
class Read:
    """Every line parsed; `requests is None` exactly when `malformed`."""

    requests: int | None
    first_user_text: str
    last_turn: LastTurn | None
    malformed: bool

    def __post_init__(self) -> None:
        if (self.requests is None) != self.malformed:
            raise ValueError("the request count is unknown exactly when a record is malformed")


TranscriptReading = Union[Missing, Unreadable, Read]  # noqa: UP007 -- runtime value, 3.9 floor


def read_transcript(path: Path | None) -> TranscriptReading:
    if path is None:
        return Missing()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return Unreadable(lines_ok=0, last_ok=False)
    return parse_transcript(text)


def locate(
    agent_id: str,
    *,
    session_id: str | None = None,
    transcript_path: str | None = None,
    config: Path | None = None,
    search_all: bool = True,
) -> Path | None:
    """The agent's transcript file, or `None`: beside the parent transcript when the session is
    known, else (when `search_all`) searched by agent id under `<config>/projects/*/*/`."""
    if not _AGENT_ID.fullmatch(agent_id):
        return None
    name = f"agent-{agent_id}.jsonl"
    searched = []
    if session_id and transcript_path:
        searched.append(Path(transcript_path).parent / session_id / "subagents")
    if search_all:
        config = config or Path(os.environ.get(CONFIG_DIR_VARIABLE) or Path.home() / ".claude")
        searched += sorted(config.glob("projects/*/*/subagents"))
    found = (_first_file(subagents, name) for subagents in searched)
    return next((path for path in found if path is not None), None)


def locate_session(session_id: str, cwd: Path, config: Path | None = None) -> Path | None:
    """A top-level session's transcript, or `None`: `<config>/projects/<slug of cwd>/<id>.jsonl`,
    else the first `<config>/projects/*/<id>.jsonl` (session ids are unique, so the glob absorbs
    a slug that drifts: a truncation hash, an overridden project dir name, a symlinked root).
    Reached only by an explicit call, never from `locate`: the reminder's lookup is unchanged."""
    if not _AGENT_ID.fullmatch(session_id):
        return None
    config = config or Path(os.environ.get(CONFIG_DIR_VARIABLE) or Path.home() / ".claude")
    name = f"{session_id}.jsonl"
    derived = config / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(cwd.resolve())) / name
    candidates = [derived, *sorted(config.glob(f"projects/*/{name}"))]
    return next((path for path in candidates if path.is_file()), None)


def request_count(reading: TranscriptReading) -> int | None:
    """The agent's distinct requests, or `None` when the transcript is missing, unreadable or
    holds an assistant record without a request id."""
    return reading.requests if isinstance(reading, Read) else None


def _first_file(subagents: Path, name: str) -> Path | None:
    candidates = [subagents / name, *sorted(subagents.glob(f"workflows/*/{name}"))]
    return next((path for path in candidates if path.is_file()), None)


def parse_transcript(text: str) -> Union[Unreadable, Read]:  # noqa: UP007 -- runtime, 3.9 floor
    lines = [line for line in text.split("\n") if line.strip()]
    parsed = [_as_record(line) for line in lines]
    records = [record for record in parsed if record is not None]
    if len(records) < len(lines):
        return Unreadable(lines_ok=len(records), last_ok=parsed[-1] is not None)
    assistant = [record for record in records if record.get("type") == "assistant"]
    well_formed = [record for record in assistant if _request_id(record) is not None]
    malformed = len(well_formed) < len(assistant)
    return Read(
        requests=None if malformed else len({_request_id(record) for record in well_formed}),
        first_user_text=_first_user_text(records),
        last_turn=_last_turn(well_formed),
        malformed=malformed,
    )


def _as_record(line: str) -> dict | None:
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _request_id(record: dict) -> str | None:
    """The record's request id, or `None` when it is absent or the message is not an object."""
    request_id = record.get("requestId")
    has_message = isinstance(record.get("message"), dict)
    return request_id if isinstance(request_id, str) and request_id and has_message else None


def _blocks(record: dict) -> list:
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    items = [{"type": "text", "text": content}] if isinstance(content, str) else content
    return [block for block in items if isinstance(block, dict)] if isinstance(items, list) else []


def _text_of(blocks: list) -> str:
    texts = [block.get("text") for block in blocks if block.get("type") == "text"]
    return "\n".join(text for text in texts if isinstance(text, str))


def _first_user_text(records: list) -> str:
    texts = (_text_of(_blocks(record)) for record in records if record.get("type") == "user")
    return next((text for text in texts if text), "")


def _last_turn(well_formed: list) -> LastTurn | None:
    if not well_formed:
        return None
    last_id = _request_id(well_formed[-1])
    blocks = [b for r in well_formed if _request_id(r) == last_id for b in _blocks(r)]
    calls = [block for block in blocks if block.get("type") == "tool_use"]
    handbacks = [call for call in calls if call.get("name") == HANDBACK_TOOL]
    if handbacks:
        tool_input = handbacks[-1].get("input")
        message = tool_input.get("message") if isinstance(tool_input, dict) else None
        return Final(message if isinstance(message, str) else "")
    if calls:
        return Calling(str(calls[-1].get("name") or ""))
    return Final(_text_of(blocks))
