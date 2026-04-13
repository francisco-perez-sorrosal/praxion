"""Tests for the behavioral eval runner (pure filesystem)."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from praxion_evals.behavioral.artifact_manifest import PipelineTier
from praxion_evals.behavioral.runner import run_behavioral


def _seed_complete_pipeline(repo_root: Path, slug: str) -> Path:
    task_dir = repo_root / ".ai-work" / slug
    task_dir.mkdir(parents=True, exist_ok=True)
    for fname in ("SYSTEMS_PLAN.md", "IMPLEMENTATION_PLAN.md", "WIP.md", "VERIFICATION_REPORT.md"):
        (task_dir / fname).write_text(f"# {fname}\n", encoding="utf-8")
    return task_dir


def test_runner_all_present_is_pass(tmp_path: Path):
    _seed_complete_pipeline(tmp_path, "sample")
    report = run_behavioral(task_slug="sample", repo_root=tmp_path)
    assert report.error is None
    assert report.passed is True
    assert report.score == 100
    assert all(v.verdict == "present" for v in report.verdicts if v.required)


def test_runner_missing_verification_report_fails(tmp_path: Path):
    task_dir = _seed_complete_pipeline(tmp_path, "sample")
    (task_dir / "VERIFICATION_REPORT.md").unlink()
    report = run_behavioral(task_slug="sample", repo_root=tmp_path)
    assert report.passed is False
    assert report.score < 100
    missing = [v for v in report.verdicts if v.verdict == "missing"]
    assert any(v.path.endswith("VERIFICATION_REPORT.md") for v in missing)


def test_runner_missing_systems_plan_reports_hint(tmp_path: Path):
    task_dir = _seed_complete_pipeline(tmp_path, "sample")
    (task_dir / "SYSTEMS_PLAN.md").unlink()
    report = run_behavioral(task_slug="sample", repo_root=tmp_path)
    assert report.passed is False
    plan_verdict = next(v for v in report.verdicts if v.path.endswith("SYSTEMS_PLAN.md"))
    assert plan_verdict.verdict == "missing"
    assert "SYSTEMS_PLAN.md" in plan_verdict.detail


def test_runner_missing_task_dir_sets_error(tmp_path: Path):
    report = run_behavioral(task_slug="no-such-slug", repo_root=tmp_path)
    assert report.error is not None
    assert report.passed is False
    assert report.verdicts == ()


def test_runner_stale_mtime_for_full_tier(tmp_path: Path):
    _seed_complete_pipeline(tmp_path, "sample")
    arch_path = tmp_path / ".ai-state" / "ARCHITECTURE.md"
    arch_path.parent.mkdir(parents=True, exist_ok=True)
    arch_path.write_text("# arch\n", encoding="utf-8")
    docs_path = tmp_path / "docs" / "architecture.md"
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    docs_path.write_text("# arch\n", encoding="utf-8")

    # Pin mtime in the past.
    past = datetime(2020, 1, 1, tzinfo=UTC).timestamp()
    os.utime(arch_path, (past, past))
    os.utime(docs_path, (past, past))

    pipeline_start = datetime.now(UTC) - timedelta(minutes=1)
    report = run_behavioral(
        task_slug="sample",
        repo_root=tmp_path,
        tier=PipelineTier.FULL,
        pipeline_start=pipeline_start,
    )
    stale = [v for v in report.verdicts if v.verdict == "stale"]
    assert any(v.path.endswith("ARCHITECTURE.md") for v in stale)
