"""With Praxion's hooks absent, a session never falls to nothing.

Hooks absent is either the rule injection impaired (switched off with
`PRAXION_DISABLE_RULE_INJECTION`, or its YAML reader or rules manifest unavailable while its hook
still runs) or no Praxion hook running at all (switched off, the plugin
disabled, no working Python). With the injection impaired, a managed session and each inheriting
spawn it starts still receive what they receive today: the coordination protocol, the
intermediate-documents rule, the ADR resident, the behavioural contract and the user's personal
instructions. With no hook running, they receive at least the constitution as it arrives without
hooks (the contract, the user's personal instructions and the two constitutional sentences) plus
the project's own `CLAUDE.md`, and the full procedures return at the next start with hooks
running. An unmanaged session, in either case, keeps the contract, the user's personal
instructions and the two constitutional sentences.
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


PROJECT_INSTRUCTIONS = (
    "# Billing service\n\n"
    "Every amount in this service is an integer number of cents, never a float.\n\n"
    "Run the ledger reconciliation suite before touching any refund code path.\n"
)
SPAWNS = [f"praxion:{gate.INHERITING_ROLE}", gate.HOST_NATIVE]


def _managed_project(machine: gate.Machine) -> Path:
    project = places.repository(machine.sandbox / "project", state_marker="hookless gating fixture")
    (project / "CLAUDE.md").write_text(PROJECT_INSTRUCTIONS, encoding="utf-8")
    return project


def _keeps_the_constitution_and_the_project_file(started: gate.Start) -> list[str]:
    """What a hookless managed start lacks of its floor: each lack named."""
    text = started.process_text
    lacks = [
        unit
        for unit in (oracles.BEHAVIOURAL_CONTRACT, oracles.USER_INSTRUCTIONS)
        if oracles.missing_statements(unit, text)
    ]
    if not oracles.holds_external_docs_sentence(text):
        lacks.append("the external-documentation sentence")
    if not oracles.holds_delegation_depth_sentence(text):
        lacks.append("the delegation-depth sentence")
    if oracles.statements(PROJECT_INSTRUCTIONS) - oracles.statements(started.text):
        lacks.append("the project's own CLAUDE.md")
    return lacks


# -- The injection impaired -----------------------------------------------------------------------


@pytest.mark.parametrize("unit", MANAGED_FLOOR)
@pytest.mark.parametrize("entrypoint", [gate.INTERACTIVE, gate.HEADLESS])
def test_a_managed_session_with_the_injection_off_still_receives_todays_floor(
    machine, unit, entrypoint
):
    project = places.repository(machine.sandbox / "project", managed=True)

    started = gate.session_start(machine, project, hooks="injection-off", entrypoint=entrypoint)

    assert oracles.missing_statements(unit, started.process_text) == [], f"the {unit} is gone"


@pytest.mark.parametrize("unit", MANAGED_FLOOR)
@pytest.mark.parametrize("agent", SPAWNS)
def test_an_inheriting_spawn_with_the_injection_off_still_receives_todays_floor(
    machine, unit, agent
):
    project = places.repository(machine.sandbox / "project", managed=True)

    text = gate.spawn_start(machine, project, agent, hooks="injection-off").process_text

    assert oracles.missing_statements(unit, text) == [], f"{agent} lost the {unit}"


# -- The injector's inputs impaired, its hook still running ---------------------------------------


def _lacks_floor(text: str) -> list[str]:
    return [unit for unit in MANAGED_FLOOR if oracles.missing_statements(unit, text)]


@pytest.mark.parametrize("how", gate.IMPAIRMENTS)
@pytest.mark.parametrize("entrypoint", [gate.INTERACTIVE, gate.HEADLESS])
def test_a_managed_session_with_an_impaired_injector_still_receives_todays_floor(
    template, tmp_path, how, entrypoint
):
    machine = gate.impaired_machine(template, tmp_path / "machine", how)
    project = places.repository(machine.sandbox / "project", managed=True)

    started = gate.session_start(machine, project, entrypoint=entrypoint)

    assert _lacks_floor(started.process_text) == [], f"lost with the injector impaired ({how})"


@pytest.mark.parametrize("how", gate.IMPAIRMENTS)
@pytest.mark.parametrize("agent", SPAWNS)
def test_an_inheriting_spawn_with_an_impaired_injector_still_receives_todays_floor(
    template, tmp_path, how, agent
):
    machine = gate.impaired_machine(template, tmp_path / "machine", how)
    project = places.repository(machine.sandbox / "project", managed=True)

    text = gate.spawn_start(machine, project, agent).process_text

    assert _lacks_floor(text) == [], f"{agent} lost its floor with the injector impaired ({how})"


@pytest.mark.parametrize("how", gate.IMPAIRMENTS)
def test_an_unmanaged_session_with_an_impaired_injector_keeps_the_constitution(
    template, tmp_path, how
):
    machine = gate.impaired_machine(template, tmp_path / "machine", how)
    directory = places.repository(machine.sandbox / "plain")

    text = gate.session_start(machine, directory).process_text

    assert oracles.missing_statements(oracles.BEHAVIOURAL_CONTRACT, text) == []
    assert oracles.missing_statements(oracles.USER_INSTRUCTIONS, text) == []
    assert oracles.holds_external_docs_sentence(text), "the documentation sentence is gone"
    assert oracles.holds_delegation_depth_sentence(text), "the delegation sentence is gone"


# -- No hook running ------------------------------------------------------------------------------


@pytest.mark.parametrize("entrypoint", [gate.INTERACTIVE, gate.HEADLESS])
def test_a_hookless_managed_session_keeps_the_constitution_and_its_project_file(
    machine, entrypoint
):
    project = _managed_project(machine)

    started = gate.session_start(machine, project, hooks="off", entrypoint=entrypoint)

    assert _keeps_the_constitution_and_the_project_file(started) == []


@pytest.mark.parametrize("agent", SPAWNS)
def test_a_hookless_inheriting_spawn_keeps_the_constitution_and_its_project_file(machine, agent):
    project = _managed_project(machine)

    spawned = gate.spawn_start(machine, project, agent, hooks="off")

    assert _keeps_the_constitution_and_the_project_file(spawned) == []


def test_the_full_procedures_return_at_the_next_start_with_hooks_running(machine):
    project = _managed_project(machine)
    gate.session_start(machine, project, hooks="off")

    text = gate.session_start(machine, project).process_text

    lost = [u for u in oracles.MANAGED_ONLY_TEXTS if oracles.missing_statements(u, text)]
    assert lost == [], f"after a hookless start the next start lacks: {lost}"
    assert oracles.holds_decision_context(text, "hookless gating fixture")


# -- Unmanaged ------------------------------------------------------------------------------------


@pytest.mark.parametrize("hooks", ABSENT)
def test_an_unmanaged_session_without_hooks_still_receives_the_constitution(machine, hooks):
    directory = places.repository(machine.sandbox / "plain")

    text = gate.session_start(machine, directory, hooks=hooks).process_text

    assert oracles.missing_statements(oracles.BEHAVIOURAL_CONTRACT, text) == []
    assert oracles.missing_statements(oracles.USER_INSTRUCTIONS, text) == []
    assert oracles.holds_external_docs_sentence(text), "the documentation sentence is gone"
    assert oracles.holds_delegation_depth_sentence(text), "the delegation sentence is gone"
