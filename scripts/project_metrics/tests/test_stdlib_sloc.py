"""Behavioral tests for the stdlib SLOC fallback.

When ``scc`` is absent, ``aggregate.compose_aggregate`` must still populate
``sloc_total`` and ``language_count`` per the graceful-degradation ADR. These
tests exercise the fallback path against a minimal fixture repo.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.test"], cwd=root, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)


def _commit_all(root: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=root, check=True)


class TestStdlibSlocCountsCommittedFiles:
    def test_counts_non_blank_lines_in_tracked_python_file(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics._stdlib_sloc import compute_stdlib_sloc

        _init_repo(tmp_path)
        (tmp_path / "foo.py").write_text(
            "def hello():\n\n    return 1\n\nx = 2\n",
            encoding="utf-8",
        )
        _commit_all(tmp_path, "add foo.py")

        result = compute_stdlib_sloc(tmp_path)

        # 3 non-blank lines: "def hello():", "    return 1", "x = 2"
        assert result["sloc_total"] == 3
        assert result["file_count"] == 1
        assert result["per_file_sloc"]["foo.py"] == 3

    def test_counts_multiple_languages_and_reports_language_breakdown(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics._stdlib_sloc import compute_stdlib_sloc

        _init_repo(tmp_path)
        (tmp_path / "foo.py").write_text("print(1)\nprint(2)\n", encoding="utf-8")
        (tmp_path / "foo.md").write_text("# Title\n\nbody\n", encoding="utf-8")
        (tmp_path / "bar.ts").write_text("export const x = 1;\n", encoding="utf-8")
        _commit_all(tmp_path, "add multi-lang")

        result = compute_stdlib_sloc(tmp_path)

        assert "Python" in result["language_breakdown"]
        assert "Markdown" in result["language_breakdown"]
        assert "TypeScript" in result["language_breakdown"]
        assert result["language_count"] == 3
        assert result["language_breakdown"]["Python"]["file_count"] == 1

    def test_ignores_untracked_files(self, tmp_path: Path) -> None:
        from scripts.project_metrics._stdlib_sloc import compute_stdlib_sloc

        _init_repo(tmp_path)
        (tmp_path / "tracked.py").write_text("x = 1\n", encoding="utf-8")
        _commit_all(tmp_path, "add tracked")
        # Untracked — not committed
        (tmp_path / "untracked.py").write_text("y = 2\n", encoding="utf-8")

        result = compute_stdlib_sloc(tmp_path)

        assert "tracked.py" in result["per_file_sloc"]
        assert "untracked.py" not in result["per_file_sloc"]

    def test_unknown_extension_falls_into_other_bucket(self, tmp_path: Path) -> None:
        from scripts.project_metrics._stdlib_sloc import compute_stdlib_sloc

        _init_repo(tmp_path)
        (tmp_path / "known.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "weird.xyz").write_text("data\n", encoding="utf-8")
        _commit_all(tmp_path, "add both")

        result = compute_stdlib_sloc(tmp_path)

        # Unknown extension counted but does not increment language_count
        assert result["sloc_total"] == 2
        assert result["language_count"] == 1  # only Python
        assert "Other" in result["language_breakdown"]

    def test_binary_file_is_skipped_silently(self, tmp_path: Path) -> None:
        from scripts.project_metrics._stdlib_sloc import compute_stdlib_sloc

        _init_repo(tmp_path)
        (tmp_path / "foo.py").write_text("x = 1\n", encoding="utf-8")
        # Binary-looking content that fails UTF-8 decode
        (tmp_path / "blob.dat").write_bytes(b"\x00\x01\xff\xfe" + b"\x80" * 10)
        _commit_all(tmp_path, "add binary")

        result = compute_stdlib_sloc(tmp_path)

        # blob.dat is skipped, foo.py counted
        assert "foo.py" in result["per_file_sloc"]
        assert "blob.dat" not in result["per_file_sloc"]

    def test_source_marker_identifies_fallback_path(self, tmp_path: Path) -> None:
        from scripts.project_metrics._stdlib_sloc import compute_stdlib_sloc

        _init_repo(tmp_path)
        (tmp_path / "x.py").write_text("a=1\n", encoding="utf-8")
        _commit_all(tmp_path, "init")

        result = compute_stdlib_sloc(tmp_path)
        assert result["source"] == "stdlib_fallback"

    def test_empty_repo_returns_zeros(self, tmp_path: Path) -> None:
        from scripts.project_metrics._stdlib_sloc import compute_stdlib_sloc

        _init_repo(tmp_path)
        # Initial commit with no files — create one empty sentinel then the
        # caller's concern is zero-tracked-files. Simulate by not committing.
        result = compute_stdlib_sloc(tmp_path)

        assert result["sloc_total"] == 0
        assert result["file_count"] == 0
        assert result["language_count"] == 0

    def test_non_git_directory_returns_zeros(self, tmp_path: Path) -> None:
        from scripts.project_metrics._stdlib_sloc import compute_stdlib_sloc

        # No git init — directory is not a repo
        (tmp_path / "foo.py").write_text("x = 1\n", encoding="utf-8")
        result = compute_stdlib_sloc(tmp_path)

        # git ls-files fails → empty result, no exception
        assert result["sloc_total"] == 0
        assert result["file_count"] == 0


class TestComposeAggregateUsesFallback:
    def test_sloc_total_populated_from_fallback_when_scc_missing(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.aggregate import compose_aggregate
        from scripts.project_metrics.schema import AggregateBlock, Report, TrendBlock

        _init_repo(tmp_path)
        (tmp_path / "a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("# h\n", encoding="utf-8")
        _commit_all(tmp_path, "seed")

        aggregate = AggregateBlock(
            schema_version="1.0.0",
            timestamp="2026-04-24T00:00:00+00:00",
            commit_sha="a" * 40,
            window_days=90,
            sloc_total=0,
            file_count=0,
            language_count=0,
            ccn_p95=None,
            cognitive_p95=None,
            cyclic_deps=None,
            churn_total_90d=0,
            change_entropy_90d=0.0,
            truck_factor=0,
            hotspot_top_score=None,
            hotspot_gini=None,
            coverage_line_pct=None,
        )
        # scc is absent (no collector entry); only git with empty data
        report = Report(
            schema_version="1.0.0",
            aggregate=aggregate,
            tool_availability={},
            collectors={},
            trends=TrendBlock(status="first_run"),
        )

        result = compose_aggregate(report, repo_root=tmp_path)

        assert result.aggregate.sloc_total == 3  # "x = 1", "y = 2", "# h"
        assert result.aggregate.language_count == 2  # Python + Markdown
        assert result.aggregate.file_count == 2

    def test_no_repo_root_passed_keeps_zeros(self, tmp_path: Path) -> None:
        """Unit-test callers that pass no repo_root should not trigger fallback."""
        from scripts.project_metrics.aggregate import compose_aggregate
        from scripts.project_metrics.schema import AggregateBlock, Report, TrendBlock

        aggregate = AggregateBlock(
            schema_version="1.0.0",
            timestamp="2026-04-24T00:00:00+00:00",
            commit_sha="a" * 40,
            window_days=90,
            sloc_total=0,
            file_count=0,
            language_count=0,
            ccn_p95=None,
            cognitive_p95=None,
            cyclic_deps=None,
            churn_total_90d=0,
            change_entropy_90d=0.0,
            truck_factor=0,
            hotspot_top_score=None,
            hotspot_gini=None,
            coverage_line_pct=None,
        )
        report = Report(
            schema_version="1.0.0",
            aggregate=aggregate,
            tool_availability={},
            collectors={},
            trends=TrendBlock(status="first_run"),
        )

        result = compose_aggregate(report)  # no repo_root

        assert result.aggregate.sloc_total == 0
        assert result.aggregate.language_count == 0
