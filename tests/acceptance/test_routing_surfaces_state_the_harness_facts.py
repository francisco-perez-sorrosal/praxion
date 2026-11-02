"""Every routing surface states the precedence and alias facts the harness applies today.

A spawn's model is chosen per-spawn first, then by its definition's `model:` floor, then by
`CLAUDE_CODE_SUBAGENT_MODEL`, then by the main session model; the variable overrides every other
layer only with `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`, so no sentence calls it a kill switch
without that condition. `opus` and `sonnet` track the newest generation; `haiku` resolves to
Haiku 5.5 on the Anthropic API and Haiku 4.5 elsewhere, never below 4.5, so the L tier is the
`haiku` alias and the researcher's simple-lookup mode and an implementer step hinted `tier: L`
pass it. A full id is never passed per spawn. The discipline-consultant's row, the policy
reference and the parity gate's description name both sanctioned downgrades: the routine consult
and the verifier's light review. No text this correction edits cites an internal record.

The surfaces: the session-start text (what the injection delivers), the path-loaded rule, the
policy reference, the L-tier definition's `model:` line, the deployment document's configuration
row, and the routing checks' shipped descriptions.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import routing_facts as rf

S, P, R, D = rf.S, rf.P, rf.R, rf.D


@pytest.fixture(scope="module")
def surfaces(tmp_path_factory) -> dict[str, str]:
    return rf.surfaces(tmp_path_factory.mktemp("session"))


@pytest.fixture(scope="module")
def descriptions(tmp_path_factory) -> dict[str, str]:
    scratch = tmp_path_factory.mktemp("descriptions")
    return {
        script: rf.check_description(script, scratch / script.split("/")[-1])
        for script in (rf.SPAWN_CHECK, rf.PARITY_GATE)
    }


def _sentences(surfaces: dict[str, str], surface: str) -> list[str]:
    return rf.sentences(surfaces[surface])


# -- The resolution order -------------------------------------------------------------------------


@pytest.mark.parametrize("surface", [S, P])
def test_the_resolution_order_reads_per_spawn_then_floor_then_the_variable_then_the_session(
    surface, surfaces
):
    layers = ("per-spawn", "capability floor", rf.ENV_VAR, "fallback")

    found = rf.first_positions(surfaces[surface], layers)

    assert -1 not in found.values(), f"the {surface} lacks a layer: {found}"
    assert list(found.values()) == sorted(found.values()), f"out of order on the {surface}: {found}"


@pytest.mark.parametrize("surface", [S, P, R])
def test_each_surface_names_the_forcing_setting(surface, surfaces):
    assert rf.holds(surfaces[surface], rf.FORCING), f"the {surface} never names {rf.FORCING}"


@pytest.mark.parametrize("surface", [S, P, R])
def test_no_surface_calls_the_variable_a_kill_switch_without_its_forcing_condition(
    surface, surfaces
):
    assert rf.unconditioned_kill_switch(surfaces[surface]) == []


def test_the_deployment_row_names_the_forcing_condition_with_any_kill_switch_claim():
    row = rf.deployment_row()

    assert rf.unconditioned_kill_switch(row) == [], row


def test_the_policy_reference_never_ranks_the_variable_above_the_floor_or_the_per_spawn_model(
    surfaces,
):
    ranking = [s for s in _sentences(surfaces, R) if rf.places_env_var_above_the_floor(s)]

    assert ranking == []


def test_the_policy_reference_names_both_effects_of_forcing(surfaces):
    blocks = [b for b in rf.move.paragraphs(surfaces[R]) if rf.FORCING in rf.move.normalize(b)]
    lines = [s for b in blocks for s in rf.sentences(b)]

    ignores_the_floor = [
        s for s in lines if "ignor" in s.lower() and any(w in s for w in ("model:", "frontmatter"))
    ]
    stops_per_spawn = [
        s
        for s in lines
        if "per-spawn" in s.lower()
        and any(w in s.lower() for w in ("cannot", "can't", "not be passed", "stop", "prevent"))
    ]

    assert ignores_the_floor, "no sentence beside the forcing setting says model: is ignored"
    assert stops_per_spawn, "no sentence beside the forcing setting says per-spawn model stops"


@pytest.mark.parametrize("surface", [P, R])
def test_inherit_is_named_as_the_floor_value_that_selects_the_main_session_model(surface, surfaces):
    assert rf.holds(surfaces[surface], "inherit")


# -- Alias facts ----------------------------------------------------------------------------------


@pytest.mark.parametrize("surface", [S, P, R])
def test_opus_and_sonnet_are_said_to_track_the_newest_generation(surface, surfaces):
    assert rf.holds(surfaces[surface], "newest generation")


def test_the_session_start_text_says_haiku_never_resolves_below_4_5(surfaces):
    saying = [s for s in _sentences(surfaces, S) if rf.names_alias(s, "haiku") and "4.5" in s]

    assert saying, "no session-start sentence names the haiku alias with 4.5"


@pytest.mark.parametrize("surface", [P, R])
@pytest.mark.parametrize("version", ["Haiku 5.5", "Haiku 4.5"])
def test_the_rule_and_reference_name_what_haiku_resolves_to_by_provider(version, surface, surfaces):
    assert rf.holds(surfaces[surface], version), f"the {surface} never names {version}"


@pytest.mark.parametrize("surface", [S, P, R, D])
def test_no_surface_says_haiku_resolves_to_haiku_3_5(surface, surfaces):
    assert [s for s in _sentences(surfaces, surface) if rf.says_haiku_is_3_5(s)] == []


@pytest.mark.parametrize("script", [rf.SPAWN_CHECK, rf.PARITY_GATE])
def test_no_check_description_says_haiku_resolves_to_haiku_3_5(script, descriptions):
    assert [s for s in rf.sentences(descriptions[script]) if rf.says_haiku_is_3_5(s)] == []


@pytest.mark.parametrize("surface", [S, P, D])
def test_the_pinned_haiku_id_is_gone_from_the_session_text_the_rule_and_the_floor_line(
    surface, surfaces
):
    assert "claude-haiku-4-5" not in surfaces[surface]


@pytest.mark.parametrize("surface", [S, P])
def test_a_full_id_is_said_never_to_be_passed_per_spawn(surface, surfaces):
    saying = [
        s for s in _sentences(surfaces, surface) if rf.says_a_full_id_is_never_passed_per_spawn(s)
    ]

    assert saying, f"no sentence on the {surface} says a full id is never passed per spawn"


@pytest.mark.parametrize("surface", [S, P, R])
def test_no_surface_says_a_full_id_is_pinned_at_spawn_time(surface, surfaces):
    assert [
        s for s in _sentences(surfaces, surface) if rf.says_a_full_id_is_pinned_at_spawn_time(s)
    ] == []


def test_the_policy_reference_names_fable_among_the_per_spawn_values(surfaces):
    assert rf.names_alias(rf.move.normalize(surfaces[R]), "fable")


def test_the_policy_reference_says_a_family_alias_resolves_to_the_session_model_of_that_family(
    surfaces,
):
    assert rf.holds(surfaces[R], "same family")


@pytest.mark.parametrize("surface", [S, P, R])
def test_full_ids_stay_reserved_for_version_locking(surface, surfaces):
    assert rf.holds(surfaces[surface], "version-locking")


# -- The L tier is the haiku alias ----------------------------------------------------------------


def test_the_tier_tables_doc_engineer_row_reads_tier_l_alias_haiku():
    cells = rf.table_row(rf.read(rf.RULE), "doc-engineer")

    assert cells[1:3] == ["L", "haiku"], cells


def test_the_l_tier_definitions_floor_is_the_haiku_alias():
    assert rf.move.frontmatter(rf.read(rf.L_TIER_DEFINITION))["model"] == "haiku"


def test_the_policy_reference_names_the_l_tier_as_the_haiku_alias(surfaces):
    naming = [
        s
        for s in _sentences(surfaces, R)
        if rf.names_the_l_tier(s)
        and rf.names_alias(s, "haiku")
        and "claude-haiku" not in s
        and not rf.says_haiku_is_3_5(s)
    ]

    assert naming, "no policy-reference sentence names the L tier as the haiku alias itself"


def test_the_policy_reference_names_no_pinned_id_as_the_l_tier(surfaces):
    pinning = [s for s in _sentences(surfaces, R) if rf.names_the_l_tier(s) and "claude-haiku" in s]

    assert pinning == []


# -- The L-tier deviations pass haiku -------------------------------------------------------------


@pytest.mark.parametrize("surface", [S, P])
def test_the_directive_tells_a_researcher_in_its_simple_lookup_mode_to_pass_haiku(
    surface, surfaces
):
    naming = [
        s
        for s in _sentences(surfaces, surface)
        if "researcher" in s and "mode" in s.lower() and rf.names_alias(s, "haiku")
    ]

    assert naming, f"no sentence on the {surface} names the researcher, a mode and haiku"


@pytest.mark.parametrize("surface", [S, P])
def test_the_directive_tells_an_implementer_step_hinted_tier_l_to_pass_haiku(surface, surfaces):
    naming = [
        s
        for s in _sentences(surfaces, surface)
        if "implementer" in s and "tier: L" in s and rf.names_alias(s, "haiku")
    ]

    assert naming, f"no sentence on the {surface} names the implementer, tier: L and haiku"


@pytest.mark.parametrize("surface", [S, P])
def test_no_surface_says_the_l_tier_is_not_a_value_to_pass(surface, surfaces):
    assert [s for s in _sentences(surfaces, surface) if rf.says_the_l_tier_is_not_passable(s)] == []


@pytest.mark.parametrize("surface", [S, P])
def test_the_doc_engineer_gains_no_per_spawn_deviation(surface, surfaces):
    passing = [
        s for s in _sentences(surfaces, surface) if "doc-engineer" in s and "pass" in s.lower()
    ]

    assert passing == []


# -- Both sanctioned downgrades -------------------------------------------------------------------


def test_the_consultant_row_names_the_routine_consult_and_the_light_review():
    row = " ".join(rf.table_row(rf.read(rf.RULE), "discipline-consultant"))

    assert "routine" in row, row
    assert rf.LIGHT_REVIEW.search(row), row


def test_the_policy_reference_names_the_routine_consult_and_the_light_review(surfaces):
    assert rf.holds(surfaces[R], "routine")
    assert rf.LIGHT_REVIEW.search(surfaces[R])


def test_the_parity_gates_description_names_the_routine_consult_and_the_light_review(
    descriptions,
):
    text = descriptions[rf.PARITY_GATE]

    assert "routine" in text, "the parity gate's description never names the routine consult"
    assert rf.LIGHT_REVIEW.search(text), "the parity gate's description never names light review"


@pytest.mark.parametrize("surface", [P, R])
def test_no_routing_surface_calls_either_downgrade_the_only_one(surface, surfaces):
    assert rf.SINGLE_SANCTIONED_DOWNGRADE.findall(rf.move.normalize(surfaces[surface])) == []


def test_the_parity_gates_description_calls_neither_downgrade_the_only_one(descriptions):
    text = rf.move.normalize(descriptions[rf.PARITY_GATE])

    assert rf.SINGLE_SANCTIONED_DOWNGRADE.findall(text) == []


# -- Changed texts cite no internal record --------------------------------------------------------


EDITED_TEXTS = sorted(
    {
        rf.RULE,
        rf.RESIDENT,
        rf.POLICY_REFERENCE,
        rf.L_TIER_DEFINITION,
        *rf.definitions_naming("check_spawn_models.py"),
    }
)


@pytest.mark.parametrize("relpath", EDITED_TEXTS)
def test_an_edited_routing_text_cites_no_decision_ledger_or_archived_spec_id(relpath):
    assert rf.INTERNAL_RECORD.findall(rf.read(relpath)) == []


@pytest.mark.parametrize("script", [rf.SPAWN_CHECK, rf.PARITY_GATE])
def test_a_routing_checks_description_cites_no_decision_ledger_or_archived_spec_id(
    script, descriptions
):
    assert rf.INTERNAL_RECORD.findall(descriptions[script]) == []
