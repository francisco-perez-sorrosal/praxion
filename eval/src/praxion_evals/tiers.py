"""Tier registry — declarative status table for `praxion-evals list`.

Tier 1 ("ready") entries have runnable implementations in the behavioral and
regression sub-packages. Tier 2 ("stub") entries raise NotImplementedError until
a future phase implements them — see dec-040 for the out-of-band constraint.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tier:
    """One row in the tier status table."""

    name: str
    status: str  # "ready" | "stub"
    description: str


TIERS: tuple[Tier, ...] = (
    Tier(
        name="behavioral",
        status="ready",
        description="Artifact manifest check: expected pipeline deliverables exist per tier.",
    ),
    Tier(
        name="regression",
        status="ready",
        description="Phoenix trace diff against a baseline summary (span count, tool calls, duration).",
    ),
    Tier(
        name="judge-openai",
        status="ready",
        description="OpenAI GPT judge over TOOL spans (preserved shim; see trajectory_eval.py).",
    ),
    Tier(
        name="judge-anthropic",
        status="stub",
        description="Claude-as-judge — Tier 2, deferred (dec-040).",
    ),
    Tier(
        name="cost",
        status="stub",
        description="Token and dollar cost analysis — Tier 2, deferred.",
    ),
    Tier(
        name="decision-quality",
        status="stub",
        description="ADR/decision quality analysis — Tier 2, deferred.",
    ),
)


def format_status_table() -> str:
    """Render the tier registry as a Markdown table suitable for stdout."""
    lines = [
        "| Tier | Status | Description |",
        "|------|--------|-------------|",
    ]
    for tier in TIERS:
        lines.append(f"| {tier.name} | {tier.status} | {tier.description} |")
    return "\n".join(lines)
