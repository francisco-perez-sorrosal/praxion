"""Outside a managed project a session keeps the constitution and loses the pipeline procedures.

A directory with no `.ai-state/` (in it, or above it inside its repository) is not managed. A
session started there, and every inheriting spawn it starts, receives the behavioural contract,
the user's personal instructions and the two constitutional sentences (the session also the git
conventions), and none of the five managed-only procedures: the coordination protocol, the
intermediate-documents rule, the ADR resident, the routing resident and the decision context.
The always-loaded budget reading for such a directory counts the same composition.

The managed-only texts and the constitution were frozen from the base (`session_start_text`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import session_start_text as gate

TEXT_UNITS = tuple(gate.MANAGED_ONLY_TEXTS)


@pytest.fixture(scope="module")
def template(tmp_path_factory) -> Path:
    return gate.installed_home(tmp_path_factory.mktemp("install"))


@pytest.fixture
def machine(template, tmp_path) -> gate.Machine:
    return gate.new_machine(template, tmp_path / "machine")


def _plain_directory(machine: gate.Machine) -> Path:
    directory = machine.sandbox / "plain"
    directory.mkdir()
    return directory


def _repository_without_state(machine: gate.Machine) -> Path:
    return gate.repository(machine.sandbox / "unmanaged-repo")


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

    held = gate.held_statements(unit, started.process_text)

    assert held == [], f"an unmanaged session receives {len(held)} statements of the {unit}"


@pytest.mark.parametrize(
    "unit", [gate.BEHAVIOURAL_CONTRACT, gate.USER_INSTRUCTIONS, gate.GIT_CONVENTIONS]
)
def test_an_unmanaged_session_keeps_each_constitution_text(machine, unmanaged, unit):
    started = gate.session_start(machine, unmanaged)

    missing = gate.missing_statements(unit, started.process_text)

    assert missing == [], f"an unmanaged session lost {len(missing)} statements of the {unit}"


def test_an_unmanaged_session_keeps_both_constitutional_sentences(machine, unmanaged):
    text = gate.session_start(machine, unmanaged).process_text

    assert gate.holds_external_docs_sentence(text), "the external-documentation sentence is gone"
    assert gate.holds_delegation_depth_sentence(text), "the delegation-depth sentence is gone"


# -- Its inheriting spawns ------------------------------------------------------------------------

SPAWNS = (f"praxion:{gate.INHERITING_ROLE}", gate.HOST_NATIVE)


@pytest.mark.parametrize("agent", SPAWNS)
@pytest.mark.parametrize("unit", TEXT_UNITS)
def test_an_inheriting_spawn_in_an_unmanaged_directory_receives_no_managed_only_procedure(
    machine, unmanaged, agent, unit
):
    spawned = gate.spawn_start(machine, unmanaged, agent)

    held = gate.held_statements(unit, spawned.process_text)

    assert held == [], f"{agent} receives {len(held)} statements of the {unit} unmanaged"


@pytest.mark.parametrize("agent", SPAWNS)
def test_an_inheriting_spawn_in_an_unmanaged_directory_keeps_the_constitution(
    machine, unmanaged, agent
):
    text = gate.spawn_start(machine, unmanaged, agent).process_text

    assert gate.missing_statements(gate.BEHAVIOURAL_CONTRACT, text) == []
    assert gate.missing_statements(gate.USER_INSTRUCTIONS, text) == []
    assert gate.holds_external_docs_sentence(text), f"{agent} lost the documentation sentence"
    assert gate.holds_delegation_depth_sentence(text), f"{agent} lost the delegation sentence"


# -- The budget reading ---------------------------------------------------------------------------


@pytest.mark.parametrize("unit", TEXT_UNITS)
def test_the_budget_reading_of_an_unmanaged_directory_counts_no_managed_only_procedure(
    machine, unit
):
    _, reading = gate.budget_reading(machine, _repository_without_state(machine))

    held = gate.held_statements(unit, gate.counted_text(reading))

    assert held == [], f"the unmanaged reading counts {len(held)} statements of the {unit}"


def test_the_budget_reading_of_an_unmanaged_directory_counts_the_constitution(machine):
    _, reading = gate.budget_reading(machine, _repository_without_state(machine))
    text = gate.counted_text(reading)

    assert gate.missing_statements(gate.BEHAVIOURAL_CONTRACT, text) == []
    assert gate.missing_statements(gate.USER_INSTRUCTIONS, text) == []
    assert gate.holds_external_docs_sentence(text)
    assert gate.holds_delegation_depth_sentence(text)
