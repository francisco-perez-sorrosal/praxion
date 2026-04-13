"""Behavioral eval runner — filesystem-only verdict computation.

Contract: read-only. Never invokes subprocesses, never imports ``phoenix.*``,
never starts agents. Each expected artifact is classified ``present``,
``missing``, or (for recency-checked artifacts) ``stale``.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

from praxion_evals.behavioral.artifact_manifest import (
    ArtifactSpec,
    PipelineTier,
    expected_artifacts,
)
from praxion_evals.behavioral.report import ArtifactVerdict, Report


def _resolve_path(spec: ArtifactSpec, task_slug: str, repo_root: Path) -> Path:
    return repo_root / spec.path.format(slug=task_slug)


def _verdict_for(
    spec: ArtifactSpec,
    task_slug: str,
    repo_root: Path,
    pipeline_start: datetime | None,
) -> ArtifactVerdict:
    path = _resolve_path(spec, task_slug, repo_root)
    if not path.exists():
        return ArtifactVerdict(
            path=str(path.relative_to(repo_root)),
            verdict="missing",
            required=spec.required,
            description=spec.description,
        )

    if spec.check_recency and pipeline_start is not None:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=pipeline_start.tzinfo)
        if mtime < pipeline_start:
            return ArtifactVerdict(
                path=str(path.relative_to(repo_root)),
                verdict="stale",
                required=spec.required,
                description=spec.description,
                detail=f"mtime {mtime.isoformat()} precedes pipeline start {pipeline_start.isoformat()}",
            )

    return ArtifactVerdict(
        path=str(path.relative_to(repo_root)),
        verdict="present",
        required=spec.required,
        description=spec.description,
    )


def run_behavioral(
    task_slug: str,
    repo_root: Path | None = None,
    tier: PipelineTier = PipelineTier.STANDARD,
    pipeline_start: datetime | None = None,
) -> Report:
    """Evaluate a task-scoped pipeline against the artifact manifest.

    Arguments:
        task_slug: The pipeline's task slug (the `.ai-work/<slug>/` directory).
        repo_root: Repository root. Defaults to the current working directory.
        tier: Pipeline tier governing which artifacts are expected.
        pipeline_start: Optional timestamp gating recency checks for `FULL` tier.

    Returns:
        A structured ``Report`` containing per-artifact verdicts.
    """
    root = repo_root or Path.cwd()
    task_dir = root / ".ai-work" / task_slug

    if not task_dir.exists():
        return Report(
            task_slug=task_slug,
            tier=tier.value,
            verdicts=(),
            error=f"Task directory not found: {task_dir}",
        )

    specs = expected_artifacts(tier)
    verdicts = tuple(_verdict_for(spec, task_slug, root, pipeline_start) for spec in specs)

    # Attach SYSTEMS_PLAN.md absence detail if present in verdicts — callers
    # frequently need the hint to distinguish "no plan yet" from "plan consumed".
    plan_verdict = next(
        (v for v in verdicts if v.path.endswith("SYSTEMS_PLAN.md")),
        None,
    )
    if plan_verdict is not None and plan_verdict.verdict == "missing":
        verdicts = tuple(
            replace(v, detail="cannot determine expected deliverables without a SYSTEMS_PLAN.md")
            if v.path.endswith("SYSTEMS_PLAN.md")
            else v
            for v in verdicts
        )

    return Report(task_slug=task_slug, tier=tier.value, verdicts=verdicts)
