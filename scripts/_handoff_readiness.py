"""The handoff readiness gate: is this moment a boundary at all?

One responsibility, split out of `compose_handoff.py` so that composing a
document and deciding whether one may be composed do not share a file. The
composer imports `readiness` and the three states from here and re-exports
them; nothing here knows the handoff's wire format, and nothing in the composer
needs to know how a spawn is detected.

A handoff written over a half-finished tree is worse than no handoff: it
presents a false position with the authority of a generated document. So the
gate is a three-state sum type, not a boolean -- `Ready` and `Overridden` are
distinct because the next window's correct behaviour differs between them, and
an override is recorded in the artifact rather than only in the operator's
memory.

Three reasons, each mechanically decidable:

  ``spawn-in-flight``   an ``agent_start`` with no matching ``agent_stop``
                        among the composing session's rows.
  ``wal-unreadable``    no row carries a ``session_id``: the WAL is missing,
                        empty, or unparseable enough that the composing session
                        cannot be identified in it. The gate then cannot answer
                        the spawn question, so it **fails closed** rather than
                        reporting a ready it never verified. Mutually exclusive
                        with ``spawn-in-flight`` -- "cannot answer" and
                        "answered yes" are different states, and reporting both
                        would imply the gate had looked.
  ``dirty-step-files``  uncommitted changes in the current step's declared
                        files, which the next window would inherit invisibly.

A fourth condition was considered and dropped: a detached test suite's
done-file is not mechanically decidable (that convention fixes no path and no
schema), and a blocking check built on a heuristic teaches operators to reach
for ``--force`` by reflex, which would cost the three reasons that are sound.
The composer reports a recently-touched raw step log as an advisory instead.

Stdlib-only and loadable under the ambient interpreter, because the composer
above it is invoked by a slash command with a bare `python3`.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from _git_runner import git_output

# `_parse_jsonl` is imported rather than re-written: a second JSONL reader for
# the same WAL would be free to disagree with the reconciler's about partial
# lines, which is exactly the drift this gate exists to catch.
from reconcile_pipeline_state import _parse_jsonl

READY, BLOCKED, OVERRIDDEN = "ready", "blocked", "overridden"

SPAWN_IN_FLIGHT = "spawn-in-flight"
WAL_UNREADABLE = "wal-unreadable"
DIRTY_STEP_FILES = "dirty-step-files"
REMEDIES = {
    SPAWN_IN_FLIGHT: "wait for the running subagent to return, then re-run",
    WAL_UNREADABLE: (
        "check `.ai-state/observations.jsonl`; pass --force only if you know no subagent is running"
    ),
    DIRTY_STEP_FILES: "commit or revert the current step's declared files, then re-run",
}

WAL_AGENT_START = "agent_start"
WAL_AGENT_STOP = "agent_stop"

OBSERVATIONS_WAL = Path(".ai-state") / "observations.jsonl"


def readiness(
    wal_rows: Sequence[dict[str, Any]],
    git_status: Sequence[str],
    step_files: Sequence[str],
    force: bool,
) -> dict[str, Any]:
    """Decide whether a handoff may be written now. Pure.

    ``wal_rows`` is presumed already scoped to the composing session by the
    caller (see `session_wal_rows`); an ``agent_start`` with no matching
    ``agent_stop`` inside those rows is what fires ``spawn-in-flight``. Rows in
    which no session can be identified at all -- an empty list, or rows carrying
    no ``session_id`` -- fire ``wal-unreadable`` instead. ``git_status`` and
    ``step_files`` are plain path lists intersected by exact membership.

    Returns ``{"state": ready|blocked|overridden, "reasons": [...]}``. ``force``
    downgrades a block to an override; it can never invent a reason, so a clean
    tree stays ``ready`` whether or not it was passed.
    """
    reasons: list[str] = []
    if not _identifies_a_session(wal_rows):
        reasons.append(WAL_UNREADABLE)
    elif _unstopped_agent_ids(wal_rows):
        reasons.append(SPAWN_IN_FLIGHT)
    if set(git_status) & set(step_files):
        reasons.append(DIRTY_STEP_FILES)
    if not reasons:
        return {"state": READY, "reasons": []}
    return {"state": OVERRIDDEN if force else BLOCKED, "reasons": reasons}


def _identifies_a_session(wal_rows: Sequence[dict[str, Any]]) -> bool:
    """Can the gate tell whose spawns these are? Empty or session-less rows
    answer no, and "no" is the one answer that must not read as ready."""
    return any(row.get("session_id") for row in wal_rows)


def _unstopped_agent_ids(wal_rows: Sequence[dict[str, Any]]) -> set[str]:
    started = {r.get("agent_id") for r in wal_rows if r.get("event_type") == WAL_AGENT_START}
    stopped = {r.get("agent_id") for r in wal_rows if r.get("event_type") == WAL_AGENT_STOP}
    return {agent_id for agent_id in started - stopped if agent_id}


def session_wal_rows(repo_root: Path) -> list[dict[str, Any]]:
    """WAL rows belonging to the session composing this handoff.

    The gate asks about *this* session's spawns, and the WAL carries no marker
    for "current" -- so the newest row bearing a `session_id` names it. The
    harness appends live, so the tail is this session by construction. A
    missing or unparseable file yields no session-bearing row, which `readiness`
    reads as `wal-unreadable` and refuses on: telling "nothing is running" from
    "I could not look" is the gate's job, and this function must not disguise
    the second as the first.
    """
    rows = [row for row in _parse_jsonl(repo_root / OBSERVATIONS_WAL) if isinstance(row, dict)]
    session_id = next((r.get("session_id") for r in reversed(rows) if r.get("session_id")), None)
    if session_id is None:
        return []
    return [row for row in rows if row.get("session_id") == session_id]


def dirty_paths(repo_root: Path) -> list[str]:
    """Repo-relative paths `git status --porcelain` reports as not clean."""
    output = git_output(repo_root, "status", "--porcelain")
    if not output:
        return []
    paths = []
    for line in output.splitlines():
        entry = line[3:].strip()
        # A rename is reported as `old -> new`; only the destination exists now.
        paths.append(entry.split(" -> ")[-1].strip('"'))
    return [path for path in paths if path]
