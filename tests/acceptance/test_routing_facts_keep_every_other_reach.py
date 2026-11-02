"""Correcting the routing facts changes no other reach, and the spawn-model check gains a reader.

The gate-liveness check finds an invoker for the spawn-model check, and every reader its texts
name invokes it. The always-loaded reading counts the base's files. The Codex and Cursor exports
equal the base's after root normalisation except where a corrected statement explains the
difference: the L-tier row's alias, the rationale of the rows whose cell changed, the routing
rule's corrected paragraphs. Without the session-start injection, each definition still carries
its floor and Cursor still gets the routing rule. The named gates pass and still bite.

The base observations were frozen before the change (`routing_facts.freeze`).
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import routing_facts as rf

L_TIER_AGENT = "doc-engineer"
CHANGED_ROWS = {"doc-engineer", "discipline-consultant"}
GATES = (
    [rf.PARITY_GATE],
    ["scripts/regenerate_rules_manifest.py", "--check"],
    ["scripts/check_kernel_manifest.py"],
    ["scripts/generate_kernels.py", "--check"],
    ["scripts/sync_canonical_blocks.py", "--check"],
)


# -- The spawn-model check has a reader -----------------------------------------------------------


def test_the_uninvoked_gate_check_finds_an_invoker_for_the_spawn_model_check(tmp_path):
    findings = rf.uninvoked_gate_findings(tmp_path)

    assert [f for f in findings if f.get("file") == rf.SPAWN_CHECK] == []


def test_an_agent_definition_tells_its_agent_to_run_the_check_over_routing_sessions():
    telling = [
        relpath
        for relpath in rf.definitions_naming("check_spawn_models.py")
        if rf.shipped_texts.sentences_matching(rf.read(relpath), "check_spawn_models", "rout")
    ]

    assert telling, "no agent definition tells its agent to run the spawn-model check"


def _readers_named(text: str) -> set[str]:
    sentences = rf.shipped_texts.sentences_matching(text, r"\breaders?\b")
    return {role for role in rf.agent_roles() for s in sentences if role in s}


@pytest.fixture(scope="module")
def reader_texts(tmp_path_factory) -> dict[str, str]:
    scratch = tmp_path_factory.mktemp("descriptions")
    return {
        rf.POLICY_REFERENCE: rf.read(rf.POLICY_REFERENCE),
        rf.SPAWN_CHECK: rf.check_description(rf.SPAWN_CHECK, scratch),
    }


@pytest.mark.parametrize("source", [rf.POLICY_REFERENCE, rf.SPAWN_CHECK])
def test_every_reader_a_text_names_for_the_check_invokes_it(source, reader_texts):
    named = _readers_named(reader_texts[source])
    invoking = {
        path.split("/")[-1][: -len(".md")]
        for path in rf.definitions_naming("check_spawn_models.py")
    }

    assert named, f"{source} names no reader of the spawn-model check"
    assert named <= invoking, (
        f"{source} names readers whose definitions never invoke it: {named - invoking}"
    )


# -- The always-loaded routing text does not grow its file list -----------------------------------


def test_the_always_loaded_reading_counts_the_bases_files(tmp_path):
    assert rf.budget_files(tmp_path) == rf.fixture_json("base_budget_files.json")


# -- Exporter output is the base's or explained ---------------------------------------------------


@pytest.fixture(scope="module")
def adapter(tmp_path_factory) -> dict:
    return rf.adapter_exports(tmp_path_factory.mktemp("adapter"))


@pytest.fixture(scope="module")
def base_adapter() -> dict:
    return rf.fixture_json("base_adapter.json")


def test_the_codex_adapter_keeps_every_agents_tier_and_codex_route(adapter, base_adapter):
    def tier_routes(exports: dict) -> dict:
        return {
            agent: (route["canonical_tier"], route["codex_adapter"])
            for agent, route in rf.routes(exports["model_routing.json"]).items()
        }

    assert tier_routes(adapter) == tier_routes(base_adapter)


def test_the_codex_adapter_reads_the_l_tier_alias_as_haiku_and_every_other_alias_as_the_base(
    adapter, base_adapter
):
    shipped = {a: r["canonical_alias"] for a, r in rf.routes(adapter["model_routing.json"]).items()}
    base = {
        a: r["canonical_alias"] for a, r in rf.routes(base_adapter["model_routing.json"]).items()
    }

    assert shipped == base | {L_TIER_AGENT: "haiku"}


def test_the_codex_adapter_changes_rationale_only_on_the_rows_whose_cell_changed(
    adapter, base_adapter
):
    shipped = rf.routes(adapter["model_routing.json"])
    base = rf.routes(base_adapter["model_routing.json"])

    changed = {a for a in base if shipped.get(a, {}).get("rationale") != base[a]["rationale"]}

    assert changed <= CHANGED_ROWS, changed


def test_the_codex_adapters_other_exports_equal_the_bases(adapter, base_adapter):
    def rest(exports: dict) -> dict:
        routing = {k: v for k, v in exports["model_routing.json"].items() if k != "agent_routes"}
        return {
            "model_routing.json": routing,
            "pipeline_semantics.json": exports["pipeline_semantics.json"],
        }

    assert rest(adapter) == rest(base_adapter)


@pytest.fixture(scope="module")
def codex_agents(tmp_path_factory) -> dict:
    return rf.codex_agents(tmp_path_factory.mktemp("codex-agents"))


def test_every_codex_agent_keeps_the_bases_model_settings(codex_agents):
    base = rf.fixture_json("base_codex_agents.json")["agents"]

    settings = {
        name: {"model": a["model"], "model_reasoning_effort": a["model_reasoning_effort"]}
        for name, a in codex_agents.items()
    }

    assert settings == {
        name: {"model": a["model"], "model_reasoning_effort": a["model_reasoning_effort"]}
        for name, a in base.items()
    }


def test_every_codex_agents_instructions_but_the_l_tier_agents_are_the_bases(codex_agents):
    base = rf.fixture_json("base_codex_agents.json")["agents"]

    changed = sorted(
        name
        for name, a in codex_agents.items()
        if rf.digest(a["instructions"]) != base.get(name, {}).get("instructions_digest")
    )

    assert set(changed) <= {L_TIER_AGENT}, changed


def test_the_l_tier_agents_codex_instructions_differ_only_by_its_model_line(codex_agents):
    before = rf.fixture_json("base_codex_agents.json")["l_tier_instructions"].splitlines()
    after = codex_agents[L_TIER_AGENT]["instructions"].splitlines()

    differing = sorted(set(before) ^ set(after))

    assert all(line.startswith("model:") for line in differing), differing


@pytest.fixture(scope="module")
def bridge(tmp_path_factory) -> dict:
    return rf.bridge_reach(tmp_path_factory.mktemp("bridge"))


@pytest.mark.parametrize(
    "key", ["always_on", "portable_always_on", "path_scoped", "rule_paths", "pointer"]
)
def test_the_codex_bridge_keeps_the_bases_rule_sets_paths_and_pointer(bridge, key):
    assert bridge[key] == rf.fixture_json("base_bridge.json")[key]


def test_the_routing_rules_bridge_entry_differs_only_by_a_summary_drawn_from_the_rule(bridge):
    base = rf.fixture_json("base_bridge.json")["routing_entry"]
    shipped = bridge["routing_entry"] or {}

    differing = rf.move.routing_entry_difference(base, shipped)
    summary = rf.move.normalize(shipped.get("summary", "")).strip()

    assert set(differing) <= {"summary"}, differing
    assert summary in rf.move.normalize(rf.read(rf.RULE)), summary


@pytest.fixture(scope="module")
def cursor(tmp_path_factory) -> dict[str, bytes]:
    return rf.cursor_export(tmp_path_factory.mktemp("cursor"))


def test_the_cursor_export_writes_the_bases_files_and_all_but_the_routing_rule_unchanged(cursor):
    base = rf.fixture_json("base_cursor.json")

    changed = sorted(
        rel
        for rel, data in cursor.items()
        if rel != rf.CURSOR_RULE and rf.move.digest(data) != base.get(rel)
    )

    assert sorted(cursor) == sorted(base)
    assert changed == []


def test_the_cursor_routing_files_changes_are_the_routing_rules_corrected_paragraphs(cursor):
    rule_dropped, rule_added = rf.changed_paragraphs(
        rf.move.body(rf.fixture_text("base_rule.md")), rf.move.body(rf.read(rf.RULE))
    )
    cursor_dropped, cursor_added = rf.changed_paragraphs(
        rf.fixture_text("base_cursor_rule.md"), cursor[rf.CURSOR_RULE].decode("utf-8")
    )

    assert cursor_added <= rule_added, sorted(cursor_added - rule_added)
    assert cursor_dropped <= rule_dropped, sorted(cursor_dropped - rule_dropped)


# -- Routing without the hooks falls back to today's -----------------------------------------------


@pytest.mark.parametrize("role", rf.agent_roles())
def test_every_agent_definition_carries_its_own_model_floor(role):
    assert rf.move.frontmatter(rf.read(f"agents/{role}.md")).get("model"), role


def test_cursor_still_gets_the_routing_rule_with_its_tier_table(cursor):
    text = cursor[rf.CURSOR_RULE].decode("utf-8")

    assert rf.move.TIER_TABLE_HEADING in text
    assert "| `doc-engineer` |" in text


# -- The named gates pass and still bite ----------------------------------------------------------


@pytest.mark.parametrize("argv", GATES, ids=lambda argv: argv[0].split("/")[-1])
def test_the_named_gate_passes_on_the_shipped_tree(tmp_path, argv):
    result = rf.run_check(argv, tmp_path)

    assert result.returncode == 0, (result.stdout + result.stderr)[-2000:]


def test_the_install_check_reports_no_rule_finding_after_an_install(tmp_path):
    installed = rf.move.install(tmp_path)
    assert installed.returncode == 0, (installed.stdout + installed.stderr)[-2000:]

    checked = rf.move.install_check(tmp_path)

    assert rf.move.install_check_rule_findings(checked.stdout) == [], checked.stdout[-2000:]


def test_the_parity_gate_reports_an_l_tier_definition_pinned_to_a_full_id(tmp_path):
    sandbox = rf.new_sandbox(tmp_path)
    rf.set_floor(sandbox, L_TIER_AGENT, "claude-haiku-4-5")

    result = rf.gate_in_sandbox([rf.PARITY_GATE], sandbox)

    assert result.returncode == 1, result.stdout + result.stderr
    assert L_TIER_AGENT in result.stdout + result.stderr


def test_the_parity_gates_declared_difference_is_still_the_consultants_floor(tmp_path):
    sandbox = rf.new_sandbox(tmp_path)
    rf.set_floor(sandbox, "discipline-consultant", "opus")

    result = rf.gate_in_sandbox([rf.PARITY_GATE], sandbox)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "discipline-consultant" in result.stdout + result.stderr


def test_the_kernel_gate_reports_a_session_start_routing_line_that_is_no_line_of_the_rule(tmp_path):
    sandbox = rf.new_sandbox(tmp_path)
    sandbox.append(rf.RESIDENT, "Spawns pass a pinned full id for the L tier on every spawn.")

    result = rf.gate_in_sandbox(["scripts/check_kernel_manifest.py"], sandbox)

    assert result.returncode != 0
    assert "pinned full id for the L tier" in result.stdout + result.stderr
