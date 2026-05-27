"""Tier registry — declarative status table for `praxion-evals list`.

Tier 1 ("ready") entries have runnable implementations. Tier 2 ("stub") entries raise
NotImplementedError until a future phase implements them.

The `regression`, `judge-openai`, and `judge-anthropic` tiers were retired in v1
(regression package and judges/ stubs deleted; the `eval-praxion` tier provides the
LLM-as-judge surface via the harness, invoked via /eval-praxion).
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
        name="eval-praxion",
        status="ready",
        description=(
            "LLM-as-judge over completed artifacts: Family 1 (pipeline-outcome fidelity) + "
            "Family 2 (behavioral-contract adherence). Invoke via /eval-praxion."
        ),
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
