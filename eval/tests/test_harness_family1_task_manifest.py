"""Tests for Family 1's in-flight artifact-manifest sub-check.

The check activates only when the Corpus carries a populated ``task_slug``
and corresponding ``task_artifacts`` verdicts. Mechanical only — no judge.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from praxion_evals.harness.corpus_reader import CorpusReader
from praxion_evals.harness.families.family1_pipeline_fidelity import (
    Family1PipelineOutcomeFidelity,
)
from praxion_evals.harness.judge_client import NullJudgeClient
from praxion_evals.harness.schemas import Corpus, TaskArtifactVerdict
from praxion_evals.harness.task_manifest import (
    PipelineTier,
    expected_artifacts,
    scan_task_manifest,
)

# ---------------------------------------------------------------------------
# task_manifest module — pure functional tests
# ---------------------------------------------------------------------------


def test_standard_tier_lists_four_required_artifacts():
    specs = expected_artifacts(PipelineTier.STANDARD)
    paths = [s.path for s in specs]
    assert ".ai-work/{slug}/SYSTEMS_PLAN.md" in paths
    assert ".ai-work/{slug}/IMPLEMENTATION_PLAN.md" in paths
    assert ".ai-work/{slug}/WIP.md" in paths
    assert ".ai-work/{slug}/VERIFICATION_REPORT.md" in paths
    assert all(s.required for s in specs)


def test_full_tier_includes_architecture_docs():
    specs = expected_artifacts(PipelineTier.FULL)
    paths = [s.path for s in specs]
    assert ".ai-state/DESIGN.md" in paths
    assert "docs/architecture.md" in paths
    recency = {s.path for s in specs if s.check_recency}
    assert ".ai-state/DESIGN.md" in recency


def test_lightweight_tier_is_minimal():
    specs = expected_artifacts(PipelineTier.LIGHTWEIGHT)
    assert len(specs) == 1
    assert specs[0].path == ".ai-work/{slug}/WIP.md"


def test_scan_returns_present_for_existing_artifacts(tmp_path: Path):
    slug = "demo"
    task_dir = tmp_path / ".ai-work" / slug
    task_dir.mkdir(parents=True)
    for fname in ("SYSTEMS_PLAN.md", "IMPLEMENTATION_PLAN.md", "WIP.md", "VERIFICATION_REPORT.md"):
        (task_dir / fname).write_text("x", encoding="utf-8")

    verdicts = scan_task_manifest(tmp_path, slug, PipelineTier.STANDARD)
    assert len(verdicts) == 4
    assert all(v.verdict == "present" for v in verdicts)


def test_scan_returns_missing_when_artifact_absent(tmp_path: Path):
    slug = "demo"
    (tmp_path / ".ai-work" / slug).mkdir(parents=True)
    verdicts = scan_task_manifest(tmp_path, slug, PipelineTier.STANDARD)
    assert all(v.verdict == "missing" for v in verdicts)
    assert all(v.required for v in verdicts)


# ---------------------------------------------------------------------------
# CorpusReader — manifest attachment
# ---------------------------------------------------------------------------


def test_corpus_reader_attaches_manifest_when_task_slug_set(tmp_path: Path):
    slug = "demo"
    task_dir = tmp_path / ".ai-work" / slug
    task_dir.mkdir(parents=True)
    (task_dir / "WIP.md").write_text("x", encoding="utf-8")

    corpus = CorpusReader(tmp_path).resolve(
        str(tmp_path),
        task_slug=slug,
        pipeline_tier=PipelineTier.LIGHTWEIGHT,
    )
    assert corpus.task_slug == slug
    assert corpus.pipeline_tier == "lightweight"
    assert len(corpus.task_artifacts) == 1
    assert corpus.task_artifacts[0].verdict == "present"


def test_corpus_reader_no_manifest_without_task_slug(tmp_path: Path):
    corpus = CorpusReader(tmp_path).resolve(str(tmp_path))
    assert corpus.task_slug is None
    assert corpus.pipeline_tier is None
    assert corpus.task_artifacts == ()


# ---------------------------------------------------------------------------
# Family 1 — translates verdicts into CheckResults
# ---------------------------------------------------------------------------


def _make_corpus_with_verdicts(verdicts: tuple[TaskArtifactVerdict, ...]) -> Corpus:
    return Corpus(
        target_kind="path",
        target_label="(test)",
        decisions=(),
        specs=(),
        verification_reports=(),
        task_slug="demo",
        pipeline_tier="standard",
        task_artifacts=verdicts,
    )


def test_family1_emits_pass_for_present_artifacts():
    corpus = _make_corpus_with_verdicts(
        (
            TaskArtifactVerdict(
                path=".ai-work/demo/WIP.md",
                verdict="present",
                required=True,
                description="Live execution state.",
            ),
        )
    )
    results = Family1PipelineOutcomeFidelity().run(corpus, NullJudgeClient(), mechanical_only=True)
    manifest_rows = [r for r in results if r.check_name == "task_artifact_manifest"]
    assert len(manifest_rows) == 1
    assert manifest_rows[0].verdict == "PASS"
    assert manifest_rows[0].artifact_path == ".ai-work/demo/WIP.md"


def test_family1_emits_fail_for_required_missing():
    corpus = _make_corpus_with_verdicts(
        (
            TaskArtifactVerdict(
                path=".ai-work/demo/SYSTEMS_PLAN.md",
                verdict="missing",
                required=True,
                description="Architect's system plan.",
            ),
        )
    )
    results = Family1PipelineOutcomeFidelity().run(corpus, NullJudgeClient(), mechanical_only=True)
    manifest_rows = [r for r in results if r.check_name == "task_artifact_manifest"]
    assert manifest_rows[0].verdict == "FAIL"


def test_family1_emits_warn_for_optional_missing_or_stale():
    corpus = _make_corpus_with_verdicts(
        (
            TaskArtifactVerdict(
                path=".ai-state/DESIGN.md",
                verdict="missing",
                required=False,
                description="Design-target architecture.",
            ),
            TaskArtifactVerdict(
                path="docs/architecture.md",
                verdict="stale",
                required=False,
                description="Developer architecture guide.",
                detail="mtime preceded pipeline start",
            ),
        )
    )
    results = Family1PipelineOutcomeFidelity().run(corpus, NullJudgeClient(), mechanical_only=True)
    manifest_rows = [r for r in results if r.check_name == "task_artifact_manifest"]
    assert all(r.verdict == "WARN" for r in manifest_rows)


def test_family1_skips_manifest_when_task_slug_absent():
    corpus = Corpus(
        target_kind="path",
        target_label="(test)",
        decisions=(),
        specs=(),
        verification_reports=(),
    )
    results = Family1PipelineOutcomeFidelity().run(corpus, NullJudgeClient(), mechanical_only=True)
    manifest_rows = [r for r in results if r.check_name == "task_artifact_manifest"]
    assert manifest_rows == []


# ---------------------------------------------------------------------------
# Mechanical-only mode — NullJudgeClient must never be called
# ---------------------------------------------------------------------------


def test_null_judge_client_raises_if_called():
    judge = NullJudgeClient()
    with pytest.raises(RuntimeError, match="NullJudgeClient.judge"):
        judge.judge("rubric", "artifact", {})


def test_family1_mechanical_only_skips_judge_calls():
    """Family 1 with mechanical_only=True must not call judge.judge()."""
    corpus = Corpus(
        target_kind="path",
        target_label="(test)",
        decisions=(),
        specs=(),
        verification_reports=(),
    )
    # NullJudgeClient raises if called — passing it here is the assertion.
    results = Family1PipelineOutcomeFidelity().run(corpus, NullJudgeClient(), mechanical_only=True)
    # Should still emit some mechanical SKIP rows for the empty corpus
    assert len(results) > 0
    assert all(r.check_kind == "mechanical" for r in results)
