"""The checkout listing: a repository's main working tree and its linked worktrees.

These tests run real git in temporary repositories, because the contract is what
`git worktree list` and `git merge-base` answer, not how this module parses them.
A listing that git could not produce is an error, never an empty repository, and
the scoping variables git exports to a hook must not redirect the questions.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from hooks._observation_log import checkouts

REPO_ROOT = Path(__file__).resolve().parent.parent


def _git(cwd: Path, *args: str) -> str:
    """Run git in `cwd` with a fixed identity and no inherited repository scoping."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    identity = ("-c", "user.name=T", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false")
    completed = subprocess.run(
        ["git", *identity, "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return completed.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "commit", "--allow-empty", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def main(tmp_path: Path) -> Path:
    repo = tmp_path / "main"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _commit(repo, "first")
    return repo


def _add_worktree(repo: Path, name: str) -> Path:
    path = repo.parent / name
    _git(repo, "worktree", "add", "-b", name, str(path))
    return path


def test_the_main_checkout_comes_first_then_each_linked_worktree(main: Path) -> None:
    linked = _add_worktree(main, "pipeline-a")

    listing = checkouts.repository_checkouts(main)

    assert listing.error is None
    first, second = listing.checkouts
    assert (first.root, first.is_main, first.name) == (main.resolve(), True, "main")
    assert (second.root, second.is_main, second.name) == (linked.resolve(), False, "pipeline-a")


def test_each_checkout_names_its_state_directory_and_its_head(main: Path) -> None:
    linked = _add_worktree(main, "pipeline-a")
    advanced = _commit(linked, "work")

    first, second = checkouts.repository_checkouts(main).checkouts

    assert first.state_dir == main.resolve() / ".ai-state"
    assert second.state_dir == linked.resolve() / ".ai-state"
    assert first.head == _git(main, "rev-parse", "HEAD")
    assert second.head == advanced


def test_the_listing_is_the_same_whichever_checkout_it_is_asked_from(main: Path) -> None:
    linked = _add_worktree(main, "pipeline-a")

    from_main = checkouts.repository_checkouts(main)
    from_linked = checkouts.repository_checkouts(linked)

    assert from_linked == from_main
    assert from_linked.checkouts[0].is_main


def test_a_worktree_whose_directory_is_gone_is_left_out(main: Path) -> None:
    gone = _add_worktree(main, "removed-by-hand")
    kept = _add_worktree(main, "kept")
    shutil.rmtree(gone)

    names = [c.name for c in checkouts.repository_checkouts(main).checkouts]

    assert names == ["main", "kept"]
    assert kept.is_dir()


def test_a_directory_that_is_no_repository_gives_an_error_and_no_checkouts(
    tmp_path: Path,
) -> None:
    listing = checkouts.repository_checkouts(tmp_path)

    assert listing.checkouts == ()
    assert listing.error


def test_a_directory_that_does_not_exist_gives_an_error_and_no_checkouts(tmp_path: Path) -> None:
    listing = checkouts.repository_checkouts(tmp_path / "absent")

    assert listing.checkouts == ()
    assert listing.error


def test_a_repository_with_no_main_working_tree_gives_an_error(tmp_path: Path, main: Path) -> None:
    bare = tmp_path / "bare.git"
    _git(tmp_path, "clone", "--bare", str(main), str(bare))

    listing = checkouts.repository_checkouts(bare)

    assert listing.checkouts == ()
    assert "main working tree" in listing.error


def test_git_missing_from_the_machine_gives_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(checkouts.subprocess, "run", no_git)

    listing = checkouts.repository_checkouts(tmp_path)

    assert listing.checkouts == ()
    assert "could not be run" in listing.error


def test_a_hung_git_gives_an_error_naming_the_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def hung(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(checkouts.subprocess, "run", hung)

    listing = checkouts.repository_checkouts(tmp_path)

    assert listing.checkouts == ()
    assert f"{checkouts.GIT_TIMEOUT_SECONDS} s" in listing.error


def test_repository_scoping_variables_inherited_from_a_hook_do_not_redirect_git(
    main: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("GIT_DIR", str(elsewhere))
    monkeypatch.setenv("GIT_INDEX_FILE", ".git/index")
    monkeypatch.setenv("GIT_WORK_TREE", str(elsewhere))

    listing = checkouts.repository_checkouts(main)

    assert listing.error is None
    assert [c.root for c in listing.checkouts] == [main.resolve()]
    assert checkouts.contains(main, _git(main, "rev-parse", "HEAD"))


def test_a_commit_the_main_checkout_contains_is_contained(main: Path) -> None:
    linked = _add_worktree(main, "pipeline-a")
    work = _commit(linked, "work")
    assert not checkouts.contains(main, work)

    _git(main, "merge", "--no-ff", "-m", "merge", "pipeline-a")

    assert checkouts.contains(main, work)


def test_a_commit_ahead_of_the_main_checkout_is_not_contained(main: Path) -> None:
    linked = _add_worktree(main, "pipeline-a")

    assert not checkouts.contains(main, _commit(linked, "work"))


def test_a_commit_git_does_not_know_is_not_contained(main: Path) -> None:
    assert not checkouts.contains(main, "0" * 40)


def test_a_failure_to_ask_reads_as_not_contained(tmp_path: Path) -> None:
    assert not checkouts.contains(tmp_path, "0" * 40)


def test_a_commit_is_contained_within_the_revision_asked_about(main: Path) -> None:
    before = _git(main, "rev-parse", "HEAD")
    linked = _add_worktree(main, "pipeline-a")
    work = _commit(linked, "work")
    _git(main, "merge", "--no-ff", "-m", "merge", "pipeline-a")

    assert checkouts.contains(main, work, within="HEAD")
    assert not checkouts.contains(main, work, within=before)
    assert checkouts.contains(main, before, within=before)


def test_a_worktree_with_no_commit_of_its_own_is_contained_in_the_revision_before_the_merge(
    main: Path,
) -> None:
    before = _git(main, "rev-parse", "HEAD")
    idle = _add_worktree(main, "idle")
    idle_head = _git(idle, "rev-parse", "HEAD")
    _commit(main, "later work on main")

    assert checkouts.contains(main, idle_head)
    assert checkouts.contains(main, idle_head, within=before)


def test_a_revision_that_does_not_exist_reads_as_not_containing(main: Path) -> None:
    assert not checkouts.contains(main, _git(main, "rev-parse", "HEAD"), within="no-such-rev")


def test_a_revision_resolves_to_its_commit_in_the_main_checkout(main: Path) -> None:
    head = _git(main, "rev-parse", "HEAD")
    _commit(main, "second")
    _git(main, "reset", "--hard", head)

    assert checkouts.resolve_commit(main, "HEAD") == head
    assert checkouts.resolve_commit(main, "ORIG_HEAD") != head  # points at "second"


def test_a_revision_git_cannot_resolve_gives_none(main: Path, tmp_path: Path) -> None:
    assert checkouts.resolve_commit(main, "ORIG_HEAD") is None
    assert checkouts.resolve_commit(main, "no-such-rev") is None
    assert checkouts.resolve_commit(tmp_path, "HEAD") is None


def test_the_hook_hot_path_never_loads_the_modules_that_run_git() -> None:
    script = (
        "import sys\n"
        "from hooks._observation_log import reader, writer\n"
        "loaded = [m for m in ('checkouts', 'merge_in')"
        " if f'hooks._observation_log.{m}' in sys.modules]\n"
        "print(','.join(loaded))\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""
