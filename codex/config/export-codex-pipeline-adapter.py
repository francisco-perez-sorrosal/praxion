#!/usr/bin/env python3
"""Export Praxion pipeline semantics into Codex adapter metadata."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


class PipelineAdapterError(ValueError):
    """Raised when canonical Praxion pipeline data cannot be exported."""


TABLE_SEPARATOR_PATTERN = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


PROCESS_TIER_ADAPTER = {
    "Direct": {
        "codex_process": "work_in_main_thread",
        "agents": "none",
        "worktree": "current_checkout",
        "planning_documents": "none",
    },
    "Lightweight": {
        "codex_process": "main_thread_with_optional_researcher",
        "agents": "optional_researcher_only",
        "worktree": "current_checkout",
        "planning_documents": "inline_acceptance_criteria",
    },
    "Standard": {
        "codex_process": "pipeline_with_shared_documents",
        "agents": "researcher_to_architect_to_planner_to_implementation_group_to_verifier",
        "worktree": "dedicated_worktree",
        "planning_documents": "three_document_model_plus_sdd",
    },
    "Full": {
        "codex_process": "expanded_pipeline_with_parallel_execution",
        "agents": "standard_plus_context_engineer_doc_engineer_parallelism",
        "worktree": "dedicated_worktree",
        "planning_documents": "three_document_model_plus_sdd_and_archival",
    },
    "Spike": {
        "codex_process": "timeboxed_research_before_implementation",
        "agents": "researcher_only",
        "worktree": "current_checkout",
        "planning_documents": "learnings_decision_only",
    },
}


CODEX_MODEL_TIER_ADAPTER = {
    "opus": {
        "codex_tier": "high",
        "model_selection": "strongest_available_codex_model",
        "reasoning_effort": "high",
    },
    "sonnet": {
        "codex_tier": "medium",
        "model_selection": "default_strong_codex_coding_model",
        "reasoning_effort": "medium",
    },
    "haiku": {
        "codex_tier": "low",
        "model_selection": "fast_cost_efficient_codex_model",
        "reasoning_effort": "low",
    },
}


PIPELINE_FLOW = [
    "promethean",
    "researcher",
    "systems-architect",
    "implementation-planner",
    "implementer",
    "test-engineer",
    "doc-engineer",
    "verifier",
]


def clean_cell(value: str) -> str:
    value = value.strip()
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"\1", value)
    value = re.sub(
        r"\[[^]]+\]\([^)]+\)",
        lambda match: match.group(0).split("](")[0][1:],
        value,
    )
    value = re.sub(r"<br\s*/?>", " ", value)
    value = value.replace("--", "-")
    return " ".join(value.split())


def slug_header(value: str) -> str:
    value = clean_cell(value).lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def read_source(repo_root: Path, relpath: str) -> tuple[Path, str]:
    path = repo_root / relpath
    if not path.is_file():
        raise PipelineAdapterError(f"missing canonical source: {path}")
    return path, path.read_text(encoding="utf-8")


def table_after_heading(text: str, heading: str) -> list[dict[str, str]]:
    lines = text.splitlines()
    start_index = None
    for index, line in enumerate(lines):
        if line.strip() == heading:
            start_index = index
            break
    if start_index is None:
        raise PipelineAdapterError(f"heading not found: {heading}")

    header_index = None
    for index in range(start_index + 1, len(lines) - 1):
        if lines[index].lstrip().startswith("|") and TABLE_SEPARATOR_PATTERN.match(
            lines[index + 1]
        ):
            header_index = index
            break
    if header_index is None:
        raise PipelineAdapterError(f"table not found after heading: {heading}")

    headers = [slug_header(cell) for cell in lines[header_index].strip().strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for line in lines[header_index + 2 :]:
        if not line.lstrip().startswith("|"):
            break
        cells = [clean_cell(cell) for cell in line.strip().strip("|").split("|")]
        if len(cells) != len(headers):
            raise PipelineAdapterError(f"malformed table row under {heading}: {line!r}")
        rows.append(dict(zip(headers, cells, strict=True)))
    return rows


def export_pipeline_semantics(repo_root: Path) -> dict[str, object]:
    coordination_path, coordination_text = read_source(
        repo_root, "rules/swe/swe-agent-coordination-protocol.md"
    )
    intermediate_path, _intermediate_text = read_source(
        repo_root, "rules/swe/agent-intermediate-documents.md"
    )

    tiers = []
    for row in table_after_heading(coordination_text, "### Process Calibration"):
        tier = row["tier"]
        if tier not in PROCESS_TIER_ADAPTER:
            raise PipelineAdapterError(f"missing Codex process adapter for tier: {tier}")
        tiers.append(
            {
                "tier": tier,
                "signals": row["signals"],
                "canonical_process": row["process"],
                "codex_adapter": PROCESS_TIER_ADAPTER[tier],
            }
        )

    agents = table_after_heading(coordination_text, "### Available Agents")
    return {
        "generated_by": "Praxion Codex pipeline adapter exporter",
        "schema_version": 1,
        "source_paths": {
            "coordination_protocol": coordination_path.resolve().as_posix(),
            "agent_intermediate_documents": intermediate_path.resolve().as_posix(),
        },
        "process_tiers": tiers,
        "pipeline": {
            "canonical_flow": PIPELINE_FLOW,
            "task_slug_required": True,
            "shared_document_root": ".ai-work/<task-slug>/",
            "persistent_document_root": ".ai-state/",
            "codex_boundary": (
                "Use Codex subagents only from the main agent; keep "
                "agent-to-agent coordination document-based."
            ),
        },
        "agents": agents,
    }


def export_model_routing(repo_root: Path) -> dict[str, object]:
    model_path, model_text = read_source(repo_root, "rules/swe/agent-model-routing.md")
    routes = []
    for row in table_after_heading(model_text, "### Tier Table"):
        alias = row["alias"]
        if alias not in CODEX_MODEL_TIER_ADAPTER:
            raise PipelineAdapterError(f"missing Codex model adapter for alias: {alias}")
        routes.append(
            {
                "agent": row["agent"],
                "canonical_tier": row["tier"],
                "canonical_alias": alias,
                "rationale": row["rationale"],
                "codex_adapter": CODEX_MODEL_TIER_ADAPTER[alias],
            }
        )

    return {
        "generated_by": "Praxion Codex pipeline adapter exporter",
        "schema_version": 1,
        "source_path": model_path.resolve().as_posix(),
        "codex_resolution_order": [
            "explicit_spawn_agent_model_or_reasoning_effort",
            "generated_agent_route",
            "main_session_default",
        ],
        "tier_mapping": CODEX_MODEL_TIER_ADAPTER,
        "agent_routes": routes,
        "notes": [
            "Canonical Claude aliases remain source semantics; Codex model IDs are intentionally not pinned here.",
            "Choose the strongest available Codex model for high-tier routes, a strong default coding model for medium-tier routes, and a fast cost-efficient model for low-tier routes.",
        ],
    }


def export_pipeline_adapter(repo_root: Path, out_dir: Path) -> list[Path]:
    praxion_dir = out_dir / "praxion"
    praxion_dir.mkdir(parents=True, exist_ok=True)

    payloads = {
        "pipeline_semantics.json": export_pipeline_semantics(repo_root),
        "model_routing.json": export_model_routing(repo_root),
    }
    written: list[Path] = []
    for filename, payload in payloads.items():
        path = praxion_dir / filename
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    written = export_pipeline_adapter(args.repo_root.resolve(), args.out_dir.resolve())
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
