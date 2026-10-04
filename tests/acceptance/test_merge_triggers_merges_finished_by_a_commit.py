"""A merge git finishes outside `git merge` merges in the worktrees it brought in.

A merge stopped on a conflict, or run with `--no-commit`, and then finished with
`git commit` or `git merge --continue` runs no merge-time step; once the finalize
hooks are installed, the commit that finishes it copies into the main checkout's
log the rows of every worktree that commit brought in -- judged against the
commit's first parent -- once, unchanged, reported the way the merge-time step
reports a merge, and never at the cost of the merge itself.

Rows are compared as canonical JSON, so key order and spacing never matter.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers.hooks import (
    NON_BLOCKING_WARNING,
    install_finalize_hooks,
    lines_naming,
    normalized,
    output_of,
)
from tests.acceptance.drivers.log_segments import (
    active_log,
    append_rows,
    contents,
    history_rows,
    make_unreadable,
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
    write_project_setting,
)
from tests.acceptance.drivers.repository import add_worktree, branch_of, new_repository

WORKTREE = "pipeline-wt"
FINISHES = {
    "git commit": ("commit", "-q", "--no-edit"),
    "git merge --continue": ("merge", "--continue"),
}


def _conflicted_merge_scene(tmp_path: Path, name: str = "main-repo"):
    """A main checkout whose merge of a worktree's branch stopped on a conflict."""
    main = new_repository(tmp_path / name)
    worktree, rows = worktree_holding_rows(main, WORKTREE)
    conflicting_change(worktree, "worktree side")
    conflicting_change(main, "main side")
    hooked = install_finalize_hooks(main, tmp_path / f"{name}-sandbox")
    stopped = hooked.git("merge", "-q", "--no-edit", branch_of(WORKTREE), check=False)
    assert stopped.returncode != 0, "the scene needs a merge that stops on a conflict"
    resolve_conflict(hooked)
    return hooked, worktree, rows


# -- A merge finished by a commit merges in what it brought in ---------------------------


@pytest.mark.parametrize("finish", list(FINISHES))
def test_a_merge_stopped_on_a_conflict_merges_in_the_worktree_once_it_is_finished(
    tmp_path: Path, finish: str
) -> None:
    hooked, _worktree, rows = _conflicted_merge_scene(tmp_path)

    hooked.git(*FINISHES[finish])

    assert len(hooked.head_parents()) == 2
    assert times_held(hooked.main, rows) == [1, 1, 1]


def test_a_merge_run_with_no_commit_merges_in_the_worktree_once_it_is_committed(
    tmp_path: Path,
) -> None:
    main = new_repository(tmp_path / "main-repo")
    _worktree, rows = worktree_holding_rows(main, WORKTREE)
    hooked = install_finalize_hooks(main, tmp_path / "sandbox")
    hooked.git("merge", "-q", "--no-ff", "--no-commit", branch_of(WORKTREE))

    hooked.git("commit", "-q", "--no-edit")

    assert len(hooked.head_parents()) == 2
    assert times_held(main, rows) == [1, 1, 1]


def test_an_octopus_merge_finished_by_a_commit_merges_in_every_worktree_it_brought_in(
    tmp_path: Path,
) -> None:
    main = new_repository(tmp_path / "main-repo")
    _first, first_rows = worktree_holding_rows(main, "first-wt")
    _second, second_rows = worktree_holding_rows(main, "second-wt")
    hooked = install_finalize_hooks(main, tmp_path / "sandbox")
    hooked.git(
        "merge", "-q", "--no-ff", "--no-commit", branch_of("first-wt"), branch_of("second-wt")
    )

    hooked.git("commit", "-q", "--no-edit")

    assert len(hooked.head_parents()) == 3
    assert times_held(main, first_rows + second_rows) == [1] * 6


def test_a_merge_finished_by_a_commit_is_judged_by_its_first_parent_whatever_orig_head_holds(
    tmp_path: Path,
) -> None:
    hooked, worktree, rows = _conflicted_merge_scene(tmp_path)
    hooked.git("update-ref", "ORIG_HEAD", hooked.head(cwd=worktree))

    hooked.git("commit", "-q", "--no-edit")

    assert times_held(hooked.main, rows) == [1, 1, 1]


