"""Behavioral tests for scripts/regenerate_specs_index.py.

Tests are designed from the index generator's behavioral contract:
  1. Parses bold-key fields from a well-formed SPEC file (slug, archived, status,
     tier, ADRs, summary).
  2. Missing bold-key field produces a blank cell — no crash.
  3. Sort order is by Archived date descending; tie-break is by slug.
  4. Summary is extracted from the first line of ## Feature Summary.
  5. An empty directory still writes a valid index with header + empty table.
  6. The generated table has exactly one data row per SPEC_*.md file.
  7. Files that do not match SPEC_*.md are skipped.
  8. ADRs field captures all dec-NNN identifiers from the bold-key line.
  9. Summary is truncated to MAX_SUMMARY_LEN characters.

Each test is self-contained via tmp_path. Real specs are used only in the
smoke test (test_smoke_against_real_specs).

Strategy: monkeypatch the module-level SPECS_DIR and INDEX_PATH constants,
then call collect_specs() / generate_index() directly, mirroring the approach
used in other scripts tests.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
GENERATOR_SCRIPT = SCRIPTS_DIR / "regenerate_specs_index.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

WELL_FORMED_SPEC = """\
# SPEC: `/project-metrics` Command — Project Health Metrics

**Task slug**: `project-metrics`
**Tier**: Full (escalated from Standard)
**Archived**: 2026-04-23
**Status**: Shipped
**ADRs**: `dec-062` (storage schema), `dec-063` (collector protocol)

## Feature Summary

Adds a slash command that computes project health metrics on any onboarded repo.
A second paragraph that should not appear in the summary.
"""

SPEC_MISSING_ARCHIVED = """\
# SPEC: Some Other Feature

**Task slug**: `some-feature`
**Tier**: Standard
**Status**: Shipped

## Feature Summary

This spec has no Archived field.
"""

SPEC_MISSING_ADRS = """\
# SPEC: Minimal Spec

**Task slug**: `minimal`
**Tier**: Lightweight
**Archived**: 2025-12-01
**Status**: Shipped

## Feature Summary

A minimal spec with no ADRs field.
"""

SPEC_NO_SUMMARY_SECTION = """\
# SPEC: No Summary

**Task slug**: `no-summary`
**Archived**: 2024-01-15
**Status**: Shipped
"""

SPEC_VERBOSE_STATUS = """\
# SPEC: Verbose Status Spec

**Task slug**: `verbose-status`
**Archived**: 2026-05-01
**Status**: Shipped — verifier PASS-WITH-WARNINGS (step-21); 2 catalog-text WARNs fixed; ADRs finalized

## Feature Summary

A spec whose Status line has verbose detail that should not appear in the index.
"""

SPEC_VERBOSE_STATUS_PAREN = """\
# SPEC: Verbose Status Paren

**Task slug**: `verbose-status-paren`
**Archived**: 2026-05-02
**Status**: Shipped (PASS WITH FINDINGS — verifier verdict)

## Feature Summary

A spec whose Status uses a parenthetical suffix.
"""

SPEC_LONG_SUMMARY = (
    """\
# SPEC: Long Summary Spec

**Task slug**: `long-summary`
**Archived**: 2025-06-15
**Status**: Shipped

## Feature Summary

