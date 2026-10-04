"""A rebase in the main checkout that brings worktrees in merges in their logs.

`git pull --rebase` over local commits (and a plain `git rebase`) runs no merge-time
step. Once the finalize hooks are installed, a rebase that finishes with a tip
containing a worktree's HEAD that the tip before the rebase lacked copies that
worktree's rows into the main log -- once, after the rebase has finished, never
while commits are replayed, never for an abandoned rebase, and silently not at all
when nothing new came in. A before-revision that cannot be resolved is a one-line
named skip, not a fault.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers.hooks import (
    NON_BLOCKING_WARNING,
    Hooked,
    install_finalize_hooks,
    lines_naming,
    output_of,
)
from tests.acceptance.drivers.log_segments import (
    active_log,
    append_rows,
    contents,
    history_rows,
    rows_of,
    running_as_root,
    state_dir_of,
)
from tests.acceptance.drivers.merge_scenes import (
    canonical,
    conflicting_change,
    merged_without_hooks,
    resolve_conflict,
    rows_for,
    times_held,
    worktree_holding_rows,
)
from tests.acceptance.drivers.repository import (
    add_worktree,
    branch_of,
    commit_file,
    git,
    new_repository,
)

WORKTREE = "pipeline-wt"
BRANCH = branch_of(WORKTREE)
REBASES = {
    "git pull --rebase": ("pull", "-q", "--rebase", ".", BRANCH),
    "git rebase": ("rebase", "-q", BRANCH),
}


def _forget_before_revision(hooked: Hooked) -> str:
    """An exec step deleting the record of the tip before the rebase.

    It runs from a script file: git echoes an exec step's command line, and that
    echo must not name the revision a scenario looks for in the hooks' report.
    """
    script = hooked.sandbox / "forget-before-revision.sh"
    script.write_text('rm -f "$(git rev-parse --git-path ORIG_HEAD)"\n', encoding="utf-8")
    return f"sh '{script}'"


def _local_commits_behind_a_worktree(tmp_path: Path) -> tuple[Hooked, Path, list[dict]]:
    """Main has two local commits; a worktree's branch has work main lacks."""
    main = new_repository(tmp_path / "main-repo")
    worktree, rows = worktree_holding_rows(main, WORKTREE, commits=2)
    commit_file(main, "local-1.txt", "one\n", "local one")
    commit_file(main, "local-2.txt", "two\n", "local two")
    return install_finalize_hooks(main, tmp_path / "sandbox"), worktree, rows


def _rebase_stopped_on_a_conflict(tmp_path: Path) -> tuple[Hooked, Path, list[dict]]:
    """A pull that rebases a clean and a conflicting local commit, stopped on the conflict."""
    main = new_repository(tmp_path / "main-repo")
    worktree, rows = worktree_holding_rows(main, WORKTREE)
    conflicting_change(worktree, "worktree side")
    commit_file(main, "local-1.txt", "one\n", "local one")
    conflicting_change(main, "main side")
    hooked = install_finalize_hooks(main, tmp_path / "sandbox")
    stopped = hooked.git("pull", "-q", "--rebase", ".", BRANCH, check=False)
    assert stopped.returncode != 0, "the scene needs a rebase that stops on a conflict"
    return hooked, worktree, rows


def _local_merge_commit(main: Path) -> None:
    """Main gains a local merge commit of a side branch no worktree holds."""
    git(main, "switch", "-q", "-c", "side")
    commit_file(main, "side.txt", "side\n", "side work")
    git(main, "switch", "-q", "main")
    commit_file(main, "local-1.txt", "one\n", "local one")
    git(main, "merge", "-q", "--no-ff", "--no-edit", "side")


# -- A finished rebase merges in what it brought in ---------------------------------------


@pytest.mark.parametrize("how", list(REBASES))
def test_a_rebase_that_brings_in_a_worktree_merges_in_its_log_once(
    tmp_path: Path, how: str
) -> None:
    hooked, worktree, rows = _local_commits_behind_a_worktree(tmp_path)

    hooked.git(*REBASES[how])

    assert hooked.contains(hooked.head(cwd=worktree))
    assert times_held(hooked.main, rows) == [1, 1, 1]


