"""The liveness judgement over a log it cannot read whole, with no import of the checker.

The mutation sensor copies a test file next to its target and cannot take one whose import chain
reads a repository path beside `__file__`; this file imports `kernel_liveness` and `kernel_ledger`
alone, so the sensor can pin the segment read.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
# hooks/ sits beside scripts/ in the checkout and not in the sensor's copy: walk up to find it.
for ancestor in Path(__file__).resolve().parents:
    if (ancestor / "hooks" / "_observation_log").is_dir():
        sys.path.insert(0, str(ancestor / "hooks"))
        break

import kernel_ledger as kl  # noqa: E402
import kernel_liveness as kv  # noqa: E402
from _observation_log import reader, retention  # noqa: E402

ADOPTED = datetime(2026, 10, 12, tzinfo=timezone.utc)
BEFORE = datetime(2026, 9, 1, tzinfo=timezone.utc)
INSIDE = datetime(2026, 10, 14, tzinfo=timezone.utc)
LATER = datetime(2026, 10, 15, tzinfo=timezone.utc)
RESEARCHER = {"researcher": kl.Adoption("trial", ADOPTED)}


def fact(name: str, when: datetime | None, problem: str | None = None) -> kv.SegmentFact:
    return kv.SegmentFact(Path(name), when, problem)


def lost(
    *segments: kv.SegmentFact,
    adoptions: dict[str, kl.Adoption] | None = None,
    since: datetime | None = None,
) -> list[tuple[str, str]]:
    found = kv.liveness_report(RESEARCHER if adoptions is None else adoptions, [], since, segments)
    return [(segment.path.name, segment.reason) for segment in found.lost]


def start_row(agent_id: str, when: datetime) -> dict:
    return {
        "event_type": kv.SPAWN_ROW,
        "agent_id": agent_id,
        "agent_type": "praxion:researcher",
        "timestamp": when.isoformat(),
    }


# -- Which segments the window keeps ----------------------------------------------------------------


def test_a_segment_not_read_whole_inside_the_window_is_lost_with_its_reason() -> None:
    assert lost(fact("log.1", INSIDE, "unreadable: denied")) == [("log.1", "unreadable: denied")]


def test_a_segment_not_read_whole_wholly_before_the_window_is_not_lost() -> None:
    assert lost(fact("log.1", BEFORE, "unreadable: denied")) == []


def test_a_segment_last_appended_as_the_window_opens_is_inside_it() -> None:
    assert lost(fact("log.1", ADOPTED, "missing")) == [("log.1", "missing")]


def test_a_segment_read_whole_is_never_lost() -> None:
    assert lost(fact("log.1", INSIDE)) == []


def test_the_window_opens_at_the_earliest_record_start_of_any_adopted_role() -> None:
    adoptions = {**RESEARCHER, "tester": kl.Adoption("trial", BEFORE)}

    assert lost(
        fact("log.1", datetime(2026, 9, 2, tzinfo=timezone.utc), "missing"), adoptions=adoptions
    ) == [("log.1", "missing")]


def test_since_moves_the_window_open_later_than_a_record_start() -> None:
    assert lost(fact("log.1", INSIDE, "missing"), since=LATER) == []


def test_since_before_a_record_start_does_not_open_the_window_earlier() -> None:
    assert lost(fact("log.1", BEFORE, "missing"), since=BEFORE) == []


def test_no_adopted_role_opens_no_window() -> None:
    assert lost(fact("log.1", INSIDE, "missing"), adoptions={}) == []


def test_every_segment_lost_inside_the_window_is_named_oldest_first() -> None:
    assert lost(
        fact("log.2", INSIDE, "missing"), fact("log.1", INSIDE, "denied"), fact("log", LATER)
    ) == [
        ("log.2", "missing"),
        ("log.1", "denied"),
    ]


# -- A segment whose own time is unknown is dated by the next newer one -----------------------------


def test_a_gap_newer_than_the_window_start_is_lost() -> None:
    gap = fact("log.2", None, "missing")

    assert lost(fact("log.3", BEFORE), gap, fact("log.1", INSIDE), fact("log", INSIDE)) == [
        ("log.2", "missing")
    ]


def test_a_gap_beneath_only_segments_older_than_the_window_is_not_lost() -> None:
    assert lost(fact("log.3", BEFORE), fact("log.2", None, "missing"), fact("log.1", BEFORE)) == []


def test_a_gap_with_no_dated_segment_above_it_may_reach_into_the_window() -> None:
    assert lost(fact("log.2", None, "missing"), fact("log.1", None)) == [("log.2", "missing")]


def test_a_gap_below_a_dated_segment_is_dated_by_it_and_not_by_an_older_one() -> None:
    assert lost(fact("log.3", INSIDE), fact("log.2", None, "missing"), fact("log.1", BEFORE)) == []


def test_two_gaps_in_a_row_take_the_time_of_the_nearest_dated_segment_above() -> None:
    gaps = (fact("log.3", None, "missing"), fact("log.2", None, "missing"))

    assert lost(*gaps, fact("log.1", INSIDE)) == [("log.3", "missing"), ("log.2", "missing")]
    assert lost(*gaps, fact("log.1", BEFORE)) == []


# -- The report keeps its findings and is not clean when something is lost --------------------------


def test_the_findings_of_the_segments_read_are_kept_beside_the_lost_ones() -> None:
    found = kv.liveness_report(
        RESEARCHER, [start_row("a1", INSIDE)], None, [fact("log.1", INSIDE, "missing")]
    )

    assert ([f.kind for f in found.findings], found.judged, len(found.lost)) == (
        ["liveness-missing-row"],
        1,
        1,
    )


def test_a_report_over_segments_all_read_whole_loses_nothing() -> None:
    found = kv.liveness_report(RESEARCHER, [], None, [fact("log.1", INSIDE)])

    assert found.lost == ()


def test_a_report_given_no_segment_facts_loses_nothing() -> None:
    assert kv.liveness_report(RESEARCHER, [], None).lost == ()


# -- Reading a log from disk ------------------------------------------------------------------------


def write_segment(path: Path, when: datetime, *lines: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = json.dumps({"timestamp": when.isoformat(), "event_type": "padding"})
    path.write_text("\n".join([row, *lines]) + "\n")
    os.utime(path, (when.timestamp(), when.timestamp()))
    return path


def archive(project: Path, position: int, when: datetime, *lines: str) -> Path:
    log = reader.log_path(project / kv.STATE_DIR)
    return write_segment(retention.archive_path(log, position), when, *lines)


def active(project: Path, when: datetime, *lines: str) -> Path:
    return write_segment(reader.log_path(project / kv.STATE_DIR), when, *lines)


def names(facts: list[kv.SegmentFact]) -> list[str]:
    return [fact.path.name for fact in facts]


def test_the_log_is_read_oldest_segment_first_with_the_active_log_last(tmp_path: Path) -> None:
    active(tmp_path, LATER)
    archive(tmp_path, 1, INSIDE)
    archive(tmp_path, 2, BEFORE)

    _, facts = kv._read_log(tmp_path)

    assert names(facts) == [
        f"{reader.LOG_FILENAME}.2",
        f"{reader.LOG_FILENAME}.1",
        reader.LOG_FILENAME,
    ]


def test_a_gap_in_the_archive_positions_is_a_missing_segment_in_its_place(tmp_path: Path) -> None:
    active(tmp_path, LATER)
    archive(tmp_path, 3, BEFORE)
    archive(tmp_path, 1, INSIDE)

    rows, facts = kv._read_log(tmp_path)

    gap = [fact for fact in facts if fact.problem == kv.MISSING]
    assert (names(facts), [(f.path.name, f.last_append) for f in gap], len(rows)) == (
        [f"{reader.LOG_FILENAME}.{n}" for n in (3, 2, 1)] + [reader.LOG_FILENAME],
        [(f"{reader.LOG_FILENAME}.2", None)],
        3,
    )


def test_a_segment_read_whole_carries_its_last_append_and_no_problem(tmp_path: Path) -> None:
    active(tmp_path, INSIDE)

    rows, facts = kv._read_log(tmp_path)

    assert ([(f.last_append, f.problem) for f in facts], len(rows)) == ([(INSIDE, None)], 1)


def test_a_segment_with_an_unparseable_line_is_a_problem_but_keeps_its_good_rows(
    tmp_path: Path,
) -> None:
    active(tmp_path, INSIDE, "{not json")

    rows, facts = kv._read_log(tmp_path)

    assert ([f.problem for f in facts], len(rows)) == (["unparseable lines [2]"], 1)


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads a file whatever its mode"
)
def test_an_unreadable_segment_is_a_problem_and_the_others_are_still_read(tmp_path: Path) -> None:
    old = archive(tmp_path, 1, BEFORE)
    active(tmp_path, INSIDE)
    old.chmod(0o000)

    try:
        rows, facts = kv._read_log(tmp_path)
    finally:
        old.chmod(0o600)

    assert ([(f.path.name, bool(f.problem)) for f in facts], len(rows)) == (
        [(f"{reader.LOG_FILENAME}.1", True), (reader.LOG_FILENAME, False)],
        1,
    )


def test_a_project_with_no_log_is_refused_rather_than_judged_empty(tmp_path: Path) -> None:
    (tmp_path / kv.STATE_DIR).mkdir()

    with pytest.raises(kv.km.KernelModelError, match="nothing to judge"):
        kv._read_log(tmp_path)


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root lists a directory whatever its mode"
)
def test_a_state_directory_that_cannot_be_listed_is_refused_naming_why(tmp_path: Path) -> None:
    state = tmp_path / kv.STATE_DIR
    state.mkdir()
    state.chmod(0o000)

    try:
        with pytest.raises(kv.km.KernelModelError, match="cannot be listed: .+"):
            kv._read_log(tmp_path)
    finally:
        state.chmod(0o755)


def test_a_segment_missing_its_time_is_a_fact_without_one(tmp_path: Path) -> None:
    assert kv._last_append(tmp_path / "gone") is None
