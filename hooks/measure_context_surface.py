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

Disabled by PRAXION_DISABLE_OBSERVABILITY (shared with capture_session).
"""

from __future__ import annotations

import fcntl
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

from _hook_utils import DISABLE_OBSERVABILITY, is_disabled  # noqa: E402
from measure_token_budget import measure  # noqa: E402

# -- Observation emission -----------------------------------------------------


def _build_summary(tokens: int, bytes_: int, file_count: int, basis: str) -> str:
    """One-line human-readable summary for the observation row."""
    return (
        f"Always-loaded surface: {tokens:,} tokens "
        f"({bytes_:,} bytes) across {file_count} files [{basis}]"
    )


def _append_observation(obs_path: Path, observation: dict) -> None:
    """Append a single observation to JSONL with exclusive locking.

    Mirrors the locking pattern in `capture_session.py` so concurrent hook
    invocations across worktrees serialize cleanly through the same lock file.
    """
    obs_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = obs_path.parent / "observations.lock"
    lock_path.touch(exist_ok=True)

    with open(lock_path, "w") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            with open(obs_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(observation, separators=(",", ":")) + "\n")
                f.flush()
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


def main() -> None:
    if is_disabled(DISABLE_OBSERVABILITY):
        return

    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        return

    # Only fire on SessionStart — the surface doesn't change within a session.
    if payload.get("hook_event_name", "") != "SessionStart":
        return

    cwd = payload.get("cwd", ".")
    ai_state_dir = Path(cwd) / ".ai-state"
    if not ai_state_dir.exists():
        return  # graceful degradation: no state dir means no project to measure

    report = measure(Path(cwd), api_key=os.environ.get("ANTHROPIC_API_KEY"))

    if report["bytes"] == 0:
        return  # nothing measurable — skip silently

    session_id = payload.get("session_id", "")

    observation = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "agent_type": payload.get("agent_type", "main"),
        "agent_id": payload.get("agent_id", "") or session_id,
        "project": Path(cwd).name,
        "event_type": "context_surface_measurement",
        "tool_name": None,
        "summary": _build_summary(
            report["tokens"], report["bytes"], len(report["files"]), report["basis"]
        ),
        "file_paths": report["files"],
        "outcome": None,
        "classification": None,
    }

    _append_observation(ai_state_dir / "observations.jsonl", observation)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 — hooks must never escalate to the runtime
        pass