def test_a_rebase_that_recreates_local_merge_commits_merges_in_the_worktree_it_brought_in(
    tmp_path: Path,
) -> None:
    main = new_repository(tmp_path / "main-repo")
    worktree, rows = worktree_holding_rows(main, WORKTREE)
    _local_merge_commit(main)
    hooked = install_finalize_hooks(main, tmp_path / "sandbox")

    hooked.git("pull", "-q", "--rebase=merges", ".", BRANCH)

    assert hooked.contains(hooked.head(cwd=worktree))
    assert times_held(main, rows) == [1, 1, 1]


@pytest.mark.parametrize("resume", ["--continue", "--skip"])
def test_a_rebase_finished_after_a_conflict_merges_in_the_worktree_it_brought_in(
    tmp_path: Path, resume: str
) -> None:
    hooked, worktree, rows = _rebase_stopped_on_a_conflict(tmp_path)
    resolve_conflict(hooked)

    hooked.git("rebase", resume)

    assert hooked.contains(hooked.head(cwd=worktree))
    assert times_held(hooked.main, rows) == [1, 1, 1]


def test_a_rebase_copies_rows_unchanged_and_leaves_the_worktree_log_alone(
    tmp_path: Path,
) -> None:
    hooked, worktree, rows = _local_commits_behind_a_worktree(tmp_path)
    worktree_before = contents(state_dir_of(worktree))

    hooked.git(*REBASES["git pull --rebase"])

    copied = [r for r in history_rows(state_dir_of(hooked.main)) if r.get("project") == WORKTREE]
    assert canonical(copied) == canonical(rows)
    assert contents(state_dir_of(worktree)) == worktree_before


# -- Nothing while replaying, when abandoned, or when nothing came in -----------------------


def test_a_rebase_copies_nothing_and_starts_no_merge_in_while_it_replays_commits(
    tmp_path: Path,
) -> None:
    hooked, _worktree, rows = _local_commits_behind_a_worktree(tmp_path)
    log_seen = hooked.sandbox / "log-during-replay.jsonl"
    starts_seen = hooked.sandbox / "starts-during-replay.txt"
    snapshot = (
        f"cat .ai-state/observations.jsonl >> '{log_seen}' 2>/dev/null; "
        f"cat '{hooked.starts_file}' >> '{starts_seen}' 2>/dev/null; true"
    )

    hooked.git("rebase", "-q", "-x", snapshot, BRANCH)

    assert canonical(rows) & canonical(rows_of(log_seen)) == canonical([])
    assert (
        lines_naming(starts_seen.read_text() if starts_seen.exists() else "", "merge_worktree_log")
        == []
    )


def test_a_rebase_that_recreates_merge_commits_and_is_abandoned_copies_nothing(
    tmp_path: Path,
) -> None:
    main = new_repository(tmp_path / "main-repo")
    worktree, rows = worktree_holding_rows(main, WORKTREE)
    conflicting_change(worktree, "worktree side")
    _local_merge_commit(main)
    conflicting_change(main, "main side")
    hooked = install_finalize_hooks(main, tmp_path / "sandbox")
    stopped = hooked.git("pull", "-q", "--rebase=merges", ".", BRANCH, check=False)
    assert stopped.returncode != 0, "the scene needs the replay to stop after the merge commit"
    copied_while_stopped = times_held(main, rows)

    hooked.git("rebase", "--abort")

    assert copied_while_stopped == [0, 0, 0]
    assert times_held(main, rows) == [0, 0, 0]
    assert hooked.merge_in_starts() == []


def test_an_abandoned_rebase_copies_nothing(tmp_path: Path) -> None:
    hooked, _worktree, rows = _rebase_stopped_on_a_conflict(tmp_path)

    hooked.git("rebase", "--abort")

    assert times_held(hooked.main, rows) == [0, 0, 0]
    assert hooked.merge_in_starts() == []


