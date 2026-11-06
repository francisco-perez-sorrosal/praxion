"""Each writer role's free dry run plans a full, reproducible paired run in every mode it covers.

The test-engineer's and the systems-architect's dry runs each plan the target plus its slack (24
tasks at the default target of 20), drawn from at least five templates on both fixture
repositories, with every variant either role is subject to and no task twice. Each covered mode
holds at least a third of the tasks, every planned session's line names its task's mode, and a
task of a mode that carries a directive is prompted with it. The same seed plans the same tasks
in the same order in a separate process. The dry run starts no session, writes nothing, and
prints no fragment of the session token.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import writer_kits as kits
from tests.acceptance.drivers.writer_kits import (
    COVERED_MODES,
    DEFAULT_TARGET,
    DIRECTIVES,
    FIXTURE_REPOSITORIES,
    PLANNED_AT_DEFAULT,
    TEMPLATE_MINIMUM,
    VARIANTS,
    WRITER_ROLES,
    TaskId,
)

MODES = [(role, mode) for role in WRITER_ROLES for mode in COVERED_MODES[role]]
DIRECTED = [(role, mode) for role, mode in MODES if mode in DIRECTIVES]
UNDIRECTED = [(role, mode) for role, mode in MODES if mode not in DIRECTIVES]


@pytest.fixture(scope="module")
def plans(tmp_path_factory) -> dict[str, kits.Plan]:
    return {
        role: kits.plan(tmp_path_factory.mktemp(f"{role}-dry-run"), role) for role in WRITER_ROLES
    }


def parsed(plan: kits.Plan) -> list[TaskId]:
    return [TaskId.parse(task) for task in plan.task_ids()]


# -- The size of the plan ----------------------------------------------------------------------


@pytest.mark.parametrize("role", WRITER_ROLES)
def test_the_dry_run_plans_the_target_plus_its_slack(plans, role):
    tasks = plans[role].task_ids()

    assert len(tasks) == PLANNED_AT_DEFAULT, f"the {role} plans {len(tasks)} tasks"


@pytest.mark.parametrize("role", WRITER_ROLES)
def test_the_header_names_the_planned_count_and_the_target(plans, role):
    assert plans[role].header == (PLANNED_AT_DEFAULT, DEFAULT_TARGET), plans[role].output[-800:]


@pytest.mark.parametrize("role", WRITER_ROLES)
def test_no_task_is_planned_twice(plans, role):
    tasks = plans[role].task_ids()

    assert len(set(tasks)) == len(tasks), f"the {role}'s plan repeats a task"


@pytest.mark.parametrize("role", WRITER_ROLES)
def test_the_tasks_are_drawn_from_at_least_the_full_kit_template_minimum(plans, role):
    templates = {task.template for task in parsed(plans[role])}

    assert len(templates) >= TEMPLATE_MINIMUM, f"the {role} draws on {sorted(templates)}"


@pytest.mark.parametrize("role", WRITER_ROLES)
def test_the_tasks_run_in_both_fixture_repositories(plans, role):
    fixtures = {task.fixture for task in parsed(plans[role])}

    assert fixtures == set(FIXTURE_REPOSITORIES)


@pytest.mark.parametrize("role", WRITER_ROLES)
def test_the_tasks_hold_every_variant_the_role_is_subject_to(plans, role):
    variants = {task.variant for task in parsed(plans[role])}

    assert set(VARIANTS) <= variants, f"the {role}'s plan lacks {sorted(set(VARIANTS) - variants)}"


# -- The modes ---------------------------------------------------------------------------------


@pytest.mark.parametrize("role", WRITER_ROLES)
def test_every_planned_session_names_one_of_the_roles_covered_modes(plans, role):
    named = {
        (s.task_id, s.arm): plans[role].modes.get((s.task_id, s.arm)) for s in plans[role].sessions
    }

    unnamed = sorted(key for key, mode in named.items() if mode not in COVERED_MODES[role])

    assert named, f"the {role}'s dry run planned no session"
    assert unnamed == [], f"sessions naming no covered mode: {unnamed[:4]}"


@pytest.mark.parametrize(("role", "mode"), MODES)
def test_each_covered_mode_holds_at_least_a_third_of_the_tasks(plans, role, mode):
    held = plans[role].tasks_in(mode)

    assert 3 * len(held) >= PLANNED_AT_DEFAULT, f"{mode} holds {len(held)} of the {role}'s tasks"


@pytest.mark.parametrize(("role", "mode"), MODES)
def test_both_arms_of_a_task_name_the_same_mode(plans, role, mode):
    full = plans[role].tasks_in(mode, "full")
    lean = plans[role].tasks_in(mode, "lean")

    assert full, f"the {role} plans no {mode} task"
    assert full == lean


@pytest.mark.parametrize(("role", "mode"), DIRECTED)
def test_a_task_of_a_directed_mode_prompts_the_role_with_its_directive(plans, role, mode):
    tasks = plans[role].tasks_in(mode)

    undirected = [t for t in tasks if DIRECTIVES[mode] not in plans[role].session(t).prompt]

    assert tasks, f"the {role} plans no {mode} task"
    assert undirected == [], f"{mode} tasks prompted without {DIRECTIVES[mode]!r}: {undirected[:3]}"


@pytest.mark.parametrize(("role", "mode"), UNDIRECTED)
def test_a_task_of_the_other_mode_carries_no_directive_of_a_directed_one(plans, role, mode):
    tasks = plans[role].tasks_in(mode)
    directives = [DIRECTIVES[m] for m in COVERED_MODES[role] if m in DIRECTIVES]

    directed = [t for t in tasks if any(d in plans[role].session(t).prompt for d in directives)]

    assert tasks, f"the {role} plans no {mode} task"
    assert directed == [], f"{mode} tasks prompted with another mode's directive: {directed[:3]}"


# -- Reproducible, and free ----------------------------------------------------------------------


@pytest.mark.parametrize("role", WRITER_ROLES)
def test_the_same_seed_plans_the_same_tasks_in_the_same_order_in_a_separate_process(
    plans, role, tmp_path
):
    again = kits.plan(tmp_path, role, arms=("full",))

    assert again.task_ids() == plans[role].task_ids()
    assert [again.mode_of(t) for t in again.task_ids()] == [
        plans[role].mode_of(t) for t in plans[role].task_ids()
    ]


@pytest.mark.parametrize("role", WRITER_ROLES)
def test_the_dry_run_starts_no_session_and_writes_nothing(plans, role):
    plan = plans[role]

    assert plan.started_sessions == 0, "the dry run started a session"
    assert not plan.wrote_results, "the dry run wrote a results file"
    assert plan.checkout_unchanged, "the dry run changed the checkout under test"


@pytest.mark.parametrize("role", WRITER_ROLES)
def test_the_dry_run_prints_no_fragment_of_the_session_token(tmp_path, role):
    token_file, token = kits.write_token_file(tmp_path / "operator")

    printed = kits.plan(tmp_path / "run", role, token_file=token_file)

    assert printed.sessions, f"the {role}'s dry run planned no session"
    assert kits.leaked_fragments(printed.output, token) == []