"""
    + ("A" * 300)
    + "\n"
)


# ---------------------------------------------------------------------------
# Helper: load the generator module with monkeypatched paths
# ---------------------------------------------------------------------------


def _load_module(tmp_path: Path) -> object:
    """Import regenerate_specs_index fresh, rebinding paths to tmp_path."""
    # Ensure scripts/ is on sys.path so _repo_root import works.
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))

    # Force a fresh import each time so monkeypatching doesn't leak.
    mod_name = "regenerate_specs_index"
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    import regenerate_specs_index as mod  # noqa: PLC0415

    specs_dir = tmp_path / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)
    index_path = specs_dir / "SPECS_INDEX.md"

    # Rebind module constants to tmp paths.
    mod.SPECS_DIR = specs_dir
    mod.INDEX_PATH = index_path

    return mod


# ---------------------------------------------------------------------------
# Tests: parse_spec_file
# ---------------------------------------------------------------------------


class TestParseSpecFile:
    def test_parses_all_bold_key_fields(self, tmp_path: Path) -> None:
        mod = _load_module(tmp_path)
        spec_file = tmp_path / "specs" / "SPEC_project-metrics_2026-04-23.md"
        spec_file.write_text(WELL_FORMED_SPEC, encoding="utf-8")

        result = mod.parse_spec_file(spec_file)

        assert result["slug"] == "project-metrics"
        assert result["archived"] == "2026-04-23"
        assert result["status"] == "Shipped"
        assert result["tier"] == "Full"  # parenthetical trimmed for table clarity
        assert "dec-062" in result["adrs"]
        assert "dec-063" in result["adrs"]

    def test_extracts_summary_first_line_of_feature_summary(self, tmp_path: Path) -> None:
        mod = _load_module(tmp_path)
        spec_file = tmp_path / "specs" / "SPEC_project-metrics_2026-04-23.md"
        spec_file.write_text(WELL_FORMED_SPEC, encoding="utf-8")

        result = mod.parse_spec_file(spec_file)

        assert "Adds a slash command" in result["summary"]
        # Should not include the second paragraph.
        assert "second paragraph" not in result["summary"]

    def test_missing_archived_field_is_blank(self, tmp_path: Path) -> None:
        mod = _load_module(tmp_path)
        spec_file = tmp_path / "specs" / "SPEC_some-feature_2026-01-01.md"
        spec_file.write_text(SPEC_MISSING_ARCHIVED, encoding="utf-8")

        result = mod.parse_spec_file(spec_file)

        assert result["archived"] == ""

    def test_missing_adrs_field_is_blank(self, tmp_path: Path) -> None:
        mod = _load_module(tmp_path)
        spec_file = tmp_path / "specs" / "SPEC_minimal_2025-12-01.md"
        spec_file.write_text(SPEC_MISSING_ADRS, encoding="utf-8")

        result = mod.parse_spec_file(spec_file)

        assert result["adrs"] == ""

    def test_missing_summary_section_is_blank(self, tmp_path: Path) -> None:
        mod = _load_module(tmp_path)
        spec_file = tmp_path / "specs" / "SPEC_no-summary_2024-01-15.md"
        spec_file.write_text(SPEC_NO_SUMMARY_SECTION, encoding="utf-8")

        result = mod.parse_spec_file(spec_file)

        assert result["summary"] == ""

    def test_summary_is_truncated_to_max_length(self, tmp_path: Path) -> None:
        mod = _load_module(tmp_path)
        spec_file = tmp_path / "specs" / "SPEC_long-summary_2025-06-15.md"
        spec_file.write_text(SPEC_LONG_SUMMARY, encoding="utf-8")

        result = mod.parse_spec_file(spec_file)

        assert len(result["summary"]) <= mod.MAX_SUMMARY_LEN + 3  # +3 for ellipsis

    def test_verbose_status_em_dash_truncated_to_short_form(self, tmp_path: Path) -> None:
        """Status with ' — ' suffix is normalized to its leading token only."""
        mod = _load_module(tmp_path)
        spec_file = tmp_path / "specs" / "SPEC_verbose-status_2026-05-01.md"
        spec_file.write_text(SPEC_VERBOSE_STATUS, encoding="utf-8")

        result = mod.parse_spec_file(spec_file)

        assert result["status"] == "Shipped"

    def test_verbose_status_paren_truncated_to_short_form(self, tmp_path: Path) -> None:
        """Status with ' (' suffix is normalized to its leading token only."""
        mod = _load_module(tmp_path)
        spec_file = tmp_path / "specs" / "SPEC_verbose-status-paren_2026-05-02.md"
        spec_file.write_text(SPEC_VERBOSE_STATUS_PAREN, encoding="utf-8")

        result = mod.parse_spec_file(spec_file)

        assert result["status"] == "Shipped"

    def test_filename_used_as_slug_fallback(self, tmp_path: Path) -> None:
        """If no Task slug bold-key, filename stem is used as fallback."""
        mod = _load_module(tmp_path)
        spec = "# SPEC: Bare Spec\n\n## Feature Summary\n\nNo slug line here.\n"
        spec_file = tmp_path / "specs" / "SPEC_bare-spec_2025-03-10.md"
        spec_file.write_text(spec, encoding="utf-8")

        result = mod.parse_spec_file(spec_file)

        # slug comes from filename when no bold key
        assert result["slug"] != ""


# ---------------------------------------------------------------------------
# Tests: collect_specs
# ---------------------------------------------------------------------------


class TestCollectSpecs:
    def test_collects_only_spec_underscore_files(self, tmp_path: Path) -> None:
        mod = _load_module(tmp_path)
        specs_dir = tmp_path / "specs"

        (specs_dir / "SPEC_alpha_2026-01-01.md").write_text(SPEC_MISSING_ADRS, encoding="utf-8")
        (specs_dir / "NOT_A_SPEC.md").write_text("# Not a SPEC\n", encoding="utf-8")
        (specs_dir / "README.md").write_text("# Index\n", encoding="utf-8")

        results = mod.collect_specs()

        filenames = [r["_filename"] for r in results]
        assert any("SPEC_alpha" in f for f in filenames)
        assert all("NOT_A_SPEC" not in f for f in filenames)
        assert all("README" not in f for f in filenames)

    def test_sort_order_by_archived_descending(self, tmp_path: Path) -> None:
        mod = _load_module(tmp_path)
        specs_dir = tmp_path / "specs"

        older = """\
