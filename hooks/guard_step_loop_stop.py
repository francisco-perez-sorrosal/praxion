#!/usr/bin/env python3
"""Stop hook: hold a stop once when a step-loop request's agent has ended unrecorded.

The rule is `skills/step-loop/SKILL.md`'s, stated no further than the message's clause: a
terminal marker plus the step record is final even under an "interim" notice, so the stop is
held once with the exact `record` call to run.

Fail-open and read-only by construction. Empty, unparseable or non-object input, an input
that says a stop hook already held this stop, no `.ai-work/`, no issued request, every request
recorded, an agent still running, any exception: exit 0 with nothing printed. The body writes
no file and starts no process. The probe (`scripts/_step_loop_outstanding.py`) is imported only
once a text test of the step records finds an issued request, so a project with no step loop
pays one directory walk.

Synchronous (`async: false`, a held stop needs the verdict before the turn ends), registered
once under `Stop` in `hooks/hooks.json`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

MESSAGE_PREFIX = "[step-loop-guard]"
MAX_MESSAGE_BYTES = 600  # the cap of the held message; the one command in it is not trimmed
RULE = (
    'A terminal marker plus the step record is final even under an "interim" notice, '
    "and `record` refuses a running agent, so run it now rather than wait."
)

WORK_DIR = ".ai-work"
WIP_DOC = "WIP.md"
# A step the driver issued: its `Attempts:` line names the request (`_loop_fields` owns the grammar).
ISSUED_REQUEST_LINE = re.compile(r"Attempts\W*:.*\brequest=")

# Cross-file obligation: the form the driver prints for its own commands
# (`SCRIPT` and `SELF_HOST_INVOCATION` in `scripts/_step_loop_cli.py`, pinned equal by this
# hook's unit tests).
DRIVER_ON_PATH = "step_loop.py"
DRIVER_IN_CHECKOUT = "python3 scripts/step_loop.py"


def main() -> None:
    # One handler for the whole body, by contract: a guard that cannot look lets the stop through.
    try:
        message = _hold_message(sys.stdin.read())
        if message:
            print(json.dumps({"decision": "block", "reason": message}))
    except Exception:
        pass


def _hold_message(raw: str) -> str:
    """The message that holds this stop, or "" when it goes through."""
    stop = _parse_stop(raw)
    if stop is None or stop.get("stop_hook_active"):
        return ""
    work_root = _find_work_root()
    if work_root is None or not _any_request_issued(work_root):
        return ""
    subagents = _subagents_dir(stop)
    if subagents is None:
        return ""
    held = _first_ended_unrecorded(work_root, subagents)
    return _message(held) if held is not None else ""


def _parse_stop(raw: str) -> dict | None:
    try:
        stop = json.loads(raw)
    except ValueError:
        return None
    return stop if isinstance(stop, dict) else None


# --- Is a step loop in play? ---------------------------------------------------------------


def _find_work_root() -> Path | None:
    """`.ai-work/` found by walking up from the working directory (as the orientation hook does)."""
    here = Path.cwd()
    return next(
        (parent / WORK_DIR for parent in (here, *here.parents) if (parent / WORK_DIR).is_dir()),
        None,
    )


def _any_request_issued(work_root: Path) -> bool:
    """True when some task's step record has an `Attempts:` line naming a request."""
    try:
        records = [task / WIP_DOC for task in work_root.iterdir() if task.is_dir()]
    except OSError:
        return False
    return any(_names_a_request(record) for record in records)


def _names_a_request(record: Path) -> bool:
    try:
        return ISSUED_REQUEST_LINE.search(record.read_text(encoding="utf-8")) is not None
    except (OSError, UnicodeDecodeError):
        return False


# --- Has its agent ended? -------------------------------------------------------------------


def _subagents_dir(stop: dict) -> Path | None:
    """Where the harness leaves this session's agent transcripts, beside the main transcript."""
    transcript, session = stop.get("transcript_path"), stop.get("session_id")
    if not (isinstance(transcript, str) and transcript and isinstance(session, str) and session):
        return None
    if Path(session).name != session:  # an id is one path segment
        return None
    return Path(transcript).parent / session / "subagents"


def _first_ended_unrecorded(work_root: Path, subagents: Path):
    """The oldest issued request whose agent has ended unrecorded (a `Held`), else None."""
    sys.path.append(str(_plugin_root() / "scripts"))
    from _step_loop_outstanding import ended_unrecorded
    from _step_loop_render import Invocation

    held = ended_unrecorded(work_root, subagents, Invocation(_driver_program()))
    return held[0] if held else None


def _plugin_root() -> Path:
    configured = os.environ.get("CLAUDE_PLUGIN_ROOT")
    return Path(configured) if configured else Path(__file__).resolve().parent.parent


def _driver_program() -> str:
    return DRIVER_ON_PATH if shutil.which(DRIVER_ON_PATH) else DRIVER_IN_CHECKOUT


# --- The message ----------------------------------------------------------------------------


def _message(held) -> str:
    """Three sentences: the fact, the exact call, the rule."""
    outstanding = held.outstanding
    ended = "no terminal marker" if held.marker == "none" else f"the marker {held.marker}"
    fact = (
        f"{MESSAGE_PREFIX} Request {outstanding.request} (step {outstanding.step}): "
        f"agent {held.agent_id} ended with {ended}, and its return is not recorded."
    )
    return f"{fact} Run `{held.command}`. {RULE}"


if __name__ == "__main__":
    main()
