#!/usr/bin/env python3
"""Reconcile .ai-state/ artifacts after merging a worktree branch.

Handles three reconciliation tasks:
1. memory.json — semantic JSON merge (union of entries, updated_at wins)
2. observations.jsonl — concat, dedup, sort by timestamp
3. decisions/ — renumber duplicate ADR sequence numbers, regenerate index

Designed to run AFTER `git merge` to resolve conflicts or validate
auto-merged results. Can also run standalone to reconcile two copies.

Usage:
    python scripts/reconcile_ai_state.py                  # auto-detect from git merge state
    python scripts/reconcile_ai_state.py --theirs <path>  # explicit worktree .ai-state/ path

Exit codes:
    0 — reconciliation succeeded (or nothing to do)
    1 — reconciliation failed (manual intervention needed)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
AI_STATE = REPO_ROOT / ".ai-state"
DECISIONS_DIR = AI_STATE / "decisions"
MEMORY_PATH = AI_STATE / "memory.json"
OBSERVATIONS_PATH = AI_STATE / "observations.jsonl"

ADR_FILENAME_PATTERN = re.compile(r"^(\d{3})-.+\.md$")


# -- Helpers ------------------------------------------------------------------


def info(msg: str) -> None:
    print(f"  ✓ {msg}")


def warn(msg: str) -> None:
    print(f"  ⚠ {msg}")


def fail(msg: str) -> None:
    print(f"  ✗ {msg}", file=sys.stderr)


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def is_conflicted(path: Path) -> bool:
    """Check if a file has unresolved merge conflict markers."""
    if not path.exists():
        return False
    content = path.read_text(encoding="utf-8")
    return "<<<<<<<" in content and ">>>>>>>" in content


def extract_ours_theirs_from_git(rel_path: str) -> tuple[str | None, str | None]:
    """Extract ours and theirs versions of a conflicted file from git.

    Stage 2 = ours (target branch), Stage 3 = theirs (merging branch).
    """
    ours_result = git("show", f":2:{rel_path}")
    theirs_result = git("show", f":3:{rel_path}")

    ours = ours_result.stdout if ours_result.returncode == 0 else None
    theirs = theirs_result.stdout if theirs_result.returncode == 0 else None
    return ours, theirs


# -- memory.json reconciliation -----------------------------------------------


def reconcile_memory(ours_text: str, theirs_text: str) -> dict:
    """Merge two memory.json files semantically.

    Strategy:
    - schema_version: keep the higher version
    - session_count: sum both (each session is unique)
    - memories: union of all entries per category; for duplicate keys,
      the entry with the later updated_at timestamp wins
    """
    ours = json.loads(ours_text)
    theirs = json.loads(theirs_text)

    # Schema version: keep higher
    ours_ver = ours.get("schema_version", "1.0")
    theirs_ver = theirs.get("schema_version", "1.0")
    merged_ver = max(ours_ver, theirs_ver)

    # Session count: sum (each worktree runs independent sessions)
    merged_sessions = ours.get("session_count", 0) + theirs.get("session_count", 0)

    # Memories: union per category, updated_at wins for duplicates
    ours_mem = ours.get("memories", {})
    theirs_mem = theirs.get("memories", {})
    all_categories = set(ours_mem.keys()) | set(theirs_mem.keys())

    merged_memories: dict[str, dict] = {}
    stats = {"kept_ours": 0, "kept_theirs": 0, "unique_ours": 0, "unique_theirs": 0}

    for category in sorted(all_categories):
        ours_entries = ours_mem.get(category, {})
        theirs_entries = theirs_mem.get(category, {})
        merged_entries: dict[str, dict] = {}

        all_keys = set(ours_entries.keys()) | set(theirs_entries.keys())
        for key in sorted(all_keys):
            in_ours = key in ours_entries
            in_theirs = key in theirs_entries

            if in_ours and not in_theirs:
                merged_entries[key] = ours_entries[key]
                stats["unique_ours"] += 1
            elif in_theirs and not in_ours:
                merged_entries[key] = theirs_entries[key]
                stats["unique_theirs"] += 1
            else:
                # Both have it — updated_at wins
                ours_updated = ours_entries[key].get("updated_at", "")
                theirs_updated = theirs_entries[key].get("updated_at", "")
                if theirs_updated > ours_updated:
                    merged_entries[key] = theirs_entries[key]
                    stats["kept_theirs"] += 1
                else:
                    merged_entries[key] = ours_entries[key]
                    stats["kept_ours"] += 1

        if merged_entries:
            merged_memories[category] = merged_entries

    total = sum(len(entries) for entries in merged_memories.values())
    info(
        f"memory.json: {total} entries merged "
        f"(ours: {stats['unique_ours']} unique + {stats['kept_ours']} wins, "
        f"theirs: {stats['unique_theirs']} unique + {stats['kept_theirs']} wins)"
    )

    return {
        "schema_version": merged_ver,
        "session_count": merged_sessions,
        "memories": merged_memories,
    }


# -- observations.jsonl reconciliation ----------------------------------------


def reconcile_observations(ours_text: str, theirs_text: str) -> str:
    """Merge two observations.jsonl files.

    Strategy: concat all lines, dedup by composite key, sort by timestamp.
    """
    seen: dict[str, dict] = {}  # dedup key -> parsed line

    for text in [ours_text, theirs_text]:
        for line in text.strip().splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Composite dedup key: timestamp + session_id + event_type + tool_name
            dedup_key = (
                f"{obj.get('timestamp', '')}"
                f"|{obj.get('session_id', '')}"
                f"|{obj.get('event_type', '')}"
                f"|{obj.get('tool_name', '')}"
            )
            # Keep the first seen (they should be identical for same key)
            if dedup_key not in seen:
                seen[dedup_key] = obj

    # Sort by timestamp
    sorted_obs = sorted(seen.values(), key=lambda o: o.get("timestamp", ""))

    info(f"observations.jsonl: {len(sorted_obs)} entries after dedup")

    lines = [json.dumps(obj, ensure_ascii=False) for obj in sorted_obs]
    return "\n".join(lines) + "\n" if lines else ""


# -- ADR number reconciliation ------------------------------------------------


def reconcile_adr_numbers() -> bool:
    """Detect and fix duplicate ADR sequence numbers after merge.

    When two worktrees independently create ADRs with the same NNN prefix,
    renumber the one with the later date and update its id field.

    Returns True if any renumbering was done.
    """
    if not DECISIONS_DIR.is_dir():
        return False

    # Collect all ADR files grouped by sequence number
    by_number: dict[int, list[Path]] = {}
    for path in sorted(DECISIONS_DIR.iterdir()):
        match = ADR_FILENAME_PATTERN.match(path.name)
        if not match:
            continue
        num = int(match.group(1))
        by_number.setdefault(num, []).append(path)

    # Find duplicates
    duplicates = {num: paths for num, paths in by_number.items() if len(paths) > 1}
    if not duplicates:
        return False

    # Find the next available number
    max_num = max(by_number.keys()) if by_number else 0
    next_num = max_num + 1

    changed = False
    for num, paths in sorted(duplicates.items()):
        # Keep the first file (alphabetically), renumber the rest
        for path in paths[1:]:
            old_name = path.name
            slug = old_name[4:]  # strip "NNN-" prefix
            new_name = f"{next_num:03d}-{slug}"
            new_path = path.parent / new_name
            new_id = f"dec-{next_num:03d}"
            old_id = f"dec-{num:03d}"

            # Update the id field in frontmatter
            content = path.read_text(encoding="utf-8")
            content = content.replace(f"id: {old_id}", f"id: {new_id}", 1)
            new_path.write_text(content, encoding="utf-8")

            # Remove old file
            path.unlink()

            info(f"ADR renumbered: {old_name} → {new_name} ({old_id} → {new_id})")
            next_num += 1
            changed = True

    return changed


# -- Orchestrator -------------------------------------------------------------


def reconcile_file(
    file_path: Path,
    rel_path: str,
    reconcile_fn,
    write_fn=None,
) -> bool:
    """Reconcile a single file — handles both conflicted and clean-merge cases.

    Returns True if the file was modified.
    """
    if not file_path.exists():
        return False

    if is_conflicted(file_path):
        # Extract ours/theirs from git stages
        ours, theirs = extract_ours_theirs_from_git(rel_path)
        if ours is None or theirs is None:
            warn(f"{rel_path}: conflicted but cannot extract ours/theirs from git")
            return False

        merged = reconcile_fn(ours, theirs)

        if write_fn:
            write_fn(file_path, merged)
        else:
            # Default: write JSON
            file_path.write_text(
                json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

        # Mark as resolved
        git("add", rel_path)
        info(f"{rel_path}: conflict resolved")
        return True

    # Not conflicted — validate the auto-merged result
    if file_path.suffix == ".json":
        try:
            json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            warn(f"{rel_path}: auto-merged JSON is invalid — needs manual fix")
            return False

    return False


def write_text_file(path: Path, content: str) -> None:
    """Write plain text content to a file."""
    path.write_text(content, encoding="utf-8")


def _reconcile_adr_and_index() -> bool:
    """Run ADR renumbering + index regeneration. Returns True if changes made."""
    any_changes = False

    if reconcile_adr_numbers():
        any_changes = True
    elif DECISIONS_DIR.is_dir():
        info("ADR numbers: no duplicates")

    if DECISIONS_DIR.is_dir():
        regen_script = SCRIPT_DIR / "regenerate_adr_index.py"
        if regen_script.exists():
            result = subprocess.run(
                [sys.executable, str(regen_script)],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            if result.returncode == 0:
                info("DECISIONS_INDEX.md: regenerated")
                git("add", ".ai-state/decisions/DECISIONS_INDEX.md")
                any_changes = True
            else:
                warn(f"DECISIONS_INDEX.md regeneration failed: {result.stderr.strip()}")

    return any_changes


def _check_merge_drivers() -> None:
    """Warn if custom merge drivers are not registered in git config."""
    for driver in ["memory-json", "observations-jsonl"]:
        result = git("config", f"merge.{driver}.driver")
        if result.returncode != 0:
            warn(
                f"Merge driver '{driver}' not registered in git config. "
                "Run install.sh or see .gitattributes for setup instructions"
            )


def main() -> None:
    # --post-merge: only ADR renumbering + index regen (memory/observations
    # already handled by git merge drivers during the merge itself)
    post_merge_only = "--post-merge" in sys.argv

    print("\n  .ai-state/ reconciliation\n")

    _check_merge_drivers()

    any_changes = False

    if not post_merge_only:
        # 1. memory.json
        if MEMORY_PATH.exists():
            changed = reconcile_file(
                MEMORY_PATH,
                ".ai-state/memory.json",
                reconcile_memory,
            )
            if changed:
                any_changes = True
            elif not is_conflicted(MEMORY_PATH):
                info("memory.json: no conflicts")

        # 2. observations.jsonl
        if OBSERVATIONS_PATH.exists():
            changed = reconcile_file(
                OBSERVATIONS_PATH,
                ".ai-state/observations.jsonl",
                reconcile_observations,
                write_fn=write_text_file,
            )
            if changed:
                any_changes = True
            elif not is_conflicted(OBSERVATIONS_PATH):
                info("observations.jsonl: no conflicts")

    # 3+4. ADR renumbering + index regeneration (always runs)
    if _reconcile_adr_and_index():
        any_changes = True

    if any_changes:
        print("\n  ✓ Reconciliation complete — review staged changes\n")
    else:
        print("\n  ✓ Nothing to reconcile\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        fail(f"Reconciliation failed: {e}")
        sys.exit(1)