def test_a_merge_finished_by_a_commit_merges_in_no_worktree_it_did_not_bring_in(
    tmp_path: Path,
) -> None:
    main = new_repository(tmp_path / "main-repo")
    _earlier, earlier_rows = worktree_holding_rows(main, "earlier-wt")
    merged_without_hooks(main, "earlier-wt")
    idle = add_worktree(main, "idle-wt")
    idle_rows = rows_for("idle-wt")
    append_rows(state_dir_of(idle), idle_rows)
    _brought, brought_rows = worktree_holding_rows(main, WORKTREE)
    hooked = install_finalize_hooks(main, tmp_path / "sandbox")
    hooked.git("merge", "-q", "--no-ff", "--no-commit", branch_of(WORKTREE))

    hooked.git("commit", "-q", "--no-edit")

    assert times_held(main, brought_rows) == [1, 1, 1]
    assert times_held(main, earlier_rows + idle_rows) == [0] * 6


# -- It reports what it did the way the merge-time step does --------------------------------


def test_a_merge_finished_by_a_commit_reports_its_merge_in_as_a_plain_merge_does(
    tmp_path: Path,
) -> None:
    plain_main = new_repository(tmp_path / "plain" / "main-repo")
    worktree_holding_rows(plain_main, WORKTREE)
    plain = install_finalize_hooks(plain_main, tmp_path / "plain" / "sandbox")
    merged = plain.git("merge", "-q", "--no-ff", "--no-edit", branch_of(WORKTREE))
    committed_main = new_repository(tmp_path / "committed" / "main-repo")
    worktree_holding_rows(committed_main, WORKTREE)
    committed = install_finalize_hooks(committed_main, tmp_path / "committed" / "sandbox")
    committed.git("merge", "-q", "--no-ff", "--no-commit", branch_of(WORKTREE))

    finished = committed.git("commit", "-q", "--no-edit")

    expected = normalized(
        lines_naming(output_of(merged), WORKTREE), checkout=plain_main, sandbox=plain.sandbox
    )
    actual = normalized(
        lines_naming(output_of(finished), WORKTREE),
        checkout=committed_main,
        sandbox=committed.sandbox,
    )
    assert expected, "the merge-time step said nothing about the worktree it merged in"
    assert actual == expected


# -- Each row once, however often the step runs -------------------------------------------


def test_running_the_commit_hook_again_for_the_same_merge_commit_copies_nothing_more(
    tmp_path: Path,
) -> None:
    hooked, _worktree, rows = _conflicted_merge_scene(tmp_path)
    hooked.git("commit", "-q", "--no-edit")

    again = hooked.run_hook("post-commit")

    assert again.returncode == 0, output_of(again)
    assert times_held(hooked.main, rows) == [1, 1, 1]


def test_a_plain_merge_that_creates_a_merge_commit_starts_merge_in_once(tmp_path: Path) -> None:
    main = new_repository(tmp_path / "main-repo")
    worktree_holding_rows(main, WORKTREE)
    hooked = install_finalize_hooks(main, tmp_path / "sandbox")

    hooked.git("merge", "-q", "--no-ff", "--no-edit", branch_of(WORKTREE))

    assert len(hooked.merge_in_starts()) == 1, hooked.merge_in_starts()


# -- A fault never costs the merge -----------------------------------------------------------


@pytest.mark.skipif(running_as_root(), reason="root reads a chmod-000 file")
def test_a_merge_finished_by_a_commit_with_an_unreadable_worktree_log_completes_and_reports_it(
    tmp_path: Path,
) -> None:
    plain_main = new_repository(tmp_path / "plain" / "main-repo")
    plain_worktree, _ = worktree_holding_rows(plain_main, WORKTREE)
    make_unreadable(active_log(state_dir_of(plain_worktree)))
    plain = install_finalize_hooks(plain_main, tmp_path / "plain" / "sandbox")
    merged = plain.git("merge", "-q", "--no-ff", "--no-edit", branch_of(WORKTREE))
    committed_main = new_repository(tmp_path / "committed" / "main-repo")
    committed_worktree, _ = worktree_holding_rows(committed_main, WORKTREE)
    make_unreadable(active_log(state_dir_of(committed_worktree)))
    committed = install_finalize_hooks(committed_main, tmp_path / "committed" / "sandbox")
    committed.git("merge", "-q", "--no-ff", "--no-commit", branch_of(WORKTREE))

    finished = committed.git("commit", "-q", "--no-edit")

    assert finished.returncode == 0
    assert len(committed.head_parents()) == 2
    expected = normalized(
        lines_naming(output_of(merged), WORKTREE), checkout=plain_main, sandbox=plain.sandbox
    )
    actual = normalized(
        lines_naming(output_of(finished), WORKTREE),
        checkout=committed_main,
        sandbox=committed.sandbox,
    )
    assert expected, "the merge-time step did not report the unreadable worktree log"
    assert actual == expected
    assert committed.run_hook("post-commit").returncode == 0


