#!/usr/bin/env python3
"""Stop hook: hold a stop once when a step-loop request's agent has ended unrecorded.

The rule is `skills/step-loop/SKILL.md`'s, stated no further than the message's clause: a
terminal marker plus the step record is final even under an "interim" notice, so the stop is
held once with the exact `record` call to run.

Fail-open and read-only by construction. Empty, unparseable or non-object input, an input
that says a stop hook already held this stop, a session id that is not one plain path segment,
no checkout or no `.ai-work/` in it, no issued request, every request recorded, an agent still
running, any exception: exit 0 with nothing printed. The body writes no file and starts no
process. The probe (`scripts/_step_loop_outstanding.py`) is imported only once a text test finds
an issued request its task's iteration ledger does not name, so a project with no step loop
pays one directory walk and a loop whose requests are all recorded imports nothing.

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
# The cap of the held message. The one command in it is never trimmed, so the bound holds only
# for a slug of at most 64 characters (the probe skips longer task names) and the request and
# agent ids the driver and the harness issue.
MAX_MESSAGE_BYTES = 600
RULE = (
    'A terminal marker plus the step record is final even under an "interim" notice, '
    "and `record` refuses a running agent, so run it now rather than wait."
)

WORK_DIR = ".ai-work"
WIP_DOC = "WIP.md"
# A step the driver issued: its `Attempts:` line names the request (`_loop_fields` owns the grammar).
ISSUED_REQUEST = re.compile(r"Attempts\W*:.*?\brequest=([A-Za-z0-9_-]+)")
LEDGER_FILE = "ITERATION_LEDGER.jsonl"
GIT_ENTRY = ".git"  # a directory in a checkout, a file in a linked worktree
SESSION_ID = re.compile(r"[A-Za-z0-9_-]+")

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
    """The `.ai-work/` of the checkout the working directory is in, else None.

    A walk-up of its own, not the orientation hook's: that one stops at the nearest `.ai-work/`,
    this one at the first ancestor holding a `.git` entry, the checkout `record` derives its root
    from. Crossing that boundary would read an outer checkout's loop and print a command `record`
    rejects from here.
    """
    here = Path.cwd()
    checkout = next((p for p in (here, *here.parents) if (p / GIT_ENTRY).exists()), None)
    if checkout is None or not (checkout / WORK_DIR).is_dir():
        return None
    return checkout / WORK_DIR


def _any_request_issued(work_root: Path) -> bool:
    """True when some task issued a request its iteration ledger does not name (a text test)."""
    try:
        tasks = [task for task in work_root.iterdir() if task.is_dir()]
    except OSError:
        return False
    return any(_has_unrecorded_request(task) for task in tasks)


def _has_unrecorded_request(task: Path) -> bool:
    """A request id on the task's `Attempts:` lines that its ledger's text does not contain; a
    missing or unreadable ledger contains none. A plain substring test, no JSON parse."""
    try:
        record = (task / WIP_DOC).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    issued = ISSUED_REQUEST.findall(record)
    if not issued:
        return False
    ledger = _ledger_text(task)
    return any(request not in ledger for request in issued)


def _ledger_text(task: Path) -> str:
    try:
        return (task / LEDGER_FILE).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


# --- Has its agent ended? -------------------------------------------------------------------


def _subagents_dir(stop: dict) -> Path | None:
    """Where the harness leaves this session's agent transcripts, beside the main transcript."""
    transcript, session = stop.get("transcript_path"), stop.get("session_id")
    if not (isinstance(transcript, str) and transcript and isinstance(session, str)):
        return None
    if not SESSION_ID.fullmatch(session):  # one plain path segment: never "", ".", ".." or a path
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
