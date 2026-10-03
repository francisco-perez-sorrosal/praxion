"""Tests for check_observation_log_health.py -- the log-health family, checks P09 to P14.

Cites: rules/swe/gate-liveness.md -- a CODE gate ships a canary proving it bites
on a known-bad input, not merely that it passes on the current good state. Each
check id has one canary here, built from the golden bad-case its module
docstring names, beside an inverse guard where the check could over-fire.

Every log is written by hand into `tmp_path`, so the tests need no git
repository except where a check reads the repository's worktrees; those tests
substitute the checkout listing, which the owner package pins on its own.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import check_observation_log_health as clh
import pytest

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
RECENT = (NOW - timedelta(hours=2)).isoformat()
LONG_AGO = (NOW - timedelta(days=400)).isoformat()
STALE = (NOW - clh.WORKTREE_AGE_LIMIT - timedelta(days=2)).isoformat()
SCRIPT = Path(clh.__file__)


def _row(event_type: str = "tool_use", *, at: str = RECENT, **extra: object) -> dict:
    return {"timestamp": at, "session_id": "s1", "event_type": event_type, **extra}


def _session(session_id: str, source: object = "default", *, at: str = RECENT) -> dict:
    row = _row("session_start", at=at, session_id=session_id)
    if source is not None:
        row["log_mode_source"] = source
    return row


def _write(state_dir: Path, rows: list[dict], *, name: str | None = None, extra: str = "") -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / (name or clh.reader.LOG_FILENAME)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows) + extra, encoding="utf-8")
    return path


def _archive(state_dir: Path, position: int, rows: list[dict]) -> Path:
    active = clh.reader.log_path(state_dir)
    return _write(state_dir, rows, name=clh.retention.archive_path(active, position).name)


def _state(root: Path) -> Path:
    return root / clh.AI_STATE_REL


def _run(root: Path, now: datetime = NOW) -> dict:
    return clh.classify(root, now)


def _warnings(report: dict, check: str) -> list[dict]:
    return [f for f in report["findings"] if f["check"] == check and f["severity"] == "warn"]


def _information(report: dict, check: str) -> list[dict]:
    return [f for f in report["findings"] if f["check"] == check and f["severity"] == "info"]


def _a_main_with_worktrees(monkeypatch: pytest.MonkeyPatch, root: Path, *names: str) -> list[Path]:
    """Make the listing answer `root` as the main checkout plus a worktree per name."""
    worktrees = [root / "worktrees" / name for name in names]
    entries = [clh.checkouts.Checkout(root, _state(root), root.name, True, "abc")] + [
        clh.checkouts.Checkout(w, _state(w), w.name, False, "def") for w in worktrees
    ]
    monkeypatch.setattr(
        clh.checkouts,
        "repository_checkouts",
        lambda _root: clh.checkouts.CheckoutListing(entries, None),
    )
    return worktrees


# -- A canary per check: each check, called directly, flags its golden bad-case -------------------


def test_canary_p09_flags_a_gap_between_two_present_archives(tmp_path: Path) -> None:
    state = _state(tmp_path)
    _write(state, [_row()])
    _archive(state, 1, [_row()])
    _archive(state, 3, [_row()])

    outcome = clh.check_archive_coverage(clh.read_log(state), clh.current_policy())

    assert [f["entity"] for f in outcome.findings if f["severity"] == "warn"] == [
        str(clh.retention.archive_path(clh.reader.log_path(state), 2))
    ]


def test_canary_p10_flags_an_active_log_more_than_one_append_past_the_cap(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    one = len(json.dumps(_row())) + 1
    _write(state, [_row()] * 4)
    policy = clh.Policy(5, clh.retention.HISTORY_TARGET, 3 * one, clh.WORKTREE_AGE_LIMIT)

    outcome = clh.check_rotation_state(clh.read_log(state), policy)

    assert [f["severity"] for f in outcome.findings] == ["warn", "info"]


def test_canary_p11_flags_a_line_that_is_not_one_json_object(tmp_path: Path) -> None:
    state = _state(tmp_path)
    _write(state, [_row()], extra='["an", "array"]\n')

    outcome = clh.check_segment_integrity(clh.read_log(state))

    (warning,) = [f for f in outcome.findings if f["severity"] == "warn"]
    assert warning["detail"]["lines"] == [2]


def test_canary_p12_reports_helpers_as_information_and_never_flags_them(tmp_path: Path) -> None:
    state = _state(tmp_path)
    _write(state, [_row("helper_stop", agent_id="h1"), _row("agent_stop", agent_id="a1")])

    outcome = clh.check_helper_share(clh.read_log(state))

    assert [f["severity"] for f in outcome.findings] == ["info"]
    assert outcome.examined["share"] == 0.5


def test_canary_p13_flags_a_session_recorded_with_an_invalid_setting(tmp_path: Path) -> None:
    state = _state(tmp_path)
    _write(state, [_session("typo", clh._INVALID_SETTING_SOURCE), _session("fine")])

    outcome = clh.check_mode_source(clh.read_log(state))

    assert [f["entity"] for f in outcome.findings if f["severity"] == "warn"] == ["typo"]


def test_canary_p14_flags_a_stale_worktree_log_the_main_log_lacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (worktree,) = _a_main_with_worktrees(monkeypatch, tmp_path, "stale-wt")
    _worktree_log(worktree, newest=STALE)

    outcome = clh.check_unmerged_worktrees(tmp_path, clh.current_policy(), NOW)

    assert [f["detail"]["worktree"] for f in outcome.findings if f["severity"] == "warn"] == [
        "stale-wt"
    ]


# -- The envelope ------------------------------------------------------------------------------


def test_every_check_id_has_an_entry_in_every_envelope_map(tmp_path: Path) -> None:
    report = _run(tmp_path)

    assert report["checks"] == list(clh.CHECK_IDS)
    for key in ("skipped", "examined", "bound"):
        assert sorted(report[key]) == sorted(clh.CHECK_IDS), key


def test_the_policy_judged_against_is_stated_even_when_every_check_is_skipped(
    tmp_path: Path,
) -> None:
    report = _run(tmp_path)

    assert report["judged_against"] == {
        "archive_count": clh.retention.ARCHIVE_COUNT,
        "history_target_days": clh.retention.HISTORY_TARGET.days,
        "size_cap_bytes": clh.retention.SIZE_CAP_BYTES,
        "worktree_age_limit_days": clh.WORKTREE_AGE_LIMIT.days,
    }


# -- The three named skips ---------------------------------------------------------------------


@pytest.mark.parametrize("check_id", ["P09", "P10", "P11", "P12", "P13"])
def test_an_absent_log_skips_each_log_reading_check_as_substrate_absent(
    tmp_path: Path, check_id: str
) -> None:
    report = _run(tmp_path)

    skipped = report["skipped"][check_id]
    assert skipped["reason"] == clh.SKIP_ABSENT
    assert report["examined"][check_id] is None


def test_a_log_unreadable_in_every_segment_skips_as_reader_unreachable(tmp_path: Path) -> None:
    (_state(tmp_path) / clh.reader.LOG_FILENAME).mkdir(parents=True)  # a directory is unreadable

    report = _run(tmp_path)

    assert {report["skipped"][c]["reason"] for c in clh.CHECK_IDS[:5]} == {clh.SKIP_UNREACHABLE}
    assert report["skipped"]["P09"]["detail"].startswith("unreadable:")


def test_an_empty_log_skips_as_carrying_no_history(tmp_path: Path) -> None:
    _write(_state(tmp_path), [])

    report = _run(tmp_path)

    assert {report["skipped"][c]["reason"] for c in clh.CHECK_IDS[:5]} == {clh.SKIP_NO_HISTORY}


def test_a_log_of_only_malformed_lines_is_not_skipped_and_warns(tmp_path: Path) -> None:
    _write(_state(tmp_path), [], extra="{not json\n")

    report = _run(tmp_path)

    assert report["skipped"]["P11"] is None
    assert len(_warnings(report, "P11")) == 1
    assert report["examined"]["P12"]["share"] is None


# -- P09 archive coverage ----------------------------------------------------------------------


def test_p09_a_missing_position_between_two_present_archives_warns_as_a_pending_rotation(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    _write(state, [_row()])
    _archive(state, 1, [_row()])
    _archive(state, 3, [_row()])

    report = _run(tmp_path)

    (warning,) = _warnings(report, "P09")
    assert warning["entity"].endswith(".2")
    assert "pending" in warning["message"]
    assert "lost" not in warning["message"].replace("nothing is lost", "")
    assert report["examined"]["P09"]["missing"] == [warning["entity"]]


def test_p09_an_archive_past_the_policy_count_warns_naming_it(tmp_path: Path) -> None:
    state = _state(tmp_path)
    _write(state, [_row()])
    surplus = clh.retention.ARCHIVE_COUNT + 1
    _archive(state, 1, [_row(at=LONG_AGO)])  # a span past the history target: no coverage warning
    for position in range(2, surplus + 1):
        _archive(state, position, [_row()])

    report = _run(tmp_path)

    warnings = _warnings(report, "P09")
    assert [Path(w["entity"]).name.rsplit(".", 1)[1] for w in warnings] == [str(surplus)]
    assert report["examined"]["P09"]["surplus"] == [warnings[0]["entity"]]


def test_p09_a_full_sequence_spanning_less_than_the_history_target_warns_once(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    _write(state, [_row()])
    for position in range(1, clh.retention.ARCHIVE_COUNT + 1):
        _archive(state, position, [_row()])

    report = _run(tmp_path)

    (warning,) = _warnings(report, "P09")
    assert "history target" in warning["message"]


def test_p09_a_full_sequence_spanning_the_history_target_does_not_warn(tmp_path: Path) -> None:
    state = _state(tmp_path)
    _write(state, [_row()])
    _archive(state, 1, [_row(at=LONG_AGO)])
    for position in range(2, clh.retention.ARCHIVE_COUNT + 1):
        _archive(state, position, [_row()])

    assert _warnings(_run(tmp_path), "P09") == []


def test_p09_a_short_sequence_below_the_count_is_information_only(tmp_path: Path) -> None:
    state = _state(tmp_path)
    _write(state, [_row()])
    _archive(state, 1, [_row(at=LONG_AGO)])

    report = _run(tmp_path)

    assert _warnings(report, "P09") == []
    assert report["examined"]["P09"] == {
        "archive_count": 1,
        "oldest": LONG_AGO,
        "newest": RECENT,
        "missing": [],
        "surplus": [],
    }
    assert len(_information(report, "P09")) == 1


def test_p09_a_log_of_untimed_rows_reports_null_times_and_no_span_warning(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    _write(state, [{"event_type": "tool_use"}])
    for position in range(1, clh.retention.ARCHIVE_COUNT + 1):
        _archive(state, position, [{"event_type": "tool_use"}])

    report = _run(tmp_path)

    assert report["examined"]["P09"]["oldest"] is None
    assert _warnings(report, "P09") == []


# -- P10 rotation state ------------------------------------------------------------------------


def _log_of_rows_filling(state: Path, rows: int) -> tuple[int, int]:
    """Write `rows` equal-size rows; returns (the size of one row with its newline, the log size)."""
    one = len(json.dumps(_row(pad="x" * 40))) + 1
    path = _write(state, [_row(pad="x" * 40)] * rows)
    return one, path.stat().st_size


def test_p10_an_active_log_more_than_one_append_past_the_cap_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    one, _ = _log_of_rows_filling(_state(tmp_path), 4)
    monkeypatch.setattr(clh.retention, "SIZE_CAP_BYTES", 3 * one)

    report = _run(tmp_path)

    assert len(_warnings(report, "P10")) == 1
    assert report["examined"]["P10"] == {"active_bytes": 4 * one, "cap_bytes": 3 * one}


def test_p10_the_append_that_crossed_the_cap_is_normal_and_does_not_warn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    one, size = _log_of_rows_filling(_state(tmp_path), 3)
    monkeypatch.setattr(clh.retention, "SIZE_CAP_BYTES", 2 * one + 1)  # 3 rows cross it, 2 do not

    report = _run(tmp_path)

    assert size >= clh.retention.SIZE_CAP_BYTES
    assert _warnings(report, "P10") == []
    assert len(_information(report, "P10")) == 1


# -- P11 segment integrity ---------------------------------------------------------------------


def test_p11_malformed_lines_warn_per_segment_with_count_and_line_numbers(tmp_path: Path) -> None:
    state = _state(tmp_path)
    path = _write(state, [_row()])
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n" + json.dumps(_row()) + '\n["an", "array"]\n')
    _archive(state, 1, [_row()])

    warnings = _warnings(_run(tmp_path), "P11")

    (warning,) = warnings
    assert warning["detail"] == {"segment": str(path), "count": 2, "lines": [2, 4]}
    assert path.name in warning["message"]


def test_p11_the_listed_line_numbers_are_capped_but_the_count_is_not(tmp_path: Path) -> None:
    total = clh.MAX_LINE_NUMBERS_LISTED + 5
    _write(_state(tmp_path), [_row()], extra="{bad\n" * total)

    (warning,) = _warnings(_run(tmp_path), "P11")

    assert warning["detail"]["count"] == total
    assert len(warning["detail"]["lines"]) == clh.MAX_LINE_NUMBERS_LISTED
    assert "listed" in warning["message"]


def test_p11_an_unreadable_segment_warns_and_the_other_segments_are_still_judged(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    _write(state, [_session("typo", clh._INVALID_SETTING_SOURCE)])
    broken = clh.retention.archive_path(clh.reader.log_path(state), 1)
    broken.mkdir()

    report = _run(tmp_path)

    (warning,) = _warnings(report, "P11")
    assert warning["detail"]["segment"] == str(broken)
    assert report["examined"]["P11"]["unreadable"] == [str(broken)]
    assert report["skipped"]["P13"] is None
    assert [w["entity"] for w in _warnings(report, "P13")] == ["typo"]


def test_p11_a_clean_log_has_no_warning(tmp_path: Path) -> None:
    _write(_state(tmp_path), [_row(), _row()])

    assert _warnings(_run(tmp_path), "P11") == []


# -- P12 helper share --------------------------------------------------------------------------


def _legacy_helper_stop() -> dict:
    return _row(
        "agent_stop", agent_id="h4", start_correlation="unobserved-agent", usage_source=None
    )


def test_p12_helper_share_counts_new_and_legacy_helpers_over_all_stops(tmp_path: Path) -> None:
    rows = [_row("helper_stop", agent_id=f"h{n}") for n in range(3)]
    rows += [_legacy_helper_stop(), _row("agent_stop", agent_id="a1", tokens_out=5)]
    rows += [_row("agent_stop", agent_id="a2", start_correlation="paired")]
    _write(_state(tmp_path), rows)

    figures = _run(tmp_path)["examined"]["P12"]

    assert (figures["helper_stops"], figures["agent_stops"]) == (4, 2)
    assert figures["share"] == pytest.approx(4 / 6, abs=0.001)


def test_p12_is_never_a_warning_even_when_every_stop_is_a_helper(tmp_path: Path) -> None:
    _write(_state(tmp_path), [_row("helper_stop", agent_id=f"h{n}") for n in range(5)])

    report = _run(tmp_path)

    assert _warnings(report, "P12") == []
    assert report["examined"]["P12"]["share"] == 1.0
    assert len(_information(report, "P12")) == 1


def test_p12_a_log_with_no_stops_reports_a_null_share(tmp_path: Path) -> None:
    _write(_state(tmp_path), [_row()])

    assert _run(tmp_path)["examined"]["P12"] == {
        "helper_stops": 0,
        "agent_stops": 0,
        "share": None,
    }


# -- P13 recorded mode source ------------------------------------------------------------------


def test_p13_sessions_are_counted_per_recorded_source_and_before_modes(tmp_path: Path) -> None:
    rows = [
        _session("d1"),
        _session("d2"),
        _session("set1", "setting"),
        _session("typo", clh._INVALID_SETTING_SOURCE),
        _session("old", None),
    ]
    _write(_state(tmp_path), rows)

    figures = _run(tmp_path)["examined"]["P13"]

    assert figures == {
        "sessions": 5,
        "by_source": {"default": 2, "setting": 1, "invalid-setting": 1},
        "before_modes": 1,
    }


def test_p13_each_invalid_setting_session_warns_naming_it_and_no_other(tmp_path: Path) -> None:
    rows = [
        _session("typo-1", clh._INVALID_SETTING_SOURCE),
        _session("fine"),
        _session("typo-2", clh._INVALID_SETTING_SOURCE),
    ]
    _write(_state(tmp_path), rows)

    warnings = _warnings(_run(tmp_path), "P13")

    assert sorted(w["entity"] for w in warnings) == ["typo-1", "typo-2"]


def test_p13_a_session_recorded_under_the_legacy_kill_switch_warns(tmp_path: Path) -> None:
    _write(_state(tmp_path), [_session("ghost", clh._LEGACY_DISABLE_SOURCE)])

    (warning,) = _warnings(_run(tmp_path), "P13")

    assert warning["entity"] == "ghost"
    assert "contradicts" in warning["message"]


def test_p13_a_session_start_repeated_for_one_session_warns_once(tmp_path: Path) -> None:
    rows = [_session("typo", clh._INVALID_SETTING_SOURCE)] * 2
    _write(_state(tmp_path), rows)

    assert len(_warnings(_run(tmp_path), "P13")) == 1


def test_p13_default_and_setting_sources_raise_no_warning(tmp_path: Path) -> None:
    _write(_state(tmp_path), [_session("a"), _session("b", "setting"), _session("c", None)])

    assert _warnings(_run(tmp_path), "P13") == []


# -- P14 unmerged worktree logs ----------------------------------------------------------------


def _worktree_log(worktree: Path, *, newest: str, rows: int = 3) -> list[dict]:
    log = [_row(at=newest, session_id=f"{worktree.name}-{n}") for n in range(rows)]
    _write(_state(worktree), log)
    return log


def test_p14_a_stale_worktree_with_rows_the_main_log_lacks_warns_with_count_and_newest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (worktree,) = _a_main_with_worktrees(monkeypatch, tmp_path, "stale-wt")
    _write(_state(tmp_path), [_row()])
    _worktree_log(worktree, newest=STALE)

    report = _run(tmp_path)

    (warning,) = _warnings(report, "P14")
    assert warning["detail"] == {"worktree": "stale-wt", "rows": 3, "newest": STALE}
    assert report["examined"]["P14"]["unmerged"] == [warning["detail"]]
    assert "merge_worktree_log.py" in warning["message"]


def test_p14_a_worktree_inside_the_age_limit_is_in_flight_not_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (worktree,) = _a_main_with_worktrees(monkeypatch, tmp_path, "busy-wt")
    _write(_state(tmp_path), [_row()])
    _worktree_log(worktree, newest=RECENT)

    report = _run(tmp_path)

    assert _warnings(report, "P14") == []
    assert report["examined"]["P14"]["in_flight"] == ["busy-wt"]
    assert any("busy-wt" in f["message"] for f in _information(report, "P14"))


def test_p14_a_worktree_whose_rows_are_all_in_the_main_log_raises_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (worktree,) = _a_main_with_worktrees(monkeypatch, tmp_path, "merged-wt")
    _write(_state(tmp_path), _worktree_log(worktree, newest=STALE))

    report = _run(tmp_path)

    assert _warnings(report, "P14") == []
    assert report["examined"]["P14"]["unmerged"] == []
    assert report["examined"]["P14"]["in_flight"] == []


def test_p14_an_archive_of_the_main_log_counts_as_having_the_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (worktree,) = _a_main_with_worktrees(monkeypatch, tmp_path, "rotated-wt")
    _archive(_state(tmp_path), 1, _worktree_log(worktree, newest=STALE))

    assert _warnings(_run(tmp_path), "P14") == []


def test_p14_an_absent_main_log_still_runs_and_every_worktree_row_is_unmerged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (worktree,) = _a_main_with_worktrees(monkeypatch, tmp_path, "stale-wt")
    _worktree_log(worktree, newest=STALE)

    report = _run(tmp_path)

    assert report["skipped"]["P14"] is None
    assert report["skipped"]["P09"]["reason"] == clh.SKIP_ABSENT
    assert len(_warnings(report, "P14")) == 1


def test_p14_a_worktree_without_a_log_raises_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _a_main_with_worktrees(monkeypatch, tmp_path, "empty-wt")

    report = _run(tmp_path)

    assert report["skipped"]["P14"] is None
    assert report["examined"]["P14"]["worktrees"] == 1
    assert _warnings(report, "P14") == []


def test_p14_a_worktree_log_of_untimed_rows_cannot_be_in_flight_and_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (worktree,) = _a_main_with_worktrees(monkeypatch, tmp_path, "untimed-wt")
    _write(_state(worktree), [{"event_type": "tool_use", "n": 1}])

    (warning,) = _warnings(_run(tmp_path), "P14")

    assert warning["detail"]["newest"] is None


def test_p14_a_failed_checkout_listing_skips_as_reader_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        clh.checkouts,
        "repository_checkouts",
        lambda _root: clh.checkouts.CheckoutListing((), "git worktree list failed: boom"),
    )

    skipped = _run(tmp_path)["skipped"]["P14"]

    assert skipped["reason"] == clh.SKIP_UNREACHABLE
    assert "boom" in skipped["detail"]


def test_p14_a_directory_that_is_not_a_repository_skips_rather_than_passes(
    tmp_path: Path,
) -> None:
    assert _run(tmp_path)["skipped"]["P14"]["reason"] == clh.SKIP_UNREACHABLE


# -- The command -------------------------------------------------------------------------------


def _command(root: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *flags, "--repo-root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_json_run_prints_the_envelope_and_exits_zero_with_warnings(tmp_path: Path) -> None:
    _write(_state(tmp_path), [_session("typo", clh._INVALID_SETTING_SOURCE)])

    result = _command(tmp_path, "--json")

    assert result.returncode == 0
    assert [
        w["check"] for w in json.loads(result.stdout)["findings"] if w["severity"] == "warn"
    ] == ["P13"]


def test_the_check_flag_exits_one_on_a_warning_and_zero_on_a_skip(tmp_path: Path) -> None:
    assert _command(tmp_path, "--check").returncode == 0

    _write(_state(tmp_path), [_session("typo", clh._INVALID_SETTING_SOURCE)])

    assert _command(tmp_path, "--check").returncode == 1


def test_a_plugin_cache_root_is_refused_with_exit_two(tmp_path: Path) -> None:
    cache_root = tmp_path / "plugins" / "cache" / "owner" / "praxion" / "1.0.0"
    cache_root.mkdir(parents=True)

    assert _command(cache_root, "--json").returncode == 2


def test_the_human_form_names_each_skip_and_warning(tmp_path: Path) -> None:
    _write(_state(tmp_path), [_session("typo", clh._INVALID_SETTING_SOURCE)])

    text = clh._format_human(_run(tmp_path))

    assert "1 warning(s)" in text
    assert "typo" in text
    assert "P14: skipped (reader-unreachable)" in text


def test_check_ids_is_a_module_level_literal_of_the_six_ids() -> None:
    assert clh.CHECK_IDS == ("P09", "P10", "P11", "P12", "P13", "P14")
