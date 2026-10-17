"""Earlier runs are listed by what they measured; arms launch in a seeded order; transcripts are found.

A run lists every earlier run of its role on the same role definition and kernel
identity, whatever its checkout commit, apart from runs of another identity and from
calibration runs; a JSON file beside it that is not a results file is skipped and named,
never stopping the run. Each task's two arms launch in an order drawn from the seed. The
runner and every catalog row name a session's transcript directory as the harness does.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.acceptance.drivers import adherence_runs as runs
from tests.acceptance.drivers.adherence_runs import Plan, Script

RECORDED = runs.RESULTS_SUBDIR / "20261014T045733Z-7050ca.json"
STRAY = "notes-about-the-trial.json"


def test_a_json_file_that_is_not_a_results_file_is_skipped_named_and_never_stops_the_run(
    tmp_path: Path,
) -> None:
    checkout = runs.new_checkout(tmp_path)
    (runs.results_dir(checkout) / STRAY).write_text('{"note": "kept by hand"}\n')

    result = runs.run_with_stand_in(tmp_path, checkout, Plan(max_tasks=1), Script())

    assert result.launches, "the stray file stopped the run before its first launch"
    assert STRAY in result.stdout + result.stderr
    assert runs.earlier_runs(result.results_path, runs.ROLE).skipped_files == (STRAY,)


def test_a_report_beside_a_json_file_that_is_not_a_results_file_still_renders(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "ledger"
    directory.mkdir()
    target = directory / RECORDED.name
    shutil.copy(runs.adherence_eval.REPO_ROOT / RECORDED, target)
    (directory / STRAY).write_text('{"note": "kept by hand"}\n')

    report = runs.run_report(tmp_path, target)

    assert "Role researcher" in report


def test_earlier_runs_of_the_same_identity_on_other_commits_are_all_listed_in_order(
    tmp_path: Path,
) -> None:
    checkout = runs.new_checkout(tmp_path)
    first = runs.run_with_stand_in(tmp_path / "a", checkout, Plan(max_tasks=1), Script())
    runs.change_in_checkout(checkout, "README.md")
    second = runs.run_with_stand_in(tmp_path / "b", checkout, Plan(max_tasks=1), Script())
    third = runs.run_with_stand_in(tmp_path / "c", checkout, Plan(max_tasks=1), Script())

    listed = runs.earlier_runs(third.results_path, runs.ROLE)

    assert [d.run_ids for d in listed.draws] == [
        (first.results_path.stem,),
        (second.results_path.stem,),
    ]
    assert all(d.flip for d in listed.draws), "an earlier run is listed without its verdict"


def test_an_earlier_run_of_another_role_definition_is_named_apart_with_the_difference(
    tmp_path: Path,
) -> None:
    checkout = runs.new_checkout(tmp_path)
    first = runs.run_with_stand_in(tmp_path / "a", checkout, Plan(max_tasks=1), Script())
    runs.change_in_checkout(checkout, f"agents/{runs.ROLE}.md")
    later = runs.run_with_stand_in(tmp_path / "b", checkout, Plan(max_tasks=1), Script())

    listed = runs.earlier_runs(later.results_path, runs.ROLE)

    assert listed.draws == ()
    assert first.results_path.stem in listed.apart
    assert "definition" in listed.apart[first.results_path.stem]


def test_a_calibration_run_is_listed_apart_never_as_a_draw(tmp_path: Path) -> None:
    checkout = runs.new_checkout(tmp_path)
    calibration = runs.run_with_stand_in(
        tmp_path / "a", checkout, Plan(max_tasks=1, arms=("full",), calibration=True), Script()
    )
    later = runs.run_with_stand_in(tmp_path / "b", checkout, Plan(max_tasks=1), Script())

    listed = runs.earlier_runs(later.results_path, runs.ROLE)

    assert listed.calibration == (calibration.results_path.stem,)
    assert listed.draws == ()


def test_a_results_file_recording_no_identity_is_listed_never_dropped(tmp_path: Path) -> None:
    checkout = runs.new_checkout(tmp_path)
    later = runs.run_with_stand_in(tmp_path, checkout, Plan(max_tasks=1), Script())

    listed = runs.earlier_runs(later.results_path, runs.ROLE)

    assert RECORDED.stem in {i for d in listed.draws for i in d.run_ids} | set(listed.apart), (
        "a run recorded before identities were recorded was dropped from the listing"
    )


def test_a_run_given_a_calibration_file_takes_no_allowance_from_it(tmp_path: Path) -> None:
    checkout = runs.new_checkout(tmp_path)
    calibration = runs.run_with_stand_in(
        tmp_path / "a", checkout, Plan(max_tasks=1, arms=("full",), calibration=True), Script()
    )
    plan = Plan(max_tasks=1, calibration_run=calibration.results_path)

    result = runs.run_with_stand_in(tmp_path / "b", checkout, plan, Script())

    assert runs.declared_allowance_method(result.results_path), "no allowance method declared"
    assert not runs.allowance_taken_from_calibration(result.results_path)


# -- The seeded launch order ---------------------------------------------------------------------


def test_the_same_seed_yields_the_same_per_task_launch_order(tmp_path: Path) -> None:
    checkout = runs.new_checkout(tmp_path)

    first = runs.launch_orders(runs.dry_run(tmp_path / "one", checkout))
    second = runs.launch_orders(runs.dry_run(tmp_path / "two", checkout))

    assert first == second


def test_a_planned_list_of_twenty_four_tasks_holds_both_launch_orders(tmp_path: Path) -> None:
    orders = runs.launch_orders(runs.dry_run(tmp_path, runs.new_checkout(tmp_path)))

    assert len(orders) == 24
    assert set(orders.values()) == {("full", "lean"), ("lean", "full")}


# -- Transcript directories ---------------------------------------------------------------------

WORKING_DIRECTORIES = {
    "an underscore": "/tmp/adherence_sandbox/scratch",
    "a space": "/tmp/adherence sandbox/scratch",
    "a plus": "/tmp/adherence+sandbox/scratch",
    "a non-ASCII letter": "/tmp/adhérence/scratch",
}


@pytest.mark.parametrize("cwd", WORKING_DIRECTORIES.values(), ids=WORKING_DIRECTORIES.keys())
def test_the_runner_and_every_catalog_row_name_the_transcript_directory_as_the_harness_does(
    cwd: str,
) -> None:
    harness = runs.harness_transcript_dir_name(cwd)

    named = {
        "runner": runs.runner_transcript_dir_name(cwd),
        **runs.catalog_transcript_dir_names(cwd),
    }

    assert named == dict.fromkeys(named, harness)