# SPEC: Older
**Task slug**: `older`
**Archived**: 2025-01-01
**Status**: Shipped
## Feature Summary
Older feature.
"""
        newer = """\
# SPEC: Newer
**Task slug**: `newer`
**Archived**: 2026-06-01
**Status**: Shipped
## Feature Summary
Newer feature.
"""
        middle = """\
# SPEC: Middle
**Task slug**: `middle`
**Archived**: 2025-09-15
**Status**: Shipped
## Feature Summary
Middle feature.
"""
        (specs_dir / "SPEC_older_2025-01-01.md").write_text(older, encoding="utf-8")
        (specs_dir / "SPEC_newer_2026-06-01.md").write_text(newer, encoding="utf-8")
        (specs_dir / "SPEC_middle_2025-09-15.md").write_text(middle, encoding="utf-8")

        results = mod.collect_specs()

        archived_dates = [r["archived"] for r in results]
        assert archived_dates == sorted(archived_dates, reverse=True)

    def test_tie_break_by_slug_ascending(self, tmp_path: Path) -> None:
        mod = _load_module(tmp_path)
        specs_dir = tmp_path / "specs"

        spec_b = """\
# SPEC: B
**Task slug**: `beta`
**Archived**: 2026-01-01
**Status**: Shipped
## Feature Summary
B.
"""
        spec_a = """\
# SPEC: A
**Task slug**: `alpha`
**Archived**: 2026-01-01
**Status**: Shipped
## Feature Summary
A.
"""
        (specs_dir / "SPEC_beta_2026-01-01.md").write_text(spec_b, encoding="utf-8")
        (specs_dir / "SPEC_alpha_2026-01-01.md").write_text(spec_a, encoding="utf-8")

        results = mod.collect_specs()

        slugs = [r["slug"] for r in results]
        assert slugs == ["alpha", "beta"]

    def test_empty_directory_returns_empty_list(self, tmp_path: Path) -> None:
        mod = _load_module(tmp_path)
        results = mod.collect_specs()
        assert results == []

    def test_nonexistent_directory_returns_empty_list(self, tmp_path: Path) -> None:
        mod = _load_module(tmp_path)
        mod.SPECS_DIR = tmp_path / "nonexistent"
        results = mod.collect_specs()
        assert results == []


# ---------------------------------------------------------------------------
# Tests: generate_index
# ---------------------------------------------------------------------------


class TestGenerateIndex:
    def test_empty_specs_produces_valid_table(self, tmp_path: Path) -> None:
        mod = _load_module(tmp_path)
        content = mod.generate_index([])

        assert (
            "SPECS_INDEX" in content or "Specs Index" in content or "specs index" in content.lower()
        )
        assert "do not edit" in content.lower() or "auto-generated" in content.lower()
        # Table header must be present.
        assert "|" in content

    def test_one_row_per_spec(self, tmp_path: Path) -> None:
        mod = _load_module(tmp_path)
        specs_dir = tmp_path / "specs"

        for i in range(3):
            slug = f"feature-{i}"
            date = f"2026-0{i + 1}-01"
            content = f"""\
