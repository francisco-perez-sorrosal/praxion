"""Git plumbing for the sidecar modules -- queries and parsers, no policy.

**What belongs here.** Anything that is true of *git*, independent of what
Praxion does with the answer: ref resolution and ancestry, worktree-list and
`.git`-pointer parsing, branch config get/set, the write-free patch-identity probe
that detects a squash merge, the identity fallback a merge commit needs. Every
function names its repository explicitly (first argument) and answers with a
value -- `None`/`False`/`()` when git cannot answer -- rather than raising, so
the callers that run inside git hooks stay total by construction.

**What does not.** Any knowledge of the state mount or the state branch: the
`.praxion-state` directory name, the `wt/` branch prefix, the `praxion-project-branch`
config key, and every classification those feed. Those live in
`_sidecar_mount.py` and `_sidecar_convergence.py`, which import this module.
The dependency is one-directional and must stay that way -- nothing here may
import a sidecar module back.

Sibling-imported the same way as `_git_runner` and `_repo_root` (``scripts/`` is
on ``sys.path`` when any of them runs). Stdlib only, and importable on the 3.9
floor `pyproject.toml` pins for `scripts/`, because the consumer git hooks that
reach this code run under a project's own interpreter.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

from _git_runner import GitUnavailableError, git_output, run_git

# Used only when neither the repository itself nor (for a fresh sidecar) the
# project it belongs to resolves an identity: a merge commit git would
# otherwise refuse to write is a worse outcome than a generic author on a
# machine-local state repository.
FALLBACK_IDENTITY_NAME = "Praxion"
FALLBACK_IDENTITY_EMAIL = "praxion@localhost"
FALLBACK_IDENTITY_PAIR = (FALLBACK_IDENTITY_NAME, FALLBACK_IDENTITY_EMAIL)
FALLBACK_IDENTITY = (
    "-c",
    f"user.email={FALLBACK_IDENTITY_EMAIL}",
    "-c",
    f"user.name={FALLBACK_IDENTITY_NAME}",
)


# --- total predicates -------------------------------------------------------


def succeeds(repo: Path, *args: str) -> bool:
    """Run a git predicate; ``False`` covers both non-zero and unrunnable."""
    try:
        return run_git(repo, *args).returncode == 0
    except GitUnavailableError:
        return False


def run_or_raise(
    repo: Path, error: type[Exception], *args: str
) -> subprocess.CompletedProcess[str]:
    """Run a mutating git command, raising ``error`` with git's own message.

    Returns the ``CompletedProcess`` on success -- read by callers that need
    its ``stdout`` (`_sidecar_commit.residue_paths`'s `status --porcelain`).
    """
    result = run_git(repo, *args)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise error(f"git {' '.join(args)} failed in {repo} (rc={result.returncode}): {stderr}")
    return result


def porcelain_status(repo: Path) -> str | None:
    """Return `status --porcelain` output; ``None`` when git could not answer.

    Distinct from `git_output`, which collapses "clean tree" and "git failed"
    into the same `None` -- a conflation no caller deciding whether it is safe
    to remove a working tree can afford.
    """
    try:
        result = run_git(repo, "status", "--porcelain")
    except GitUnavailableError:
        return None
    return result.stdout if result.returncode == 0 else None


# --- `.git` pointer files (stdlib reads, no subprocess) ---------------------


def read_gitdir_pointer(git_file: Path) -> Path | None:
    """Resolve the ``gitdir:`` target in a linked worktree's ``.git`` file."""
    try:
        content = git_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in content.splitlines():
        if not line.startswith("gitdir:"):
            continue
        raw = Path(line.split(":", 1)[1].strip())
        resolved = raw if raw.is_absolute() else git_file.parent / raw
        return resolved.resolve()
    return None


def common_dir_of_worktree(worktree_git_dir: Path) -> Path | None:
    """``<repo>/.git/worktrees/<name>`` -> ``<repo>/.git``; else ``None``."""
    if worktree_git_dir.parent.name != "worktrees":
        return None
    return worktree_git_dir.parent.parent


def recorded_worktree_path(worktree_git_dir: Path) -> Path | None:
    """The `.git` file path a repository records for one of its worktrees.

    The reverse of ``read_gitdir_pointer``: git keeps a ``gitdir`` file inside
    ``<repo>/.git/worktrees/<name>/`` naming where that worktree's own ``.git``
    file lives. Moving the worktree leaves the forward pointer valid (it is
    absolute and the repository did not move) while this one goes stale, which
    is the only observable difference between a healthy and a moved worktree.
    """
    try:
        recorded = (worktree_git_dir / "gitdir").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    recorded = recorded.strip()
    return Path(recorded) if recorded else None


def head_branch(worktree_git_dir: Path) -> str | None:
    """The branch a git dir's HEAD points at, or ``None`` when detached."""
    try:
        head = (worktree_git_dir / "HEAD").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    prefix = "ref: refs/heads/"
    return head[len(prefix) :] if head.startswith(prefix) else None


def merge_in_progress(worktree: Path) -> bool:
    """Whether a worktree is parked mid-merge (its ``MERGE_HEAD`` exists)."""
    git_dir = read_gitdir_pointer(worktree / ".git")
    if git_dir is None:
        return False
    return (git_dir / "MERGE_HEAD").exists()


# --- refs and branches ------------------------------------------------------


def is_ancestor(repo: Path, maybe_ancestor: str, descendant: str) -> bool:
    return succeeds(repo, "merge-base", "--is-ancestor", maybe_ancestor, descendant)


def branch_exists(repo: Path, branch: str) -> bool:
    return succeeds(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}")


def resolve_branch_ref(repo: Path, branch: str) -> str | None:
    """A resolvable ref for ``branch``, preferring the local one.

    A deleted local branch may still resolve through a remote-tracking ref; the
    glob covers every remote rather than assuming the conventional one.
    """
    if branch_exists(repo, branch):
        return branch
    remote_refs = git_output(
        repo, "for-each-ref", "--format=%(refname)", f"refs/remotes/*/{branch}"
    )
    if remote_refs:
        return remote_refs.splitlines()[0].strip()
    return None


def branches_with_prefix(repo: Path, prefix: str) -> tuple[str, ...]:
    listing = git_output(repo, "for-each-ref", "--format=%(refname:short)", f"refs/heads/{prefix}")
    if listing is None:
        return ()
    return tuple(line.strip() for line in listing.splitlines() if line.strip())


def branch_is_checked_out(repo: Path, branch: str) -> bool:
    """Whether any of the repository's worktrees holds ``branch``."""
    listing = git_output(repo, "worktree", "list", "--porcelain")
    if listing is None:
        return False
    marker = f"branch refs/heads/{branch}"
    return any(line.strip() == marker for line in listing.splitlines())


def delete_branch_if_merged(repo: Path, branch: str) -> bool:
    """`branch -d`: git refuses unless ``branch`` is contained in HEAD.

    Run this in the worktree whose HEAD is the intended base branch. Run from a
    repository whose own HEAD is detached, git measures containment against
    that detached commit and refuses every deletion.
    """
    return succeeds(repo, "branch", "-d", branch)


# --- branch config ----------------------------------------------------------


def branch_config_key(branch: str, key: str) -> str:
    return f"branch.{branch}.{key}"


def get_branch_config(repo: Path, branch: str, key: str) -> str | None:
    return git_output(repo, "config", "--get", branch_config_key(branch, key))


def set_branch_config(repo: Path, branch: str, key: str, value: str, *, error: type[Exception]):
    """Record a per-branch config value; git drops it when the branch is deleted."""
    run_or_raise(repo, error, "config", branch_config_key(branch, key), value)


# --- merging ----------------------------------------------------------------


def configured_identity(repo: Path) -> tuple[str, str] | None:
    """``repo``'s own resolved ``(name, email)``, or ``None`` if either is unset.

    Reads through git's normal resolution chain (repo-local, then global,
    then ``includeIf``) -- whatever git itself would use to author a commit
    made in ``repo`` right now.
    """
    name = git_output(repo, "config", "--get", "user.name")
    email = git_output(repo, "config", "--get", "user.email")
    if name and email:
        return (name, email)
    return None


def identity_args(repo: Path) -> tuple[str, ...]:
    """Prefer the repository's own configured identity; fall back if it has none."""
    if configured_identity(repo) is not None:
        return ()
    return FALLBACK_IDENTITY


def merge_branch(repo: Path, ref: str) -> subprocess.CompletedProcess[str]:
    """Merge ``ref`` into the repository's current branch, unjudged.

    Returns git's own result rather than a boolean: a non-zero exit means
    *either* a merge conflict *or* that git never got as far as merging, and
    collapsing the two here is what let a plumbing failure be reported to
    operators as a conflict. The caller distinguishes them (see
    ``_sidecar_mount.merge_back``) and needs git's stderr to say why.

    ``--no-ff`` because a merge-back is a *convergence point*, and a
    fast-forward records none: the target branch would silently become the
    source, leaving no commit that says when a worktree's state came home and
    nothing for `git log --first-parent` on the mount to show.
    """
    return run_git(repo, *identity_args(repo), "merge", "-q", "--no-ff", "--no-edit", ref)


def abort_merge(repo: Path) -> None:
    run_git(repo, "merge", "--abort")


def patch_already_applied(repo: Path, head: str, ref: str) -> bool:
    """Whether ``ref``'s changes are present in ``head`` under a *different* commit.

    The squash-merge detector, done without writing. ``ref``'s cumulative
    diff against the merge base is reduced to a patch id and compared with
    the patch id of every commit on ``head`` since that base which touches
    the same paths -- the only commits a squash of ``ref`` could be. That is
    what `git cherry` computes, minus the throwaway commit it needs as an
    argument: nothing here writes to ``repo``'s object store, which matters
    because ``repo`` is the *project's* repository and this probe re-runs on
    every convergence for as long as a branch stays unmerged.
    """
    merge_base = git_output(repo, "merge-base", head, ref)
    tip = git_output(repo, "rev-parse", f"{ref}^{{commit}}")
    if merge_base is None or tip is None or merge_base == tip:
        return False
    wanted = _patch_ids(repo, git_output(repo, "diff-tree", "-p", merge_base, tip))
    touched = git_output(repo, "diff-tree", "-r", "--name-only", merge_base, tip)
    if not wanted or touched is None:
        return False
    candidates = git_output(repo, "rev-list", f"{merge_base}..{head}", "--", *touched.splitlines())
    if candidates is None:
        return False
    return any(
        wanted & _patch_ids(repo, git_output(repo, "show", "-p", "--format=commit %H", *batch))
        for batch in _batched(candidates.splitlines(), _SHOW_BATCH)
    )


# `git show` takes its commits on the command line; a long-lived branch on a
# busy project can name thousands, so they go in argv-sized slices.
_SHOW_BATCH = 256


def _patch_ids(repo: Path, patch_text: str | None) -> frozenset[str]:
    """The patch ids `git patch-id --stable` assigns to each patch in ``patch_text``."""
    if not patch_text:
        return frozenset()
    listing = git_output(repo, "patch-id", "--stable", stdin=patch_text + "\n")
    if listing is None:
        return frozenset()
    return frozenset(line.split()[0] for line in listing.splitlines() if line.strip())


def _batched(items: list[str], size: int) -> Iterator[list[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
