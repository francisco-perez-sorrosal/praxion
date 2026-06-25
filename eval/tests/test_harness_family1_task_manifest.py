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


def test_standard_tier_lists_required_and_conditional_artifacts():
    specs = expected_artifacts(PipelineTier.STANDARD)
    paths = [s.path for s in specs]
    for req in ("SYSTEMS_PLAN", "IMPLEMENTATION_PLAN", "WIP", "LEARNINGS", "VERIFICATION_REPORT"):
        assert f".ai-work/{{slug}}/{req}.md" in paths
    # Conditional deliverables carry an activation predicate; the always-required ones do not.
    conditional = {s.path for s in specs if s.activation is not None}
    assert ".ai-work/{slug}/TEST_RESULTS.md" in conditional
    assert ".ai-work/{slug}/traceability.yml" in conditional
    assert all(s.required for s in specs if s.activation is None)


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


def test_lean_run_passes_with_required_present_and_conditionals_inactive(tmp_path: Path):
    """A standard pipeline with no tests and no SDD: required present, conditionals not penalised."""
    slug = "demo"
    task_dir = tmp_path / ".ai-work" / slug
    task_dir.mkdir(parents=True)
    standard_required = (
        "SYSTEMS_PLAN.md",
        "IMPLEMENTATION_PLAN.md",
        "WIP.md",
        "LEARNINGS.md",
        "VERIFICATION_REPORT.md",
    )
    for fname in standard_required:
        (task_dir / fname).write_text("x", encoding="utf-8")

    by_name = {
        Path(v.path).name: v for v in scan_task_manifest(tmp_path, slug, PipelineTier.STANDARD)
    }
    assert all(by_name[n].verdict == "present" for n in standard_required)
    # Conditional artifacts are inactive (no TEST_BASELINE, no REQ heading) -> informational, not FAIL.
    assert by_name["TEST_RESULTS.md"].required is False
    assert by_name["traceability.yml"].required is False
    assert not [v for v in by_name.values() if v.verdict == "missing" and v.required]


def test_empty_dir_flags_required_missing_but_not_inactive_conditionals(tmp_path: Path):
    slug = "demo"
    (tmp_path / ".ai-work" / slug).mkdir(parents=True)
    by_name = {
        Path(v.path).name: v for v in scan_task_manifest(tmp_path, slug, PipelineTier.STANDARD)
    }
    assert all(v.verdict == "missing" for v in by_name.values())
    assert by_name["SYSTEMS_PLAN.md"].required is True
    assert by_name["TEST_RESULTS.md"].required is False  # no TEST_BASELINE -> inactive


def test_test_results_required_when_tests_ran(tmp_path: Path):
    slug = "demo"
    task_dir = tmp_path / ".ai-work" / slug
    task_dir.mkdir(parents=True)
    (task_dir / "TEST_BASELINE.md").write_text("failing nodes\n", encoding="utf-8")
    by_name = {
        Path(v.path).name: v for v in scan_task_manifest(tmp_path, slug, PipelineTier.STANDARD)
    }
    assert by_name["TEST_RESULTS.md"].verdict == "missing"
    assert by_name["TEST_RESULTS.md"].required is True


def test_traceability_required_when_sdd_active(tmp_path: Path):
    slug = "demo"
    task_dir = tmp_path / ".ai-work" / slug
    task_dir.mkdir(parents=True)
    (task_dir / "SYSTEMS_PLAN.md").write_text(
        "## Requirements\n### REQ-01: Login works\n", encoding="utf-8"
    )
    by_name = {
        Path(v.path).name: v for v in scan_task_manifest(tmp_path, slug, PipelineTier.STANDARD)
    }
    assert by_name["traceability.yml"].required is True


def test_config_task_prose_req_does_not_activate_sdd(tmp_path: Path):
    """A plan that only mentions REQ-NN in prose is not SDD-active (the l3-readiness-config case)."""
    slug = "demo"
    task_dir = tmp_path / ".ai-work" / slug
    task_dir.mkdir(parents=True)
    (task_dir / "SYSTEMS_PLAN.md").write_text(
        "This is a config task. No `REQ-NN` block is warranted.\n", encoding="utf-8"
    )
    by_name = {
        Path(v.path).name: v for v in scan_task_manifest(tmp_path, slug, PipelineTier.STANDARD)
    }
    assert by_name["traceability.yml"].required is False


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
