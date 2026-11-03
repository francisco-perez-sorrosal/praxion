"""With Praxion's hooks absent, a session falls back to today's text, never to nothing.

Hooks absent is either no hook running (switched off, a broken or partial install) or the rule
injection switched off with `PRAXION_DISABLE_RULE_INJECTION`. A managed session and each
inheriting spawn it starts still receive the coordination protocol, the intermediate-documents
rule, the ADR resident, the behavioural contract and the user's personal instructions; an
unmanaged session still receives the contract, the user's personal instructions and the two
constitutional sentences.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import process_text_oracles as oracles
from tests.acceptance.drivers import scratch_projects as places
from tests.acceptance.drivers import session_start_text as gate

ABSENT = ("off", "injection-off")
MANAGED_FLOOR = (
    oracles.COORDINATION_PROTOCOL,
    oracles.INTERMEDIATE_DOCUMENTS,
    oracles.ADR_RESIDENT,
    oracles.BEHAVIOURAL_CONTRACT,
    oracles.USER_INSTRUCTIONS,
)


@pytest.fixture(scope="module")
def template(tmp_path_factory) -> Path:
    return places.installed_home(tmp_path_factory.mktemp("install"))


@pytest.fixture
def machine(template, tmp_path) -> gate.Machine:
    return gate.new_machine(template, tmp_path / "machine")


@pytest.mark.parametrize("hooks", ABSENT)
@pytest.mark.parametrize("unit", MANAGED_FLOOR)
@pytest.mark.parametrize("entrypoint", [gate.INTERACTIVE, gate.HEADLESS])
def test_a_managed_session_without_hooks_still_receives_todays_floor(
    machine, hooks, unit, entrypoint
):
    project = places.repository(machine.sandbox / "project", managed=True)

    text = gate.session_start(machine, project, hooks=hooks, entrypoint=entrypoint).process_text

    assert oracles.missing_statements(unit, text) == [], f"the {unit} is gone with hooks {hooks}"


@pytest.mark.parametrize("hooks", ABSENT)
@pytest.mark.parametrize("unit", MANAGED_FLOOR)
@pytest.mark.parametrize("agent", [f"praxion:{gate.INHERITING_ROLE}", gate.HOST_NATIVE])
def test_an_inheriting_spawn_without_hooks_still_receives_todays_floor(machine, hooks, unit, agent):
    project = places.repository(machine.sandbox / "project", managed=True)

    text = gate.spawn_start(machine, project, agent, hooks=hooks).process_text

    assert oracles.missing_statements(unit, text) == [], f"{agent} lost the {unit} ({hooks})"


@pytest.mark.parametrize("hooks", ABSENT)
def test_an_unmanaged_session_without_hooks_still_receives_the_constitution(machine, hooks):
    directory = places.repository(machine.sandbox / "plain")

    text = gate.session_start(machine, directory, hooks=hooks).process_text

    assert oracles.missing_statements(oracles.BEHAVIOURAL_CONTRACT, text) == []
    assert oracles.missing_statements(oracles.USER_INSTRUCTIONS, text) == []
    assert oracles.holds_external_docs_sentence(text), "the documentation sentence is gone"
    assert oracles.holds_delegation_depth_sentence(text), "the delegation sentence is gone"
