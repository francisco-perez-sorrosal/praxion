"""Commits that bring nothing in copy nothing, and the per-commit hook stays cheap.

A single-parent commit (an ordinary one, a cherry-pick, the commit completing a
squash merge), an amend (of a merge commit too), any merge, amend or rebase in a
linked worktree, and a squash merge copy no row and start no merge-in. Every
scenario starts from a history in which a trigger that judged "brought in" wrongly
would copy: the worktree is already in the main checkout's history, merged before
any hook was installed, while its rows are not in the main log.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers.hooks import (
    Hooked,
    base_scripts,
    git_processes_started_by_hooks,
    install_finalize_hooks,
)
from tests.acceptance.drivers.log_segments import contents, state_dir_of
from tests.acceptance.drivers.merge_scenes import (
    conflicting_change,
    merged_without_hooks,
    resolve_conflict,
    times_held,
    worktree_holding_rows,
)
from tests.acceptance.drivers.repository import branch_of, commit_file, git, new_repository

MERGED = "merged-wt"


def _worktree_merged_before_hooks(tmp_path: Path) -> tuple[Path, list[dict]]:
    main = new_repository(tmp_path / "main-repo")
    _worktree, rows = worktree_holding_rows(main, MERGED)
    merged_without_hooks(main, MERGED)
    return main, rows


def _ordinary_commit(hooked: Hooked) -> None:
    (hooked.main / "plain.txt").write_text("plain\n", encoding="utf-8")
    hooked.git("add", "plain.txt")
    hooked.git("commit", "-q", "-m", "an ordinary commit")


def _cherry_pick(hooked: Hooked) -> None:
    hooked.git("cherry-pick", "picked")


def _commit_completing_a_squash_merge(hooked: Hooked) -> None:
    hooked.git("merge", "-q", "--squash", "picked")
    hooked.forget_starts()
    hooked.git("commit", "-q", "-m", "squashed")


SINGLE_PARENT_COMMITS = {
    "an ordinary commit": _ordinary_commit,
    "a cherry-pick": _cherry_pick,
    "the commit completing a squash merge": _commit_completing_a_squash_merge,
}


# -- A single-parent commit ------------------------------------------------------------------


@pytest.mark.parametrize("kind", list(SINGLE_PARENT_COMMITS))
def test_a_single_parent_commit_copies_nothing_and_starts_no_merge_in(
    tmp_path: Path, kind: str
) -> None:
    main, rows = _worktree_merged_before_hooks(tmp_path)
    git(main, "branch", "picked", "HEAD~1")
    git(main, "switch", "-q", "picked")
    commit_file(main, "picked.txt", "picked\n", "work to pick")
    git(main, "switch", "-q", "main")
    hooked = install_finalize_hooks(main, tmp_path / "sandbox")

    SINGLE_PARENT_COMMITS[kind](hooked)

    assert len(hooked.head_parents()) == 1
    assert times_held(main, rows) == [0, 0, 0]
    assert hooked.merge_in_starts() == []


def test_a_single_parent_commit_adds_at_most_one_git_query_to_the_commit_hook(
    tmp_path: Path,
) -> None:
    before_change = base_scripts(tmp_path / "base")
    if before_change is None:
        pytest.skip("the base commit is not in this clone (shallow history); nothing to compare")
    base_main, _ = _worktree_merged_before_hooks(tmp_path / "base-run")
    base = install_finalize_hooks(base_main, tmp_path / "base-sandbox", scripts_dir=before_change)
    now_main, _ = _worktree_merged_before_hooks(tmp_path / "now-run")
    now = install_finalize_hooks(now_main, tmp_path / "now-sandbox")
    (base_main / "plain.txt").write_text("plain\n", encoding="utf-8")
    base.git("add", "plain.txt")
    base.git("commit", "-q", "-m", "plain", GIT_TRACE2_EVENT=str(tmp_path / "base.trace"))
    (now_main / "plain.txt").write_text("plain\n", encoding="utf-8")
    now.git("add", "plain.txt")

    now.git("commit", "-q", "-m", "plain", GIT_TRACE2_EVENT=str(tmp_path / "now.trace"))

    queries_before = git_processes_started_by_hooks(tmp_path / "base.trace")
    queries_now = git_processes_started_by_hooks(tmp_path / "now.trace")
    assert queries_now <= queries_before + 1, (queries_before, queries_now)


# -- An amend -------------------------------------------------------------------------------


def test_amending_a_merge_commit_copies_nothing_and_starts_no_merge_in(tmp_path: Path) -> None:
    main, rows = _worktree_merged_before_hooks(tmp_path)
    hooked = install_finalize_hooks(main, tmp_path / "sandbox")

    hooked.git("commit", "-q", "--amend", "--no-edit")

    assert len(hooked.head_parents()) == 2
    assert times_held(main, rows) == [0, 0, 0]
    assert hooked.merge_in_starts() == []


def test_amending_a_single_parent_commit_copies_nothing_and_starts_no_merge_in(
    tmp_path: Path,
) -> None:
    main, rows = _worktree_merged_before_hooks(tmp_path)
    commit_file(main, "plain.txt", "plain\n", "an ordinary commit")
    hooked = install_finalize_hooks(main, tmp_path / "sandbox")

    hooked.git("commit", "-q", "--amend", "-m", "an ordinary commit, reworded")

    assert times_held(main, rows) == [0, 0, 0]
    assert hooked.merge_in_starts() == []


# -- Operations in a linked worktree --------------------------------------------------------


def _two_worktrees(tmp_path: Path):
    """A linked worktree `here` with its own log, and `there`, merged into main before hooks."""
    main = new_repository(tmp_path / "main-repo")
    here, here_rows = worktree_holding_rows(main, "here-wt")
    there, there_rows = worktree_holding_rows(main, "there-wt")
    merged_without_hooks(main, "there-wt")
    return main, here, there, there_rows


def test_a_conflicted_merge_finished_by_a_commit_in_a_linked_worktree_copies_nothing(
    tmp_path: Path,
) -> None:
    main, here, there, there_rows = _two_worktrees(tmp_path)
    conflicting_change(there, "there side")
    git(main, "merge", "-q", "--no-edit", branch_of("there-wt"))
    conflicting_change(here, "here side")
    hooked = install_finalize_hooks(main, tmp_path / "sandbox")
    logs_before = (contents(state_dir_of(main)), contents(state_dir_of(here)))
    hooked.git("merge", "-q", "--no-edit", branch_of("there-wt"), cwd=here, check=False)
    resolve_conflict(hooked, here)

    hooked.git("commit", "-q", "--no-edit", cwd=here)

    assert len(hooked.head_parents(cwd=here)) == 2
    assert (contents(state_dir_of(main)), contents(state_dir_of(here))) == logs_before
    assert hooked.merge_in_starts() == []


def test_a_pull_that_rebases_in_a_linked_worktree_copies_nothing(tmp_path: Path) -> None:
    main, here, there, _there_rows = _two_worktrees(tmp_path)
    commit_file(here, "here-local.txt", "local\n", "local work here")
    hooked = install_finalize_hooks(main, tmp_path / "sandbox")
    logs_before = (contents(state_dir_of(main)), contents(state_dir_of(here)))

    hooked.git("pull", "-q", "--rebase", ".", branch_of("there-wt"), cwd=here)

    assert hooked.contains(hooked.head(cwd=there), cwd=here)
    assert (contents(state_dir_of(main)), contents(state_dir_of(here))) == logs_before
    assert hooked.merge_in_starts() == []


def test_an_amend_in_a_linked_worktree_copies_nothing(tmp_path: Path) -> None:
    main, here, _there, _there_rows = _two_worktrees(tmp_path)
    git(here, "merge", "-q", "--no-ff", "--no-edit", branch_of("there-wt"))
    hooked = install_finalize_hooks(main, tmp_path / "sandbox")
    logs_before = (contents(state_dir_of(main)), contents(state_dir_of(here)))

    hooked.git("commit", "-q", "--amend", "--no-edit", cwd=here)

    assert (contents(state_dir_of(main)), contents(state_dir_of(here))) == logs_before
    assert hooked.merge_in_starts() == []


def test_an_ordinary_commit_in_a_linked_worktree_copies_nothing(tmp_path: Path) -> None:
    main, here, _there, _there_rows = _two_worktrees(tmp_path)
    hooked = install_finalize_hooks(main, tmp_path / "sandbox")
    logs_before = (contents(state_dir_of(main)), contents(state_dir_of(here)))
    (here / "here-more.txt").write_text("more\n", encoding="utf-8")
    hooked.git("add", "here-more.txt", cwd=here)

    hooked.git("commit", "-q", "-m", "more work here", cwd=here)

    assert (contents(state_dir_of(main)), contents(state_dir_of(here))) == logs_before
    assert hooked.merge_in_starts() == []


# -- A squash merge stays the named limit ---------------------------------------------------


def test_a_squash_merge_copies_nothing_for_the_squashed_worktree(tmp_path: Path) -> None:
    main = new_repository(tmp_path / "main-repo")
    _worktree, rows = worktree_holding_rows(main, "squashed-wt")
    hooked = install_finalize_hooks(main, tmp_path / "sandbox")
    hooked.git("merge", "-q", "--squash", branch_of("squashed-wt"))

    hooked.git("commit", "-q", "-m", "squash the pipeline's work")

    assert times_held(main, rows) == [0, 0, 0]
