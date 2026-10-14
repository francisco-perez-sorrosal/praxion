"""The spawned role's own transcript: where Claude Code keeps it, and its attachment records.

Claude Code streams hook output only for the parent session's own hooks; a subagent's
``SubagentStart`` hook output lands in the role's transcript instead, as ``attachment``
records. That transcript is therefore where a kernel's delivery can be read. Locating it is
pure; :func:`read_role_transcript` is the one read, and it reports a transcript it could not
find as such, so a path defect is never mistaken for a hook that delivered nothing.
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
# not a letter or a digit a `-` (observed for `/`, `.` and `_`: a macOS TMPDIR such as
# `/var/folders/x5/pt_h187.../T` becomes `-private-var-folders-x5-pt-h187...-T`).
_PROJECT_DIR_CHARS = re.compile(r"[^A-Za-z0-9]")


@dataclass(frozen=True)
class TranscriptRead:
    path: Path
    attachments: tuple[Mapping[str, Any], ...]  # its attachment records, in transcript order


@dataclass(frozen=True)
class TranscriptUnread:
    reason: str  # completes "the <role> was owed an injected kernel and ..."


RoleTranscript = TranscriptRead | TranscriptUnread


def spawned_agent_id(spawn_result: str | None) -> str | None:
    """The agent id the harness reports in the spawn's tool result, when it reports one."""
    found = None if spawn_result is None else _AGENT_ID.search(spawn_result)
    return None if found is None else found["id"]


def transcript_path(config_dir: Path, cwd: str, session_id: str, agent_id: str) -> Path:
    """Where Claude Code keeps the transcript of agent ``agent_id`` spawned in ``session_id``."""
    project = _PROJECT_DIR_CHARS.sub("-", cwd)
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
    return TranscriptRead(path, _attachments(text))


def _attachments(text: str) -> tuple[Mapping[str, Any], ...]:
    records = []
    for line in text.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue  # the transcript is append-only and may end in a torn line
        if not isinstance(record, dict) or record.get("type") != "attachment":
            continue
        attachment = record.get("attachment")
        if isinstance(attachment, dict):
            records.append(attachment)
    return tuple(records)
