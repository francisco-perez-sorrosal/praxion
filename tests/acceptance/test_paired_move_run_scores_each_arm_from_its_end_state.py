"""A paired run of the refactoring move runs to its end and scores each arm from what it left.

The run builds the plugin as it is today and as the move leaves it, shows before any task of an
arm that a marked spawn there holds the refactoring skill once and by that arm's own way, runs
each task once in each shown arm, grades each session from its repository, records whether the
skill reached the role its arm's way, and reports each check's comparison of the two arms.

Every session is a stand-in (`paired_move_stand_in`) that crosses the spawn's hook boundary for
real against the arm copy it was handed, so nothing is paid for and what reaches the role is
whatever that copy delivers.
"""

from __future__ import annotations

from collections import Counter

import pytest

from tests.acceptance.drivers import paired_move_runs as paired
from tests.acceptance.drivers.paired_move_runs import ARMS, CHECKLIST, Ending, Script
from tests.acceptance.drivers.refactoring_delivery import ROLES

CONFESSION = "I left a compatibility shim and some dead code."
CLAIM = "Done: every checklist item holds."
# One checklist item per role whose violation the arm after the move leaves in its first task.
BROKEN = {
    "implementer": "no transitional shim remains",
    "test-engineer": "characterization tests pin behaviour through the public surface",
}


def scoring_script(role: str) -> Script:
    """Every session leaves a clean end state and confesses problems, except in the arm after
    the move: its first task leaves one checklist item broken and claims all is well, and its
    second task's record holds nothing the delivery added."""
    return Script(
        by_arm={
            "delivered": [
                Ending(work=BROKEN[role], account=CLAIM),
                Ending(account=CONFESSION, served=False),
            ]
        },
        default=Ending(account=CONFESSION),
    )


@pytest.fixture(scope="module", params=ROLES)
def scored(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory):
    role = request.param
    workspace = tmp_path_factory.mktemp(f"paired-{role}")
    checkout = paired.new_checkout(workspace)
    planned = paired.planned_tasks(workspace, checkout, role)
    run = paired.run_paired(workspace, checkout, role, scoring_script(role))
    return role, workspace, planned, run


@pytest.fixture(scope="module", params=ROLES)
def unshown(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory):
    role = request.param
    workspace = tmp_path_factory.mktemp(f"paired-unshown-{role}")
    checkout = paired.new_checkout(workspace)
    paired.without_the_delivery(checkout)
    return role, workspace, paired.run_paired(workspace, checkout, role)


@pytest.fixture(scope="module", params=ROLES)
def proof_refused(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory):
    """A checkout that keeps the delivery, whose proof spawn in the arm after the move receives none."""
    role = request.param
    workspace = tmp_path_factory.mktemp(f"paired-proof-refused-{role}")
    checkout = paired.new_checkout(workspace)
    script = paired.proof_unserved_in("delivered")
    return role, workspace, paired.run_paired(workspace, checkout, role, script)


def finished(scored):
    """The scored run, once it is known to have planned tasks and run to its end."""
    _, _, planned, run = scored
    assert planned, "the paired dry run plans no task"
    assert run.exit_code == 0, f"the paired run did not finish: {run.printed[-2000:]}"
    return scored


def first_launch_kinds(run: paired.PairedRun) -> dict[str, str]:
    """For each arm, whether the first session the run started in it was a proof or a task."""
    kinds: dict[str, str] = {}
    for launch in run.launches:
        kinds.setdefault(launch.arm, "proof" if launch.proof else "task")
    return kinds


def leaked_grading_material(run: paired.PairedRun, role: str) -> list[tuple[str, str, str]]:
    """Each file a task session's repository held at its start that only an end state holds."""
    return [
        (launch.arm, launch.template, rel)
        for launch in run.launches
        if not launch.proof
        for material in [paired.grading_material(role, launch.template)]
        for rel, digest in launch.start_files.items()
        if digest in material or "end_states" in rel.split("/")
    ]


def fully_passed(record: paired.SessionRecord, role: str) -> bool:
    return all(record.refactoring_checks[item] for item in CHECKLIST[role])


# -- Both arms shown, every task run once in each ---------------------------------------------


def test_a_paired_run_runs_to_its_end_with_every_session_a_stand_in(scored) -> None:
    _, _, _, run = finished(scored)

    assert run.results_path.is_file(), "the paired run wrote no results file"


def test_a_paired_run_shows_each_arm_before_launching_any_of_its_tasks(scored) -> None:
    _, _, _, run = finished(scored)

    assert first_launch_kinds(run) == dict.fromkeys(ARMS, "proof")


