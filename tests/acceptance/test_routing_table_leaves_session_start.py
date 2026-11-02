"""The routing tier table leaves session start; the orchestrator's pre-spawn guidance stays there.

A session opens holding a short routing text, delivered by the session-start rule injection, that
states the resolution order with the per-spawn lever first, the alias note with what haiku is,
and a restated spawn directive: a spawn passing no model runs at its definition's floor (held to
the table by the parity gate), and a model is passed per spawn only for a closed list of
deviations. The full rule, its tier table unchanged, loads by path when an agent definition or
the routing policy reference is touched. Every statement of today's rule lands on each surface
the placement table names, and a blacklist naming the rule still removes all routing text.

The base rule and the base always-loaded reading were frozen before the change
(`model_routing_move`).
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import model_routing_move as move

REPO = move.REPO_ROOT
BLACKLISTS = (["swe/agent-model-routing"], ["swe/*"])
SCOPED_TOUCHES = (
    "agents/implementer.md",
    "agents/discipline-consultant.md",
    "agents/a-new-role.md",
    move.POLICY_REFERENCE,
)


@pytest.fixture(scope="module")
def injected(tmp_path_factory) -> move.Injection:
    return move.session_start(tmp_path_factory.mktemp("session"))


@pytest.fixture(scope="module")
def session_text(injected) -> str:
    """The routing text the session-start injection delivers."""
    return move.routing_section(injected.context)


@pytest.fixture(scope="module")
def path_loaded_text() -> str:
    return (REPO / move.RULE).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def surfaces(session_text, path_loaded_text) -> dict[str, str]:
    return {
        move.S: session_text,
        move.P: move.body(path_loaded_text),
        move.R: (REPO / move.POLICY_REFERENCE).read_text(encoding="utf-8"),
    }


# -- At session start -----------------------------------------------------------------------------


def test_a_session_starts_with_routing_text_from_the_injection(session_text):
    assert session_text, "the session-start injection delivers no text under the routing title"


def test_a_session_starts_holding_no_row_of_the_tier_table(injected):
    rows = move.tier_rows(move.fixture_text("base_rule.md"))

    held = [row for row in rows if row in injected.context]

    assert held == [], f"{len(held)} tier-table rows reach session start"


def test_the_always_loaded_reading_counts_the_routing_text_in_place_of_the_rule(tmp_path):
    base = move.fixture_json("base_budget_files.json")

    files = move.budget_files(tmp_path)
    added = sorted(set(files) - set(base))
    removed = sorted(set(base) - set(files))

    assert removed == [f"<repo>/{move.RULE}"], removed
    assert len(added) == 1, f"expected the session-start routing text alone to join: {added}"
    assert move.session_start_routing_file(tmp_path / "again") == added[0][len("<repo>/") :]


def test_the_always_loaded_reading_stays_under_its_ceiling(tmp_path):
    exit_code, reading = move.budget(tmp_path)

    assert (exit_code, reading["over_by"]) == (0, 0), reading
    assert reading["tokens"] <= move.BUDGET_CEILING, reading


# -- Where each statement of today's rule lands ---------------------------------------------------


def _placements() -> list:
    return [
        pytest.param(statement, surface, id=f"{statement.sid}-on-the-{surface.replace(' ', '-')}")
        for statement in move.PLACEMENT
        for surface in statement.tokens
    ]


@pytest.mark.parametrize(("statement", "surface"), _placements())
def test_each_statement_lands_on_every_surface_the_placement_names(statement, surface, surfaces):
    text = surfaces[surface]

    missing = [token for token in statement.tokens[surface] if not move.holds(text, token)]

    assert missing == [], f"{statement.meaning}: the {surface} lacks {missing}"


@pytest.mark.parametrize(
    "statement",
    [s for s in move.PLACEMENT if s.absent_at_start],
    ids=lambda s: s.sid,
)
def test_statements_kept_for_authors_stay_out_of_the_session_start_text(statement, injected):
    held = [token for token in statement.absent_at_start if move.holds(injected.context, token)]

    assert held == [], f"{statement.meaning}: session start holds {held}"


@pytest.mark.parametrize("surface", [move.S, move.P])
def test_the_resolution_order_names_the_per_spawn_lever_first_and_the_session_model_last(
    surface, surfaces
):
    text = move.normalize(surfaces[surface]).lower()
    layers = ("lever", "capability floor", "claude_code_subagent_model", "fallback")

    positions = [text.find(layer) for layer in layers]

    found = dict(zip(layers, positions, strict=True))

    assert -1 not in positions, found
    assert positions == sorted(positions), found


@pytest.mark.parametrize("deviation", sorted(move.DEVIATIONS))
def test_the_session_start_text_names_each_deviations_role_marker_and_model(
    deviation, session_text
):
    role, marker, models = move.DEVIATIONS[deviation]

    naming = [
        s
        for s in move.sentences(session_text)
        if move.holds(s, role) and move.holds(s, marker) and any(move.holds(s, m) for m in models)
    ]

    assert naming, f"no sentence names {role}, {marker} and one of {models}"


# -- The restated spawn directive -----------------------------------------------------------------


@pytest.mark.parametrize("surface", [move.S, move.P, move.R])
def test_no_surface_tells_the_orchestrator_to_pass_the_rows_alias_on_every_spawn(surface, surfaces):
    directing = [
        s
        for s in move.sentences(surfaces[surface])
        if move.EVERY_SPAWN_DIRECTIVE.search(s) or move.ROW_ALIAS_DIRECTIVE.search(s)
    ]

    assert directing == [], directing


@pytest.mark.parametrize("surface", [move.S, move.P])
def test_no_surface_says_a_spawn_falls_through_to_the_session_model(surface, surfaces):
    claiming = [s for s in move.sentences(surfaces[surface]) if move.FALL_THROUGH.search(s)]

    assert claiming == [], claiming


@pytest.mark.parametrize("surface", [move.S, move.P])
def test_the_directive_says_a_spawn_passing_no_model_runs_at_its_floor_held_by_the_parity_gate(
    surface, surfaces
):
    text = surfaces[surface]

    stating = [s for s in move.sentences(text) if move.NO_MODEL_RUNS_AT_FLOOR.search(s)]

    assert stating, "no sentence says a spawn passing no model runs at its definition's floor"
    assert move.holds(text, "parity"), "the directive does not name the parity gate"


@pytest.mark.parametrize("surface", [move.S, move.P])
def test_the_directive_passes_a_model_only_for_a_listed_deviation_or_under_the_kill_switch(
    surface, surfaces
):
    sentences = move.sentences(surfaces[surface])

    only_for = [s for s in sentences if move.ONLY_FOR_A_DEVIATION.search(s)]

    assert only_for, "no sentence limits a per-spawn model to the listed deviations"
    assert any(move.holds(s, "kill switch") for s in sentences)


def test_the_policy_references_direct_invocation_entry_points_are_restated_not_dropped(surfaces):
    assert move.holds(surfaces[move.R], "Direct-invocation entry points")


# -- The full rule, by path -----------------------------------------------------------------------


@pytest.mark.parametrize("touched", SCOPED_TOUCHES)
def test_touching_an_agent_definition_or_the_policy_reference_loads_the_full_rule(
    touched, path_loaded_text
):
    scope = move.frontmatter(path_loaded_text).get("paths") or []

    assert move.scope_takes(scope, touched), (
        f"the rule's path scope {scope} does not take {touched}"
    )


CORRECTED_ROWS = ("| `doc-engineer` |", "| `discipline-consultant` |")
KEPT_PARAGRAPHS = ("## Agent Model Routing", "Governs subagent routing")


def _uncorrected_rows(text: str) -> list[str]:
    return [row for row in move.tier_table(text).splitlines() if not row.startswith(CORRECTED_ROWS)]


def test_the_full_rules_tier_table_is_the_bases_but_for_its_corrected_rows(path_loaded_text):
    assert _uncorrected_rows(path_loaded_text) == _uncorrected_rows(
        move.fixture_text("base_rule.md")
    )


def test_the_full_rule_differs_from_the_base_only_between_its_title_and_its_scope(path_loaded_text):
    before = move.paragraphs(move.body(move.fixture_text("base_rule.md")))

    dropped, added = move.replaced_paragraphs(before, move.paragraphs(move.body(path_loaded_text)))

    assert [p for p in dropped if p.startswith(KEPT_PARAGRAPHS)] == [], dropped
    assert added, "the directive paragraph was removed, not restated"


# -- The blacklist keeps its reach ----------------------------------------------------------------


@pytest.mark.parametrize("disable", BLACKLISTS, ids=lambda d: d[0])
def test_a_blacklist_naming_the_rule_removes_all_routing_text_at_session_start(tmp_path, disable):
    injection = move.session_start(tmp_path, disable=disable)

    leaked = [
        token
        for token in (move.TITLE, "CLAUDE_CODE_SUBAGENT_MODEL", "Mode: acceptance-design")
        if move.holds(injection.context, token)
    ]

    assert leaked == [], f"routing text reached a session that blacklisted it: {leaked}"


@pytest.mark.parametrize("disable", BLACKLISTS, ids=lambda d: d[0])
def test_a_blacklist_naming_the_rule_excludes_the_path_loaded_rule(tmp_path, disable):
    injection = move.session_start(tmp_path, disable=disable)

    assert "**/.claude/rules/swe/agent-model-routing.md" in injection.excludes, injection.excludes


@pytest.mark.parametrize("disable", BLACKLISTS, ids=lambda d: d[0])
def test_the_injection_summary_names_the_suppressed_routing_rule(tmp_path, disable):
    injection = move.session_start(tmp_path, disable=disable)

    assert move.RULE_ID in injection.summary, injection.stderr


def test_the_hackathon_preset_removes_all_routing_text(tmp_path):
    injection = move.session_start(tmp_path, preset=REPO / move.HACKATHON_PRESET)

    assert not move.holds(injection.context, move.TITLE), "the hackathon preset leaks routing text"
    assert "**/.claude/rules/swe/agent-model-routing.md" in injection.excludes
