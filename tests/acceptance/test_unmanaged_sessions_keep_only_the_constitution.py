"""Outside a managed project a session keeps the constitution and loses the pipeline procedures.

A directory with no `.ai-state/` (in it, or above it inside its repository) is not managed. A
session started there, and every inheriting spawn it starts, receives the behavioural contract,
the user's personal instructions and the two constitutional sentences (the session also the git
conventions), and none of the five managed-only procedures: the coordination protocol, the
intermediate-documents rule, the ADR resident, the routing resident and the decision context.
The always-loaded budget reading for such a directory counts the same composition.

The managed-only texts and the constitution were frozen from the base (`gating_readings.freeze`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import gating_readings as readings
from tests.acceptance.drivers import process_text_oracles as oracles
from tests.acceptance.drivers import scratch_projects as places
from tests.acceptance.drivers import session_start_text as gate

TEXT_UNITS = tuple(oracles.MANAGED_ONLY_TEXTS)


@pytest.fixture(scope="module")
def template(tmp_path_factory) -> Path:
    return places.installed_home(tmp_path_factory.mktemp("install"))


@pytest.fixture
def machine(template, tmp_path) -> gate.Machine:
    return gate.new_machine(template, tmp_path / "machine")


def _plain_directory(machine: gate.Machine) -> Path:
    directory = machine.sandbox / "plain"
    directory.mkdir()
    return directory


def _repository_without_state(machine: gate.Machine) -> Path:
    return places.repository(machine.sandbox / "unmanaged-repo")


UNMANAGED_PLACES = {
    "a directory outside any repository": _plain_directory,
    "a repository without state": _repository_without_state,
}


@pytest.fixture(params=sorted(UNMANAGED_PLACES))
def unmanaged(request, machine) -> Path:
    return UNMANAGED_PLACES[request.param](machine)


# -- The main session -----------------------------------------------------------------------------


@pytest.mark.parametrize("unit", TEXT_UNITS)
def test_an_unmanaged_session_receives_no_managed_only_procedure(machine, unmanaged, unit):
    started = gate.session_start(machine, unmanaged)

    held = oracles.held_statements(unit, started.process_text)

    assert held == [], f"an unmanaged session receives {len(held)} statements of the {unit}"


@pytest.mark.parametrize(
    "unit", [oracles.BEHAVIOURAL_CONTRACT, oracles.USER_INSTRUCTIONS, oracles.GIT_CONVENTIONS]
)
def test_an_unmanaged_session_keeps_each_constitution_text(machine, unmanaged, unit):
    started = gate.session_start(machine, unmanaged)

    missing = oracles.missing_statements(unit, started.process_text)

    assert missing == [], f"an unmanaged session lost {len(missing)} statements of the {unit}"


def test_an_unmanaged_session_keeps_both_constitutional_sentences(machine, unmanaged):
    text = gate.session_start(machine, unmanaged).process_text

    assert oracles.holds_external_docs_sentence(text), "the external-documentation sentence is gone"
    assert oracles.holds_delegation_depth_sentence(text), "the delegation-depth sentence is gone"


# -- Its inheriting spawns ------------------------------------------------------------------------

SPAWNS = (f"praxion:{gate.INHERITING_ROLE}", gate.HOST_NATIVE)


@pytest.mark.parametrize("agent", SPAWNS)
@pytest.mark.parametrize("unit", TEXT_UNITS)
def test_an_inheriting_spawn_in_an_unmanaged_directory_receives_no_managed_only_procedure(
    machine, unmanaged, agent, unit
):
    spawned = gate.spawn_start(machine, unmanaged, agent)

    held = oracles.held_statements(unit, spawned.process_text)

    assert held == [], f"{agent} receives {len(held)} statements of the {unit} unmanaged"


@pytest.mark.parametrize("agent", SPAWNS)
def test_an_inheriting_spawn_in_an_unmanaged_directory_keeps_the_constitution(
    machine, unmanaged, agent
):
    text = gate.spawn_start(machine, unmanaged, agent).process_text

    assert oracles.missing_statements(oracles.BEHAVIOURAL_CONTRACT, text) == []
    assert oracles.missing_statements(oracles.USER_INSTRUCTIONS, text) == []
    assert oracles.holds_external_docs_sentence(text), f"{agent} lost the documentation sentence"
    assert oracles.holds_delegation_depth_sentence(text), f"{agent} lost the delegation sentence"


# -- The budget reading ---------------------------------------------------------------------------


@pytest.mark.parametrize("unit", TEXT_UNITS)
def test_the_budget_reading_of_an_unmanaged_directory_counts_no_managed_only_procedure(
    machine, unit
):
    _, reading = readings.budget_reading(machine, _repository_without_state(machine))

    held = oracles.held_statements(unit, readings.counted_text(reading))

    assert held == [], f"the unmanaged reading counts {len(held)} statements of the {unit}"


def test_the_budget_reading_of_an_unmanaged_directory_counts_the_constitution(machine):
    _, reading = readings.budget_reading(machine, _repository_without_state(machine))
    text = readings.counted_text(reading)

    assert oracles.missing_statements(oracles.BEHAVIOURAL_CONTRACT, text) == []
    assert oracles.missing_statements(oracles.USER_INSTRUCTIONS, text) == []
    assert oracles.holds_external_docs_sentence(text)
    assert oracles.holds_delegation_depth_sentence(text)
