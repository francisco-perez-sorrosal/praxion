"""A worktree's log rows reach the main checkout's log when its branch is merged.

Merge-in copies every row of the worktree's log (active and archives) that the
main log does not already hold, unchanged; it is repeatable without duplicates,
leaves the worktree's own log intact, shares the main log with rotation, and
degrades visibly when a log cannot be read or written. A plain merge or pull in
the main checkout performs the same merge-in, and a log fault never blocks the
code merge.

Two rows are equal when they hold the same fields with the same values: the
scenarios compare rows as canonical JSON, so key order and spacing never matter.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.acceptance.drivers.log_merge_in import install_merge_trigger, merge_in
from tests.acceptance.drivers.log_rows import agent_start
from tests.acceptance.drivers.log_segments import (
    active_log,
    append_lines,
    append_rows,
    contents,
    fill_to_cap,
    history_rows,
    listed_archives,
    make_unreadable,
    rotate,
    rows_of,
    running_as_root,
    session_ids_in,
    size_cap,
    state_dir_of,
)
from tests.acceptance.drivers.observation_harness import HookHarness, Session
from tests.acceptance.drivers.repository import (
    add_worktree,
    branch_of,
    commit_file,
    contains_commit,
    merge_branch,
    new_repository,
)

WORKTREE = "pipeline-wt"
MAIN_SESSION = "5e551011-0000-4000-8000-0000000c0001"
WORKTREE_SESSION = "5e551011-0000-4000-8000-0000000c0002"
LATER_SESSION = "5e551011-0000-4000-8000-0000000c0003"
LEGACY_ROW = agent_start("legacy-agent-0001", at="2026-08-30T23:31:50+00:00", project="old-wt")


def _canonical(rows: list[dict]) -> Counter:
    return Counter(json.dumps(row, sort_keys=True) for row in rows)


@dataclass(frozen=True)
class Repo:
    main: Path
    worktree: Path
    harness: HookHarness

    @property
    def main_state(self) -> Path:
        return state_dir_of(self.main)

    @property
    def worktree_state(self) -> Path:
        return state_dir_of(self.worktree)

    def session(self, session_id: str, cwd: Path) -> Session:
        return Session(self.harness, session_id, cwd)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    """A main checkout with its own rows, and a worktree whose log has an archive and a legacy row."""
    main = new_repository(tmp_path / "main-repo")
    worktree = add_worktree(main, WORKTREE)
    harness = HookHarness(tmp_path / "harness")
    Session(harness, MAIN_SESSION, main).session_start()
    in_worktree = Session(harness, WORKTREE_SESSION, worktree)
    in_worktree.session_start()
    in_worktree.spawn_foreground("Task slug: merged-slug\nDo the work.", "a-wt-0001", cwd=worktree)
    rotate(in_worktree, state_dir_of(worktree), 1)
    append_rows(state_dir_of(worktree), [LEGACY_ROW])
    return Repo(main, worktree, harness)


# -- Merge-in copies what the main log lacks ---------------------------------------------


def test_merge_in_copies_every_worktree_row_the_main_log_lacks_and_reports_the_counts(
    repo: Repo,
) -> None:
    worktree_rows = history_rows(repo.worktree_state)
    already_held = worktree_rows[0]
    append_rows(repo.main_state, [already_held])
    main_before = _canonical(history_rows(repo.main_state))

    report = merge_in(repo.main, repo.worktree)

    expected = main_before + _canonical(worktree_rows) - _canonical([already_held])
    assert _canonical(history_rows(repo.main_state)) == expected
    assert (report.copied, report.skipped) == (len(worktree_rows) - 1, 1)


def test_a_worktree_with_no_log_has_nothing_to_merge_and_that_is_not_a_failure(
    tmp_path: Path, repo: Repo
) -> None:
    empty = add_worktree(repo.main, "never-recorded")
    main_before = contents(repo.main_state)

    report = merge_in(repo.main, empty)

    assert (report.copied, report.exit_code, report.reason) == (0, 0, None)
    assert contents(repo.main_state) == main_before


def test_merge_in_under_the_off_mode_appends_nothing_and_says_so(repo: Repo) -> None:
    main_before = contents(repo.main_state)

    report = merge_in(repo.main, repo.worktree, mode="off")

    assert contents(repo.main_state) == main_before
    assert "off" in report.output, report.output


# -- A merge outside the command merges the log too -------------------------------------


@pytest.mark.parametrize("how", ["merge", "pull"])
def test_merging_a_worktree_branch_in_the_main_checkout_merges_its_log(
    repo: Repo, how: str
) -> None:
    install_merge_trigger(repo.main)
    commit_file(repo.worktree, "feature.txt", "feature\n", "add feature")
    worktree_rows = _canonical(history_rows(repo.worktree_state))

    result = merge_branch(repo.main, branch_of(WORKTREE), how=how)

    assert result.returncode == 0, result.stderr
    assert worktree_rows - _canonical(history_rows(repo.main_state)) == Counter()


# -- Merged rows keep their identity and mode -------------------------------------------


def test_copied_rows_keep_every_field_their_project_and_their_recording_mode(repo: Repo) -> None:
    worktree_rows = history_rows(repo.worktree_state)

    merge_in(repo.main, repo.worktree)

    copied = [r for r in history_rows(repo.main_state) if r.get("session_id") == WORKTREE_SESSION]
    assert _canonical(copied) == _canonical(
        [r for r in worktree_rows if r.get("session_id") == WORKTREE_SESSION]
    )
    assert {r["project"] for r in copied} == {WORKTREE}
    assert {r.get("log_mode") for r in copied} == {"standard"}
    legacy = [r for r in history_rows(repo.main_state) if r == LEGACY_ROW]
    assert [("log_mode" in r) for r in legacy] == [False]


# -- Merge-in is repeatable without duplicates ------------------------------------------


def test_a_second_merge_in_copies_nothing(repo: Repo) -> None:
    merge_in(repo.main, repo.worktree)
    after_first = contents(repo.main_state)

    report = merge_in(repo.main, repo.worktree)

    assert report.copied == 0
    assert contents(repo.main_state) == after_first


def test_a_merge_in_after_the_main_log_rotated_copies_nothing(repo: Repo) -> None:
    merge_in(repo.main, repo.worktree)
    rotate(repo.session(MAIN_SESSION, repo.main), repo.main_state, 1)

    report = merge_in(repo.main, repo.worktree)

    assert report.copied == 0
    held = _canonical(history_rows(repo.main_state))
    assert {held[row] for row in _canonical(history_rows(repo.worktree_state))} == {1}


@pytest.mark.parametrize(
    ("field", "other_value"),
    [
        ("agent_id", "another-agent-0002"),
        ("tool_name", "Edit"),
        ("hook", "commit_gate"),
        ("timestamp", "2026-09-20T10:00:00.000001+00:00"),
    ],
)
def test_merge_in_skips_only_rows_equal_to_one_the_main_log_holds(
    repo: Repo, field: str, other_value: str
) -> None:
    held = {
        "timestamp": "2026-09-20T10:00:00+00:00",
        "event_type": "gate_fire",
        "agent_id": "g1",
        "tool_name": "Bash",
        "hook": "id_citation",
        "project": WORKTREE,
    }
    reordered = json.dumps(dict(reversed(list(held.items()))), indent=None, separators=(", ", ": "))
    append_lines(repo.main_state, [reordered])
    append_rows(repo.worktree_state, [held, {**held, field: other_value}])
    main_before = _canonical(history_rows(repo.main_state))

    merge_in(repo.main, repo.worktree)

    after = _canonical(history_rows(repo.main_state))
    assert after[json.dumps(held, sort_keys=True)] == 1
    assert after[json.dumps({**held, field: other_value}, sort_keys=True)] == 1
    assert (
        sum(after.values()) - sum(main_before.values())
        == len(history_rows(repo.worktree_state)) - 1
    )


def test_rows_recorded_after_an_earlier_merge_in_are_copied_by_the_next(repo: Repo) -> None:
    merge_in(repo.main, repo.worktree)
    repo.session(LATER_SESSION, repo.worktree).session_start()

    report = merge_in(repo.main, repo.worktree)

    later_rows = [
        r for r in history_rows(repo.worktree_state) if r.get("session_id") == LATER_SESSION
    ]
    assert report.copied == len(later_rows) > 0
    assert session_ids_in(repo.main_state).count(LATER_SESSION) == 1


# -- The worktree's own log is left intact ----------------------------------------------


def test_merge_in_leaves_every_worktree_segment_byte_for_byte_unchanged(repo: Repo) -> None:
    before = contents(repo.worktree_state)

    merge_in(repo.main, repo.worktree)

    assert contents(repo.worktree_state) == before


def test_the_worktree_keeps_recording_to_its_own_log_after_merge_in(repo: Repo) -> None:
    merge_in(repo.main, repo.worktree)

    repo.session(LATER_SESSION, repo.worktree).session_start()

    assert session_ids_in(repo.worktree_state).count(LATER_SESSION) == 1
    assert session_ids_in(repo.main_state).count(LATER_SESSION) == 0


# -- Merge-in shares the main log with rotation -----------------------------------------


def test_merged_rows_that_carry_the_main_log_past_its_cap_rotate_it_like_any_append(
    repo: Repo,
) -> None:
    fill_to_cap(repo.main_state, 90, extra_bytes=-4096)
    archives_before = len(listed_archives(repo.main_state))
    main_before = _canonical(history_rows(repo.main_state))

    merge_in(repo.main, repo.worktree)

    assert len(listed_archives(repo.main_state)) > archives_before
    assert active_log(repo.main_state).stat().st_size <= size_cap() + 4096
    assert _canonical(history_rows(repo.main_state)) == main_before + _canonical(
        history_rows(repo.worktree_state)
    )


# -- A log that cannot be merged degrades visibly ----------------------------------------


@pytest.mark.skipif(running_as_root(), reason="root reads a chmod-000 file")
def test_an_unreadable_worktree_log_copies_what_it_can_and_reports_why(repo: Repo) -> None:
    archived = [row for a in listed_archives(repo.worktree_state) for row in rows_of(a)]
    make_unreadable(active_log(repo.worktree_state))

    report = merge_in(repo.main, repo.worktree)

    assert report.reason, "an unreadable worktree log was not reported"
    assert report.copied == len(archived)
    assert _canonical(archived) - _canonical(history_rows(repo.main_state)) == Counter()


def test_malformed_worktree_lines_are_skipped_and_counted(repo: Repo) -> None:
    well_formed = history_rows(repo.worktree_state)
    append_lines(repo.worktree_state, ["{not json", '["an", "array"]'])

    report = merge_in(repo.main, repo.worktree)

    assert report.malformed == 2
    assert _canonical(well_formed) - _canonical(history_rows(repo.main_state)) == Counter()


@pytest.mark.skipif(running_as_root(), reason="root writes a read-only file")
def test_an_unwritable_main_log_is_reported_and_leaves_the_worktree_log_intact(
    repo: Repo,
) -> None:
    worktree_before = contents(repo.worktree_state)
    active_log(repo.main_state).chmod(0o444)
    repo.main_state.chmod(0o555)
    try:
        report = merge_in(repo.main, repo.worktree)
    finally:
        repo.main_state.chmod(0o755)
        active_log(repo.main_state).chmod(0o644)

    assert report.reason, "an unwritable main log was not reported"
    assert contents(repo.worktree_state) == worktree_before


@pytest.mark.skipif(running_as_root(), reason="root reads a chmod-000 file")
def test_a_worktree_log_that_cannot_be_merged_never_blocks_the_code_merge(repo: Repo) -> None:
    install_merge_trigger(repo.main)
    feature = commit_file(repo.worktree, "feature.txt", "feature\n", "add feature")
    make_unreadable(active_log(repo.worktree_state))

    result = merge_branch(repo.main, branch_of(WORKTREE), how="merge")

    assert result.returncode == 0, result.stderr
    assert contains_commit(repo.main, feature)