def test_a_pull_with_nothing_new_upstream_copies_nothing_and_prints_nothing_about_merge_in(
    tmp_path: Path,
) -> None:
    main = new_repository(tmp_path / "main-repo")
    _worktree, rows = worktree_holding_rows(main, WORKTREE)
    merged_without_hooks(main, WORKTREE)
    commit_file(main, "local-1.txt", "one\n", "local one")
    hooked = install_finalize_hooks(main, tmp_path / "sandbox")

    pulled = hooked.git("pull", "-q", "--rebase", ".", BRANCH)

    assert times_held(main, rows) == [0, 0, 0]
    assert lines_naming(output_of(pulled), WORKTREE, NON_BLOCKING_WARNING, "ORIG_HEAD") == []


def test_a_rebase_that_only_replays_local_commits_copies_nothing_and_prints_nothing_about_it(
    tmp_path: Path,
) -> None:
    main = new_repository(tmp_path / "main-repo")
    _worktree, rows = worktree_holding_rows(main, WORKTREE)
    merged_without_hooks(main, WORKTREE)
    commit_file(main, "local-1.txt", "one\n", "local one")
    commit_file(main, "local-2.txt", "two\n", "local two")
    hooked = install_finalize_hooks(main, tmp_path / "sandbox")

    replayed = hooked.git("rebase", "-q", "--force-rebase", "HEAD~2")

    assert times_held(main, rows) == [0, 0, 0]
    assert lines_naming(output_of(replayed), WORKTREE, NON_BLOCKING_WARNING, "ORIG_HEAD") == []


# -- A before-revision that cannot be resolved ----------------------------------------------


def test_a_rebase_whose_before_revision_cannot_be_resolved_prints_one_named_skip(
    tmp_path: Path,
) -> None:
    hooked, worktree, rows = _local_commits_behind_a_worktree(tmp_path)

    rebased = hooked.git("rebase", "-q", "-x", _forget_before_revision(hooked), BRANCH)

    skip_lines = lines_naming(output_of(rebased), "ORIG_HEAD")
    assert len(skip_lines) == 1, output_of(rebased)
    assert "skip" in skip_lines[0].lower(), skip_lines
    assert NON_BLOCKING_WARNING not in output_of(rebased)
    assert hooked.contains(hooked.head(cwd=worktree))
    assert times_held(hooked.main, rows) == [0, 0, 0]


def test_an_unresolvable_before_revision_with_no_worktree_log_prints_nothing_about_it(
    tmp_path: Path,
) -> None:
    main = new_repository(tmp_path / "main-repo")
    silent = add_worktree(main, "silent-wt")
    commit_file(silent, "upstream.txt", "upstream\n", "upstream work")
    commit_file(main, "local-1.txt", "one\n", "local one")
    hooked = install_finalize_hooks(main, tmp_path / "sandbox")

    rebased = hooked.git(
        "rebase", "-q", "-x", _forget_before_revision(hooked), branch_of("silent-wt")
    )

    assert lines_naming(output_of(rebased), "ORIG_HEAD", NON_BLOCKING_WARNING) == []


# -- A fault never costs the rebase ---------------------------------------------------------


@pytest.mark.skipif(running_as_root(), reason="root writes a read-only file")
def test_a_rebase_that_cannot_write_the_main_log_completes_and_reports_the_worktree(
    tmp_path: Path,
) -> None:
    hooked, worktree, _rows = _local_commits_behind_a_worktree(tmp_path)
    main_state = state_dir_of(hooked.main)
    append_rows(main_state, rows_for("main-session", count=1))
    active_log(main_state).chmod(0o444)
    main_state.chmod(0o555)
    try:
        rebased = hooked.git(*REBASES["git pull --rebase"])
    finally:
        main_state.chmod(0o755)
        active_log(main_state).chmod(0o644)

    assert rebased.returncode == 0
    assert hooked.contains(hooked.head(cwd=worktree))
    assert lines_naming(output_of(rebased), WORKTREE), output_of(rebased)


# -- What the drivers assume about git -------------------------------------------------------


def test_guard_an_exec_step_that_deletes_orig_head_leaves_it_unresolvable_after_the_rebase(
    tmp_path: Path,
) -> None:
    hooked, _worktree, _rows = _local_commits_behind_a_worktree(tmp_path)

    hooked.git("rebase", "-q", "-x", _forget_before_revision(hooked), BRANCH)

    resolved = hooked.git("rev-parse", "--verify", "-q", "ORIG_HEAD", check=False)
    assert resolved.returncode != 0, resolved.stdout
