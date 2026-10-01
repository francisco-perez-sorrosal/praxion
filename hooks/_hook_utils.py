"""Shared utilities for Praxion hooks.

Provides the per-project opt-out check (``is_disabled``) and the observability
kill-switch flag consumed by the capture/telemetry hooks (``capture_observations``,
``capture_session``, ``send_event``, ``measure_context_surface``,
``notify_bg_session_state``).

Also provides ``stated_task_slug`` -- the one reading of the ``Task slug:``
marker an orchestrator writes into a spawn prompt -- and
``record_gate_fire`` -- a thin forwarding wrapper for
commit-gate scripts recording their own pass/warn/block verdict. The row
shape, mode gating, and the append/rotate/lock machinery now live in
``hooks/_observation_log/writer.py``; this module keeps the same public
name and signature so no gate call site needs to change.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# -- Per-project opt-out flag --------------------------------------------------
# Read from Claude Code's per-project settings.json `env` block. Set to "1",
# "true", or "yes" (case-insensitive) to disable the observability hooks for
# the project. Absence of the flag preserves default behavior.

DISABLE_OBSERVABILITY = "PRAXION_DISABLE_OBSERVABILITY"

# Narrower: silences only send_event.py's chronograph POSTs while the local
# observations log keeps being written -- what an isolated sandbox needs when a
# hook under test reads that log.
DISABLE_EVENT_POSTING = "PRAXION_DISABLE_EVENT_POSTING"

_TRUTHY = frozenset({"1", "true", "yes"})


def is_disabled(flag_name: str) -> bool:
    """Return True if the named opt-out env var is set to a truthy value."""
    return os.environ.get(flag_name, "").strip().lower() in _TRUTHY


# `Task slug: <slug>` per the task-slug propagation contract. An opening
# backtick is optional because orchestrators write the slug both ways.
#
# The slug alphabet is letters, digits, `-` and `_` (the one extract_spec.py
# accepts). `.` is excluded on purpose: orchestrators write the label inside
# ordinary sentences, and a sentence-final period read into the slug names a
# path that can never exist. The slug ends at the first character outside the
# alphabet, so a closing backtick needs no pattern of its own. Gaps are
# horizontal whitespace only: a label left empty must not borrow the first word
# of the next line as its slug.
_TASK_SLUG_RE = re.compile(r"Task[ \t]+slug:[ \t]*`?([A-Za-z0-9][A-Za-z0-9_-]*)")


def stated_task_slug(text: object) -> str | None:
    """The slug the first ``Task slug:`` marker in ``text`` names, else None.

    Total over its input: anything that is not text reads as "no marker", so a
    caller handing it a raw payload field needs no type check of its own.
    """
    if not isinstance(text, str):
        return None
    match = _TASK_SLUG_RE.search(text)
    return match.group(1) if match else None


def record_gate_fire(
    hook: str,
    decision: str,
    reason: str = "",
    *,
    session_id: str = "",
    project_dir: Path | None = None,
) -> None:
    """Forward one commit-gate verdict to the observation-log writer.

    See ``hooks/_observation_log/writer.py::record_gate_fire`` for the row
    shape and mode gating -- this wrapper exists only so gate call sites
    (``from _hook_utils import record_gate_fire``) never need to change.
    The writer is imported *inside* this function, not at module level, so a
    bare importer of this module (``send_event.py``, which only needs
    ``is_disabled``) never eagerly loads the observation-log package.

    Fail-open, mirroring the writer: any exception here (including the
    import itself) is swallowed so a gate's own instrumentation can never
    affect the gate's exit code or its stdout/stderr output.
    """
    try:
        from _observation_log import writer

        writer.record_gate_fire(
            hook, decision, reason, session_id=session_id, project_dir=project_dir
        )
    except Exception:
        pass
