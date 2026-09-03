"""Git plumbing for the sidecar modules -- queries and parsers, no policy.

**What belongs here.** Anything that is true of *git*, independent of what
Praxion does with the answer: ref resolution and ancestry, worktree-list and
`.git`-pointer parsing, branch config get/set, the patch-identity probe that
detects a squash merge, the identity fallback a merge commit needs. Every
function names its repository explicitly (first argument) and answers with a
value -- `None`/`False`/`()` when git cannot answer -- rather than raising, so
the callers that run inside git hooks stay total by construction.

**What does not.** Any knowledge of the state mount or the state branch: the
`.praxion` directory name, the `wt/` branch prefix, the `praxion-project-branch`
config key, and every classification those feed. Those live in
`_sidecar_mount.py`, which imports this module. The dependency is
one-directional and must stay that way -- nothing here may import a sidecar
module back.

Sibling-imported the same way as `_git_runner` and `_repo_root` (``scripts/`` is
on ``sys.path`` when any of them runs). Stdlib only, and importable on the 3.9
floor `pyproject.toml` pins for `scripts/`, because the consumer git hooks that
reach this code run under a project's own interpreter.
"""

from __future__ import annotations

from pathlib import Path

from _git_runner import GitUnavailableError, git_output, run_git

# Used only when a repository resolves no identity of its own: a merge commit
# git would otherwise refuse to write is a worse outcome than a generic author
# on a machine-local state repository.
FALLBACK_IDENTITY = ("-c", "user.email=praxion@localhost", "-c", "user.name=Praxion")


# --- total predicates -------------------------------------------------------


def succeeds(repo: Path, *args: str) -> bool:
    """Run a git predicate; ``False`` covers both non-zero and unrunnable."""
    try:
        return run_git(repo, *args).returncode == 0
    except GitUnavailableError:
        return False


def run_or_raise(repo: Path, error: type[Exception], *args: str) -> None:
    """Run a mutating git command, raising ``error`` with git's own message."""
    result = run_git(repo, *args)
    if result.returncode != 0:
        raise error(result.stderr.strip() or f"git {args[0]} exited {result.returncode}")


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


def identity_args(repo: Path) -> tuple[str, ...]:
    """Prefer the repository's own configured identity; fall back if it has none."""
    if git_output(repo, "config", "--get", "user.email") and git_output(
        repo, "config", "--get", "user.name"
    ):
        return ()
    return FALLBACK_IDENTITY


def merge_branch(repo: Path, ref: str) -> bool:
    """Merge ``ref`` into the repository's current branch. ``False`` on conflict."""
    return run_git(repo, *identity_args(repo), "merge", "-q", "--no-edit", ref).returncode == 0


def abort_merge(repo: Path) -> None:
    run_git(repo, "merge", "--abort")


def patch_already_applied(repo: Path, head: str, ref: str) -> bool:
    """Whether ``ref``'s changes are present in ``head`` under a *different* commit.

    The standard squash-merge detector: replay ``ref``'s tree as a throwaway
    commit on the merge base, then ask `git cherry` whether an equivalent patch
    already exists in ``head`` (a `-` prefix means it does). Callers run this
    only after the cheap ancestor test fails, because it costs several plumbing
    calls and writes one **unreachable** commit object into ``repo`` --
    invisible to `git status`, reclaimed by routine gc, but a write.
    """
    merge_base = git_output(repo, "merge-base", head, ref)
    tip = git_output(repo, "rev-parse", f"{ref}^{{commit}}")
    if merge_base is None or tip is None or merge_base == tip:
        return False
    tree = git_output(repo, "rev-parse", f"{ref}^{{tree}}")
    if tree is None:
        return False
    probe = git_output(repo, "commit-tree", tree, "-p", merge_base, "-m", "_")
    if probe is None:
        return False
    applied = git_output(repo, "cherry", head, probe)
    return bool(applied) and any(line.startswith("-") for line in applied.splitlines())
