"""The one writer of main-session records, in the harness's own JSONL form.

A planted session record and the record the move stand-in leaves for a launched session are
written here and nowhere else, so the runner's reader meets one shape. The shape is the one
the harness and the role stand-in already use for a spawned role's transcript
(`stand_in_claude._write_role_transcript`, read by `adherence.transcript`), extended to a main
session. One JSON object per line, each stamped with an increasing UTC `timestamp`:

- an `attachment` record is what a hook delivered into the session:
  `{"type": "attachment", "timestamp", "attachment": {"type": "hook_additional_context",
  "hookEvent": "SessionStart" | "PreToolUse", "content": [text, ...]}}`;
- a `user` record is the prompt, `{"type": "user", "timestamp", "message": {"role": "user",
  "content": [{"type": "text", "text"}]}}`, or a tool result,
  `{"content": [{"type": "tool_result", "tool_use_id", "content": [{"type": "text", "text"}]}]}`
  (a gate's refusal is a tool result carrying the reason);
- an `assistant` record holds `tool_use` blocks, `{"type": "assistant", "timestamp",
  "message": {"role": "assistant", "content": [{"type": "tool_use", "id", "name", "input"}]}}`.

What arrives at session start is a `SessionStart` attachment, as `hooks/inject_rules.py` emits
it: the rule bodies with their frontmatter stripped. What arrives at the point of use is a
`PreToolUse` attachment ahead of the tool call it governs. This is the designer's reading of
that form until a real main-session record is frozen; it is not a claim about any harness
version. A planted session whose arm owes no text still carries a `SessionStart` attachment
(of unrelated text), so an unreadable record is never mistaken for an empty one.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from tests.acceptance.drivers import move_declarations
from tests.acceptance.drivers.move_declarations import Payload

Entry = dict[str, Any]
HookEvent = Literal["SessionStart", "PreToolUse"]
SessionStart = Literal[
    "the whole rule", "the resident kernel only", "one line of the rule", "no line of the rule"
]
FIRST_TIMESTAMP = datetime(2026, 10, 27, 9, 0, 0, tzinfo=UTC)
UNRELATED_CONTEXT = "Session context: no rule text is loaded here."
_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


# -- Entries ----------------------------------------------------------------------------------


def attachment(event: HookEvent, text: str) -> Entry:
    """Text a hook delivered into the session at `event`."""
    return {
        "type": "attachment",
        "attachment": {
            "type": "hook_additional_context",
            "hookEvent": event,
            "content": [text],
        },
    }


def prompt(text: str) -> Entry:
    return {
        "type": "user",
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }


def tool_call(use_id: str, name: str, tool_input: Mapping[str, Any]) -> Entry:
    block = {"type": "tool_use", "id": use_id, "name": name, "input": dict(tool_input)}
    return {"type": "assistant", "message": {"role": "assistant", "content": [block]}}


def tool_result(use_id: str, text: str) -> Entry:
    block = {
        "type": "tool_result",
        "tool_use_id": use_id,
        "content": [{"type": "text", "text": text}],
    }
    return {"type": "user", "message": {"role": "user", "content": [block]}}


def write_record(path: Path, entries: Sequence[Entry]) -> Path:
    """Write `entries` in order, each stamped one second after the one before."""
    lines = []
    for position, entry in enumerate(entries):
        stamp = (FIRST_TIMESTAMP + timedelta(seconds=position)).isoformat().replace("+00:00", "Z")
        lines.append(json.dumps({**entry, "timestamp": stamp}))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# -- What an arm owes the record --------------------------------------------------------------


def rule_body(payload: Payload) -> str:
    """The moved rule as the session-start injection delivers it: frontmatter stripped."""
    text = (move_declarations.REPO_ROOT / payload["moved_rule"]).read_text(encoding="utf-8")
    return _FRONTMATTER.sub("", text, count=1).strip("\n")


def session_start_text(payload: Payload, at_session_start: SessionStart) -> str:
    """The text a planted session's start carries of the moved rule, as the scenario names it."""
    body = rule_body(payload)
    if at_session_start == "the whole rule":
        return body
    if at_session_start == "the resident kernel only":
        return move_declarations.resident_kernel(payload)
    if at_session_start == "one line of the rule":
        return next(line for line in body.splitlines() if line.strip() and line[0] != "#")
    return UNRELATED_CONTEXT


def point_of_use_text(payload: Payload) -> str:
    """What the lean arm delivers at the point of use: the rule's lines the kernel does not keep."""
    resident = set(move_declarations.resident_kernel(payload).splitlines())
    return "\n".join(line for line in rule_body(payload).splitlines() if line not in resident)


GOVERNED_COMMAND = "git add -- notes.md && git commit -m 'Add the notes'"


def plant_session(
    path: Path,
    payload: Payload,
    arm: str,
    at_session_start: SessionStart,
    point_of_use_arrived: bool,
) -> Path:
    """A main-session record by what arrived: at session start, and (lean only) at the point of use.

    Point-of-use text belongs to the lean arm's delivery: a full or a floor record never carries
    it, whatever `point_of_use_arrived` says, so a floor record holds no line of the rule.
    """
    entries = [
        attachment("SessionStart", session_start_text(payload, at_session_start)),
        prompt("Commit the notes file."),
    ]
    if arm == "lean" and point_of_use_arrived:
        entries.append(attachment("PreToolUse", point_of_use_text(payload)))
    entries += [
        tool_call("toolu_planted", "Bash", {"command": GOVERNED_COMMAND}),
        tool_result("toolu_planted", "[main 1a2b3c4] Add the notes"),
    ]
    return write_record(path, entries)
