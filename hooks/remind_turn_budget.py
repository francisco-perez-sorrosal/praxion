#!/usr/bin/env python3
"""Turn-budget reminder hook -- tells a subagent it is nearing its turn cap while it can still
stop in a committable state.

PreToolUse hook, registered for every tool call. A subagent that hits its `maxTurns` cap is
cut off mid-edit with no chance to report; this hook counts the distinct API requests in the
calling agent's own transcript against the cap its definition declares, and injects one line
at 60 percent and one at 80 percent of that cap, once per agent and threshold, as
`hookSpecificOutput.additionalContext` (stderr at exit 0 never reaches the model).

Advisory by construction: it exits 0 on every path, so a failure of any kind is a missed
reminder and never a blocked tool call. It is silent for the main session (the payload carries
no `agent_id`, even for a `--agent` session, which carries `agent_type` only) and for an agent
whose definition declares no cap. The main-session path opens no file and never loads the
transcript reader: the hook runs on every tool call of every session.

The once-state is an empty marker file per agent and threshold, claimed with `O_EXCL` so that
concurrent calls emit at most once. Stdlib only and 3.9-safe.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from _hook_utils import is_disabled

DISABLE_FLAG = "PRAXION_DISABLE_TURN_BUDGET_REMINDER"
PREFIX = "[turn-budget]"
THRESHOLDS = (60, 80)
MARKER_DIR = "praxion-turn-budget"
PLUGIN_AGENT_PREFIX = "praxion:"
CONFIG_DIR_VARIABLE = "CLAUDE_CONFIG_DIR"
PLUGIN_AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"

IMPLEMENTER_60 = (
    "Finish the edit you are making, then run your step's Check: command once and record "
    "its Result: line in TEST_RESULTS.md."
)
IMPLEMENTER_80 = (
    "Start nothing new: finish the current file edit, leave the tree committable, record "
    "Result: if you have not, update your step's WIP.md line and return [PARTIAL] — or "
    "[COMPLETE] if your Check: is met. Never commit."
)
OTHER_60 = (
    "Write what you have to your output document now; keep its [PARTIAL] header until it "
    "is complete."
)
OTHER_80 = (
    "Start nothing new: bring your output document to its final state, or leave its "
    "[PARTIAL] header on what you have, then return."
)
ACTIONS = {
    "praxion:implementer": {60: IMPLEMENTER_60, 80: IMPLEMENTER_80},
}
DEFAULT_ACTIONS = {60: OTHER_60, 80: OTHER_80}

# Ids and agent names become path segments; anything outside this alphabet is not one.
_SAFE_NAME = re.compile(r"[A-Za-z0-9_-]+")
_MAX_TURNS = re.compile(r"^maxTurns:\s*(\d+)\s*$", re.MULTILINE)
_FRONTMATTER = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)


@dataclass(frozen=True)
class SubagentCall:
    """A tool call made inside a subagent."""

    session_id: str
    agent_id: str
    agent_type: str
    transcript_path: str
    cwd: str


@dataclass(frozen=True)
class MainCall:
    """A tool call made by a main session."""


@dataclass(frozen=True)
class Unusable:
    """Not a JSON object, or a required field is missing, empty or unsafe."""


Call = Union[SubagentCall, MainCall, Unusable]  # noqa: UP007 -- runtime value, 3.9 floor


def parse_payload(text: str) -> Call:
    """The one boundary: everything past it trusts the variant it holds."""
    try:
        payload = json.loads(text)
    except ValueError:
        return Unusable()
    if not isinstance(payload, dict):
        return Unusable()
    if payload.get("agent_id") is None:
        return MainCall()
    fields = [
        payload.get(name)
        for name in ("session_id", "agent_id", "agent_type", "transcript_path", "cwd")
    ]
    if not all(isinstance(value, str) and value for value in fields):
        return Unusable()
    call = SubagentCall(*fields)
    safe_ids = _SAFE_NAME.fullmatch(call.session_id) and _SAFE_NAME.fullmatch(call.agent_id)
    return call if safe_ids else Unusable()


def declared_cap(agent_type: str, cwd: str) -> int | None:
    """The `maxTurns` of the first readable definition of the agent, else `None`."""
    for path in _definition_paths(agent_type, cwd):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, ValueError):  # unreadable, undecodable, or a path no file can have
            continue
        return _max_turns(text)
    return None


def _definition_paths(agent_type: str, cwd: str) -> list:
    """Where the agent's definition lives: the plugin's own agents for `praxion:<name>`; for a
    bare `<name>`, the project's and then the user's."""
    if agent_type.startswith(PLUGIN_AGENT_PREFIX):
        name = agent_type[len(PLUGIN_AGENT_PREFIX) :]
        return [PLUGIN_AGENTS_DIR / f"{name}.md"] if _SAFE_NAME.fullmatch(name) else []
    if not _SAFE_NAME.fullmatch(agent_type):
        return []
    config = Path(os.environ.get(CONFIG_DIR_VARIABLE) or Path.home() / ".claude")
    return [
        Path(cwd) / ".claude" / "agents" / f"{agent_type}.md",
        config / "agents" / f"{agent_type}.md",
    ]


def _max_turns(definition: str) -> int | None:
    block = _FRONTMATTER.match(definition)
    found = _MAX_TURNS.search(block.group(1)) if block else None
    cap = int(found.group(1)) if found else 0
    return cap if cap > 0 else None


def _marker(call: SubagentCall, threshold: int) -> Path:
    return (
        Path(tempfile.gettempdir()) / MARKER_DIR / call.session_id / f"{call.agent_id}.{threshold}"
    )


def _claim(marker: Path) -> bool:
    """Create the marker; `False` when it already exists (the reminder was given)."""
    marker.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.close(os.open(str(marker), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return False
    return True


def _requests_used(call: SubagentCall) -> int | None:
    # Imported here so the main-session path never loads the transcript reader.
    from _agent_transcript import locate, read_transcript, request_count

    path = locate(
        call.agent_id,
        session_id=call.session_id,
        transcript_path=call.transcript_path,
        search_all=False,
    )
    return request_count(read_transcript(path))


def reminder_line(call: SubagentCall) -> str | None:
    """The line to inject now, or `None`. Cheapest exits first."""
    cap = declared_cap(call.agent_type, call.cwd)
    if cap is None or _marker(call, THRESHOLDS[-1]).exists():
        return None
    used = _requests_used(call)
    if used is None:
        return None
    crossed = [t for t in THRESHOLDS if used * 100 >= cap * t]
    if not crossed or not _claim(_marker(call, crossed[-1])):
        return None
    for lower in crossed[:-1]:
        _claim(_marker(call, lower))
    actions = ACTIONS.get(call.agent_type, DEFAULT_ACTIONS)
    return f"{PREFIX} {used} of {cap} turns used. {actions[crossed[-1]]}"


def main() -> None:
    """Read the PreToolUse payload from stdin and remind. Never blocks."""
    call = parse_payload(sys.stdin.read())
    if not isinstance(call, SubagentCall) or is_disabled(DISABLE_FLAG):
        return
    line = reminder_line(call)
    if line is not None:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": line}}
        print(json.dumps(output))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Fail-open: a reminder must never be the reason a tool call fails.
        pass
    sys.exit(0)
