"""Behavioral tests for the LLM-judge artifact gatherers.

Pins the evidence contract for the readiness judge:

* registry dispatch — ``c.testing.test_quality`` gets the evidence bundle,
  ``c.docs.*`` reads the README, everything else gets the repo listing,
* test-file discovery — ecosystem patterns, excluded/hidden dirs pruned,
  deterministic ordering, explicit (never silent) discovery cap,
* each bundle section degrades to absence rather than raising,
* size budgets — sections and the total artifact are clipped with a marker,
* the cli wiring threads the coverage collector's data into the context.

All tests run against tmp_path fixture repos; no network, no subprocess.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.project_metrics.cli import _artifact_context
from scripts.project_metrics.collectors.base import CollectorResult
from scripts.project_metrics.collectors.readiness import artifacts
from scripts.project_metrics.schema import Report

# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


_PYTHON_TEST_BODY = (
    "def test_rejects_empty_input():\n"
    "    assert validate('') is False\n"
    "\n"
    "def test_accepts_valid_input():\n"
    "    assert validate('x') is True\n"
)

_JS_TEST_BODY = (
    "describe('widget', () => {\n"
    "  it('renders the empty state', () => {});\n"
    "  test('handles a click', () => {});\n"
    "});\n"
)


def _ctx(root: Path, coverage: dict | None = None) -> artifacts.ArtifactContext:
    return artifacts.ArtifactContext(repo_root=root, coverage=coverage)


# ---------------------------------------------------------------------------
# Registry dispatch + fallbacks.
# ---------------------------------------------------------------------------


class TestArtifactDispatch:
    def test_docs_criterion_reads_readme(self, tmp_path: Path) -> None:
        _write(tmp_path, "README.md", "# The Project\n")

        artifact = artifacts.artifact_for("c.docs.readme_quality", _ctx(tmp_path))

        assert artifact == "# The Project\n"

    def test_docs_criterion_without_readme_is_empty(self, tmp_path: Path) -> None:
        artifact = artifacts.artifact_for("c.docs.readme_quality", _ctx(tmp_path))

        assert artifact == ""

    def test_unregistered_criterion_gets_repo_listing(self, tmp_path: Path) -> None:
        _write(tmp_path, "b.txt", "b")
        _write(tmp_path, "a.txt", "a")

        artifact = artifacts.artifact_for("c.code.naming_conventions", _ctx(tmp_path))

        assert artifact == "a.txt\nb.txt"

    def test_test_quality_gets_evidence_bundle(self, tmp_path: Path) -> None:
        _write(tmp_path, "tests/test_widget.py", _PYTHON_TEST_BODY)

        artifact = artifacts.artifact_for("c.testing.test_quality", _ctx(tmp_path))

        assert artifact.startswith("Test-quality evidence bundle")
        assert "## Test inventory" in artifact
        assert "## Sample test files" in artifact

    def test_test_quality_on_empty_repo_falls_back_to_listing(self, tmp_path: Path) -> None:
        _write(tmp_path, "main.py", "print('hi')\n")

        artifact = artifacts.artifact_for("c.testing.test_quality", _ctx(tmp_path))

        assert artifact == "main.py"


# ---------------------------------------------------------------------------
# Test-file discovery.
# ---------------------------------------------------------------------------


class TestDiscovery:
    def test_finds_python_js_and_go_test_files(self, tmp_path: Path) -> None:
        _write(tmp_path, "tests/test_a.py", "")
        _write(tmp_path, "pkg/a_test.py", "")
        _write(tmp_path, "web/app.test.tsx", "")
        _write(tmp_path, "web/app.spec.js", "")
        _write(tmp_path, "svc/handler_test.go", "")
        _write(tmp_path, "src/main.py", "")

        found, capped = artifacts._discover_test_files(tmp_path)

        assert [p.as_posix() for p in found] == [
            "pkg/a_test.py",
            "svc/handler_test.go",
            "tests/test_a.py",
            "web/app.spec.js",
            "web/app.test.tsx",
        ]
        assert capped is False

    def test_prunes_excluded_and_hidden_directories(self, tmp_path: Path) -> None:
        _write(tmp_path, "node_modules/pkg/test_dep.py", "")
        _write(tmp_path, ".venv/lib/test_env.py", "")
        _write(tmp_path, ".claude/worktrees/w/tests/test_shadow.py", "")
        _write(tmp_path, "tests/test_real.py", "")

        found, _capped = artifacts._discover_test_files(tmp_path)

        assert [p.as_posix() for p in found] == ["tests/test_real.py"]

    def test_discovery_cap_is_reported_not_silent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for index in range(6):
            _write(tmp_path, f"tests/test_{index}.py", "")
        monkeypatch.setattr(artifacts, "_DISCOVERY_FILE_CAP", 4)

        found, capped = artifacts._discover_test_files(tmp_path)

        assert len(found) == 4
        assert capped is True

    def test_cap_note_surfaces_in_inventory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for index in range(6):
            _write(tmp_path, f"tests/test_{index}.py", _PYTHON_TEST_BODY)
        monkeypatch.setattr(artifacts, "_DISCOVERY_FILE_CAP", 4)

        bundle = artifacts.gather_test_quality(_ctx(tmp_path))

        assert "discovery capped at 4 files" in bundle


# ---------------------------------------------------------------------------
# Framework configuration evidence.
# ---------------------------------------------------------------------------


class TestConfigEvidence:
    def test_extracts_pytest_section_literally(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "pyproject.toml",
            "[project]\nname = 'x'\n\n"
            "[tool.pytest.ini_options]\n"
            "# keep subprocess coverage consistent\n"
            'addopts = "-q"\n\n'
            "[tool.ruff]\nline-length = 88\n",
        )

        evidence = artifacts._test_config_evidence(tmp_path)

        assert "[tool.pytest.ini_options]" in evidence
        assert "# keep subprocess coverage consistent" in evidence
        assert 'addopts = "-q"' in evidence
        assert "[tool.ruff]" not in evidence

    def test_monorepo_app_configs_are_labeled(self, tmp_path: Path) -> None:
        _write(tmp_path, "webapp/package.json", '{"scripts": {"test": "vitest run"}}')
        _write(tmp_path, "webapp/vitest.config.ts", "export default {};\n")

        evidence = artifacts._test_config_evidence(tmp_path)

        assert "# webapp/vitest.config.ts" in evidence
        assert "# webapp/package.json test scripts" in evidence
        assert "test: vitest run" in evidence

    def test_non_test_package_scripts_are_ignored(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "package.json",
            '{"scripts": {"build": "tsc", "test:unit": "jest"}}',
        )

        evidence = artifacts._test_config_evidence(tmp_path)

        assert "test:unit: jest" in evidence
        assert "build" not in evidence


# ---------------------------------------------------------------------------
# Coverage evidence.
# ---------------------------------------------------------------------------


class TestCoverageEvidence:
    def test_combines_config_and_measured_result(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "pyproject.toml",
            "[tool.coverage.run]\nbranch = true\n\n[tool.coverage.report]\nfail_under = 70\n",
        )
        coverage = {
            "line_pct": 0.7982,
            "artifact_format": "cobertura",
            "artifact_path": "coverage.xml",
            "status": "ok",
            "per_file": {"a.py": {}, "b.py": {}},
        }

        evidence = artifacts._coverage_evidence(_ctx(tmp_path, coverage))

        assert "branch = true" in evidence
        assert "fail_under = 70" in evidence
        assert "line coverage: 79.8%" in evidence
        assert "cobertura artifact at coverage.xml, freshness: ok" in evidence
        assert "files measured: 2" in evidence

    def test_no_coverage_data_omits_measured_block(self, tmp_path: Path) -> None:
        evidence = artifacts._coverage_evidence(_ctx(tmp_path, None))

        assert "Coverage measured" not in evidence

    def test_malformed_coverage_data_is_ignored(self, tmp_path: Path) -> None:
        evidence = artifacts._coverage_evidence(_ctx(tmp_path, {"line_pct": "not-a-number"}))

        assert evidence == ""


# ---------------------------------------------------------------------------
# Inventory + samples.
# ---------------------------------------------------------------------------


class TestInventoryAndSamples:
    def test_inventory_counts_files_and_cases_per_ecosystem(self, tmp_path: Path) -> None:
        _write(tmp_path, "tests/test_a.py", _PYTHON_TEST_BODY)
        _write(tmp_path, "web/app.test.ts", _JS_TEST_BODY)

        files, capped = artifacts._discover_test_files(tmp_path)
        evidence = artifacts._test_inventory_evidence(files, capped, tmp_path)

        assert "Discovered 2 test files." in evidence
        assert "python: 1 files, 2 test cases" in evidence
        assert "js/ts: 1 files, 2 test cases" in evidence
        assert "  tests: 1 files" in evidence
        assert "  web: 1 files" in evidence

    def test_samples_spread_across_the_sorted_suite(self, tmp_path: Path) -> None:
        for index in range(9):
            _write(tmp_path, f"tests/test_{index}.py", f"def test_{index}(): pass\n")

        files, _capped = artifacts._discover_test_files(tmp_path)
        evidence = artifacts._test_samples_evidence(tmp_path, files)

        assert "### tests/test_0.py" in evidence
        assert "### tests/test_4.py" in evidence
        assert "### tests/test_8.py" in evidence
        assert "### tests/test_1.py" not in evidence

    def test_long_sample_files_are_truncated(self, tmp_path: Path) -> None:
        body = "\n".join(f"def test_{i}(): pass" for i in range(300))
        _write(tmp_path, "tests/test_long.py", body)

        files, _capped = artifacts._discover_test_files(tmp_path)
        evidence = artifacts._test_samples_evidence(tmp_path, files)

        assert "... [truncated]" in evidence
        assert len(evidence) < len(body)


# ---------------------------------------------------------------------------
# Testing-policy documentation.
# ---------------------------------------------------------------------------


class TestPolicyDocsEvidence:
    def test_finds_dedicated_policy_docs(self, tmp_path: Path) -> None:
        _write(tmp_path, "TESTING.md", "# Testing\nRun pytest.\n")
        _write(tmp_path, "docs/testing-strategy.md", "## Strategy\nPyramid.\n")

        evidence = artifacts._testing_docs_evidence(tmp_path)

        assert "# TESTING.md" in evidence
        assert "Run pytest." in evidence
        assert "# docs/testing-strategy.md" in evidence

    def test_candidate_and_glob_hits_are_deduplicated(self, tmp_path: Path) -> None:
        _write(tmp_path, "docs/testing.md", "One canonical doc.\n")

        evidence = artifacts._testing_docs_evidence(tmp_path)

        assert evidence.count("# docs/testing.md") == 1

    def test_extracts_contributing_testing_section(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "CONTRIBUTING.md",
            "# Contributing\n\n## Setup\npip install\n\n"
            "## Testing\nRun `pytest -q` before every PR.\n\n"
            "## Releases\ntag it\n",
        )

        evidence = artifacts._testing_docs_evidence(tmp_path)

        assert "Run `pytest -q` before every PR." in evidence
        assert "pip install" not in evidence
        assert "tag it" not in evidence


# ---------------------------------------------------------------------------
# Text helpers + budgets.
# ---------------------------------------------------------------------------


class TestTextHelpers:
    def test_toml_section_stops_at_next_table(self) -> None:
        text = "[a]\nx = 1\n\n[b]\ny = 2\n"

        assert artifacts._toml_section(text, "[a]") == "[a]\nx = 1"
        assert artifacts._toml_section(text, "[missing]") == ""

    def test_heading_section_stops_at_peer_heading(self) -> None:
        text = "## Testing\nbody line\n### Sub\nsub line\n## Next\nother\n"

        section = artifacts._heading_section(text, artifacts._TESTING_HEADING_PATTERN)

        assert "body line" in section
        assert "sub line" in section
        assert "other" not in section

    def test_clip_appends_marker_only_when_over_limit(self) -> None:
        assert artifacts._clip("short", 100) == "short"
        clipped = artifacts._clip("x" * 200, 50)
        assert len(clipped) == 50
        assert clipped.endswith("... [truncated]")

    def test_total_bundle_respects_global_budget(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(tmp_path, "tests/test_a.py", _PYTHON_TEST_BODY * 200)
        monkeypatch.setattr(artifacts, "_TOTAL_CHAR_LIMIT", 500)

        bundle = artifacts.gather_test_quality(_ctx(tmp_path))

        assert len(bundle) <= 500


# ---------------------------------------------------------------------------
# cli wiring — the coverage collector's data reaches the gatherer context.
# ---------------------------------------------------------------------------


class TestArtifactContextWiring:
    def _report(self, collectors: dict) -> Report:
        return Report(
            schema_version="1.1.0",
            aggregate=None,
            tool_availability={},
            collectors=collectors,
        )

    def test_coverage_block_data_is_threaded(self, tmp_path: Path) -> None:
        coverage = CollectorResult(status="ok", data={"line_pct": 0.5})

        ctx = _artifact_context(self._report({"coverage": coverage}), tmp_path)

        assert ctx.repo_root == tmp_path
        assert ctx.coverage == {"line_pct": 0.5}

    def test_missing_coverage_block_yields_none(self, tmp_path: Path) -> None:
        ctx = _artifact_context(self._report({}), tmp_path)

        assert ctx.coverage is None

    def test_skip_marker_dict_yields_none(self, tmp_path: Path) -> None:
        """A skipped collector leaves a plain marker dict, not a CollectorResult."""

        marker = {"status": "skipped", "reason": "tool unavailable", "data": {}}

        ctx = _artifact_context(self._report({"coverage": marker}), tmp_path)

        assert ctx.coverage is None
