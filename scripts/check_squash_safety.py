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

Under the sidecar-placement ruling (`ARCH_WT_RULING.md` § 8) the project
repository no longer owns `.ai-state/` when it is `SidecarOwned` -- the
squash signature this script exists to catch happens in the state mount at
merge-back, not in the project repo. `--target-mount <mount>` diagnoses
that mount directly; `--repo-root <project>` (no `--target-mount`) is a
no-op on a `SidecarOwned` project for the same reason.

Invocation:

    check_squash_safety.py                     # check HEAD automatically
    check_squash_safety.py --verbose            # DEBUG logging
    check_squash_safety.py --since REF          # compare against REF instead of HEAD~1
    check_squash_safety.py --dry-run            # accepted for interface symmetry; no-op
    check_squash_safety.py --target-mount PATH  # diagnose a state mount at merge-back

Exit code: 0 for every diagnostic outcome (including a skip and including
`--target-mount` naming a valid mount; diagnostics never abort a completed
merge). `--target-mount` naming something that is not a real state mount is
the one usage error this script reports non-zero (exit 1).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import _sidecar_mount
from _git_runner import git_output
from _repo_root import resolve_repo_root as _resolve_repo_root
from _script_cli import configure_logging
from _state_repo import SidecarOwned, resolve_placement

# -- Constants ----------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
AI_STATE_PREFIX = ".ai-state/"
MAX_LISTED_FILES = 20

logger = logging.getLogger("check_squash_safety")


def resolve_repo_root(cli_repo_root: str | None) -> Path:
    """Resolve the repo root via the shared resolver."""
    return _resolve_repo_root(cli_repo_root, script_dir=SCRIPT_DIR)


def apply_repo_root(root: Path) -> None:
    """Rebind the module-level REPO_ROOT (git `cwd`) to a resolved repo root."""
    global REPO_ROOT
    REPO_ROOT = root


def resolve_target_mount(path_str: str) -> Path:
    """Validate `--target-mount` and return the mount path.

    Mirrors `reconcile_ai_state.resolve_target_mount` -- refuses anything
    that is not itself `<checkout>/.praxion` for some checkout currently on
    a state branch, so a shadow symlink or an arbitrary directory is
    refused even when it resolves into a real mount's content.
    """
    mount = Path(path_str)
    if mount.name != _sidecar_mount.MOUNT_DIRNAME:
        raise ValueError(
            f"--target-mount must name a state mount "
            f"({_sidecar_mount.MOUNT_DIRNAME} directory); got {mount}"
        )
    state = _sidecar_mount.classify_mount(mount.parent, expected_common_dir=None)
    if not isinstance(state, _sidecar_mount.SidecarWorktree):
        raise ValueError(f"{mount} is not a state mount: {state!r}")
    return mount


# -- Git helpers --------------------------------------------------------------


def _git(*args: str) -> str | None:
    """Run `git <args>` and return stdout stripped; None on failure.

    Reads the module-level `REPO_ROOT` at call time so `apply_repo_root`'s
    rebind still takes effect.
    """
    return git_output(REPO_ROOT, *args, logger=logger)


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

    Uses `git diff --no-renames --diff-filter=D --name-only` which lists
    files removed in the target revision compared to the source.
    `--no-renames` is deliberate: two ADR files sharing the same frontmatter
    template are similar enough that git's default heuristic reports the
    deletion as a rename into the new file's path, which `--diff-filter=D`
    then never sees -- exactly the failure mode this diagnostic exists to
    catch (a specific path erased) regardless of what else may have been
    added under a different name in the same commit. An empty list means
    either no `.ai-state/` deletions occurred or the git query failed (in
    which case callers should not warn -- false positives from warnings are
    preferable, but spurious warnings on git failure are not).
    """
    output = _git(
        "diff",
        "--no-renames",
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
        "--repo-root",
        metavar="PATH",
        help=(
            "Repo root to diagnose. When omitted, resolved from "
            "`git rev-parse --show-toplevel` in the current directory. Required "
            "when the script runs from a symlinked plugin cache."
        ),
    )
    parser.add_argument(
        "--target-mount",
        metavar="PATH",
        default=None,
        help=(
            "Diagnose a sidecar state mount instead of --repo-root -- the "
            "merge-back case (ARCH_WT_RULING.md § 8). Must name a real "
            "state mount (<checkout>/.praxion, currently on a state branch)."
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
    """CLI entry point. Never raises for a diagnostic outcome; exits 0.

    Exception: `--target-mount` naming something that is not a real state
    mount is a caller/usage error, not a diagnostic verdict, and exits 1.
    """
    args = _parse_args(argv)
    configure_logging(args.verbose)

    if args.target_mount is not None:
        try:
            mount = resolve_target_mount(args.target_mount)
        except ValueError as exc:
            logger.error("check_squash_safety: %s", exc)
            sys.exit(1)
        apply_repo_root(mount)
    else:
        root = resolve_repo_root(args.repo_root)
        # The project repository does not own .ai-state/ when it is
        # SidecarOwned -- the diagnostic runs at merge-back, against the
        # mount (the --target-mount branch above), not here.
        placement = resolve_placement(root)
        if isinstance(placement, SidecarOwned):
            logger.info(
                "check_squash_safety: .ai-state/ check skipped -- the "
                "project repository does not own .ai-state/ (the "
                "diagnostic runs at merge-back, against the state mount)"
            )
            sys.exit(0)
        apply_repo_root(root)

    try:
        code = _run(args.since)
    except OSError as exc:
        logger.error("check_squash_safety: %s", exc)
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
