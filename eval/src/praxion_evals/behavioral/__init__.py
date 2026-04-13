"""Tier 1 behavioral eval — artifact manifest check over `.ai-work/` + `.ai-state/`.

Pure filesystem reads; never invokes agents, subprocesses, or the LLM. The
behavioral eval answers: did the expected pipeline deliverables land?
"""

from praxion_evals.behavioral.artifact_manifest import (
    ArtifactSpec,
    PipelineTier,
    expected_artifacts,
)
from praxion_evals.behavioral.report import ArtifactVerdict, Report, render_markdown
from praxion_evals.behavioral.runner import run_behavioral

__all__ = [
    "ArtifactSpec",
    "ArtifactVerdict",
    "PipelineTier",
    "Report",
    "expected_artifacts",
    "render_markdown",
    "run_behavioral",
]
