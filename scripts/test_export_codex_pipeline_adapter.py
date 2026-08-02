from __future__ import annotations

import importlib.util
import json
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
    architect = next(
        route for route in routing["agent_routes"] if route["agent"] == "systems-architect"
    )
    assert architect["canonical_alias"] == "opus"
    assert architect["codex_adapter"]["codex_tier"] == "high"
    doc_engineer = next(
        route for route in routing["agent_routes"] if route["agent"] == "doc-engineer"
    )
    assert doc_engineer["canonical_alias"] == "haiku"
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
