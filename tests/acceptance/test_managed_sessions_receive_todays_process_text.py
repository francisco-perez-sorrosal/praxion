"""In a managed project every session and spawn receives the process text it receives today.

Checked by content against readings frozen at the base: every statement present today is present
as often as today, none is added, the declared edits excepted (the two constitutional sentences
relocated into every-project text, and every-project sentences reworded so they stay true where a
managed-only procedure is absent). This holds for interactive and headless sessions of a project
nobody opened before, and for a project whose own instruction file predates the change. A lean
spawn's delivery is byte-identical to today's, and the generated kernels are unchanged. The
always-loaded reading of a managed directory counts today's composition, and Praxion's own
checkout stays under the 25,000-token ceiling.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import flip_gate as flip
from tests.acceptance.drivers import gating_readings as readings
from tests.acceptance.drivers import process_text_oracles as oracles
from tests.acceptance.drivers import scratch_projects as places
from tests.acceptance.drivers import session_start_text as gate

ROOT_MARKER = "root gating fixture"
BUDGET_CEILING = 25_000


@pytest.fixture(scope="module")
def template(tmp_path_factory) -> Path:
    return places.installed_home(tmp_path_factory.mktemp("install"))


@pytest.fixture
def machine(template, tmp_path) -> gate.Machine:
    return gate.new_machine(template, tmp_path / "machine")


@pytest.fixture
def project(machine) -> Path:
    """A managed project nobody has opened a session in, with two recorded decisions."""
    return places.repository(machine.sandbox / "project", state_marker=ROOT_MARKER)


def _today(name: str) -> str:
    return oracles.base_reading(name)


def _now(started: gate.Start, machine: gate.Machine) -> str:
    return oracles.mask(started.process_text, machine.tokens())


# -- The main session -----------------------------------------------------------------------------


@pytest.mark.parametrize("entrypoint", [gate.INTERACTIVE, gate.HEADLESS])
def test_a_managed_session_receives_todays_process_text(machine, project, entrypoint):
    started = gate.session_start(machine, project, entrypoint=entrypoint)

    changes = oracles.unexplained_changes(
        _today(f"managed-main-{entrypoint}"), _now(started, machine)
    )

    assert changes.none, f"missing: {changes.missing[:5]}\nadded: {changes.added[:5]}"


def test_a_managed_session_receives_its_projects_decision_context(machine, project):
    text = gate.session_start(machine, project).process_text

    assert oracles.holds_decision_context(text, ROOT_MARKER), "the decision context is missing"


def test_a_managed_project_whose_instructions_predate_the_change_receives_todays_process_text(
    machine,
):
    project = places.project_with_old_instructions(machine.sandbox / "older-project")

    started = gate.session_start(machine, project)

    changes = oracles.unexplained_changes(_today("managed-main-onboarded"), _now(started, machine))
    assert changes.none, f"missing: {changes.missing[:5]}\nadded: {changes.added[:5]}"


def test_a_managed_project_with_current_instructions_receives_todays_process_text(machine):
    project = places.project_with_current_instructions(machine.sandbox / "current-project")

    started = gate.session_start(machine, project)

    changes = oracles.unexplained_changes(_today("managed-main-onboarded"), _now(started, machine))
    assert changes.none, f"missing: {changes.missing[:5]}\nadded: {changes.added[:5]}"


# -- Its spawns -----------------------------------------------------------------------------------


def test_the_inheriting_example_is_a_role_no_flip_can_make_lean():
    assert gate.INHERITING_ROLE not in flip.eligible_roles(oracles.REPO_ROOT), (
        f"{gate.INHERITING_ROLE} is in the eligibility pin, so a flip can make it lean and the"
        " inheriting-spawn scenarios lose their premise; name a role outside the pin"
    )


@pytest.mark.parametrize("agent", [f"praxion:{gate.INHERITING_ROLE}", gate.HOST_NATIVE])
def test_an_inheriting_spawn_in_a_managed_project_receives_todays_process_text(
    machine, project, agent
):
    spawned = gate.spawn_start(machine, project, agent)

    changes = oracles.spawn_changes(agent, _today(f"managed-spawn-{agent}"), _now(spawned, machine))

    assert changes.none, f"missing: {changes.missing[:5]}\nadded: {changes.added[:5]}"


def test_a_lean_spawn_in_a_managed_project_receives_exactly_todays_delivery(machine, project):
    spawned = gate.spawn_start(machine, project, f"praxion:{gate.LEAN_ROLE}")

    assert _now(spawned, machine) == _today(f"managed-spawn-praxion:{gate.LEAN_ROLE}")


def test_the_kernels_lean_spawns_receive_are_unchanged():
    assert readings.kernel_digests() == oracles.fixture_json("base_kernels.json")


# -- The budget reading ---------------------------------------------------------------------------


def test_the_budget_reading_of_a_managed_directory_counts_todays_composition(machine):
    directory = places.repository(machine.sandbox / "budget-project", managed=True)

    _, reading = readings.budget_reading(machine, directory)

    changes = oracles.unexplained_changes(
        _today("managed-budget-text"),
        oracles.mask(readings.counted_text(reading), machine.tokens()),
    )
    assert changes.none, f"missing: {changes.missing[:5]}\nadded: {changes.added[:5]}"


def test_the_budget_reading_of_praxions_checkout_stays_under_the_ceiling(machine):
    _, reading = readings.budget_reading(machine, oracles.REPO_ROOT)

    assert reading["budget"] == BUDGET_CEILING
    assert reading["over_by"] == 0, f"the managed reading is {reading['tokens']} tokens"
