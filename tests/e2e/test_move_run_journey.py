"""A move is measured in the main session through the role machinery, and touches no role run.

The operator runs the git-conventions move: two floor runs, then a paired run citing the first.
Driven by a stand-in launcher over planted session records, each run writes one results file
naming its subject as a move (never a role) with the move's identity (the moved rule's text and
every declared change with its content); it pins the commit-attribution setting, the model, the
effort and the user instruction file before its first launch, equal in every arm; it declares
the `own-discordance-exact` allowance method and records each task's seeded launch order; it
grades none of the role-only checks; each session starts in its task's fixture, and none is
spent proving an arm. Recording the run changes no finding of the kernel manifest gate and no
role entry of the run index. A paired run is refused before any launch when it cites no floor
run, a floor run of another identity, or arms that would differ in a pinned setting, while a
change confined to the lean arm's declaration leaves the floor run citable.

The journey runs once per module and its tests only read it; each refusal gets its own copy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.acceptance.drivers.adherence_eval import COMMON_CHECKS
from tests.acceptance.drivers.move_eval import (
    FIRST_MOVE,
    FLOOR_MINIMUM,
    MOVED_RULES,
    REPO_ROOT,
    MoveResults,
    declare,
    kernel_manifest_findings,
    move_checkout,
    read_move_results,
    render_report,
    role_index_entries,
)
from tests.e2e.drivers.move_journey import (
    RunOutcome,
    Script,
    StandIn,
    commit_change,
    copy_checkout,
    install_stand_in,
    run,
)

PAIRED_TASKS = 4


@dataclass(frozen=True)
class Journey:
    checkout: Path
    stand_in: StandIn
    floor: RunOutcome
    second_floor: RunOutcome
    paired: RunOutcome
    findings: tuple[str, str]  # before, after
    role_entries: tuple[dict, dict]  # before, after


@pytest.fixture(scope="module")
def journey(tmp_path_factory: pytest.TempPathFactory) -> Journey:
    workspace = tmp_path_factory.mktemp("move-journey")
    checkout = move_checkout(workspace)
    findings_before, entries_before = (
        kernel_manifest_findings(checkout),
        role_index_entries(checkout),
    )
    stand_in = install_stand_in(
        workspace,
        Script(by_arm={"floor": "violating"}, by_launch={("lean", 1): "kernel never arrived"}),
    )
    floor = run(stand_in, checkout, "floor", max_tasks=FLOOR_MINIMUM)
    second_floor = run(stand_in, checkout, "floor", max_tasks=FLOOR_MINIMUM)
    paired = run(
        stand_in, checkout, "paired", max_tasks=PAIRED_TASKS, floor_citation=floor.written[0]
    )
    return Journey(
        checkout,
        stand_in,
        floor,
        second_floor,
        paired,
        (findings_before, kernel_manifest_findings(checkout)),
        (entries_before, role_index_entries(checkout)),
    )


@pytest.fixture(scope="module")
def paired(journey) -> MoveResults:
    return read_move_results(journey.paired.results)


@pytest.fixture(scope="module")
def floor(journey) -> MoveResults:
    return read_move_results(journey.floor.results)


# -- One results file per run, naming a move ---------------------------------------------------


@pytest.mark.parametrize("which", ["floor", "second_floor", "paired"])
def test_each_move_run_writes_one_results_file(journey, which):
    outcome: RunOutcome = getattr(journey, which)

    assert outcome.cli.exit_code == 0, outcome.describe()
    assert len(outcome.written) == 1, f"{which} wrote {outcome.written}"


def test_a_move_results_file_names_its_subject_as_a_move_never_as_a_role(floor, paired):
    assert {(r.subject_kind, r.subject, r.run_kind) for r in (floor, paired)} == {
        ("move", FIRST_MOVE, "floor"),
        ("move", FIRST_MOVE, "paired"),
    }


def test_the_results_file_records_the_moved_rules_text_and_each_declared_change(journey, paired):
    rule_text = (journey.checkout / MOVED_RULES[FIRST_MOVE]).read_text(encoding="utf-8")

    assert paired.moved_rule_text == rule_text
    assert paired.declared_changes["lean"], "the lean arm records no declared change"
    assert all(
        re.fullmatch(r"[0-9a-f]{64}", change.sha256)
        for changes in paired.declared_changes.values()
        for change in changes
    )


def test_the_report_of_a_move_run_names_its_subject_as_a_move(journey):
    report = render_report(journey.paired.results, journey.stand_in.bin_dir)

    assert report.exit_code == 0, report.stderr[-1500:]
    assert f"move {FIRST_MOVE}" in report.stdout.lower(), report.stdout[:1500]
    assert f"role {FIRST_MOVE}" not in report.stdout.lower()


def test_no_role_only_check_is_graded_on_a_move_session(floor, paired):
    graded = floor.checks_graded | paired.checks_graded

    assert graded, "no governed check was graded"
    assert not graded & set(COMMON_CHECKS), (
        f"role-only checks graded: {graded & set(COMMON_CHECKS)}"
    )
    assert len(paired.checks_graded) <= 2


# -- Sessions: where they start, what they prove, what counts ---------------------------------


def test_every_session_starts_in_its_tasks_fixture_never_in_the_checkout(journey):
    launches = [*journey.floor.launches, *journey.paired.launches]
    in_checkout = [
        launch
        for launch in launches
        if launch.cwd.resolve() in (journey.checkout.resolve(), REPO_ROOT)
        or journey.checkout.resolve() in launch.cwd.resolve().parents
    ]

    assert launches, "the journey launched no session"
    assert in_checkout == [], in_checkout[:3]


def test_no_session_is_launched_to_prove_an_arm(journey):
    assert len(journey.floor.launches) == FLOOR_MINIMUM
    assert len(journey.paired.launches) == 2 * PAIRED_TASKS


def test_a_lean_session_whose_kernel_never_arrived_enters_no_count_and_keeps_its_reason(paired):
    assert paired.complete_pairs == PAIRED_TASKS - 1
    assert len(paired.refusal_reasons) == 1
    assert all(paired.refusal_reasons.values())


# -- What a move run declares before its first launch -----------------------------------------


def test_the_pinned_settings_are_equal_in_every_arm_floor_included(floor, paired):
    pinned = {paired.pinned["full"], paired.pinned["lean"], floor.pinned["floor"]}

    assert len(pinned) == 1, pinned
    (settings,) = pinned
    assert all(
        (settings.commit_attribution, settings.model, settings.effort, settings.user_instructions)
    )


@pytest.mark.parametrize("which", ["floor", "paired"])
def test_the_settings_are_recorded_before_the_first_launch(request, which):
    results: MoveResults = request.getfixturevalue(which)

    assert results.first_launch_at
    assert results.declared_at < results.first_launch_at


def test_a_move_run_declares_the_own_discordance_exact_allowance_method(paired):
    assert paired.allowance_method == "own-discordance-exact"


def test_each_paired_task_records_a_launch_order_holding_both_arms(paired):
    assert len(paired.launch_orders) == PAIRED_TASKS
    assert {frozenset(order) for order in paired.launch_orders.values()} == {
        frozenset({"full", "lean"})
    }


# -- The cited floor run and the earlier-runs listing -----------------------------------------


def test_the_paired_run_records_the_floor_lineage_it_cites(journey, paired):
    assert paired.cited_floor_lineage == (journey.floor.results.stem,)


def test_floor_runs_are_listed_apart_from_paired_draws_naming_the_other_floor_run(journey, paired):
    floors = {journey.floor.results.stem, journey.second_floor.results.stem}

    assert floors <= set(paired.earlier_floor_runs), paired.earlier_floor_runs
    assert not floors & set(paired.earlier_paired_runs), paired.earlier_paired_runs


# -- Nothing a role run reads changes ---------------------------------------------------------


def test_recording_a_move_run_changes_no_kernel_manifest_finding(journey):
    before, after = journey.findings

    assert after == before


def test_recording_a_move_run_changes_no_role_entry_of_the_run_index(journey):
    before, after = journey.role_entries

    assert before, "the checkout's run index records no role run to compare"
    assert after == before


# -- Refused before any launch ----------------------------------------------------------------


def _refused(outcome: RunOutcome) -> None:
    assert outcome.cli.exit_code != 0, f"the run was not refused: {outcome.describe()}"
    assert outcome.launches == (), "a refused run launched a session"
    assert outcome.written == (), "a refused run wrote a results file"


def _citation_in(copy: Path, journey: Journey) -> Path:
    return copy / journey.floor.results.relative_to(journey.checkout)


def test_a_paired_run_citing_no_floor_run_is_refused_before_any_launch(journey, tmp_path):
    copy = copy_checkout(journey.checkout, tmp_path)
    stand_in = install_stand_in(tmp_path, Script())

    _refused(run(stand_in, copy, "paired", max_tasks=1))


def test_a_paired_run_citing_a_floor_run_of_another_identity_is_refused(journey, tmp_path):
    copy = copy_checkout(journey.checkout, tmp_path)
    commit_change(copy, "README.md", "a checkout the floor run was not measured on\n")
    stand_in = install_stand_in(tmp_path, Script())

    _refused(run(stand_in, copy, "paired", max_tasks=1, floor_citation=_citation_in(copy, journey)))


def test_a_paired_run_whose_floor_arm_changed_since_the_floor_run_is_refused(journey, tmp_path):
    copy = copy_checkout(journey.checkout, tmp_path)
    stand_in = install_stand_in(tmp_path, Script())
    declared = declare(FIRST_MOVE, "a change to the floor arm", tmp_path)

    outcome = run(
        stand_in,
        copy,
        "paired",
        max_tasks=1,
        floor_citation=_citation_in(copy, journey),
        declared=declared,
    )

    _refused(outcome)


def test_a_change_confined_to_the_lean_arm_leaves_the_floor_run_citable(journey, tmp_path):
    copy = copy_checkout(journey.checkout, tmp_path)
    stand_in = install_stand_in(tmp_path, Script())
    declared = declare(FIRST_MOVE, "a change confined to the lean arm", tmp_path)

    outcome = run(
        stand_in,
        copy,
        "paired",
        max_tasks=1,
        floor_citation=_citation_in(copy, journey),
        declared=declared,
    )

    assert outcome.cli.exit_code == 0, outcome.describe()
    assert len(outcome.launches) == 2


def test_a_paired_run_whose_arms_would_render_different_user_instructions_is_refused_naming_it(
    journey, tmp_path
):
    copy = copy_checkout(journey.checkout, tmp_path)
    stand_in = install_stand_in(tmp_path, Script())
    declared = declare(FIRST_MOVE, "the arms differ in the user instruction file", tmp_path)

    outcome = run(
        stand_in,
        copy,
        "paired",
        max_tasks=1,
        floor_citation=_citation_in(copy, journey),
        declared=declared,
    )

    _refused(outcome)
    assert "instruction" in outcome.cli.stderr.lower() + outcome.cli.stdout.lower()
