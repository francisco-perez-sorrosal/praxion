"""Lifecycle hook: measure the always-loaded context surface at session start.

Fires on SessionStart. Async hook (async: true) -- never blocks the session.
Exit 0 unconditionally.

For each session, compute the byte size and approximate token count of the
always-loaded context surface (CLAUDE.md files + rules without `paths:`
frontmatter) and emit one observation to `.ai-state/observations.jsonl`.

Future context audits become data-driven instead of one-off `wc` exercises:
- Which rules earn their >30% session-relevance threshold? (count appearances)
- Did B-tier extractions actually reduce per-session bytes? (compare over time)
- Is the budget drifting toward the 25k guardrail? (trend analysis)

Disabled by PRAXION_DISABLE_OBSERVABILITY (shared with capture_session).
"""

from __future__ import annotations

import fcntl
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

# Allow hook tests to import shared utilities without forcing repo-relative
# layout on plugin-installed copies.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _hook_utils import DISABLE_OBSERVABILITY, is_disabled  # noqa: E402

# -- Constants ----------------------------------------------------------------

# Conservative bytes-per-token estimate for Markdown — matches the figure
# documented in `rules/CLAUDE.md` (Token Budget section). Real usage with
# Claude's tokenizer averages ~4.0 bytes/token; we use 3.6 to bias toward
# over-reporting rather than under-reporting.
BYTES_PER_TOKEN = 3.6

# Frontmatter `paths:` key signals a path-scoped (NOT always-loaded) rule.
# Match either inline list (`paths: [a, b]`) or block style (`paths:` followed
# by indented `- item` lines).
_PATHS_KEY = re.compile(r"^paths:\s*", re.MULTILINE)
_FRONTMATTER_DELIMITER = "---"

# Where rules live once installed. The plugin install symlinks the repo's
# rules/ tree into ~/.claude/rules/, so this path works for both Praxion-the-
# repo (where the symlink points back to ./rules/) and any onboarded project.
_GLOBAL_RULES_DIR = Path.home() / ".claude" / "rules"
_GLOBAL_CLAUDE_MD = Path.home() / ".claude" / "CLAUDE.md"


# -- Frontmatter scanning -----------------------------------------------------


def _has_paths_frontmatter(content: str) -> bool:
    """Return True if the file's YAML frontmatter declares a `paths:` key.

    Path-scoped rules load only when matching files are accessed, so they do
    not contribute to the always-loaded surface.
    """
    lines = content.split("\n", 32)
    if not lines or lines[0].strip() != _FRONTMATTER_DELIMITER:
        return False
    # Walk frontmatter lines until the closing delimiter.
    for line in lines[1:]:
        if line.strip() == _FRONTMATTER_DELIMITER:
            return False
        if _PATHS_KEY.match(line):
            return True
    return False


def _is_rule_README(path: Path) -> bool:
    """README.md files in the rules directory are documentation, not rules.

    They are not symlinked into ~/.claude/rules/ by the installer, so they
    do not count toward the always-loaded surface.
    """
    return path.name == "README.md"


# -- Surface measurement ------------------------------------------------------


def _collect_always_loaded(
    project_claude_md: Path,
    global_claude_md: Path,
    rules_dir: Path,
) -> tuple[int, list[dict]]:
    """Return (total_bytes, [file_record, ...]) for every always-loaded file.

    file_record schema: {"path": str, "bytes": int, "type": "claude_md"|"rule"}.
    Missing files are skipped silently — graceful degradation across hosts
    where the global config or rules tree may be absent.
    """
    records: list[dict] = []
    total = 0

    for path, kind in (
        (project_claude_md, "claude_md_project"),
        (global_claude_md, "claude_md_global"),
    ):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        records.append({"path": str(path), "bytes": size, "type": kind})
        total += size

    if rules_dir.is_dir():
        for path in sorted(rules_dir.rglob("*.md")):
            if not path.is_file():
                continue
            if _is_rule_README(path):
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if _has_paths_frontmatter(content):
                continue
            size = len(content.encode("utf-8"))
            records.append({"path": str(path), "bytes": size, "type": "rule"})
            total += size

    return total, records


def _build_summary(total_bytes: int, file_count: int) -> str:
    """One-line human-readable summary for the observation row."""
    tokens = int(total_bytes / BYTES_PER_TOKEN)
    return (
        f"Always-loaded surface: {tokens:,} tokens "
        f"({total_bytes:,} bytes) across {file_count} files"
    )


# -- Observation emission -----------------------------------------------------


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

    project_claude_md = Path(cwd) / "CLAUDE.md"
    total_bytes, records = _collect_always_loaded(
        project_claude_md, _GLOBAL_CLAUDE_MD, _GLOBAL_RULES_DIR
    )

    if total_bytes == 0:
        return  # nothing measurable — skip silently

    file_paths = [r["path"] for r in records]
    session_id = payload.get("session_id", "")

    observation = {
        "timestamp": datetime.now(UTC).isoformat(),
        "session_id": session_id,
        "agent_type": payload.get("agent_type", "main"),
        "agent_id": payload.get("agent_id", "") or session_id,
        "project": Path(cwd).name,
        "event_type": "context_surface_measurement",
        "tool_name": None,
        "summary": _build_summary(total_bytes, len(records)),
        "file_paths": file_paths,
        "outcome": None,
        "classification": None,
    }

    _append_observation(ai_state_dir / "observations.jsonl", observation)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 — hooks must never escalate to the runtime
        pass
