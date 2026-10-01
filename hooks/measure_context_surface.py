"""Lifecycle hook: measure the always-loaded context surface at session start.

Fires on SessionStart. Async hook (async: true) -- never blocks the session.
Exit 0 unconditionally.

Delegates the actual measurement to `scripts.measure_token_budget.measure()` --
the same function the commit-gate check calls -- so this hook can never report
a different figure than the gate on the same tree by construction. Previously
this hook carried its own file-glob + hardcoded divisor, which counted a wider
(and wrong) file set: 14 files / 41,216 tokens here versus the gate's 9 files /
24,542 tokens on an identical checkout. Importing `measure()` fixes the file
set by reuse, not by patching the divisor.

Future context audits become data-driven instead of one-off `wc` exercises:
- Which rules earn their >30% session-relevance threshold? (count appearances)
- Did B-tier extractions actually reduce per-session bytes? (compare over time)
- Is the budget drifting toward the 25k guardrail? (trend analysis)

Skipped whenever the observation log would not record its row: under
PRAXION_OBSERVATION_LOG=off, or the legacy PRAXION_DISABLE_OBSERVABILITY switch
(which resolves to off) -- before measuring, so no count_tokens call is made.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow hook tests to import shared utilities without forcing repo-relative
# layout on plugin-installed copies.
sys.path.insert(0, str(Path(__file__).resolve().parent))
# `measure_token_budget` lives in the sibling scripts/ tree -- same
# cross-directory import precedent as hooks/remind_calibration.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from _observation_log import registry, writer  # noqa: E402
from _observation_log.location import locate  # noqa: E402
from _observation_log.modes import resolve_mode  # noqa: E402
from _observation_log.registry import EventClass  # noqa: E402

# -- Observation emission -----------------------------------------------------


def _build_summary(tokens: int, bytes_: int, file_count: int, basis: str) -> str:
    """One-line human-readable summary for the observation row."""
    return (
        f"Always-loaded surface: {tokens:,} tokens "
        f"({bytes_:,} bytes) across {file_count} files [{basis}]"
    )


def main() -> None:
    # Asks the registry rather than testing for `off`: this hook's only output
    # is one CONTEXT_SURFACE row, so it measures exactly when that row is kept.
    mode, _source = resolve_mode(os.environ)
    if not registry.records(EventClass.CONTEXT_SURFACE, mode):
        return

    try:
        # Imported here, not at module scope: an import failure (broken
        # sys.path, a plugin-cache layout where scripts/ isn't a sibling, a
        # bad import inside measure_token_budget.py itself) must be caught by
        # this hook's own fail-open contract ("Exit 0 unconditionally.",
        # module docstring) -- a module-level import raises before the
        # __main__ guard's `except Exception: pass` is ever reached.
        from measure_token_budget import measure
    except Exception as exc:  # noqa: BLE001 - fail-open on any import failure
        print(f"measure_context_surface: import failed -- {exc}", file=sys.stderr)
        return

    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        return

    # Only fire on SessionStart — the surface doesn't change within a session.
    if payload.get("hook_event_name", "") != "SessionStart":
        return

    location = locate(payload.get("cwd"))
    if location is None:
        return  # graceful degradation: no project serves this directory

    report = measure(location.project_dir, api_key=os.environ.get("ANTHROPIC_API_KEY"))

    if report["bytes"] == 0:
        return  # nothing measurable — skip silently

    session_id = payload.get("session_id", "")

    observation = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "agent_type": payload.get("agent_type", "main"),
        "agent_id": payload.get("agent_id", "") or session_id,
        "project": location.project,
        "event_type": "context_surface_measurement",
        "tool_name": None,
        "summary": _build_summary(
            report["tokens"], report["bytes"], len(report["files"]), report["basis"]
        ),
        "file_paths": report["files"],
        "outcome": None,
        "classification": None,
    }

    writer.record(location.state_dir, EventClass.CONTEXT_SURFACE, observation)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 — hooks must never escalate to the runtime
        pass
