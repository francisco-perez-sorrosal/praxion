"""Driver for scratch repositories with a main checkout and pipeline worktrees.

Plain git, nothing of the system under test: a repository whose main checkout
records into `.ai-state/` (tracked, so every worktree gets its own), worktrees
created with `git worktree add` (by default where pipelines put them, under the
main checkout's `.claude/worktrees/`), commits, merges, pulls and removals.

Isolation: git runs with no inherited `GIT_*` variables, a fixed identity, no
signing, and no hooks other than the ones a scenario installs in the scratch
repository itself.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

STATE_DIR = ".ai-state"
_IDENTITY = (
    "-c",
    "user.name=Retention Acceptance",
    "-c",
    "user.email=retention-acceptance@example.invalid",
    "-c",
    "commit.gpgsign=false",
)


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "CLAUDE", "PRAXION_"))}
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *_IDENTITY, *args],
        cwd=cwd,
        env=_env(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {cwd}: {result.stderr}")
    return result


def new_repository(path: Path) -> Path:
    """A main checkout on branch `main` with a tracked `.ai-state/` and one commit."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    (path / STATE_DIR).mkdir(exist_ok=True)
    (path / STATE_DIR / "README.md").write_text("state\n", encoding="utf-8")
    (path / "README.md").write_text("scratch\n", encoding="utf-8")
    git(path, "add", "README.md", f"{STATE_DIR}/README.md")
    git(path, "commit", "-q", "--no-verify", "-m", "initial")
    return path


def branch_of(name: str) -> str:
    return f"worktree-{name}"


def add_worktree(main: Path, name: str, *, parent: Path | None = None) -> Path:
    """A worktree on its own branch; under `.claude/worktrees/` unless `parent` is given."""
    location = (parent or main / ".claude" / "worktrees") / name
    location.parent.mkdir(parents=True, exist_ok=True)
    git(main, "worktree", "add", "-q", "-b", branch_of(name), str(location))
    return location


def commit_file(checkout: Path, relpath: str, text: str, message: str) -> str:
    target = checkout / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    git(checkout, "add", relpath)
    git(checkout, "commit", "-q", "--no-verify", "-m", message)
    return git(checkout, "rev-parse", "HEAD").stdout.strip()


def merge_branch(main: Path, branch: str, *, how: str) -> subprocess.CompletedProcess[str]:
    """Bring `branch` into the main checkout by a plain merge or a pull, hooks enabled."""
    if how == "merge":
        return git(main, "merge", "--no-edit", branch, check=False)
    if how == "pull":
        return git(main, "pull", "--no-edit", "--no-rebase", ".", branch, check=False)
    raise ValueError(f"unknown way to merge: {how}")


def contains_commit(checkout: Path, sha: str) -> bool:
    return git(checkout, "merge-base", "--is-ancestor", sha, "HEAD", check=False).returncode == 0


def remove_worktree(main: Path, worktree: Path) -> None:
    git(main, "worktree", "remove", "--force", str(worktree))
