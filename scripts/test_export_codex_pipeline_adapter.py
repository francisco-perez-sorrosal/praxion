from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPORTER_PATH = REPO_ROOT / "codex" / "config" / "export-codex-pipeline-adapter.py"


def load_exporter():
    spec = importlib.util.spec_from_file_location("export_codex_pipeline_adapter", EXPORTER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_pipeline_adapter_derives_metadata_from_canonical_rules(tmp_path: Path):
    exporter = load_exporter()
    out_dir = tmp_path / ".codex"

    written = exporter.export_pipeline_adapter(REPO_ROOT, out_dir)

    pipeline_path = out_dir / "praxion" / "pipeline_semantics.json"
    routing_path = out_dir / "praxion" / "model_routing.json"
    assert pipeline_path in written
    assert routing_path in written

    pipeline = json.loads(pipeline_path.read_text(encoding="utf-8"))
    routing = json.loads(routing_path.read_text(encoding="utf-8"))

    assert pipeline["source_paths"]["coordination_protocol"].endswith(
        "rules/swe/swe-agent-coordination-protocol.md"
    )
    assert pipeline["source_paths"]["agent_intermediate_documents"].endswith(
        "rules/swe/agent-intermediate-documents.md"
    )
    assert [tier["tier"] for tier in pipeline["process_tiers"]] == [
        "Direct",
        "Lightweight",
        "Standard",
        "Full",
        "Spike",
    ]
    standard = next(tier for tier in pipeline["process_tiers"] if tier["tier"] == "Standard")
    assert standard["codex_adapter"]["worktree"] == "dedicated_worktree"
    assert pipeline["pipeline"]["shared_document_root"] == ".ai-work/<task-slug>/"
    assert any(agent["agent"] == "verifier" for agent in pipeline["agents"])

    assert routing["source_path"].endswith("rules/swe/agent-model-routing.md")

    # Alias expectations are re-derived from the routing rule's own table, not hardcoded --
    # a doc-contract test that hard-codes the value it is meant to check against is not a
    # contract test (the rule, not this file, is the source of truth for which alias an
    # agent currently resolves to).
    model_text = (REPO_ROOT / "rules" / "swe" / "agent-model-routing.md").read_text(
        encoding="utf-8"
    )
    rule_rows_by_agent = {
        row["agent"]: row for row in exporter.table_after_heading(model_text, "### Tier Table")
    }

    architect = next(
        route for route in routing["agent_routes"] if route["agent"] == "systems-architect"
    )
    assert architect["canonical_alias"] == rule_rows_by_agent["systems-architect"]["alias"]
    assert architect["codex_adapter"]["codex_tier"] == "high"

    doc_engineer = next(
        route for route in routing["agent_routes"] if route["agent"] == "doc-engineer"
    )
    assert doc_engineer["canonical_tier"] == "L"
    assert doc_engineer["codex_adapter"]["reasoning_effort"] == "low"
    assert "gpt-" not in routing_path.read_text(encoding="utf-8")


def test_export_pipeline_adapter_fails_when_canonical_table_changes(tmp_path: Path):
    exporter = load_exporter()
    repo_root = tmp_path / "repo"
    rules_dir = repo_root / "rules" / "swe"
    rules_dir.mkdir(parents=True)
    (rules_dir / "agent-intermediate-documents.md").write_text(
        "## Agent Intermediate Documents\n",
        encoding="utf-8",
    )
    (rules_dir / "swe-agent-coordination-protocol.md").write_text(
        "## SWE Agent Coordination Protocol\n\n### Process Calibration\n\n"
        "| Tier | Signals | Process |\n|---|---|---|\n| Weird | x | y |\n\n"
        "### Available Agents\n\n| Agent | Purpose | Output | Bg Safe |\n|---|---|---|---|\n"
        "| `researcher` | x | y | Yes |\n",
        encoding="utf-8",
    )
    (rules_dir / "agent-model-routing.md").write_text(
        "## Agent Model Routing\n\n### Tier Table\n\n"
        "| Agent | Tier | Alias | Rationale |\n|---|---|---|---|\n"
        "| `researcher` | M | sonnet | x |\n",
        encoding="utf-8",
    )

    with pytest.raises(
        exporter.PipelineAdapterError, match="missing Codex process adapter for tier: Weird"
    ):
        exporter.export_pipeline_adapter(repo_root, tmp_path / ".codex")


def test_model_routing_resolves_every_tier_declared_in_the_routing_rule():
    # Totality: the adapter must key on the routing rule's stable semantic column (Tier:
    # H/M/L), never on the volatile Alias column. Every Tier cell the rule declares must
    # resolve through CODEX_MODEL_TIER_ADAPTER -- this fails the moment the adapter is keyed
    # on something other than Tier, independent of which alias currently happens to be
    # assigned to which agent.
    exporter = load_exporter()
    model_text = (REPO_ROOT / "rules" / "swe" / "agent-model-routing.md").read_text(
        encoding="utf-8"
    )
    rows = exporter.table_after_heading(model_text, "### Tier Table")
    tiers_in_rule = {row["tier"] for row in rows}

    assert tiers_in_rule, "expected at least one Tier row in the routing rule's Tier Table"
    unresolved = sorted(
        tier for tier in tiers_in_rule if tier not in exporter.CODEX_MODEL_TIER_ADAPTER
    )
    assert not unresolved, (
        "CODEX_MODEL_TIER_ADAPTER does not resolve every Tier cell declared in "
        f"rules/swe/agent-model-routing.md: missing {unresolved}"
    )


def test_model_adapter_source_contains_no_claude_alias_literal():
    # No-alias-literal: a Claude alias in the adapter's own source is the coupling this
    # invariant removes. This is stricter than the totality test above -- it fails at
    # authoring time if alias coupling is reintroduced, rather than waiting for an alias to
    # change.
    source = EXPORTER_PATH.read_text(encoding="utf-8")
    alias_literals = re.findall(r"opus|sonnet|haiku|claude-", source)

    assert not alias_literals, (
        "codex/config/export-codex-pipeline-adapter.py must contain no Claude alias literal "
        f"(found: {alias_literals}); key on the routing rule's Tier column instead"
    )


def _write_model_routing_rule(repo_root: Path, *, tier: str, alias: str) -> None:
    rules_dir = repo_root / "rules" / "swe"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "agent-model-routing.md").write_text(
        "## Agent Model Routing\n\n### Tier Table\n\n"
        "| Agent | Tier | Alias | Rationale |\n|---|---|---|---|\n"
        f"| `researcher` | {tier} | {alias} | x |\n",
        encoding="utf-8",
    )


