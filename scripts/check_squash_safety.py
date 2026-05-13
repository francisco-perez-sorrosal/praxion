#!/usr/bin/env python3
"""Diagnose whether the just-completed merge erased `.ai-state/` via squash.

Invoked by `scripts/git-finalize-hook.sh` (post-merge entry, via `finalize_chain.sh`) after a merge
completes. Detects the case where HEAD is a single-parent commit whose tree
has `.ai-state/` files present in the parent but removed at HEAD -- the
signature of a `git merge --squash` or a fast-forward that dropped state.

**Detection strategy**: tree-diff heuristic, not `git reflog` introspection.

We compare the tree at HEAD against its sole parent (HEAD~1). If HEAD has
only one parent AND any file under `.ai-state/` was deleted relative to
HEAD~1, we emit a loud warning with recovery steps. Multi-parent commits
(regular merges) are always safe. No reflog parsing is required, and the
check works uniformly across git 2.x without depending on reflog retention.

Trade-off accepted: a plain deletion commit that removes a `.ai-state/`
file deliberately will also trigger the warning. That is a false positive,
not a false negative -- users can inspect the diagnostic message and ignore
it. Missing a real squash erasure would be worse.

Invocation:

    check_squash_safety.py              # check HEAD automatically
    check_squash_safety.py --verbose    # DEBUG logging
    check_squash_safety.py --since REF  # compare against REF instead of HEAD~1
    check_squash_safety.py --dry-run    # accepted for interface symmetry; no-op

Exit code: always 0 (diagnostic; cannot abort a completed merge).
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

# -- Constants ----------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
AI_STATE_PREFIX = ".ai-state/"
MAX_LISTED_FILES = 20

logger = logging.getLogger("check_squash_safety")


# -- Git helpers --------------------------------------------------------------


def _git(*args: str) -> str | None:
    """Run `git <args>` and return stdout stripped; None on failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        logger.debug(
            "git %s failed (rc=%s): %s",
            " ".join(args),
            result.returncode,
            result.stderr.strip(),
        )
        return None
    return result.stdout.strip() or None


def _is_git_worktree() -> bool:
    return _git("rev-parse", "--is-inside-work-tree") == "true"


# -- Parent-count probe -------------------------------------------------------


def is_single_parent_commit(ref: str = "HEAD") -> bool:
    """Return True when `ref` has exactly one parent.

    Single-parent commits include squash merges, fast-forwards, and plain
    commits. Multi-parent commits are regular (non-squash) merges and are
    always safe for `.ai-state/`.

    Returns False on git failure (conservative: callers treat unknown
    parentage as non-actionable).
    """
    output = _git("rev-list", "--parents", "-n", "1", ref)
    if output is None:
        return False
    tokens = output.split()
    # tokens[0] is the commit hash itself; the remainder are parents.
    parent_count = len(tokens) - 1
    return parent_count == 1


# -- Tree-diff detection ------------------------------------------------------


def detect_potentially_erased_files(parent_sha: str, head_sha: str) -> list[str]:
    """Return `.ai-state/` paths deleted in `head_sha` relative to `parent_sha`.

    Uses `git diff --diff-filter=D --name-only` which lists files removed in
    the target revision compared to the source. An empty list means either
    no `.ai-state/` deletions occurred or the git query failed (in which
    case callers should not warn -- false positives from warnings are
    preferable, but spurious warnings on git failure are not).
    """
    output = _git(
        "diff",
        "--diff-filter=D",
        "--name-only",
        parent_sha,
        head_sha,
        "--",
        AI_STATE_PREFIX,
    )
    if output is None:
        return []
    return sorted(line for line in output.splitlines() if line.strip())


def _resolve_parent(since: str | None) -> str | None:
    """Resolve the comparison parent: either `--since <ref>` or HEAD~1.

    Returns None when HEAD has no parents (root commit) or git fails.
    """
    if since is not None:
        sha = _git("rev-parse", since)
        return sha

    # Default: derive parent from HEAD's parent list.
    output = _git("rev-list", "--parents", "-n", "1", "HEAD")
    if output is None:
        return None
    tokens = output.split()
    if len(tokens) < 2:
        # Root commit; no parent to compare against.
        return None
    return tokens[1]


# -- Warning emission ---------------------------------------------------------


def _format_warning(erased: list[str]) -> str:
    """Format the multi-line warning block for human operators."""
    total = len(erased)
    listed = erased[:MAX_LISTED_FILES]
    overflow = total - len(listed)

    lines: list[str] = [
        "",
        "=" * 72,
        "WARNING: Squash-merge detected; .ai-state/ history may have been erased.",
        "=" * 72,
        f"Files deleted under .ai-state/: {total}",
        "",
    ]
    lines.extend(f"  - {path}" for path in listed)
    if overflow > 0:
        lines.append(f"  ... and {overflow} more (showing first {MAX_LISTED_FILES})")
    lines.extend(
        [
            "",
            "Recovery:",
            "  1. Run `git reflog` to locate the pre-squash HEAD of the source branch.",
            "  2. Cherry-pick the .ai-state/ changes back:",
            "       git cherry-pick <pre-squash-sha> -- .ai-state/",
            "     or restore individual files:",
            "       git checkout <pre-squash-sha> -- <path>",
            "",
            "Prevention:",
            "  Prefer regular merge (no --squash) or rebase-and-merge for branches",
            "  that touch .ai-state/. See rules/swe/vcs/pr-conventions.md.",
            "=" * 72,
            "",
        ]
    )
    return "\n".join(lines)


def emit_warning(erased: list[str]) -> None:
    """Print the warning block to stderr (visible to post-merge hook output)."""
    print(_format_warning(erased), file=sys.stderr)


# -- Orchestration ------------------------------------------------------------


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="check_squash_safety",
        description=(
            "Post-merge diagnostic: warn when a squash-merge or fast-forward "
            "erased .ai-state/ state. Exit 0 regardless."
        ),
    )
    parser.add_argument(
        "--since",
        metavar="REF",
        default=None,
        help=(
            "Compare HEAD against REF instead of auto-detecting HEAD~1. "
            "Useful for tests and manual post-hoc inspection."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Accepted for interface symmetry with finalize_adrs.py. This "
            "script is diagnostic-only; --dry-run has no distinct effect."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    return parser.parse_args(argv)


def _run(since: str | None) -> int:
    """Core detection workflow. Always returns 0 (non-blocking diagnostic)."""
    if not _is_git_worktree():
        logger.debug("not inside a git worktree; skipping squash-safety check")
        return 0

    # Multi-parent commits are regular merges -- always safe.
    if not is_single_parent_commit("HEAD"):
        logger.info("check_squash_safety: merge is regular (multi-parent); no concern")
        return 0

    parent_sha = _resolve_parent(since)
    if parent_sha is None:
        logger.debug("no parent to compare against (root commit or git failure)")
        return 0

    erased = detect_potentially_erased_files(parent_sha, "HEAD")
    if not erased:
        logger.info("check_squash_safety: no .ai-state/ erasure detected")
        return 0

    emit_warning(erased)
    return 0


def main(argv: list[str] | None = None) -> None:
    """CLI entry point. Never raises; logs errors and exits 0."""
    args = _parse_args(argv)
    _configure_logging(args.verbose)
    try:
        code = _run(args.since)
    except OSError as exc:
        logger.error("check_squash_safety: %s", exc)
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
