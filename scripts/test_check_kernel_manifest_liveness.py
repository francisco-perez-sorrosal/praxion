"""Canaries for the liveness mode: a spawn of an adopted role left its kernel row."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _kernel_checker_testkit as kit  # noqa: E402
import check_kernel_manifest as cb  # noqa: E402
import kernel_ledger as kl  # noqa: E402
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
        "kernel liveness: clean (1 spawn(s) of 1 adopted role(s) judged)",
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


def test_a_log_with_an_unparseable_line_is_an_input_error_not_a_pass(
    repo: Path, tmp_path: Path
) -> None:
    write_ledger(repo, researcher=trial_row())
    project = tmp_path / "project"
    write_log(project, started("a1"), delivered("a1"))
    log = cb.reader.log_path(project / ".ai-state")
    log.write_text(log.read_text(encoding="utf-8") + "{torn\n", encoding="utf-8")

    result = liveness(repo, project)

    assert result.returncode == 2
    assert "not readable whole" in result.stderr


def test_a_log_segment_that_cannot_be_read_is_an_input_error_not_a_pass(
    repo: Path, tmp_path: Path
) -> None:
    write_ledger(repo, researcher=trial_row())
    project = tmp_path / "project"
    write_log(project, started("a1"))
    log = cb.reader.log_path(project / ".ai-state")
    log.chmod(0o000)

    try:
        result = liveness(repo, project)
    finally:
        log.chmod(0o600)

    assert result.returncode == 2


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