def test_rejects_unknown_tier_in_model_routing_rule(tmp_path: Path):
    # REQ-02: export_model_routing()'s own raise (export-codex-pipeline-adapter.py:194)
    # must fire, naming the tier, when the Tier Table declares a value
    # CODEX_MODEL_TIER_ADAPTER does not know. The existing raise-path test above
    # (test_export_pipeline_adapter_fails_when_canonical_table_changes) only reaches
    # export_pipeline_semantics()'s *process*-tier raise -- export_pipeline_adapter()
    # fails there before export_model_routing() is ever called, so this line has never
    # been exercised. Calling export_model_routing() directly closes that gap.
    exporter = load_exporter()
    repo_root = tmp_path / "repo"
    _write_model_routing_rule(repo_root, tier="X", alias="sonnet")

    with pytest.raises(
        exporter.PipelineAdapterError, match="missing Codex model adapter for tier: X"
    ):
        exporter.export_model_routing(repo_root)


def test_model_routing_accepts_any_alias_for_a_recognised_tier(tmp_path: Path):
    # REQ-01 companion: canonical_alias is opaque pass-through provenance, never a lookup
    # key -- an arbitrary/unfamiliar alias string on a recognised Tier must resolve
    # cleanly, not raise, so an alias-only rule change can never break the Codex export.
    exporter = load_exporter()
    repo_root = tmp_path / "repo"
    _write_model_routing_rule(repo_root, tier="M", alias="claude-future-9")

    routing = exporter.export_model_routing(repo_root)

    route = next(r for r in routing["agent_routes"] if r["agent"] == "researcher")
    assert route["canonical_tier"] == "M"
    assert route["canonical_alias"] == "claude-future-9"
