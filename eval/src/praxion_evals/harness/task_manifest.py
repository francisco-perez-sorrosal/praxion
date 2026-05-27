"""Expected-artifact manifest for in-flight pipelines, keyed by pipeline tier.

The manifest is the source of truth for which files a completed pipeline at a
given tier must produce. Family 1's in-flight artifact-manifest check consumes
these specs (via the corpus reader) to verdict each expected deliverable.

Migrated from the retired ``praxion_evals.behavioral`` package; the corpus
reader now performs the scan once and surfaces verdicts on the Corpus, so
Family 1 stays stateless.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from praxion_evals.harness.schemas import TaskArtifactVerdict


class PipelineTier(StrEnum):
    """Coordination-protocol tiers that produce different artifact sets."""

    LIGHTWEIGHT = "lightweight"
    STANDARD = "standard"
    FULL = "full"


@dataclass(frozen=True)
class ArtifactSpec:
    """One expected deliverable.

    ``path`` is relative to the repo root and may contain ``{slug}`` as a
    placeholder for the task slug. ``required`` gates whether absence flips
    the verdict to ``missing`` vs informational. ``check_recency`` asks the
    scan to compare mtime against ``pipeline_start`` when one is available —
    used for living docs that must be refreshed per-pipeline.
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
        path=".ai-state/DESIGN.md",
        required=False,
        check_recency=True,
        description="Architect-facing design target; should be touched for structural changes.",
    ),
    ArtifactSpec(
        path="docs/architecture.md",
        required=False,
        check_recency=True,
        description="Developer-facing navigation guide derived from DESIGN.md.",
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
    if tier is PipelineTier.STANDARD:
        return _STANDARD_REQUIRED
    # FULL extends STANDARD with the architecture-doc recency checks.
    return _STANDARD_REQUIRED + _FULL_EXTRA


def scan_task_manifest(
    repo_root: Path,
    task_slug: str,
    tier: PipelineTier,
    pipeline_start: datetime | None = None,
) -> tuple[TaskArtifactVerdict, ...]:
    """Walk the per-tier manifest under *repo_root* and return verdicts.

    Pure filesystem read; never invokes subprocesses or imports judging code.

    Args:
        repo_root: Filesystem root to scan (a working tree, a worktree, or any
            checkout-like directory).
        task_slug: The pipeline's task slug (``.ai-work/<slug>/`` directory).
        tier: Pipeline tier governing which artifacts are expected.
        pipeline_start: Optional timestamp gating recency checks for FULL tier.

    Returns:
        Tuple of ``TaskArtifactVerdict`` in manifest order.
    """
    specs = expected_artifacts(tier)
    verdicts: list[TaskArtifactVerdict] = []
    for spec in specs:
        verdicts.append(_verdict_for(spec, task_slug, repo_root, pipeline_start))
    return tuple(verdicts)


def _verdict_for(
    spec: ArtifactSpec,
    task_slug: str,
    repo_root: Path,
    pipeline_start: datetime | None,
) -> TaskArtifactVerdict:
    relative = spec.path.format(slug=task_slug)
    path = repo_root / relative
    if not path.exists():
        return TaskArtifactVerdict(
            path=relative,
            verdict="missing",
            required=spec.required,
            description=spec.description,
        )
    if spec.check_recency and pipeline_start is not None:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=pipeline_start.tzinfo)
        if mtime < pipeline_start:
            return TaskArtifactVerdict(
                path=relative,
                verdict="stale",
                required=spec.required,
                description=spec.description,
                detail=(
                    f"mtime {mtime.isoformat()} precedes pipeline start "
                    f"{pipeline_start.isoformat()}"
                ),
            )
    return TaskArtifactVerdict(
        path=relative,
        verdict="present",
        required=spec.required,
        description=spec.description,
    )