# SPEC: Feature {i}
**Task slug**: `{slug}`
**Archived**: {date}
**Status**: Shipped
## Feature Summary
Summary {i}.
"""
            (specs_dir / f"SPEC_{slug}_{date}.md").write_text(content, encoding="utf-8")

        specs = mod.collect_specs()
        table = mod.generate_index(specs)

        # Separator row + 3 data rows + header
        rows = [line for line in table.splitlines() if line.startswith("|")]
        data_rows = [r for r in rows if not all(c in "| :-" for c in r)]
        assert len(data_rows) == 4  # 1 header + 3 data rows

    def test_table_contains_expected_columns(self, tmp_path: Path) -> None:
        mod = _load_module(tmp_path)
        content = mod.generate_index([])

        # The header row must contain these column names.
        header_line = next((line for line in content.splitlines() if line.startswith("|")), "")
        for col in ("Spec", "Slug", "Status"):
            assert col in header_line, f"Column '{col}' missing from header: {header_line}"

    def test_spec_filename_appears_as_link_in_row(self, tmp_path: Path) -> None:
        mod = _load_module(tmp_path)
        specs_dir = tmp_path / "specs"
        spec_content = """\
# SPEC: Link Test
**Task slug**: `link-test`
**Archived**: 2026-03-10
**Status**: Shipped
## Feature Summary
Testing links.
"""
        (specs_dir / "SPEC_link-test_2026-03-10.md").write_text(spec_content, encoding="utf-8")

        specs = mod.collect_specs()
        table = mod.generate_index(specs)

        assert "SPEC_link-test_2026-03-10.md" in table

    def test_dec_nnn_ids_appear_in_row(self, tmp_path: Path) -> None:
        mod = _load_module(tmp_path)
        specs_dir = tmp_path / "specs"
        (specs_dir / "SPEC_project-metrics_2026-04-23.md").write_text(
            WELL_FORMED_SPEC, encoding="utf-8"
        )

        specs = mod.collect_specs()
        table = mod.generate_index(specs)

        assert "dec-062" in table
        assert "dec-063" in table


# ---------------------------------------------------------------------------
# Tests: main (write to disk)
# ---------------------------------------------------------------------------


class TestMain:
    def test_writes_index_file(self, tmp_path: Path) -> None:
        """main() with --repo-root writes index to the tmp specs dir."""
        specs_dir = tmp_path / ".ai-state" / "specs"
        specs_dir.mkdir(parents=True)
        (specs_dir / "SPEC_sample_2026-01-01.md").write_text(SPEC_MISSING_ADRS, encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(GENERATOR_SCRIPT), "--repo-root", str(tmp_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"main() failed: {result.stderr}"

        index_path = specs_dir / "SPECS_INDEX.md"
        assert index_path.exists()
        content = index_path.read_text(encoding="utf-8")
        assert "SPEC_sample" in content

    def test_empty_dir_writes_valid_index(self, tmp_path: Path) -> None:
        """main() with an empty specs dir writes a valid header-only index."""
        specs_dir = tmp_path / ".ai-state" / "specs"
        specs_dir.mkdir(parents=True)

        result = subprocess.run(
            [sys.executable, str(GENERATOR_SCRIPT), "--repo-root", str(tmp_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"main() failed: {result.stderr}"

        index_path = specs_dir / "SPECS_INDEX.md"
        content = index_path.read_text(encoding="utf-8")
        # Even with 0 specs the index must have the auto-gen header + table header.
        assert "|" in content
        assert "auto-generated" in content.lower() or "do not edit" in content.lower()


# ---------------------------------------------------------------------------
# Smoke test against real specs
# ---------------------------------------------------------------------------


class TestSmokeRealSpecs:
    def test_real_specs_index_has_one_row_per_spec_file(self) -> None:
        """Generator produces one row per real SPEC_*.md in .ai-state/specs/ (count-agnostic)."""
        real_specs_dir = SCRIPTS_DIR.parent / ".ai-state" / "specs"
        spec_count = len(list(real_specs_dir.glob("SPEC_*.md")))
        result = subprocess.run(
            [sys.executable, str(GENERATOR_SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"Generator failed: {result.stderr}"
        assert (
            str(spec_count) in result.stdout
        ), f"Expected {spec_count} entries (one per SPEC_*.md); got: {result.stdout.strip()}"

    def test_generated_index_readable(self) -> None:
        """The written SPECS_INDEX.md is a well-formed markdown file."""
        real_specs_dir = SCRIPTS_DIR.parent / ".ai-state" / "specs"
        index_path = real_specs_dir / "SPECS_INDEX.md"
        assert index_path.exists(), "SPECS_INDEX.md should exist after smoke run"
        content = index_path.read_text(encoding="utf-8")
        assert content.startswith("#"), "Index should start with a markdown heading"
        assert "|" in content, "Index should contain a table"
