"""Canaries for the liveness mode: a spawn of an adopted role left its kernel row."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _kernel_checker_testkit as kit  # noqa: E402
import check_kernel_manifest as cb  # noqa: E402
import kernel_ledger as kl  # noqa: E402
import kernel_liveness as kv  # noqa: E402
from _kernel_checker_testkit import (  # noqa: E402
    AT,
    NOON,
    SCRIPT,
    commit_all,
    delivered,
    run_checker,
    started,
    switched_row,
    trial_row,
    write_ledger,
    write_log,
)

# pytest finds a fixture by name in the module that uses it
repo = kit.repo
template = kit.template

# -- Liveness: a spawn of an adopted role left its kernel row -----------------------------------

ADOPTED = datetime(2026, 10, 12, tzinfo=timezone.utc)  # the day the records below began


def adopted(since: datetime = ADOPTED, **roles: str) -> dict[str, kl.Adoption]:
    return {role: kl.Adoption(status, since) for role, status in roles.items()}


def report(adoptions: dict[str, kl.Adoption], *rows: dict, since: datetime | None = None):
    return cb.liveness_report(adoptions, rows, since)


def silent(adoptions: dict[str, kl.Adoption], *rows: dict) -> list[tuple[str, str]]:
    return [(f.kind, f.subject) for f in report(adoptions, *rows).findings]


@pytest.mark.parametrize("status", ["trial", "switched"])
def test_a_spawn_of_an_adopted_role_with_no_kernel_row_is_reported_by_role(status: str) -> None:
    assert silent(adopted(researcher=status), started("a1")) == [
        ("liveness-missing-row", "role researcher")
    ]


def test_a_spawn_that_left_its_kernel_row_is_not_reported() -> None:
    assert silent(adopted(researcher="switched"), started("a1"), delivered("a1")) == []


def test_only_the_spawn_without_a_row_is_reported_among_several() -> None:
    found = report(
        adopted(researcher="trial"), started("a1"), delivered("a1"), started("a2")
    ).findings

    assert len(found) == 1
    assert "a2" in found[0].detail


def test_a_spawn_of_a_role_not_adopted_is_not_reported() -> None:
    assert silent(adopted(researcher="trial"), started("a1", "praxion:implementer")) == []


@pytest.mark.parametrize(
    "agent_type", ["researcher", "other:researcher", "main", "general-purpose"]
)
def test_a_spawn_that_is_not_an_agent_of_this_plugin_is_not_reported(agent_type: str) -> None:
    assert silent(adopted(researcher="switched"), started("a1", agent_type)) == []


def test_a_resume_is_not_a_second_spawn() -> None:
    rows = [started("a1", at="2026-10-13T10:00:00+00:00"), delivered("a1"), started("a1")]

    assert silent(adopted(researcher="switched"), *rows) == []


def test_a_resume_after_the_cutoff_does_not_make_an_earlier_spawn_one() -> None:
    rows = [started("a1", at="2026-10-13T10:00:00+00:00"), started("a1", at=AT)]

    assert report(adopted(researcher="switched"), *rows, since=NOON).findings == ()


def test_a_spawn_after_the_cutoff_is_reported() -> None:
    found = report(adopted(researcher="switched"), started("a1"), since=NOON).findings

    assert [f.subject for f in found] == ["role researcher"]


# -- A role's spawns count from its record, and the report says how many it judged ----------------


def test_a_spawn_before_the_record_began_is_not_judged() -> None:
    before = started("a1", at="2026-10-11T23:59:59+00:00")

    assert silent(adopted(researcher="trial"), before) == []


def test_a_spawn_at_the_moment_the_record_began_is_judged() -> None:
    at_start = started("a1", at="2026-10-12T00:00:00+00:00")

    assert silent(adopted(researcher="trial"), at_start) == [
        ("liveness-missing-row", "role researcher")
    ]


def test_each_role_is_bounded_by_its_own_record() -> None:
    adoptions = {
        "researcher": kl.Adoption("trial", datetime(2026, 10, 13, 15, tzinfo=timezone.utc)),
        "verifier": kl.Adoption("trial", ADOPTED),
    }
    rows = [started("a1"), started("a2", "praxion:verifier")]

    assert [f.subject for f in report(adoptions, *rows).findings] == ["role verifier"]


def test_a_spawn_without_a_readable_time_is_judged_not_dropped() -> None:
    row = {**started("a1"), "timestamp": "not a time"}

    assert silent(adopted(researcher="trial"), row) == [("liveness-missing-row", "role researcher")]


def test_the_report_counts_the_spawns_it_judged_and_the_roles_adopted() -> None:
    rows = [
        started("a1"),
        delivered("a1"),
        started("a2"),
        started("a3", "praxion:implementer"),
        started("a4", at="2026-10-01T00:00:00+00:00"),
    ]

    counted = report(adopted(researcher="trial", verifier="trial"), *rows)

    assert (counted.judged, counted.adopted, len(counted.findings)) == (2, 2, 1)


def test_nothing_adopted_judges_nothing_and_says_so() -> None:
    counted = report({}, started("a1"))

    assert (counted.judged, counted.adopted, counted.findings) == (0, 0, ())


# -- The command ----------------------------------------------------------------------------------


def liveness(plugin: Path, project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    argv = ["--liveness", "--repo-root", str(project), "--plugin-root", str(plugin), *args]
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def test_the_liveness_command_names_the_role_that_left_no_row(repo: Path, tmp_path: Path) -> None:
    write_ledger(repo, researcher=switched_row())
    project = tmp_path / "project"
    write_log(project, started("a1"))

    result = liveness(repo, project, "--json")

    assert result.returncode == 1
    assert [f["subject"] for f in json.loads(result.stdout)["findings"]] == ["role researcher"]


def test_the_liveness_command_is_clean_when_every_spawn_left_its_row(
    repo: Path, tmp_path: Path
) -> None:
    write_ledger(repo, researcher=trial_row())
    project = tmp_path / "project"
    write_log(project, started("a1"), delivered("a1"))

    result = liveness(repo, project)

    assert (result.returncode, result.stdout.strip()) == (
        0,
        "kernel liveness: clean (1 spawn(s) of 1 adopted role(s) judged; "
        "no ledger history to place a re-opening of researcher)",
    )


def test_a_clean_report_over_nothing_adopted_says_that_nothing_was_judged(
    repo: Path, tmp_path: Path
) -> None:
    write_ledger(repo)
    project = tmp_path / "project"
    write_log(project, started("a1"))

    result = liveness(repo, project)

    assert (result.returncode, result.stdout.strip()) == (
        0,
        "kernel liveness: clean (0 spawn(s) of 0 adopted role(s) judged)",
    )


def test_the_json_report_states_how_many_spawns_it_judged(repo: Path, tmp_path: Path) -> None:
    write_ledger(repo, researcher=trial_row())
    project = tmp_path / "project"
    write_log(project, started("a1"), delivered("a1"))

    report_json = json.loads(liveness(repo, project, "--json").stdout)

    assert (report_json["judged"], report_json["adopted"], report_json["findings"]) == (1, 1, [])


def test_the_command_does_not_judge_spawns_from_before_the_record_began(
    repo: Path, tmp_path: Path
) -> None:
    write_ledger(repo, researcher=trial_row())  # since 2026-10-12
    project = tmp_path / "project"
    write_log(project, started("a1", at="2026-10-01T10:00:00+00:00"))

    result = liveness(repo, project)

    assert (result.returncode, "0 spawn(s)" in result.stdout) == (0, True)


def test_a_record_placed_at_trial_mid_day_does_not_judge_that_days_earlier_spawns(
    repo: Path, tmp_path: Path
) -> None:
    write_ledger(repo, researcher={**trial_row(), "since": "2026-10-12T15:30:00+00:00"})
    project = tmp_path / "project"
    write_log(
        project,
        started("a1", at="2026-10-12T09:00:00+00:00"),
        started("a2", at="2026-10-12T16:00:00+00:00"),
    )

    found = json.loads(liveness(repo, project, "--json").stdout)

    assert (found["judged"], [f["detail"].split()[1] for f in found["findings"]]) == (1, ["a2"])


def test_a_record_dated_by_a_bare_date_judges_nothing_of_that_day(
    repo: Path, tmp_path: Path
) -> None:
    write_ledger(repo, researcher=trial_row())  # since: 2026-10-12, a bare date
    project = tmp_path / "project"
    write_log(project, started("a1", at="2026-10-12T22:00:00+00:00"))

    assert json.loads(liveness(repo, project, "--json").stdout)["judged"] == 0


def test_the_liveness_command_reads_only_spawns_since_a_revision(
    repo: Path, tmp_path: Path
) -> None:
    write_ledger(repo, researcher=trial_row())
    project = tmp_path / "project"
    write_log(project, started("a1", at="2026-10-13T10:00:00+00:00"))
    commit_all(project, at="2026-10-13T12:00:00+00:00")

    everything = liveness(repo, project)
    since_head = liveness(repo, project, "--since", "HEAD")

    assert (everything.returncode, since_head.returncode) == (1, 0)


def test_a_revision_that_does_not_exist_is_an_input_error(repo: Path, tmp_path: Path) -> None:
    write_ledger(repo, researcher=trial_row())
    project = tmp_path / "project"
    write_log(project, started("a1"))
    commit_all(project)

    result = liveness(repo, project, "--since", "no-such-revision")

    assert result.returncode == 2
    assert "no-such-revision" in result.stderr


def test_a_project_with_no_observation_log_is_an_input_error_not_a_pass(
    repo: Path, tmp_path: Path
) -> None:
    write_ledger(repo, researcher=switched_row())
    project = tmp_path / "project"
    (project / ".ai-state").mkdir(parents=True)

    result = liveness(repo, project)

    assert result.returncode == 2
    assert "observation log" in result.stderr


# -- A log that cannot be read whole is never a clean report ----------------------------------------


def archive(project: Path, position: int, when: datetime) -> Path:
    """An archive at `position` holding one padding row, last appended to at `when`."""
    state = project / ".ai-state"
    state.mkdir(parents=True, exist_ok=True)
    path = cb.reader.retention.archive_path(cb.reader.log_path(state), position)
    path.write_text(json.dumps({"timestamp": when.isoformat(), "event_type": "padding"}) + "\n")
    os.utime(path, (when.timestamp(), when.timestamp()))
    return path


needs_a_mode_to_bite = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads a file whatever its mode"
)


def unreadable(path: Path) -> Path:
    path.chmod(0o000)
    return path


def lost_by(project: Path, repo: Path, *args: str) -> dict:
    """The JSON report of one liveness run."""
    return json.loads(liveness(repo, project, "--json", *args).stdout)


def fact(name: str, when: datetime | None, problem: str | None = None) -> kv.SegmentFact:
    return kv.SegmentFact(Path(name), when, problem)


JUDGED_FROM = datetime(2026, 10, 12, tzinfo=timezone.utc)
BEFORE = datetime(2026, 9, 1, tzinfo=timezone.utc)
INSIDE = datetime(2026, 10, 14, tzinfo=timezone.utc)


def lost_names(*segments: kv.SegmentFact) -> list[str]:
    judged = cb.liveness_report(adopted(researcher="trial"), [], None, segments)
    return [lost.path.name for lost in judged.lost]


def test_a_segment_not_read_whole_inside_the_window_is_lost() -> None:
    assert lost_names(fact("log.1", INSIDE, "unreadable: denied")) == ["log.1"]


def test_a_segment_not_read_whole_wholly_before_the_window_is_not_lost() -> None:
    assert lost_names(fact("log.1", BEFORE, "unreadable: denied")) == []


def test_a_segment_last_appended_at_the_moment_the_window_opens_is_inside_it() -> None:
    assert lost_names(fact("log.1", JUDGED_FROM, "missing")) == ["log.1"]


def test_a_lost_segment_carries_the_reason_it_was_not_read_whole() -> None:
    judged = cb.liveness_report(
        adopted(researcher="trial"), [], None, [fact("log.1", INSIDE, "unreadable: denied")]
    )

    assert [(lost.path.name, lost.reason) for lost in judged.lost] == [
        ("log.1", "unreadable: denied")
    ]


def test_a_segment_read_whole_is_never_lost() -> None:
    assert lost_names(fact("log.1", INSIDE)) == []


def test_a_gap_between_segments_newer_than_the_window_start_is_lost() -> None:
    gap = fact("log.2", None, "missing")

    assert lost_names(fact("log.3", BEFORE), gap, fact("log.1", INSIDE), fact("log", INSIDE)) == [
        "log.2"
    ]


def test_a_gap_beneath_only_segments_older_than_the_window_is_not_lost() -> None:
    gap = fact("log.2", None, "missing")

    assert lost_names(fact("log.3", BEFORE), gap, fact("log.1", BEFORE)) == []


def test_a_gap_with_no_dated_segment_above_it_may_reach_into_the_window() -> None:
    assert lost_names(fact("log.2", None, "missing"), fact("log.1", None)) == ["log.2"]


def test_a_segment_whose_time_is_unknown_is_dated_by_the_next_newer_one() -> None:
    undated = fact("log.2", None, "unreadable: denied")

    assert lost_names(undated, fact("log.1", BEFORE)) == []


def test_no_adopted_role_opens_no_window() -> None:
    judged = cb.liveness_report({}, [], None, [fact("log.1", INSIDE, "missing")])

    assert judged.lost == ()


def test_the_window_opens_at_the_earliest_instant_any_role_is_judged_from() -> None:
    adoptions = {
        "researcher": kl.Adoption("trial", datetime(2026, 10, 14, tzinfo=timezone.utc)),
        "verifier": kl.Adoption("trial", datetime(2026, 10, 1, tzinfo=timezone.utc)),
    }
    segment = fact("log.1", datetime(2026, 10, 5, tzinfo=timezone.utc), "missing")

    assert [s.path.name for s in cb.liveness_report(adoptions, [], None, [segment]).lost] == [
        "log.1"
    ]


def test_since_moves_the_window_for_every_role() -> None:
    segment = fact("log.1", datetime(2026, 10, 13, tzinfo=timezone.utc), "missing")
    later = datetime(2026, 10, 14, tzinfo=timezone.utc)

    judged = cb.liveness_report(adopted(researcher="trial"), [], later, [segment])

    assert judged.lost == ()


@needs_a_mode_to_bite
def test_an_unreadable_segment_inside_the_window_is_named_and_the_findings_are_kept(
    repo: Path, tmp_path: Path
) -> None:
    write_ledger(repo, researcher=trial_row())
    project = tmp_path / "project"
    write_log(project, started("a1"))
    gone = archive(project, 1, INSIDE)
    unreadable(gone)

    try:
        result = liveness(repo, project)
    finally:
        gone.chmod(0o600)

    assert (result.returncode, "unknown" in result.stdout, gone.name in result.stdout) == (
        2,
        True,
        True,
    )
    assert "liveness-missing-row: role researcher" in result.stdout


def test_a_missing_archive_inside_the_window_makes_liveness_unknown(
    repo: Path, tmp_path: Path
) -> None:
    write_ledger(repo, researcher=trial_row())
    project = tmp_path / "project"
    write_log(project, started("a1"), delivered("a1"))
    archive(project, 3, BEFORE)
    archive(project, 1, INSIDE)

    result = liveness(repo, project)

    assert (result.returncode, "observations.jsonl.2 -- missing" in result.stdout) == (2, True)


@needs_a_mode_to_bite
def test_an_unreadable_segment_wholly_before_the_window_leaves_the_result_clean(
    repo: Path, tmp_path: Path
) -> None:
    write_ledger(repo, researcher=trial_row())
    project = tmp_path / "project"
    write_log(project, started("a1"), delivered("a1"))
    old = unreadable(archive(project, 1, BEFORE))

    try:
        result = liveness(repo, project)
    finally:
        old.chmod(0o600)

    assert (result.returncode, "unknown" in result.stdout) == (0, False)


def test_the_json_report_names_each_segment_it_could_not_read_whole(
    repo: Path, tmp_path: Path
) -> None:
    write_ledger(repo, researcher=trial_row())
    project = tmp_path / "project"
    write_log(project, started("a1"), delivered("a1"))
    archive(project, 2, INSIDE)

    found = lost_by(project, repo)

    assert [(Path(u["segment"]).name, u["reason"]) for u in found["unknown"]] == [
        ("observations.jsonl.1", "missing")
    ]


def test_a_clean_json_report_has_no_unknown_key(repo: Path, tmp_path: Path) -> None:
    write_ledger(repo, researcher=trial_row())
    project = tmp_path / "project"
    write_log(project, started("a1"), delivered("a1"))

    assert "unknown" not in lost_by(project, repo)


def test_a_log_with_an_unparseable_line_is_unknown_not_a_pass(repo: Path, tmp_path: Path) -> None:
    write_ledger(repo, researcher=trial_row())
    project = tmp_path / "project"
    write_log(project, started("a1"), delivered("a1"))
    log = cb.reader.log_path(project / ".ai-state")
    log.write_text(log.read_text(encoding="utf-8") + "{torn\n", encoding="utf-8")

    result = liveness(repo, project)

    assert (result.returncode, "unknown" in result.stdout, "unparseable" in result.stdout) == (
        2,
        True,
        True,
    )


@needs_a_mode_to_bite
def test_a_state_directory_that_cannot_be_listed_is_an_input_error(
    repo: Path, tmp_path: Path
) -> None:
    write_ledger(repo, researcher=trial_row())
    project = tmp_path / "project"
    write_log(project, started("a1"))
    state = project / ".ai-state"
    state.chmod(0o000)

    try:
        result = liveness(repo, project)
    finally:
        state.chmod(0o755)

    assert (result.returncode, "cannot be listed" in result.stderr) == (2, True)


@needs_a_mode_to_bite
def test_every_segment_unreadable_is_unknown_not_a_pass(repo: Path, tmp_path: Path) -> None:
    write_ledger(repo, researcher=trial_row())
    project = tmp_path / "project"
    write_log(project, started("a1"))
    log = unreadable(cb.reader.log_path(project / ".ai-state"))

    try:
        result = liveness(repo, project)
    finally:
        log.chmod(0o600)

    assert (result.returncode, "unknown" in result.stdout) == (2, True)


def test_a_ledger_whose_record_does_not_say_when_it_began_is_an_input_error(
    repo: Path, tmp_path: Path
) -> None:
    write_ledger(repo, researcher={"status": "trial", "runs": []})
    project = tmp_path / "project"
    write_log(project, started("a1"))

    result = liveness(repo, project)

    assert result.returncode == 2
    assert "since" in result.stderr


def test_since_without_liveness_is_a_usage_error(repo: Path) -> None:
    assert run_checker(repo, "--since", "HEAD").returncode == 2