def test_a_merge_finished_by_a_commit_that_copies_nothing_prints_nothing_about_merge_in(
    tmp_path: Path,
) -> None:
    main = new_repository(tmp_path / "main-repo")
    worktree_holding_rows(main, WORKTREE)
    hooked = install_finalize_hooks(main, tmp_path / "sandbox")
    hooked.git("merge", "-q", "--no-ff", "--no-commit", branch_of(WORKTREE))
    first = hooked.git("commit", "-q", "--no-edit")
    assert lines_naming(output_of(first), WORKTREE), "the first merge-in was not reported"
    hooked.git("reset", "--hard", "-q", "HEAD~1")
    hooked.git("merge", "-q", "--no-ff", "--no-commit", branch_of(WORKTREE))

    again = hooked.git("commit", "-q", "--no-edit")

    assert lines_naming(output_of(again), WORKTREE, NON_BLOCKING_WARNING) == []


# -- The same conditions as the merge-time step --------------------------------------------


def test_a_merge_finished_by_a_commit_copies_rows_unchanged_and_leaves_the_worktree_log_alone(
    tmp_path: Path,
) -> None:
    hooked, worktree, rows = _conflicted_merge_scene(tmp_path)
    worktree_before = contents(state_dir_of(worktree))

    hooked.git("commit", "-q", "--no-edit")

    copied = [r for r in history_rows(state_dir_of(hooked.main)) if r.get("project") == WORKTREE]
    assert canonical(copied) == canonical(rows)
    assert contents(state_dir_of(worktree)) == worktree_before


@pytest.mark.parametrize("settings_file", ["settings.json", "settings.local.json"])
def test_a_merge_finished_by_a_commit_copies_nothing_while_the_project_recording_mode_is_off(
    tmp_path: Path, settings_file: str
) -> None:
    recording, _recording_worktree, recording_rows = _conflicted_merge_scene(
        tmp_path, "recording-repo"
    )
    recording.git("commit", "-q", "--no-edit")
    off, _off_worktree, off_rows = _conflicted_merge_scene(tmp_path, "off-repo")
    write_project_setting(off.main, settings_file, "PRAXION_OBSERVATION_LOG", "off")
    main_before = contents(state_dir_of(off.main))

    off.git("commit", "-q", "--no-edit")

    assert times_held(recording.main, recording_rows) == [1, 1, 1], "control merge copied nothing"
    assert times_held(off.main, off_rows) == [0, 0, 0]
    assert contents(state_dir_of(off.main)) == main_before


# -- What the drivers assume about git -------------------------------------------------------


def test_guard_a_merge_stopped_on_a_conflict_runs_no_merge_time_step(tmp_path: Path) -> None:
    hooked, _worktree, rows = _conflicted_merge_scene(tmp_path)

    assert hooked.merge_in_starts() == []
    assert times_held(hooked.main, rows) == [0, 0, 0]


def test_guard_the_merge_time_step_names_the_worktree_it_merged_in(tmp_path: Path) -> None:
    main = new_repository(tmp_path / "main-repo")
    _worktree, rows = worktree_holding_rows(main, WORKTREE)
    hooked = install_finalize_hooks(main, tmp_path / "sandbox")

    merged = hooked.git("merge", "-q", "--no-ff", "--no-edit", branch_of(WORKTREE))

    assert times_held(main, rows) == [1, 1, 1]
    assert lines_naming(output_of(merged), WORKTREE), output_of(merged)
    assert hooked.merge_in_starts(), "the python3 shim did not see the merge-in start"
