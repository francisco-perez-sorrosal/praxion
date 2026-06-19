#!/usr/bin/env python3
"""Reconcile .ai-state/ artifacts after merging a worktree branch.

Handles two reconciliation tasks:
1. observations.jsonl — concat, dedup, sort by timestamp
2. decisions/ — renumber duplicate ADR sequence numbers, regenerate index

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

from _repo_root import is_plugin_cache_path
from _repo_root import resolve_repo_root as _resolve_repo_root

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
AI_STATE = REPO_ROOT / ".ai-state"
DECISIONS_DIR = AI_STATE / "decisions"
OBSERVATIONS_PATH = AI_STATE / "observations.jsonl"

ADR_FILENAME_PATTERN = re.compile(r"^(\d{3})-.+\.md$")


def resolve_repo_root(cli_repo_root: str | None) -> Path:
    """Resolve the repo root via the shared resolver, warning on fallback."""

    def _warn_fallback(fallback: Path) -> None:
        warn(
            "reconcile_ai_state: could not resolve repo root from --repo-root "
            f"or git; falling back to script-relative {fallback}"
        )

    return _resolve_repo_root(cli_repo_root, script_dir=SCRIPT_DIR, on_fallback=_warn_fallback)


def apply_repo_root(root: Path) -> None:
    """Rebind the module-level path constants to a resolved repo root."""
    global REPO_ROOT, AI_STATE, DECISIONS_DIR, OBSERVATIONS_PATH
    REPO_ROOT = root
    AI_STATE = root / ".ai-state"
    DECISIONS_DIR = AI_STATE / "decisions"
    OBSERVATIONS_PATH = AI_STATE / "observations.jsonl"


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


def has_drafts_directory_changed_in_merge() -> bool:
    """Return True if the most recent commit touched a draft ADR file.

    Used by `reconcile_adr_numbers()` to decide whether to defer to
    `scripts/finalize_adrs.py`. Only counts `.md` files under
    `.ai-state/decisions/drafts/` — runtime artifacts (locks, backups,
    `CLAUDE.md` pointers) must not trigger the deferral because they
    carry no ADR semantics. On git errors we fail safe to False so the
    legacy path still runs rather than skipping based on unreliable signal.
    """
    result = git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
    if result.returncode != 0:
        return False
    for line in result.stdout.splitlines():
        if (
            line.startswith(".ai-state/decisions/drafts/")
            and line.endswith(".md")
            and not line.endswith("/CLAUDE.md")
        ):
            return True
    return False


def reconcile_adr_numbers() -> bool:
    """Detect and fix duplicate ADR sequence numbers after merge.

    When two worktrees independently create ADRs with the same NNN prefix,
    renumber the one with the later date and update its id field.

    Returns True if any renumbering was done.
    """
    # DEPRECATED: retained for one release as a defensive safety net
    # flagged during the concurrency-collab pipeline. The primary ADR-finalize
    # path is scripts/finalize_adrs.py, invoked by the post-merge hook
    # after this reconcile pass. When drafts are present, that path owns
    # ADR lifecycle management and this legacy renumber code path is
    # skipped via has_drafts_directory_changed_in_merge() below. Remove
    # this function in the next release once finalize has proven stable.
    if has_drafts_directory_changed_in_merge():
        info("reconcile_adr_numbers: drafts present; deferring to finalize_adrs.py")
        return False

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
                [sys.executable, str(regen_script), "--repo-root", str(REPO_ROOT)],
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
    for driver in ["observations-jsonl"]:
        result = git("config", f"merge.{driver}.driver")
        if result.returncode != 0:
            warn(
                f"Merge driver '{driver}' not registered in git config. "
                "Run install.sh or see .gitattributes for setup instructions"
            )


def main() -> None:
    # --post-merge: only ADR renumbering + index regen (observations
    # already handled by git merge drivers during the merge itself)
    post_merge_only = "--post-merge" in sys.argv

    # --repo-root <path>: resolve the consumer repo explicitly. Falls back to
    # git-root (cwd) when absent, so symlinked plugin hooks act on the consumer
    # rather than the plugin cache.
    repo_root_arg: str | None = None
    if "--repo-root" in sys.argv:
        idx = sys.argv.index("--repo-root")
        if idx + 1 < len(sys.argv):
            repo_root_arg = sys.argv[idx + 1]
    root = resolve_repo_root(repo_root_arg)
    if is_plugin_cache_path(root):
        fail(
            f"refusing to reconcile against a plugin-cache path: {root}; "
            "pass --repo-root or run from the consumer worktree"
        )
        sys.exit(1)
    apply_repo_root(root)

    print("\n  .ai-state/ reconciliation\n")

    _check_merge_drivers()

    any_changes = False

    if not post_merge_only:
        # 1. observations.jsonl
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

    # 2+3. ADR renumbering + index regeneration (always runs)
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