def test_a_paired_run_runs_each_planned_task_once_in_each_shown_arm(scored) -> None:
    _, _, planned, run = finished(scored)

    assert {arm: len(run.tasks(arm)) for arm in ARMS} == {arm: len(planned) for arm in ARMS}
    assert Counter(t.template for t in run.tasks("preloaded")) == Counter(
        t.template for t in run.tasks("delivered")
    )


def test_each_task_session_starts_without_the_material_its_grade_is_decided_by(scored) -> None:
    role, _, _, run = finished(scored)

    assert run.tasks("preloaded"), "no task session started in the arm before the move"
    assert run.tasks("delivered"), "no task session started in the arm after the move"
    assert leaked_grading_material(run, role) == []


# -- Graded from the end state, the arrival recorded -------------------------------------------


def test_a_clean_end_state_passes_every_checklist_item_whatever_the_role_confesses(
    scored,
) -> None:
    role, _, planned, run = finished(scored)

    records = paired.session_records(run.results_path, role)
    before = [r for r in records if r.arm == "preloaded"]

    assert len(before) == len(planned)
    assert [r.task_id for r in before if not fully_passed(r, role)] == []


def test_a_broken_end_state_fails_its_checklist_item_whatever_the_role_claims(scored) -> None:
    role, _, planned, run = finished(scored)

    records = paired.session_records(run.results_path, role)
    after = [r for r in records if r.arm == "delivered"]

    assert len(after) == len(planned)
    assert sorted(r.refactoring_checks[BROKEN[role]] for r in after) == [False] + [True] * (
        len(planned) - 1
    )


def test_every_scored_session_is_also_graded_on_the_roles_ordinary_checks(scored) -> None:
    role, _, _, run = finished(scored)

    records = paired.session_records(run.results_path, role)

    assert records, "the paired run scored no session"
    assert [r.task_id for r in records if not r.ordinary_checks] == []


def test_each_session_record_says_whether_the_skill_reached_the_role_its_arms_way(scored) -> None:
    role, _, planned, run = finished(scored)

    records = paired.session_records(run.results_path, role)
    arrived = {
        arm: sorted(r.skill_arrived_its_arm_way for r in records if r.arm == arm) for arm in ARMS
    }

    assert arrived == {
        "preloaded": [True] * len(planned),
        "delivered": [False] + [True] * (len(planned) - 1),
    }


# -- The report ---------------------------------------------------------------------------------


def test_the_report_compares_the_arm_after_the_move_with_the_arm_before_on_each_check(
    scored,
) -> None:
    role, workspace, _, run = finished(scored)

    rendering = paired.report(workspace, run.results_path)
    compared = paired.check_comparisons(rendering.text, role)
    broken = compared[BROKEN[role]]
    kept = {item: compared[item] for item in CHECKLIST[role] if item != BROKEN[role]}

    assert rendering.exit_code == 0, rendering.stderr[-2000:]
    assert set(CHECKLIST[role]) < set(compared), "the report compares no ordinary check"
    assert (broken.before_passed, broken.after_passed) == (
        broken.tasks_in_both,
        broken.tasks_in_both - 1,
    )
    assert {i: (c.before_passed, c.after_passed) for i, c in kept.items()} == {
        i: (c.tasks_in_both, c.tasks_in_both) for i, c in kept.items()
    }


def test_the_report_says_for_each_check_whether_the_run_holds_enough_evidence(scored) -> None:
    role, workspace, _, run = finished(scored)

    compared = paired.check_comparisons(paired.report(workspace, run.results_path).text, role)

    assert compared, "the report compares no check"
    assert {type(c.evidence_enough) for c in compared.values()} == {bool}


# -- An arm that cannot be shown ----------------------------------------------------------------


def test_an_arm_that_cannot_be_shown_to_receive_the_skill_launches_none_of_its_tasks(
    proof_refused,
) -> None:
    _, _, run = proof_refused

    assert run.proofs("delivered"), "the arm after the move was never put to its proof"
    assert run.tasks("delivered") == []


def test_an_arm_that_cannot_be_shown_has_no_task_scored_and_the_report_says_why(unshown) -> None:
    role, workspace, run = unshown

    rendering = paired.report(workspace, run.results_path)
    scored_after = [
        r for r in paired.session_records(run.results_path, role) if r.arm == "delivered"
    ]

    assert scored_after == []
    assert paired.unshown_arm_reason(rendering.text, role, "delivered"), (
        "the report does not say why the arm after the move was not shown"
    )
