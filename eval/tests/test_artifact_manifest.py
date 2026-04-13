"""Tests for the expected-artifact manifest."""

from __future__ import annotations

from praxion_evals.behavioral.artifact_manifest import (
    PipelineTier,
    expected_artifacts,
)


def test_standard_tier_required_files():
    specs = expected_artifacts(PipelineTier.STANDARD)
    paths = [spec.path for spec in specs]
    assert ".ai-work/{slug}/SYSTEMS_PLAN.md" in paths
    assert ".ai-work/{slug}/IMPLEMENTATION_PLAN.md" in paths
    assert ".ai-work/{slug}/WIP.md" in paths
    assert ".ai-work/{slug}/VERIFICATION_REPORT.md" in paths
    # Each of the four is required.
    assert all(spec.required for spec in specs)


def test_full_tier_includes_architecture_docs():
    specs = expected_artifacts(PipelineTier.FULL)
    paths = [spec.path for spec in specs]
    assert ".ai-state/ARCHITECTURE.md" in paths
    assert "docs/architecture.md" in paths
    # Recency checks fire for full-tier architecture docs.
    recency_paths = {spec.path for spec in specs if spec.check_recency}
    assert ".ai-state/ARCHITECTURE.md" in recency_paths


def test_lightweight_tier_is_minimal():
    specs = expected_artifacts(PipelineTier.LIGHTWEIGHT)
    assert len(specs) == 1
    assert specs[0].path == ".ai-work/{slug}/WIP.md"
