"""The spawn tally reports the loop's agents as iterations, apart from charged spawns.

An agent the step-loop driver requested and the iteration ledger recorded under that
request is listed among the iterations and charges neither the spawn count nor the budget
verdict. An agent the driver requested that the ledger does not record yet is still
charged. With no ledger, or a ledger whose records carry no request id, the report and the
verdict are what they were before the loop existed.
"""

from __future__ import annotations

from tests.acceptance.drivers.loop_spawn_tally import (
    IMPLEMENTER,
    PLANNER,
    append_legacy_record,
    iteration_agents,
    observe_spawns,
    tally,
)
from tests.acceptance.drivers.step_loop import (
    Step,
    Work,
    build_loop,
    next_action,
    record,
    work_on,
)


def _driven_step(task) -> str:
    """One whole loop attempt: `next`, the agent's work, `record`. Returns the agent id."""
    request = next_action(task).request
    agent_id = work_on(task, request, Work())
    record(task, request["id"], agent_id=agent_id, marker="complete")
    return agent_id


def _requested_not_recorded(task) -> str:
    """`next` and the agent's work, with no `record` yet. Returns the agent id."""
    return work_on(task, next_action(task).request, Work())


def test_a_recorded_loop_agent_is_an_iteration_and_charges_nothing(tmp_path):
    task = build_loop(tmp_path / "loop", Step("1"), Step("2"))
    driven = _driven_step(task)
    observe_spawns(task, tmp_path, [("agent-planner", PLANNER), (driven, IMPLEMENTER)])

    found = tally(task, tmp_path, budget=1)

    assert iteration_agents(found) == {driven}, found.describe()
    assert (found.charged, found.verdict) == (1, "within"), found.describe()


def test_a_requested_agent_the_ledger_does_not_record_yet_is_still_charged(tmp_path):
    task = build_loop(tmp_path / "loop", Step("1"), Step("2"))
    driven = _driven_step(task)
    pending = _requested_not_recorded(task)
    observe_spawns(
        task,
        tmp_path,
        [("agent-planner", PLANNER), (driven, IMPLEMENTER), (pending, IMPLEMENTER)],
    )

    found = tally(task, tmp_path, budget=2)

    assert iteration_agents(found) == {driven}, found.describe()
    assert (found.charged, found.verdict) == (2, "within"), found.describe()


def test_without_a_ledger_every_spawn_is_charged_as_before(tmp_path):
    task = build_loop(tmp_path / "loop", Step("1"))
    observe_spawns(task, tmp_path, [("agent-planner", PLANNER), ("agent-by-hand", IMPLEMENTER)])

    found = tally(task, tmp_path, budget=1)

    assert iteration_agents(found) == set(), found.describe()
    assert (found.spawns, found.charged) == (2, 2), found.describe()
    assert found.verdict != "within", found.describe()


def test_a_ledger_without_request_ids_charges_every_spawn_as_before(tmp_path):
    task = build_loop(tmp_path / "loop", Step("1"))
    append_legacy_record(task, "1", "agent-by-hand")
    observe_spawns(task, tmp_path, [("agent-planner", PLANNER), ("agent-by-hand", IMPLEMENTER)])

    found = tally(task, tmp_path, budget=1)

    assert iteration_agents(found) == set(), found.describe()
    assert (found.spawns, found.charged) == (2, 2), found.describe()
    assert found.verdict != "within", found.describe()
