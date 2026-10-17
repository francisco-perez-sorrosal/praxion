"""The spawned role's own transcript: where Claude Code keeps it, and its attachment records.

Claude Code streams hook output only for the parent session's own hooks; a subagent's
``SubagentStart`` hook output lands in the role's transcript instead, as ``attachment``
records. That transcript is therefore where a kernel's delivery can be read. Locating it is
pure; :func:`read_role_transcript` is the one read, and it reports a transcript it could not
find as such, so a path defect is never mistaken for a hook that delivered nothing.

The same transcript holds the role's turns. The harness records no stop reason for a role that
ran out of turns (only a note in the parent's result text), so :func:`role_ending` infers it
from what the transcript does hold: a role that stopped at its cap has exactly ``cap`` distinct
requests and its last one calls a tool, because the harness runs that call and then stops
without a further request. Whatever the record cannot establish is ``Unknown``, with the reason.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# The harness trailer of an Agent tool result, synchronous or a background launch stub.
_AGENT_ID = re.compile(r"^agentId:\s*(?P<id>[\w-]+)", re.MULTILINE)
# Claude Code names a project's transcript directory after its cwd, every character that is
# not an ASCII letter or digit a `-`, one per character (recorded for `/`, `.`, `_`, a space,
# `+` and a non-ASCII letter: a macOS TMPDIR such as `/var/folders/x5/pt_h187.../T` becomes
# `-private-var-folders-x5-pt-h187...-T`).
_PROJECT_DIR_CHARS = re.compile(r"[^A-Za-z0-9]")


@dataclass(frozen=True)
class TurnsCounted:
    requests: int  # distinct API requests: one request spans several assistant records
    ends_on_tool_call: bool  # the last request calls a tool, so no text-only answer followed it


@dataclass(frozen=True)
class TurnsUncounted:
    reason: str  # a standalone sentence: why the record cannot be counted with certainty


RoleTurns = TurnsCounted | TurnsUncounted


@dataclass(frozen=True)
class TranscriptRead:
    path: Path
    attachments: tuple[Mapping[str, Any], ...]  # its attachment records, in transcript order
    turns: RoleTurns


@dataclass(frozen=True)
class TranscriptUnread:
    reason: str  # completes "the <role> was owed an injected kernel and ..."


RoleTranscript = TranscriptRead | TranscriptUnread


@dataclass(frozen=True)
class EndedOnItsOwn:
    turns: int


@dataclass(frozen=True)
class StoppedAtCap:
    turns: int
    cap: int


@dataclass(frozen=True)
class Unknown:
    reason: str  # a standalone sentence: why the transcript cannot say how the role ended


RoleEnding = EndedOnItsOwn | StoppedAtCap | Unknown


def spawned_agent_id(spawn_result: str | None) -> str | None:
    """The agent id the harness reports in the spawn's tool result, when it reports one."""
    found = None if spawn_result is None else _AGENT_ID.search(spawn_result)
    return None if found is None else found["id"]


def transcript_dir_name(cwd: str) -> str:
    """The name Claude Code gives the transcript directory of a session started in ``cwd``."""
    return _PROJECT_DIR_CHARS.sub("-", cwd)


def transcript_path(config_dir: Path, cwd: str, session_id: str, agent_id: str) -> Path:
    """Where Claude Code keeps the transcript of agent ``agent_id`` spawned in ``session_id``."""
    project = transcript_dir_name(cwd)
    return config_dir / "projects" / project / session_id / "subagents" / f"agent-{agent_id}.jsonl"


def read_role_transcript(
    config_dir: Path, cwd: str, session_id: str | None, agent_id: str | None
) -> RoleTranscript:
    """The role's transcript attachments, or why there are none to read."""
    if session_id is None:
        return TranscriptUnread("the stream reports no session id to find the role's transcript by")
    if agent_id is None:
        return TranscriptUnread("the stream reports no agent id for the role's spawn")
    path = transcript_path(config_dir, cwd, session_id, agent_id)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return TranscriptUnread(f"the role's transcript at {path} was not found")
    except OSError as error:
        return TranscriptUnread(f"the role's transcript at {path} could not be read: {error}")
    records, all_whole = _records(text)
    return TranscriptRead(path, _attachments(records), _turns(records, all_whole))


def role_ending(transcript: RoleTranscript, cap: int | None) -> RoleEnding:
    """How the role ended, judged against the turn ``cap`` it ran under (``None`` when unknown)."""
    if isinstance(transcript, TranscriptUnread):
        return Unknown(transcript.reason)
    if isinstance(transcript.turns, TurnsUncounted):
        return Unknown(transcript.turns.reason)
    if cap is None:
        return Unknown("no turn cap is known for the role to judge its turns against")
    return _ending_within(transcript.turns, cap)


def _ending_within(turns: TurnsCounted, cap: int) -> RoleEnding:
    count = turns.requests
    if count == 0:
        return Unknown("the role's transcript holds no request of the role's own")
    if count > cap:
        return Unknown(
            f"the transcript holds {count} requests, more than the {cap}-turn cap: the role was"
            " resumed after it stopped, or ran under another cap"
        )
    if not turns.ends_on_tool_call:
        return EndedOnItsOwn(count)  # a text-only request is no tool-use turn: also at exactly cap
    if count == cap:
        return StoppedAtCap(count, cap)
    return Unknown(
        f"the role's last request, its {count} of {cap}, calls a tool that nothing answered:"
        " it stopped for a reason other than its turn cap"
    )


def _records(text: str) -> tuple[list[dict], bool]:
    """The transcript's records, and whether every non-blank line was one.

    Split on a newline alone: a record holds no raw newline, but its strings can hold U+2028
    and U+2029, which ``str.splitlines()`` would cut a record at.
    """
    lines = [line for line in text.split("\n") if line.strip()]
    parsed = [_as_record(line) for line in lines]
    records = [record for record in parsed if record is not None]
    return records, len(records) == len(lines)


def _as_record(line: str) -> dict | None:
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None  # the transcript is append-only and may end in a torn line
    return record if isinstance(record, dict) else None


def _attachments(records: list[dict]) -> tuple[Mapping[str, Any], ...]:
    found = (record.get("attachment") for record in records if record.get("type") == "attachment")
    return tuple(attachment for attachment in found if isinstance(attachment, dict))


def _turns(records: list[dict], all_whole: bool) -> RoleTurns:
    if not all_whole:
        return TurnsUncounted(
            "a line of the role's transcript is not a whole record (a torn flush), so a request"
            " may be missing from its count"
        )
    assistant = [record for record in records if record.get("type") == "assistant"]
    request_ids = [_request_id(record) for record in assistant]
    if None in request_ids:
        return TurnsUncounted("an assistant record of the role carries no request id to count by")
    last_request = [
        block
        for record, request_id in zip(assistant, request_ids, strict=True)
        if request_id == request_ids[-1]
        for block in _content_blocks(record)
    ]
    ends_on_tool_call = any(block.get("type") == "tool_use" for block in last_request)
    return TurnsCounted(len(set(request_ids)), ends_on_tool_call)


def _request_id(record: dict) -> str | None:
    request_id = record.get("requestId")
    has_message = isinstance(record.get("message"), dict)
    return request_id if isinstance(request_id, str) and request_id and has_message else None


def _content_blocks(record: dict) -> list[dict]:
    content = record["message"].get("content")  # `_request_id` has vouched for the message
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []
