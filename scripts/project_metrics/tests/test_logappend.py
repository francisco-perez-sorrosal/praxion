"""Behavioral tests for ``logappend.py`` -- file-locked append to METRICS_LOG.md.

These tests encode the contract for the final composition-layer step: a
single ``append_log(report, ai_state_dir, report_md_filename)`` call that
produces one pipe-separated Markdown row in ``.ai-state/METRICS_LOG.md``,
serialized across concurrent invocations by ``fcntl.flock(LOCK_EX)``, and
atomic against mid-write interruption via a temp-file-then-rename pattern.

The storage schema ADR (``dec-draft-b068ad8e``) freezes the 16 aggregate
columns plus a trailing ``report_file`` link column. The stability contract
for that header is this test suite's responsibility: the header MUST come
verbatim from ``schema.aggregate_header_for_log()`` so column drift shows
up as a header-mismatch failure here, not as a silent divergence downstream.

Concurrency is tested with real ``subprocess.Popen`` processes rather than
threads. Threaded tests cannot exercise ``fcntl.flock`` semantics correctly
because flock is a per-open-file-description lock and threads in the same
process share descriptors; only separate processes produce the genuine
race that the implementation must survive.

Import strategy -- every test imports ``append_log`` at test-body time.
During the BDD/TDD RED handshake, ``logappend.py`` is a stub with an empty
``__all__``; top-of-module imports would fail pytest collection for every
test in this file simultaneously. Deferred imports yield per-test
RED/GREEN resolution and a specific ``AttributeError`` or
``ImportError`` for each test rather than a single collection crash.

Platform -- ``fcntl`` is POSIX-only. Windows tests (if any ran here at
all) would need a separate lock mechanism; the SYSTEMS_PLAN risk register
pins Windows out of scope for Praxion, so the concurrency tests are
explicitly ``skipif(sys.platform == "win32")``.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Sample-data helpers -- construct a minimal but complete Report that can be
# fed through append_log(). Literal values; no wall-clock, no random, no env.
# Shared with the deferred-import helpers so every test constructs its
# fixtures the same way.
# ---------------------------------------------------------------------------


def _sample_aggregate_kwargs(
    *,
    timestamp: str = "2026-04-23T14:30:00Z",
    commit_sha: str = "abc123fabc123fabc123fabc123fabc123fabc12",
    window_days: int = 90,
    sloc_total: int = 4200,
    file_count: int = 42,
    language_count: int = 3,
    ccn_p95: float | None = 7.5,
    cognitive_p95: float | None = 9.0,
    cyclic_deps: int | None = 0,
    churn_total_90d: int = 567,
    change_entropy_90d: float = 2.1,
    truck_factor: int = 2,
    hotspot_top_score: float = 123.4,
    hotspot_gini: float = 0.75,
    coverage_line_pct: float | None = 0.813,
) -> dict[str, Any]:
    """Build a full 16-field kwargs dict for AggregateBlock.

    Defaults produce an all-populated (no-null) block; individual tests
    override null-eligible fields to None to exercise the null-rendering
    contract via ``pytest.mark.parametrize``.
    """
    return {
        "schema_version": "1.0.0",
        "timestamp": timestamp,
        "commit_sha": commit_sha,
        "window_days": window_days,
        "sloc_total": sloc_total,
        "file_count": file_count,
        "language_count": language_count,
        "ccn_p95": ccn_p95,
        "cognitive_p95": cognitive_p95,
        "cyclic_deps": cyclic_deps,
        "churn_total_90d": churn_total_90d,
        "change_entropy_90d": change_entropy_90d,
        "truck_factor": truck_factor,
        "hotspot_top_score": hotspot_top_score,
        "hotspot_gini": hotspot_gini,
        "coverage_line_pct": coverage_line_pct,
    }


def _build_report(**aggregate_overrides: Any) -> Any:
    """Construct a minimal Report with overridable aggregate fields.

    Deferred-imports the schema module here (not at module top) so this
    helper is safe to define before the stub schema is fully populated --
    though in this pipeline schema.py has been GREEN since the schema module landed.
    """
    from scripts.project_metrics.schema import AggregateBlock, Report

    kwargs = _sample_aggregate_kwargs(**aggregate_overrides)
    aggregate = AggregateBlock(**kwargs)
    return Report(
        schema_version="1.0.0",
        aggregate=aggregate,
        tool_availability={},
        collectors={},
    )


# ---------------------------------------------------------------------------
# Small file-reading helpers -- keep the "arrange / act / assert" bodies
# compact by absorbing the routine "read METRICS_LOG.md and split into
# trimmed, non-empty lines" idiom.
# ---------------------------------------------------------------------------


def _read_log_lines(ai_state_dir: Path) -> list[str]:
    log_path = ai_state_dir / "METRICS_LOG.md"
    raw = log_path.read_text(encoding="utf-8")
    return [line for line in raw.splitlines() if line.strip()]


def _row_cells(line: str) -> list[str]:
    """Parse a pipe-separated Markdown table row into trimmed cell values.

    Markdown-table rows start and end with ``|``, so ``split('|')[1:-1]``
    discards the empty edge tokens. Cells are stripped of surrounding
    whitespace so assertions don't have to worry about "| 1.0.0 |" vs
    "|1.0.0|".
    """
    parts = line.split("|")
    return [cell.strip() for cell in parts[1:-1]]


# ---------------------------------------------------------------------------
# First-run-creates-header behavior. File does not exist; append_log must
# create it with the two-line header (header row + separator) plus one data
# row.
# ---------------------------------------------------------------------------


class TestFirstRunCreatesHeader:
    """When METRICS_LOG.md is absent, append_log creates it with header + data row."""

    def test_log_file_created_when_absent(self, tmp_path: Path) -> None:
        from scripts.project_metrics.logappend import append_log

        report = _build_report()
        log_path = tmp_path / "METRICS_LOG.md"
        assert not log_path.exists(), "precondition: log must not exist"

        append_log(report, tmp_path, "METRICS_REPORT_2026-04-23_14-30-00.md")

        assert log_path.exists(), "append_log must create METRICS_LOG.md on first run"

    def test_first_run_writes_header_row_matching_schema(self, tmp_path: Path) -> None:
        from scripts.project_metrics.logappend import append_log
        from scripts.project_metrics.schema import aggregate_header_for_log

        report = _build_report()
        append_log(report, tmp_path, "METRICS_REPORT_2026-04-23_14-30-00.md")

        content = (tmp_path / "METRICS_LOG.md").read_text(encoding="utf-8")
        expected_header = aggregate_header_for_log()
        assert expected_header in content, (
            "First-run METRICS_LOG.md must embed the two-line header "
            "from schema.aggregate_header_for_log() verbatim -- "
            "header drift must surface as this assertion failure."
        )

    def test_first_run_writes_exactly_one_data_row(self, tmp_path: Path) -> None:
        from scripts.project_metrics.logappend import append_log

        report = _build_report()
        append_log(report, tmp_path, "METRICS_REPORT_2026-04-23_14-30-00.md")

        # Structure: line 0 header, line 1 separator, line 2 data row.
        lines = _read_log_lines(tmp_path)
        assert len(lines) == 3, (
            f"First run must yield header + separator + 1 data row; "
            f"got {len(lines)} non-empty lines: {lines!r}"
        )

    def test_creates_parent_ai_state_directory_if_missing(self, tmp_path: Path) -> None:
        from scripts.project_metrics.logappend import append_log

        ai_state_dir = tmp_path / "nested" / ".ai-state"
        # Caller passes a non-existent directory -- common on truly-first-run
        # of /project-metrics in a repo whose .ai-state/ has been cleaned.
        report = _build_report()

        append_log(report, ai_state_dir, "METRICS_REPORT_2026-04-23_14-30-00.md")

        assert (ai_state_dir / "METRICS_LOG.md").exists()


# ---------------------------------------------------------------------------
# Subsequent-appends-add-only-rows behavior. Second call to append_log on an
# existing file must NOT duplicate the header.
# ---------------------------------------------------------------------------


class TestSubsequentAppendOnly:
    """After first append, subsequent appends add data rows only -- no header duplication."""

    def test_second_append_adds_only_one_row(self, tmp_path: Path) -> None:
        from scripts.project_metrics.logappend import append_log

        first = _build_report(timestamp="2026-04-23T14:30:00Z")
        append_log(first, tmp_path, "METRICS_REPORT_2026-04-23_14-30-00.md")
        lines_after_first = len(_read_log_lines(tmp_path))

        second = _build_report(timestamp="2026-04-23T15:45:00Z", commit_sha="f" * 40)
        append_log(second, tmp_path, "METRICS_REPORT_2026-04-23_15-45-00.md")

        lines_after_second = len(_read_log_lines(tmp_path))
        assert lines_after_second - lines_after_first == 1, (
            "Second append must add exactly 1 row; delta was "
            f"{lines_after_second - lines_after_first}."
        )

    def test_second_append_does_not_duplicate_header(self, tmp_path: Path) -> None:
        from scripts.project_metrics.logappend import append_log
        from scripts.project_metrics.schema import aggregate_header_for_log

        first = _build_report(timestamp="2026-04-23T14:30:00Z")
        append_log(first, tmp_path, "METRICS_REPORT_2026-04-23_14-30-00.md")

        second = _build_report(timestamp="2026-04-23T15:45:00Z")
        append_log(second, tmp_path, "METRICS_REPORT_2026-04-23_15-45-00.md")

        content = (tmp_path / "METRICS_LOG.md").read_text(encoding="utf-8")
        header = aggregate_header_for_log()
        first_line = header.splitlines()[0]
        # The header's first line should appear exactly once in the file.
        assert content.count(first_line) == 1, (
            "Header row must appear exactly once; "
            f"found {content.count(first_line)} copies."
        )

    def test_two_appends_preserve_row_order(self, tmp_path: Path) -> None:
        """Order is first-in / first-row after header -- timestamps are
        the discriminator downstream consumers sort by."""
        from scripts.project_metrics.logappend import append_log

        first = _build_report(timestamp="2026-04-23T10:00:00Z")
        append_log(first, tmp_path, "METRICS_REPORT_2026-04-23_10-00-00.md")
        second = _build_report(timestamp="2026-04-23T11:00:00Z")
        append_log(second, tmp_path, "METRICS_REPORT_2026-04-23_11-00-00.md")

        lines = _read_log_lines(tmp_path)
        # lines[0] header, lines[1] separator, lines[2] first data row,
        # lines[3] second data row.
        assert "2026-04-23T10:00:00Z" in lines[2]
        assert "2026-04-23T11:00:00Z" in lines[3]


# ---------------------------------------------------------------------------
# Row-content behavior. The 16 aggregate columns plus report_file must all
# appear in the row, positionally aligned with the frozen AGGREGATE_COLUMNS
# declaration order.
# ---------------------------------------------------------------------------


class TestRowContent:
    """Each aggregate column surfaces as a pipe-separated cell; final cell is report_file link."""

    def test_row_contains_all_sixteen_aggregate_column_values(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.logappend import append_log

        report = _build_report()
        append_log(report, tmp_path, "METRICS_REPORT_2026-04-23_14-30-00.md")

        lines = _read_log_lines(tmp_path)
        data_row = lines[2]  # header + separator + first data row

        # Every populated aggregate value must appear as a substring of the
        # data row. String coercion is the reader's contract; this is a
        # "presence" check, not a format check (which lives in
        # TestNullColumnRendering for null-eligible columns).
        for value in (
            "1.0.0",  # schema_version
            "2026-04-23T14:30:00Z",  # timestamp
            "abc123fabc123fabc123fabc123fabc123fabc12",  # commit_sha
            "90",  # window_days
            "4200",  # sloc_total
            "42",  # file_count
            "3",  # language_count
            "7.5",  # ccn_p95
            "9.0",  # cognitive_p95
            "567",  # churn_total_90d
            "2.1",  # change_entropy_90d
            "2",  # truck_factor
            "123.4",  # hotspot_top_score
            "0.75",  # hotspot_gini
        ):
            assert value in data_row, (
                f"Aggregate value {value!r} must appear in the data row: "
                f"got {data_row!r}"
            )

    def test_row_cell_count_matches_columns_plus_report_file(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.logappend import append_log
        from scripts.project_metrics.schema import AGGREGATE_COLUMNS

        report = _build_report()
        append_log(report, tmp_path, "METRICS_REPORT_2026-04-23_14-30-00.md")

        lines = _read_log_lines(tmp_path)
        cells = _row_cells(lines[2])
        expected = len(AGGREGATE_COLUMNS) + 1  # +1 for trailing report_file
        assert len(cells) == expected, (
            f"Data row must have {expected} cells "
            f"({len(AGGREGATE_COLUMNS)} aggregate + 1 report_file); "
            f"got {len(cells)}: {cells!r}"
        )

    def test_final_cell_contains_report_md_filename(self, tmp_path: Path) -> None:
        """The trailing report_file cell must surface the MD filename so
        future UI can cross-link rows to reports. Substring-presence
        assertion -- the exact link format (bare filename vs markdown
        link) is a formatting concern the implementer may choose."""
        from scripts.project_metrics.logappend import append_log

        md_filename = "METRICS_REPORT_2026-04-23_14-30-00.md"
        report = _build_report()
        append_log(report, tmp_path, md_filename)

        lines = _read_log_lines(tmp_path)
        cells = _row_cells(lines[2])
        last_cell = cells[-1]
        assert md_filename in last_cell, (
            "Final cell must reference the passed report_md_filename; "
            f"got {last_cell!r}"
        )

    def test_final_cell_renders_as_markdown_link(self, tmp_path: Path) -> None:
        """Per plan's File Format section, the report_file column is a
        Markdown link ``[filename](filename)`` so MD viewers render it as
        a navigable reference."""
        from scripts.project_metrics.logappend import append_log

        md_filename = "METRICS_REPORT_2026-04-23_14-30-00.md"
        report = _build_report()
        append_log(report, tmp_path, md_filename)

        lines = _read_log_lines(tmp_path)
        cells = _row_cells(lines[2])
        last_cell = cells[-1]
        # Markdown-link shape: [text](target). Accept either exact
        # "[file.md](file.md)" or any link embedding the filename.
        assert (
            last_cell.startswith("[") and "](" in last_cell and last_cell.endswith(")")
        ), f"Final cell must be a Markdown link; got {last_cell!r}"

    def test_no_python_none_literal_appears_in_row(self, tmp_path: Path) -> None:
        """Guardrail: even with all-populated fields, Python's ``None``
        must never be string-coerced into the row. Catches lazy
        ``str(value)`` implementations that forget to special-case None
        before rendering."""
        from scripts.project_metrics.logappend import append_log

        report = _build_report()
        append_log(report, tmp_path, "METRICS_REPORT_2026-04-23_14-30-00.md")

        content = (tmp_path / "METRICS_LOG.md").read_text(encoding="utf-8")
        assert "None" not in content, (
            "Python None literal must never appear in rendered log; "
            "null-eligible columns must render as a dedicated marker."
        )


# ---------------------------------------------------------------------------
# Null-column rendering. Nullable aggregate columns (ccn_p95, cognitive_p95,
# cyclic_deps, coverage_line_pct) must render as a non-None marker.
# ---------------------------------------------------------------------------


class TestNullColumnRendering:
    """Nullable aggregate columns render as a dedicated marker, never as 'None'."""

    _NULLABLE_COLUMNS = ("ccn_p95", "cognitive_p95", "cyclic_deps", "coverage_line_pct")

    @pytest.mark.parametrize("column", _NULLABLE_COLUMNS)
    def test_nullable_column_renders_without_python_none_literal(
        self, tmp_path: Path, column: str
    ) -> None:
        from scripts.project_metrics.logappend import append_log

        report = _build_report(**{column: None})
        append_log(report, tmp_path, "METRICS_REPORT_2026-04-23_14-30-00.md")

        content = (tmp_path / "METRICS_LOG.md").read_text(encoding="utf-8")
        assert "None" not in content, (
            f"Column {column!r} set to None must render as a non-None marker; "
            f"found Python 'None' in the log."
        )

    @pytest.mark.parametrize("column", _NULLABLE_COLUMNS)
    def test_nullable_column_renders_as_non_empty_marker(
        self, tmp_path: Path, column: str
    ) -> None:
        """Cell must be non-empty so the column alignment holds. Empty
        cells break trailing-column detection in downstream parsers that
        split on ``|`` and count cells."""
        from scripts.project_metrics.logappend import append_log
        from scripts.project_metrics.schema import AGGREGATE_COLUMNS

        report = _build_report(**{column: None})
        append_log(report, tmp_path, "METRICS_REPORT_2026-04-23_14-30-00.md")

        lines = _read_log_lines(tmp_path)
        cells = _row_cells(lines[2])
        # Find the cell corresponding to the nullified column.
        col_idx = AGGREGATE_COLUMNS.index(column)
        null_cell = cells[col_idx]
        assert null_cell != "", (
            f"Nullable column {column!r} rendered as empty cell; "
            "must use a placeholder marker (e.g., '-', 'N/A')."
        )

    def test_all_nullable_columns_use_same_marker(self, tmp_path: Path) -> None:
        """Consistency: whatever marker the implementer picks, all four
        nullable columns use the same one. Prevents mixing ``-``,
        ``N/A``, and ``null`` in the same row."""
        from scripts.project_metrics.logappend import append_log
        from scripts.project_metrics.schema import AGGREGATE_COLUMNS

        null_kwargs = {col: None for col in self._NULLABLE_COLUMNS}
        report = _build_report(**null_kwargs)
        append_log(report, tmp_path, "METRICS_REPORT_2026-04-23_14-30-00.md")

        lines = _read_log_lines(tmp_path)
        cells = _row_cells(lines[2])
        markers = {
            cells[AGGREGATE_COLUMNS.index(col)] for col in self._NULLABLE_COLUMNS
        }
        assert len(markers) == 1, (
            f"All nullable columns must share one marker; found {markers!r}"
        )


# ---------------------------------------------------------------------------
# Atomic-write behavior. The implementation must use temp-file-then-rename
# so that a crash or rename failure mid-write cannot leave the log in a
# torn state.
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    """Temp-file-then-rename: rename failure preserves the original file content."""

    def test_rename_failure_preserves_original_file_content(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.logappend import append_log

        # Seed an initial log via a clean append_log call.
        first = _build_report(timestamp="2026-04-23T10:00:00Z")
        append_log(first, tmp_path, "METRICS_REPORT_2026-04-23_10-00-00.md")
        pristine_content = (tmp_path / "METRICS_LOG.md").read_text(encoding="utf-8")

        # Second call must fail at rename time. Patching os.replace is
        # the standard choice because temp-file-then-rename usually uses
        # Path.replace / os.replace (atomic on POSIX) rather than
        # os.rename. We patch both to cover either implementation choice.
        second = _build_report(timestamp="2026-04-23T11:00:00Z")

        def _raise_oserror(*_args: Any, **_kwargs: Any) -> None:
            raise OSError("simulated disk-full during atomic rename")

        with (
            patch(
                "scripts.project_metrics.logappend.os.replace",
                side_effect=_raise_oserror,
            ),
            patch(
                "scripts.project_metrics.logappend.os.rename",
                side_effect=_raise_oserror,
                create=True,
            ),
        ):
            with pytest.raises(OSError, match="simulated"):
                append_log(second, tmp_path, "METRICS_REPORT_2026-04-23_11-00-00.md")

        # After the failed append, the log content must be byte-identical
        # to the pre-failure snapshot. No partial row, no tail corruption.
        post_failure_content = (tmp_path / "METRICS_LOG.md").read_text(encoding="utf-8")
        assert post_failure_content == pristine_content, (
            "Rename failure must leave METRICS_LOG.md unchanged; "
            "atomic-write contract violated."
        )

    def test_rename_failure_leaves_no_temp_file_artifacts(self, tmp_path: Path) -> None:
        """A failed rename should clean up or never materialize temp
        files. Stale ``.tmp``/``.part`` artifacts confuse downstream
        readers and accumulate disk pressure over many runs."""
        from scripts.project_metrics.logappend import append_log

        first = _build_report(timestamp="2026-04-23T10:00:00Z")
        append_log(first, tmp_path, "METRICS_REPORT_2026-04-23_10-00-00.md")

        second = _build_report(timestamp="2026-04-23T11:00:00Z")

        def _raise_oserror(*_args: Any, **_kwargs: Any) -> None:
            raise OSError("simulated rename failure")

        with (
            patch(
                "scripts.project_metrics.logappend.os.replace",
                side_effect=_raise_oserror,
            ),
            patch(
                "scripts.project_metrics.logappend.os.rename",
                side_effect=_raise_oserror,
                create=True,
            ),
        ):
            with pytest.raises(OSError):
                append_log(second, tmp_path, "METRICS_REPORT_2026-04-23_11-00-00.md")

        # Enumerate stray artifacts. The legitimate files are
        # METRICS_LOG.md and nothing else; anything with ``.tmp``,
        # ``.part``, ``.new``, or ``~`` suffixes is an atomic-write leak.
        # We allow the canonical log file but reject temp artifacts.
        suspicious = []
        for entry in tmp_path.iterdir():
            if entry.name == "METRICS_LOG.md":
                continue
            # Temp-file patterns commonly used by atomic-write implementations.
            if any(
                marker in entry.name
                for marker in (".tmp", ".part", ".new", "~", ".swp")
            ):
                suspicious.append(entry.name)
        assert not suspicious, (
            f"Atomic-write failure left stale temp artifacts: {suspicious!r}"
        )


# ---------------------------------------------------------------------------
# fcntl.flock concurrency. Real subprocesses, real flock, genuine race.
# POSIX-only; skipped on Windows.
# ---------------------------------------------------------------------------


_CONCURRENT_APPEND_SCRIPT = textwrap.dedent(
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, {repo_root!r})

    from scripts.project_metrics.logappend import append_log
    from scripts.project_metrics.schema import AggregateBlock, Report

    timestamp = sys.argv[1]
    commit_sha = sys.argv[2]
    md_filename = sys.argv[3]
    ai_state_dir = Path(sys.argv[4])

    aggregate = AggregateBlock(
        schema_version="1.0.0",
        timestamp=timestamp,
        commit_sha=commit_sha,
        window_days=90,
        sloc_total=1000,
        file_count=10,
        language_count=1,
        ccn_p95=5.0,
        cognitive_p95=6.0,
        cyclic_deps=0,
        churn_total_90d=100,
        change_entropy_90d=1.5,
        truck_factor=1,
        hotspot_top_score=50.0,
        hotspot_gini=0.5,
        coverage_line_pct=0.8,
    )
    report = Report(
        schema_version="1.0.0",
        aggregate=aggregate,
        tool_availability={{}},
        collectors={{}},
    )
    append_log(report, ai_state_dir, md_filename)
    """
).strip()


def _repo_root_for_subprocess() -> Path:
    """Return the repo root that a subprocess must put on sys.path to
    ``from scripts.project_metrics... import ...``. Walks up from this
    test file until we find the directory containing ``scripts/``."""
    current = Path(__file__).resolve().parent
    for candidate in [current, *current.parents]:
        if (candidate / "scripts").is_dir() and (candidate / "scripts").joinpath(
            "project_metrics"
        ).is_dir():
            return candidate
    raise RuntimeError("Could not locate repo root from test file location.")


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl is POSIX-only")
class TestFlockConcurrency:
    """Two parallel subprocess appends serialize via fcntl.flock -- no corruption."""

    def test_two_concurrent_appends_produce_exactly_two_rows(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.logappend import append_log

        # Seed the log with a first write so the concurrent workers append
        # rather than race on header-creation. Removing this seed is also
        # valid and tests a stricter contract; choosing to seed narrows
        # the test to the concurrency behavior rather than the
        # header-creation-under-race behavior.
        first = _build_report(timestamp="2026-04-23T10:00:00Z")
        append_log(first, tmp_path, "METRICS_REPORT_2026-04-23_10-00-00.md")
        header_plus_sep_plus_first_row = _read_log_lines(tmp_path)
        assert len(header_plus_sep_plus_first_row) == 3, (
            "Test-design precondition: seed must yield 3 non-empty lines."
        )

        # Spawn two concurrent workers. Popen.wait() is blocking; we
        # start both before waiting so they really overlap.
        repo_root = _repo_root_for_subprocess()
        script = _CONCURRENT_APPEND_SCRIPT.format(repo_root=str(repo_root))
        worker_a = subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                "2026-04-23T11:00:00Z",
                "aaa" + "1" * 37,
                "METRICS_REPORT_2026-04-23_11-00-00.md",
                str(tmp_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        worker_b = subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                "2026-04-23T12:00:00Z",
                "bbb" + "2" * 37,
                "METRICS_REPORT_2026-04-23_12-00-00.md",
                str(tmp_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout_a, stderr_a = worker_a.communicate(timeout=30)
        stdout_b, stderr_b = worker_b.communicate(timeout=30)

        assert worker_a.returncode == 0, (
            f"Worker A failed (rc={worker_a.returncode}); "
            f"stderr:\n{stderr_a.decode('utf-8', errors='replace')}"
        )
        assert worker_b.returncode == 0, (
            f"Worker B failed (rc={worker_b.returncode}); "
            f"stderr:\n{stderr_b.decode('utf-8', errors='replace')}"
        )

        # Expected structure: header + separator + 1 seed row + 2 concurrent
        # rows = 5 non-empty lines total.
        lines = _read_log_lines(tmp_path)
        assert len(lines) == 5, (
            f"Expected 5 non-empty lines (header + sep + seed + 2 concurrent); "
            f"got {len(lines)}:\n" + "\n".join(lines)
        )

    def test_concurrent_appends_do_not_duplicate_header(self, tmp_path: Path) -> None:
        """Even without a seed -- when both workers hit a not-yet-created
        file -- exactly one header must emerge. The lock ensures the
        first worker's create-plus-header completes before the second
        sees the file."""
        from scripts.project_metrics.schema import aggregate_header_for_log

        repo_root = _repo_root_for_subprocess()
        script = _CONCURRENT_APPEND_SCRIPT.format(repo_root=str(repo_root))
        worker_a = subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                "2026-04-23T11:00:00Z",
                "aaa" + "1" * 37,
                "METRICS_REPORT_2026-04-23_11-00-00.md",
                str(tmp_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        worker_b = subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                "2026-04-23T12:00:00Z",
                "bbb" + "2" * 37,
                "METRICS_REPORT_2026-04-23_12-00-00.md",
                str(tmp_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        worker_a.communicate(timeout=30)
        worker_b.communicate(timeout=30)
        assert worker_a.returncode == 0
        assert worker_b.returncode == 0

        content = (tmp_path / "METRICS_LOG.md").read_text(encoding="utf-8")
        header_first_line = aggregate_header_for_log().splitlines()[0]
        assert content.count(header_first_line) == 1, (
            "Concurrent first-run workers must race into exactly one header; "
            f"found {content.count(header_first_line)} header copies."
        )

    def test_concurrent_appends_produce_no_truncated_rows(self, tmp_path: Path) -> None:
        """Each data row must have the full cell count. Mid-write
        interleaving would surface as rows with fewer cells than the
        header, or rows containing partial text from another write."""
        from scripts.project_metrics.logappend import append_log
        from scripts.project_metrics.schema import AGGREGATE_COLUMNS

        seed = _build_report(timestamp="2026-04-23T10:00:00Z")
        append_log(seed, tmp_path, "METRICS_REPORT_2026-04-23_10-00-00.md")

        repo_root = _repo_root_for_subprocess()
        script = _CONCURRENT_APPEND_SCRIPT.format(repo_root=str(repo_root))
        workers = [
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    script,
                    f"2026-04-23T{11 + i}:00:00Z",
                    chr(ord("a") + i) * 3 + str(i) * 37,
                    f"METRICS_REPORT_2026-04-23_{11 + i}-00-00.md",
                    str(tmp_path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for i in range(2)
        ]
        for worker in workers:
            worker.communicate(timeout=30)
            assert worker.returncode == 0

        lines = _read_log_lines(tmp_path)
        # Skip header (lines[0]) and separator (lines[1]); every data row
        # must have exactly len(AGGREGATE_COLUMNS) + 1 cells.
        expected_cells = len(AGGREGATE_COLUMNS) + 1
        for idx, line in enumerate(lines[2:], start=2):
            cells = _row_cells(line)
            assert len(cells) == expected_cells, (
                f"Row {idx} has {len(cells)} cells (expected {expected_cells}); "
                f"concurrent writes corrupted alignment: {line!r}"
            )


# ---------------------------------------------------------------------------
# Exception safety. If fcntl.flock itself raises (e.g., EDEADLK, EIO on a
# network filesystem), append_log must re-raise without corrupting the file.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl is POSIX-only")
class TestExceptionSafety:
    """fcntl.flock raising OSError re-propagates and leaves the file unchanged."""

    def test_flock_raising_oserror_propagates_out_of_append_log(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.logappend import append_log

        report = _build_report()

        def _flock_raises(*_args: Any, **_kwargs: Any) -> None:
            raise OSError("simulated lock acquisition failure")

        with patch(
            "scripts.project_metrics.logappend.fcntl.flock", side_effect=_flock_raises
        ):
            with pytest.raises(OSError, match="simulated lock acquisition failure"):
                append_log(report, tmp_path, "METRICS_REPORT_2026-04-23_14-30-00.md")

    def test_flock_failure_leaves_pre_existing_file_unchanged(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.logappend import append_log

        # Seed a known-good log first.
        seed = _build_report(timestamp="2026-04-23T10:00:00Z")
        append_log(seed, tmp_path, "METRICS_REPORT_2026-04-23_10-00-00.md")
        pristine = (tmp_path / "METRICS_LOG.md").read_text(encoding="utf-8")

        # Next append fails at flock acquisition.
        second = _build_report(timestamp="2026-04-23T11:00:00Z")

        def _flock_raises(*_args: Any, **_kwargs: Any) -> None:
            raise OSError("EDEADLK-like simulated failure")

        with patch(
            "scripts.project_metrics.logappend.fcntl.flock", side_effect=_flock_raises
        ):
            with pytest.raises(OSError):
                append_log(second, tmp_path, "METRICS_REPORT_2026-04-23_11-00-00.md")

        post = (tmp_path / "METRICS_LOG.md").read_text(encoding="utf-8")
        assert post == pristine, (
            "flock failure corrupted METRICS_LOG.md; "
            "append_log must roll back before any on-disk mutation."
        )
