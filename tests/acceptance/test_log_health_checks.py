"""The log-health family audits a checkout's log, its archives and its worktrees' logs.

Each check reports information and warnings apart: archive coverage against the
retention policy, rotation state, malformed lines per segment, the share of
helper stops, how each session's recording mode was chosen, and worktree logs
left unmerged past a stated age. A log the family cannot look at is a skip that
names exactly one of three substrate states, never a clean pass. The family
states the policy and the age limit it judged against.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tests.acceptance.drivers.log_health import (
    LOG_READING_CHECKS,
    ArchiveCoverage,
    Check,
    HelperShare,
    LogHealthReport,
    RotationState,
    Unmerged,
    archive_coverage,
    helper_share,
    in_flight_worktrees,
    judged_against,
    malformed_detail,
    mode_sources,
    rotation_state,
    run_log_health,
    unmerged_detail,
)
from tests.acceptance.drivers.log_rows import (
    agent_stop,
    costed_stop,
    helper_stop,
    legacy_helper_stop,
    session_start,
)
from tests.acceptance.drivers.log_segments import (
    LOG_NAME,
    active_log,
    append_lines,
    append_rows,
    archive_position_path,
    fill_to_cap,
    listed_archives,
    make_unreadable,
    now_iso,
    require_archive_positions,
    retention_archive_count,
    retention_history_target,
    rotate,
    rotate_times,
    running_as_root,
    size_cap,
    state_dir_of,
)
from tests.acceptance.drivers.observation_harness import HookHarness, Session
from tests.acceptance.drivers.repository import add_worktree, new_repository

REPO = "health-repo"
SESSION_ID = "5e551011-0000-4000-8000-0000000d0001"
OLDEST = "2026-09-01T00:00:00+00:00"
NEWEST = "2030-01-01T00:00:00+00:00"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return new_repository(tmp_path / REPO)


@pytest.fixture
def session(tmp_path: Path, repo: Path) -> Session:
    return Session(HookHarness(tmp_path / "harness"), SESSION_ID, repo)


def _rows(repo: Path, rows: list[dict]) -> None:
    append_rows(state_dir_of(repo), rows)


def _mentions(findings: list, text: str) -> bool:
    return any(text in finding.text() for finding in findings)


def _age_limit(tmp_path: Path) -> timedelta:
    """The worktree age limit the family states, read from a run over an empty repository."""
    return judged_against(
        run_log_health(new_repository(tmp_path / "probe-repo"))
    ).worktree_age_limit


# -- The family states what it judged against -----------------------------------------------


def test_the_family_reports_the_retention_policy_and_age_limit_it_judged_against(
    repo: Path,
) -> None:
    _rows(repo, [session_start("s1", at=OLDEST, project=REPO)])

    judged = judged_against(run_log_health(repo))

    assert (judged.archive_count, judged.history_target) == (
        retention_archive_count(),
        retention_history_target(),
    )
    assert judged.worktree_age_limit > timedelta(0)


# -- Archive coverage ---------------------------------------------------------------------------


def test_archive_coverage_reports_the_retained_span_and_archive_count(
    repo: Path, session: Session
) -> None:
    rotate_times(session, state_dir_of(repo), 2, at=OLDEST)
    _rows(repo, [session_start("newest-session", at=NEWEST, project=REPO)])

    coverage = archive_coverage(run_log_health(repo))

    assert coverage == ArchiveCoverage(
        2, datetime.fromisoformat(OLDEST), datetime.fromisoformat(NEWEST)
    )


def test_a_missing_archive_between_two_present_ones_warns_naming_it(
    repo: Path, session: Session
) -> None:
    require_archive_positions(3)
    rotate_times(session, state_dir_of(repo), 3)
    missing = listed_archives(state_dir_of(repo))[1]
    missing.unlink()

    report = run_log_health(repo)

    assert _mentions(report.warnings(Check.ARCHIVE_COVERAGE), missing.name), report.describe()


def test_more_archives_than_the_policy_keeps_warns(repo: Path, session: Session) -> None:
    kept = retention_archive_count()
    rotate_times(session, state_dir_of(repo), kept)
    surplus = archive_position_path(state_dir_of(repo), kept + 1)
    shutil.copyfile(listed_archives(state_dir_of(repo))[0], surplus)

    report = run_log_health(repo)

    assert report.warnings(Check.ARCHIVE_COVERAGE), report.describe()


def test_a_full_archive_sequence_spanning_less_than_the_history_target_warns(
    repo: Path, session: Session
) -> None:
    rotate_times(session, state_dir_of(repo), retention_archive_count())

    report = run_log_health(repo)

    assert report.warnings(Check.ARCHIVE_COVERAGE), report.describe()


def test_a_full_archive_sequence_spanning_the_history_target_raises_no_coverage_warning(
    repo: Path, session: Session
) -> None:
    long_ago = now_iso(-(retention_history_target() + timedelta(days=1)))
    rotate_times(session, state_dir_of(repo), retention_archive_count(), oldest_at=long_ago)

    report = run_log_health(repo)

    assert report.warnings(Check.ARCHIVE_COVERAGE) == []


# -- Rotation state ----------------------------------------------------------------------------


def test_rotation_state_reports_the_active_size_against_the_cap(repo: Path) -> None:
    _rows(repo, [session_start("s1", at=OLDEST, project=REPO)])

    state = rotation_state(run_log_health(repo))

    assert state == RotationState(active_log(state_dir_of(repo)).stat().st_size, size_cap())


def test_an_active_log_past_the_cap_by_more_than_one_append_warns(repo: Path) -> None:
    fill_to_cap(state_dir_of(repo), 1, at=OLDEST, extra_bytes=1_000_000)

    report = run_log_health(repo)

    assert report.warnings(Check.ROTATION_STATE), report.describe()


def test_an_active_log_below_the_cap_raises_no_rotation_warning(repo: Path) -> None:
    _rows(repo, [session_start("s1", at=OLDEST, project=REPO)])

    report = run_log_health(repo)

    assert report.warnings(Check.ROTATION_STATE) == []


# -- Malformed lines ---------------------------------------------------------------------------


def _log_with_malformed_lines_at_three_and_five(repo: Path) -> None:
    good = session_start("typo-session", at=OLDEST, project=REPO, source="invalid-setting")
    append_rows(state_dir_of(repo), [session_start("s1", at=OLDEST, project=REPO), good])
    append_lines(state_dir_of(repo), ["{not json"])
    append_rows(state_dir_of(repo), [session_start("s2", at=OLDEST, project=REPO)])
    append_lines(state_dir_of(repo), ['["an", "array"]'])
    append_rows(state_dir_of(repo), [session_start("s3", at=OLDEST, project=REPO)])


def test_malformed_lines_warn_per_segment_with_count_and_line_numbers(repo: Path) -> None:
    _log_with_malformed_lines_at_three_and_five(repo)

    warnings = run_log_health(repo).warnings(Check.MALFORMED_LINES)

    assert len(warnings) == 1, warnings
    assert LOG_NAME in warnings[0].text()
    assert malformed_detail(warnings[0]) == (2, (3, 5))


def test_a_segment_with_malformed_lines_still_has_its_well_formed_rows_judged(repo: Path) -> None:
    _log_with_malformed_lines_at_three_and_five(repo)

    report = run_log_health(repo)

    assert _mentions(report.warnings(Check.MODE_SOURCE), "typo-session"), report.describe()


# -- Helper share ------------------------------------------------------------------------------


def _stops(repo: Path) -> None:
    _rows(
        repo,
        [
            helper_stop("h1", at=OLDEST, project=REPO),
            helper_stop("h2", at=OLDEST, project=REPO),
            helper_stop("h3", at=OLDEST, project=REPO),
            legacy_helper_stop("h4", at=OLDEST, project=REPO),
            costed_stop("real-1", at=OLDEST, project=REPO),
            agent_stop("real-2", at=OLDEST, project=REPO),
        ],
    )


def test_helper_share_counts_new_and_legacy_helper_stops_as_information(repo: Path) -> None:
    _stops(repo)

    share = helper_share(run_log_health(repo))

    assert (share.helper_stops, share.agent_stops) == (4, 2)
    assert share == HelperShare(4, 2, pytest.approx(4 / 6, abs=0.01))


def test_helper_share_is_never_a_warning(repo: Path) -> None:
    _rows(repo, [helper_stop(f"h{n}", at=OLDEST, project=REPO) for n in range(5)])

    report = run_log_health(repo)

    assert report.warnings(Check.HELPER_SHARE) == []


# -- Recorded mode source ----------------------------------------------------------------------


def test_sessions_are_counted_per_recorded_mode_source(repo: Path) -> None:
    _rows(
        repo,
        [
            session_start("d1", at=OLDEST, project=REPO, source="default"),
            session_start("d2", at=OLDEST, project=REPO, source="default"),
            session_start("set1", at=OLDEST, project=REPO, source="setting"),
            session_start("typo-1", at=OLDEST, project=REPO, source="invalid-setting"),
            session_start("before-modes", at=OLDEST, project=REPO, source=None),
        ],
    )

    sources = mode_sources(run_log_health(repo))

    assert sources == {"default": 2, "setting": 1, "invalid-setting": 1, None: 1}


@pytest.mark.parametrize("session_id", ["typo-1", "typo-2"])
def test_each_session_recorded_with_an_invalid_setting_warns_naming_it(
    repo: Path, session_id: str
) -> None:
    _rows(
        repo,
        [
            session_start("typo-1", at=OLDEST, project=REPO, source="invalid-setting"),
            session_start("fine", at=OLDEST, project=REPO, source="default"),
            session_start("typo-2", at=OLDEST, project=REPO, source="invalid-setting"),
        ],
    )

    report = run_log_health(repo)

    assert _mentions(report.warnings(Check.MODE_SOURCE), session_id), report.describe()
    assert not _mentions(report.warnings(Check.MODE_SOURCE), "fine")


def test_a_row_recorded_under_the_legacy_kill_switch_warns(repo: Path) -> None:
    _rows(repo, [session_start("ghost-session", at=OLDEST, project=REPO, source="legacy-disable")])

    report = run_log_health(repo)

    assert _mentions(report.warnings(Check.MODE_SOURCE), "ghost-session"), report.describe()


# -- Unmerged worktree logs --------------------------------------------------------------------


def _worktree_with_rows(repo: Path, name: str, newest: str) -> Path:
    worktree = add_worktree(repo, name)
    append_rows(
        state_dir_of(worktree),
        [
            session_start(f"{name}-a", at=newest, project=name),
            session_start(f"{name}-b", at=newest, project=name),
            session_start(f"{name}-c", at=newest, project=name),
        ],
    )
    return worktree


def test_an_unmerged_worktree_log_older_than_the_age_limit_warns_with_its_count_and_newest_row(
    tmp_path: Path, repo: Path
) -> None:
    newest = now_iso(-(_age_limit(tmp_path) + timedelta(days=2)))
    _rows(repo, [session_start("main-session", at=now_iso(), project=REPO)])
    _worktree_with_rows(repo, "stale-wt", newest)

    warnings = run_log_health(repo).warnings(Check.UNMERGED_WORKTREES)

    assert [unmerged_detail(w) for w in warnings] == [
        Unmerged("stale-wt", 3, datetime.fromisoformat(newest))
    ]


def test_an_unmerged_worktree_log_within_the_age_limit_is_in_flight_not_a_warning(
    repo: Path,
) -> None:
    _rows(repo, [session_start("main-session", at=now_iso(), project=REPO)])
    _worktree_with_rows(repo, "busy-wt", now_iso(-timedelta(hours=1)))

    report = run_log_health(repo)

    assert report.warnings(Check.UNMERGED_WORKTREES) == []
    assert in_flight_worktrees(report) == ["busy-wt"]


def test_a_worktree_whose_rows_are_all_in_the_main_log_raises_nothing(
    tmp_path: Path, repo: Path
) -> None:
    newest = now_iso(-(_age_limit(tmp_path) + timedelta(days=2)))
    worktree = _worktree_with_rows(repo, "merged-wt", newest)
    append_lines(state_dir_of(repo), active_log(state_dir_of(worktree)).read_text().splitlines())

    report = run_log_health(repo)

    assert report.warnings(Check.UNMERGED_WORKTREES) == []


# -- Named substrate skips ---------------------------------------------------------------------


@pytest.mark.parametrize("check", LOG_READING_CHECKS, ids=lambda c: c.name.lower())
def test_an_absent_log_skips_each_log_reading_check_as_substrate_absent(
    repo: Path, check: Check
) -> None:
    report = run_log_health(repo)

    assert report.skip_reason(check) == "substrate absent", report.describe()


@pytest.mark.skipif(running_as_root(), reason="root reads a chmod-000 file")
@pytest.mark.parametrize("check", LOG_READING_CHECKS, ids=lambda c: c.name.lower())
def test_a_log_unreadable_in_every_segment_skips_each_log_reading_check_as_reader_unreachable(
    repo: Path, check: Check
) -> None:
    _rows(repo, [session_start("s1", at=OLDEST, project=REPO)])
    make_unreadable(active_log(state_dir_of(repo)))

    report = run_log_health(repo)

    assert report.skip_reason(check) == "reader unreachable", report.describe()


@pytest.mark.parametrize("check", LOG_READING_CHECKS, ids=lambda c: c.name.lower())
def test_an_empty_log_skips_each_log_reading_check_as_carrying_no_history(
    repo: Path, check: Check
) -> None:
    active_log(state_dir_of(repo)).write_text("", encoding="utf-8")

    report = run_log_health(repo)

    assert report.skip_reason(check) == "substrate carries no history", report.describe()


def test_an_absent_main_log_still_runs_the_unmerged_worktree_check(
    tmp_path: Path, repo: Path
) -> None:
    _worktree_with_rows(repo, "stale-wt", now_iso(-(_age_limit(tmp_path) + timedelta(days=2))))

    report = run_log_health(repo)

    assert report.skip_reason(Check.UNMERGED_WORKTREES) is None
    assert report.warnings(Check.UNMERGED_WORKTREES), report.describe()


@pytest.mark.skipif(running_as_root(), reason="root reads a chmod-000 file")
def test_a_partly_unreadable_log_warns_per_unreadable_segment_and_judges_the_rest(
    repo: Path, session: Session
) -> None:
    rotate(session, state_dir_of(repo), 1)
    archive = listed_archives(state_dir_of(repo))[0]
    make_unreadable(archive)
    _rows(repo, [session_start("typo-session", at=OLDEST, project=REPO, source="invalid-setting")])

    report: LogHealthReport = run_log_health(repo)

    assert _mentions(report.warnings(), archive.name), report.describe()
    assert _mentions(report.warnings(Check.MODE_SOURCE), "typo-session"), report.describe()
