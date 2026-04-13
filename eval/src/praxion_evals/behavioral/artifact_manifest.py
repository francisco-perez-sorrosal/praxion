"""Expected-artifact manifest per pipeline tier.

The manifest is the source of truth for which files a completed pipeline at a
given tier must produce. The runner consumes these specs to verdict per artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PipelineTier(StrEnum):
    """Coordination-protocol tiers that produce different artifact sets."""

    LIGHTWEIGHT = "lightweight"
    STANDARD = "standard"
    FULL = "full"


@dataclass(frozen=True)
class ArtifactSpec:
    """One expected deliverable.

    ``path`` is relative to the repo root. ``required`` gates whether absence
    flips the verdict to ``missing`` vs. informational. ``check_recency`` asks
    the runner to compare mtime against a pipeline-start timestamp when one is
    available — used for docs that must be refreshed per-pipeline.
    """

    path: str
    required: bool = True
    check_recency: bool = False
    description: str = ""


_STANDARD_REQUIRED: tuple[ArtifactSpec, ...] = (
    ArtifactSpec(
        path=".ai-work/{slug}/SYSTEMS_PLAN.md",
        description="Architect's system plan with acceptance criteria.",
    ),
    ArtifactSpec(
        path=".ai-work/{slug}/IMPLEMENTATION_PLAN.md",
        description="Planner's step decomposition.",
    ),
    ArtifactSpec(
        path=".ai-work/{slug}/WIP.md",
        description="Live execution state.",
    ),
    ArtifactSpec(
        path=".ai-work/{slug}/VERIFICATION_REPORT.md",
        description="Verifier's post-implementation review.",
    ),
)


_FULL_EXTRA: tuple[ArtifactSpec, ...] = (
    ArtifactSpec(
        path=".ai-state/ARCHITECTURE.md",
        required=False,
        check_recency=True,
        description="Architect-facing design target; should be touched for structural changes.",
    ),
    ArtifactSpec(
        path="docs/architecture.md",
        required=False,
        check_recency=True,
        description="Developer-facing navigation guide derived from ARCHITECTURE.md.",
    ),
)


def expected_artifacts(tier: PipelineTier = PipelineTier.STANDARD) -> tuple[ArtifactSpec, ...]:
    """Return the ordered artifact specs for the given pipeline tier."""
    if tier is PipelineTier.LIGHTWEIGHT:
        # Lightweight tier requires only WIP.md; other docs are optional.
        return (
            ArtifactSpec(
                path=".ai-work/{slug}/WIP.md",
                description="Live execution state (lightweight pipelines).",
            ),
        )
    if tier is PipelineTier.FULL:
        return _STANDARD_REQUIRED + _FULL_EXTRA
    return _STANDARD_REQUIRED
