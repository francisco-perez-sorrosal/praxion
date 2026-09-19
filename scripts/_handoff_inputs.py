"""The readers behind the handoff composer: one question each, no rendering.

Split out of `compose_handoff.py` so the composer holds the document and this
module holds the world. Each function answers exactly one question a handoff
needs answered -- what did this pipeline fork from, what artifacts exist, is a
test log warm, which files should the readiness gate measure -- and none of
them knows what the answer will look like on the page. The dependency runs one
way: the composer imports these, never the reverse.

The clock is deliberately *not* here. `compose_handoff` reads it and passes it
down (see `recent_log`), so the whole time-dependent surface stays in one
module and one monkeypatch seam.

Stdlib-only and loadable under the ambient interpreter, because the composer
above it is invoked by a slash command with a bare `python3`.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from _git_runner import git_output

VERIFIED_COMPLETE = "verified-complete"

# Tried in order only when `refs/remotes/origin/HEAD` is unset (no remote, or a
# clone that never populated it) -- both conventional default-branch names,
# since guessing one and stopping is how a fixture or a `master` repo silently
# loses its diff base.
DEFAULT_BRANCH_FALLBACKS = ("main", "master")

RAW_LOG_GLOB = "step-*.log"
RECENT_LOG_WINDOW_SECONDS = 60

# Where the step-owned half of the `dirty-step-files` scope came from. Every
# uncommitted non-bookkeeping path is in scope regardless; these name what leads
# the list, and the composer surfaces the two widened cases -- a gate that
# quietly changed its own scope is a gate a reader cannot calibrate.
SCOPE_CURRENT_STEP = "current-step-files"
SCOPE_UNFINISHED_STEPS = "unfinished-steps-files"
SCOPE_DIRTY_SOURCE = "every-dirty-source-path"

# Written by the machinery itself and dirty almost always; blocking on them
# would block every handoff, so they are excluded from the widest scope rule.
BOOKKEEPING_PREFIXES = (".ai-state/", ".ai-work/")
BOOKKEEPING_PATHS = frozenset({"coverage.xml"})


def resolve_base_ref(repo_root: Path) -> str | None:
    """The pipeline's fork point: `git merge-base HEAD <default-branch>`.

    Without it the reconciler diffs the working tree alone, so every *committed*
    step reads as a disagreement -- and a resuming window would be told that
    finished work contradicts the record, which is worse than being told
    nothing. Returns None when no candidate resolves; the composer then says so
    rather than presenting the over-report as fact.
    """
    for candidate in _base_ref_candidates(repo_root):
        base_ref = git_output(repo_root, "merge-base", "HEAD", candidate)
        if base_ref:
            return base_ref
    return None


def _base_ref_candidates(repo_root: Path) -> tuple[str, ...]:
    """Default-branch refs to fork from, best first.

    `refs/remotes/origin/HEAD` is the ref a clone populates from the remote's
    own HEAD -- a local read, never a fetch -- and is what the finalize chain
    resolves the default branch from too. The remote-tracking ref is tried
    before the bare branch name because pipeline worktrees branch from
    `origin/<default>`, which is therefore the more recent common ancestor.
    """
    ref = git_output(repo_root, "symbolic-ref", "refs/remotes/origin/HEAD")
    if ref:
        return (ref, ref.rsplit("/", 1)[-1])
    return tuple(
        candidate for name in DEFAULT_BRANCH_FALLBACKS for candidate in (f"origin/{name}", name)
    )


def artifact_names(task_dir: Path) -> tuple[str, ...] | None:
    """The task directory's Markdown artifacts, or None when it cannot be read."""
    try:
        return tuple(
            sorted(p.name for p in task_dir.iterdir() if p.is_file() and p.suffix == ".md")
        )
    except OSError:
        return None


def recent_log(task_dir: Path, now: float) -> tuple[str, int] | None:
    """The first raw step log touched inside the advisory window, with its age.

    `now` is passed in rather than read here so the composer owns the single
    clock read, and so this function is replayable against a fixed instant.
    """
    try:
        logs = sorted((task_dir / "logs").glob(RAW_LOG_GLOB))
    except OSError:
        return None
    for path in logs:
        try:
            age = now - path.stat().st_mtime
        except OSError:
            continue
        if age < RECENT_LOG_WINDOW_SECONDS:
            return path.name, int(age)
    return None


def step_file_scope(
    verdicts: Sequence[dict[str, Any]], dirty: Sequence[str]
) -> tuple[list[str], str]:
    """What `dirty-step-files` is measured against, and where its step half came from.

    **Any uncommitted path outside bookkeeping; step-owned paths named first.**
    The scope is a union, not a first-non-empty chain: the gate's own
    justification is that the next window inherits uncommitted work invisibly,
    and that is true of a dirty source file whichever step owns it -- including
    one owned by a step already verified-complete, which no step-scoped rule
    reaches. Step-owned paths lead the list so the refusal names what is most
    likely the operator's own work first; the remedy either way is a pathspec
    commit or `--force` with the override stamped into the artifact.

    Pipeline bookkeeping is excluded -- `.ai-state/`, `.ai-work/` and the
    coverage artifact are rewritten by the machinery itself and are dirty almost
    always, so blocking on them would block every handoff.
    """
    step_owned, rule = _step_owned_paths(verdicts)
    leading = set(step_owned)
    trailing = [
        path for path in dirty if not _is_pipeline_bookkeeping(path) and path not in leading
    ]
    return list(step_owned) + trailing, rule


def _step_owned_paths(verdicts: Sequence[dict[str, Any]]) -> tuple[list[str], str]:
    """The step-owned half of the scope, and which rule produced it.

    The current step's declared `Files:` when it declares any; otherwise the
    union across every unfinished step; otherwise nothing, which an integration
    checkpoint with no `Files:` legitimately yields.
    """
    current = declared_files(first_unfinished(verdicts))
    if current:
        return current, SCOPE_CURRENT_STEP
    union = sorted(
        {
            path
            for verdict in verdicts
            if verdict.get("verdict") != VERIFIED_COMPLETE
            for path in declared_files(verdict)
        }
    )
    if union:
        return union, SCOPE_UNFINISHED_STEPS
    return [], SCOPE_DIRTY_SOURCE


def first_unfinished(verdicts: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """The first step ground truth has not confirmed, or None."""
    return next((v for v in verdicts if v.get("verdict") != VERIFIED_COMPLETE), None)


def declared_files(verdict: dict[str, Any] | None) -> list[str]:
    """A step's declared `Files:`, as the reconciler split them by change state."""
    tier1 = (verdict or {}).get("tier1", {})
    return list(tier1.get("files_changed", [])) + list(tier1.get("files_unchanged", []))


def _is_pipeline_bookkeeping(path: str) -> bool:
    return path.startswith(BOOKKEEPING_PREFIXES) or path in BOOKKEEPING_PATHS
