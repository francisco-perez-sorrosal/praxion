"""Each role's task set is reproducible and large enough for the flip rule.

A seed fixes a role's task list: the same seed gives the same tasks every time,
even in a fresh process. The researcher, the verifier and the implementer each
have at least 20 distinct runnable paired tasks; every other role has at least
three runnable smoke tasks from templates able to produce at least 20.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.adherence_eval import (
    PILOT_ROLES,
    SEED,
    SMOKE_ROLES,
    producible_task_count,
    task_ids,
)


@pytest.mark.parametrize("role", ["researcher", "skill-genesis"])
def test_the_same_seed_gives_the_same_task_list_in_separate_runs(role):
    first = task_ids(role, SEED)
    second = task_ids(role, SEED)

    assert first, f"the {role} has no tasks"
    assert first == second, f"the {role}'s task list changed between two runs with seed {SEED}"


@pytest.mark.parametrize("role", PILOT_ROLES)
def test_a_pilot_role_has_at_least_twenty_distinct_runnable_tasks(role):
    tasks = task_ids(role, SEED)

    assert len(set(tasks)) == len(tasks), f"the {role}'s task identifiers repeat"
    assert len(tasks) >= 20, f"the {role} has {len(tasks)} runnable tasks, fewer than 20"


@pytest.mark.parametrize("role", SMOKE_ROLES)
def test_every_other_role_has_three_smoke_tasks_from_templates_able_to_produce_twenty(role):
    tasks = task_ids(role, SEED)

    assert len(set(tasks)) >= 3, f"the {role} has {len(set(tasks))} distinct smoke tasks"
    assert producible_task_count(role, SEED) >= 20, (
        f"the {role}'s templates cannot produce 20 distinct tasks"
    )
