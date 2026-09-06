"""Behavioral tests for the configurable coverage-refresh timeout and the
explicit staleness marker ``/project-metrics`` must emit when a
``--refresh-coverage`` attempt does not produce a trustworthy, current
``coverage.xml``.

These tests encode the contract the implementer must satisfy in
``scripts/project_metrics/cli.py``:

* ``_COVERAGE_INVOKE_TIMEOUT_SECONDS`` (currently a hardcoded ``600.0``,
  against an 8-11 minute suite) becomes overridable via a
  ``--coverage-timeout <seconds>`` CLI flag, threaded through to the
  ``subprocess.run(..., timeout=...)`` call inside
  ``_refresh_coverage_artifact``. The un-overridden default must sit
  comfortably above the suite's observed 8-11 minute runtime.
* The composed report (the written ``METRICS_REPORT_*.json``) carries an
  explicit top-level ``coverage_refresh`` field: ``"timed-out"`` when the
  refresh subprocess raised ``subprocess.TimeoutExpired``, ``"failed"``
  when it raised for any other reason (including "no coverage target
  discoverable"), and ``"fresh"`` when it completed successfully. The
  field (and a companion ``coverage_artifact_mtime``, reflecting the
  artifact's own mtime captured *before* the refresh attempt) is present
  only when ``--refresh-coverage`` was actually passed.
* The rendered Markdown names the coverage figures "stale" in human
  prose whenever ``coverage_refresh`` is ``"timed-out"`` or ``"failed"`` --
  never silently presenting a stale artifact's numbers as current -- and
  says nothing of the sort on a successful refresh.

Interface contract mocked here (the implementer owns the exact
mechanism; these tests only pin the externally observable JSON/Markdown
shape and the ``subprocess.run`` call the timeout must reach):

    scripts.project_metrics.cli._COVERAGE_INVOKE_TIMEOUT_SECONDS
    scripts.project_metrics.cli._refresh_coverage_artifact(repo_root) -> None

Unlike ``test_refresh_coverage_flag.py``'s full mock stack, this suite
deliberately leaves ``render_markdown``/``render_json`` and
``_refresh_coverage_artifact`` themselves unpatched: the staleness marker
under test is only observable in the *real* rendered output, and the
refresh helper's real body is exactly what calls the (mocked)
``subprocess.run`` this suite manipulates -- per the plan's own
instruction to monkeypatch ``subprocess.run``, never invoke the real
suite.

Import strategy -- every test imports ``main``/``_build_parser`` inside
its body, matching ``test_refresh_coverage_flag.py``'s convention, so
collection cannot collapse into a single ``ImportError`` before the
BDD/TDD RED handshake.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Test-data builders -- mirror test_refresh_coverage_flag.py's structure so a
# mocked Runner returns a fully-populated, schema-valid Report the real
# render_markdown/render_json can serialize without special-casing.
# ---------------------------------------------------------------------------


def _minimal_aggregate_kwargs() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "timestamp": "2026-04-23T18:45:00Z",
        "commit_sha": "abc123fabc123fabc123fabc123fabc123fabc12",
        "window_days": 90,
        "sloc_total": 4200,
        "file_count": 42,
        "language_count": 3,
        "ccn_p95": 7.5,
        "cognitive_p95": 9.0,
        "cyclic_deps": 0,
        "churn_total_90d": 567,
        "change_entropy_90d": 2.1,
        "truck_factor": 2,
        "hotspot_top_score": 123.4,
        "hotspot_gini": 0.75,
        "coverage_line_pct": 0.813,
    }


def _build_synthetic_report() -> Any:
    from scripts.project_metrics.schema import AggregateBlock, Report

    aggregate = AggregateBlock(**_minimal_aggregate_kwargs())
    return Report(
        schema_version="1.0.0",
        aggregate=aggregate,
        tool_availability={},
        collectors={},
    )


class _MockedCollaborators:
    """Holder for every CLI collaborator mocked here -- everything except
    rendering, which must run for real so this suite can inspect the actual
    written JSON/Markdown bytes."""

    def __init__(self) -> None:
        self.runner_cls: MagicMock = MagicMock(name="Runner")
        self.compose_aggregate: MagicMock = MagicMock(name="compose_aggregate")
        self.compose_hotspots: MagicMock = MagicMock(name="compose_hotspots")
        self.compute_trends: MagicMock = MagicMock(name="compute_trends")
        self.append_log: MagicMock = MagicMock(name="append_log")
        self.subprocess_run: MagicMock = MagicMock(name="subprocess.run")


def _install_partial_cli_mocks(*, repo_root: Path) -> tuple[_MockedCollaborators, list[Any]]:
    mocks = _MockedCollaborators()

    synthetic_report = _build_synthetic_report()
    runner_instance = MagicMock(name="RunnerInstance")
    runner_instance.run.return_value = synthetic_report
    mocks.runner_cls.return_value = runner_instance

    mocks.compose_aggregate.return_value = synthetic_report
    mocks.compose_hotspots.return_value = synthetic_report

    from scripts.project_metrics.schema import TrendBlock

    mocks.compute_trends.return_value = TrendBlock(status="first_run")
    mocks.append_log.return_value = None

    patchers = [
        patch("scripts.project_metrics.cli.Runner", mocks.runner_cls),
        patch("scripts.project_metrics.cli.compose_aggregate", mocks.compose_aggregate),
        patch("scripts.project_metrics.cli.compose_hotspots", mocks.compose_hotspots),
        patch("scripts.project_metrics.cli.compute_trends", mocks.compute_trends),
        patch("scripts.project_metrics.cli.append_log", mocks.append_log),
        patch("scripts.project_metrics.cli.subprocess.run", mocks.subprocess_run),
    ]
    return mocks, patchers


# ---------------------------------------------------------------------------
# subprocess.run side_effect plumbing -- answers the CLI's own git plumbing
# for real orchestration (repo-root resolution, provenance) and delegates
# only the coverage-target invocation (whatever argv _discover_coverage_target
# resolved to) to a per-test handler.
# ---------------------------------------------------------------------------


def _make_subprocess_side_effect(
    repo_root: Path,
    coverage_handler: Callable[[list[str], dict[str, Any]], Any],
) -> Callable[..., Any]:
    def _side_effect(argv: list[str], *_args: Any, **kwargs: Any) -> Any:
        if argv == ["git", "rev-parse", "--show-toplevel"]:
            completed = MagicMock(name="CompletedProcess-git-toplevel")
            completed.returncode = 0
            completed.stdout = str(repo_root) + "\n"
            return completed
        if argv[:2] in (["git", "rev-parse"], ["git", "status"]):
            completed = MagicMock(name="CompletedProcess-git-other")
            completed.returncode = 1
            completed.stdout = ""
            return completed
        return coverage_handler(argv, kwargs)

    return _side_effect


def _timeout_handler(argv: list[str], kwargs: dict[str, Any]) -> Any:
    raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout"))


def _unreachable_coverage_handler(argv: list[str], _kwargs: dict[str, Any]) -> Any:
    raise AssertionError(
        "coverage-target subprocess.run must not be invoked when no coverage "
        f"target is discoverable (or --refresh-coverage was not passed); "
        f"got called with argv={argv!r}"
    )


def _success_handler(coverage_xml: Path, *, bump_seconds: float = 5.0) -> Callable[..., Any]:
    def _handler(_argv: list[str], _kwargs: dict[str, Any]) -> Any:
        stat = coverage_xml.stat()
        new_mtime = stat.st_mtime + bump_seconds
        os.utime(coverage_xml, (new_mtime, new_mtime))
        completed = MagicMock(name="CompletedProcess-coverage-success")
        completed.returncode = 0
        return completed

    return _handler


def _recording_success_handler(
    calls: list[tuple[list[str], dict[str, Any]]],
) -> Callable[..., Any]:
    def _handler(argv: list[str], kwargs: dict[str, Any]) -> Any:
        calls.append((argv, kwargs))
        completed = MagicMock(name="CompletedProcess-coverage-recorded")
        completed.returncode = 0
        return completed

    return _handler


# ---------------------------------------------------------------------------
# Fixture-repo builders.
# ---------------------------------------------------------------------------


def _write_coverage_discoverable_pyproject(repo_root: Path) -> None:
    """Write a ``pyproject.toml`` that makes a coverage target discoverable.

    A ``[tool.coverage.run]`` section is the cheapest hit in
    ``_discover_coverage_target``'s probe order (ahead of the
    dependency-manifest and Makefile probes), and it does not depend on
    ``uv.lock`` being present, so the resolved target is deterministically
    ``["pytest"]`` regardless of the host's toolchain.
    """

    (repo_root / "pyproject.toml").write_text(
        '[tool.coverage.run]\nsource = ["scripts"]\n',
        encoding="utf-8",
    )


def _write_coverage_xml(repo_root: Path, *, age_seconds: float = 3600.0) -> Path:
    """Write a ``coverage.xml`` with a known, deliberately-stale mtime."""

    artifact = repo_root / "coverage.xml"
    artifact.write_text("<coverage/>\n", encoding="utf-8")
    past = time.time() - age_seconds
    os.utime(artifact, (past, past))
    return artifact


def _mtime_close(value: Any, expected_epoch: float, *, tolerance_seconds: float = 5.0) -> bool:
    """Return True when ``value`` (epoch float or ISO-8601 string) resolves
    close to ``expected_epoch``. Lenient on representation, strict on the
    underlying timestamp -- the field must be the artifact's own mtime, not
    "now" or some other run-time clock reading."""

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        candidate = float(value)
    elif isinstance(value, str):
        from datetime import datetime as _dt

        try:
            candidate = _dt.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return False
    else:
        return False
    return abs(candidate - expected_epoch) <= tolerance_seconds


def _run_main_and_read_latest_report(
    argv: list[str], repo_root: Path
) -> tuple[int, dict[str, Any], str]:
    from scripts.project_metrics.cli import main

    exit_code = main(argv)

    reports_dir = repo_root / ".ai-state" / "metrics_reports"
    json_files = sorted(reports_dir.glob("METRICS_REPORT_*.json"))
    md_files = sorted(reports_dir.glob("METRICS_REPORT_*.md"))
    assert json_files, f"main() did not write a METRICS_REPORT_*.json under {reports_dir}"
    assert md_files, f"main() did not write a METRICS_REPORT_*.md under {reports_dir}"
    payload = json.loads(json_files[-1].read_text(encoding="utf-8"))
    md_text = md_files[-1].read_text(encoding="utf-8")
    return exit_code, payload, md_text


# ---------------------------------------------------------------------------
# --coverage-timeout: argparse surface, default bound, and value threading.
# ---------------------------------------------------------------------------


class TestCoverageTimeoutIsConfigurable:
    """The 600s ``_COVERAGE_INVOKE_TIMEOUT_SECONDS`` bound becomes an
    overridable, sensibly-raised CLI option."""

    def test_help_output_advertises_coverage_timeout_flag(self) -> None:
        from scripts.project_metrics.cli import _build_parser

        help_text = _build_parser().format_help()
        assert "--coverage-timeout" in help_text, (
            "Help output must advertise --coverage-timeout so operators can "
            "raise the bound above the suite's 8-11 minute runtime without "
            f"reading source. format_help() returned:\n{help_text}"
        )

    def test_default_timeout_exceeds_the_suites_worst_case_duration(self, tmp_path: Path) -> None:
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        _write_coverage_discoverable_pyproject(tmp_path)
        _write_coverage_xml(tmp_path)

        mocks, patchers = _install_partial_cli_mocks(repo_root=tmp_path)
        recorded: list[tuple[list[str], dict[str, Any]]] = []
        mocks.subprocess_run.side_effect = _make_subprocess_side_effect(
            tmp_path, _recording_success_handler(recorded)
        )
        try:
            for p in patchers:
                p.start()
            from scripts.project_metrics.cli import main

            main(["--refresh-coverage", "--window-days", "90", "--top-n", "10"])
        finally:
            for p in patchers:
                p.stop()

        assert recorded, "The coverage-target subprocess.run call was never made."
        _, kwargs = recorded[0]
        timeout_used = kwargs.get("timeout")
        assert timeout_used is not None, (
            "_refresh_coverage_artifact must pass an explicit timeout= to "
            "subprocess.run; got no timeout kwarg at all."
        )
        assert timeout_used > 660, (
            "The default coverage-refresh timeout must sit comfortably above "
            "the suite's observed 8-11 minute (<=660s) runtime; got "
            f"{timeout_used}s, which would abort a normal run before it "
            "finishes."
        )

    def test_flag_value_is_threaded_into_the_refresh_subprocess_call(self, tmp_path: Path) -> None:
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        _write_coverage_discoverable_pyproject(tmp_path)
        _write_coverage_xml(tmp_path)

        mocks, patchers = _install_partial_cli_mocks(repo_root=tmp_path)
        recorded: list[tuple[list[str], dict[str, Any]]] = []
        mocks.subprocess_run.side_effect = _make_subprocess_side_effect(
            tmp_path, _recording_success_handler(recorded)
        )
        try:
            for p in patchers:
                p.start()
            from scripts.project_metrics.cli import main

            main(
                [
                    "--refresh-coverage",
                    "--coverage-timeout",
                    "30",
                    "--window-days",
                    "90",
                    "--top-n",
                    "10",
                ]
            )
        finally:
            for p in patchers:
                p.stop()

        assert recorded, "The coverage-target subprocess.run call was never made."
        _, kwargs = recorded[0]
        assert kwargs.get("timeout") == 30, (
            "--coverage-timeout 30 must be threaded through to "
            "_refresh_coverage_artifact's subprocess.run(..., timeout=30); "
            f"got timeout={kwargs.get('timeout')!r}."
        )


# ---------------------------------------------------------------------------
# Staleness marking: the composed report and its rendered Markdown must
# never present a not-actually-refreshed artifact as current.
# ---------------------------------------------------------------------------


class TestCoverageRefreshStalenessMarking:
    """AC-10/REQ-10: a refresh that does not produce a trustworthy fresh
    ``coverage.xml`` must mark the report accordingly -- never silently."""

    def test_timed_out_refresh_marks_the_report_stale_with_timed_out_reason(
        self, tmp_path: Path
    ) -> None:
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        _write_coverage_discoverable_pyproject(tmp_path)
        artifact = _write_coverage_xml(tmp_path)
        pre_attempt_mtime = artifact.stat().st_mtime

        mocks, patchers = _install_partial_cli_mocks(repo_root=tmp_path)
        mocks.subprocess_run.side_effect = _make_subprocess_side_effect(tmp_path, _timeout_handler)
        try:
            for p in patchers:
                p.start()
            exit_code, payload, md_text = _run_main_and_read_latest_report(
                ["--refresh-coverage", "--window-days", "90", "--top-n", "10"],
                tmp_path,
            )
        finally:
            for p in patchers:
                p.stop()

        assert exit_code == 0, (
            f"A refresh timeout must not hard-fail /project-metrics; got exit {exit_code}."
        )
        assert payload.get("coverage_refresh") == "timed-out", (
            "A refresh subprocess that raised subprocess.TimeoutExpired must "
            "mark the report coverage_refresh == 'timed-out', not silently "
            f"present the pre-existing artifact as current. Got: "
            f"{payload.get('coverage_refresh')!r}."
        )
        recorded_mtime = payload.get("coverage_artifact_mtime")
        assert recorded_mtime is not None, (
            "The report must carry the artifact's own mtime (captured before "
            "the refresh attempt) so a consumer can independently judge "
            "staleness; got no coverage_artifact_mtime field."
        )
        assert _mtime_close(recorded_mtime, pre_attempt_mtime), (
            "coverage_artifact_mtime must reflect the artifact's own "
            f"pre-refresh-attempt mtime (epoch {pre_attempt_mtime}); got "
            f"{recorded_mtime!r}, which does not resolve to a close timestamp."
        )
        assert "stale" in md_text.lower(), (
            "The rendered Markdown must name the coverage figures stale in "
            f"human-readable prose. Markdown did not mention 'stale':\n"
            f"{md_text[:2000]}"
        )

    def test_no_target_discoverable_marks_the_report_failed(self, tmp_path: Path) -> None:
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        # Deliberately no pyproject.toml / pixi.toml / Makefile -- no coverage
        # target is discoverable, so _refresh_coverage_artifact raises before
        # ever invoking subprocess.run for a coverage command.
        _write_coverage_xml(tmp_path)

        mocks, patchers = _install_partial_cli_mocks(repo_root=tmp_path)
        mocks.subprocess_run.side_effect = _make_subprocess_side_effect(
            tmp_path, _unreachable_coverage_handler
        )
        try:
            for p in patchers:
                p.start()
            exit_code, payload, md_text = _run_main_and_read_latest_report(
                ["--refresh-coverage", "--window-days", "90", "--top-n", "10"],
                tmp_path,
            )
        finally:
            for p in patchers:
                p.stop()

        assert exit_code == 0, (
            f"A refresh failure must not hard-fail /project-metrics; got exit {exit_code}."
        )
        assert payload.get("coverage_refresh") == "failed", (
            "A refresh that raised for a non-timeout reason (here: no "
            "discoverable coverage target) must mark coverage_refresh == "
            f"'failed'. Got: {payload.get('coverage_refresh')!r}."
        )
        assert "stale" in md_text.lower(), (
            "The rendered Markdown must name the coverage figures stale in "
            f"human-readable prose. Markdown did not mention 'stale':\n"
            f"{md_text[:2000]}"
        )

    def test_successful_refresh_marks_the_report_fresh(self, tmp_path: Path) -> None:
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        _write_coverage_discoverable_pyproject(tmp_path)
        artifact = _write_coverage_xml(tmp_path)

        mocks, patchers = _install_partial_cli_mocks(repo_root=tmp_path)
        mocks.subprocess_run.side_effect = _make_subprocess_side_effect(
            tmp_path, _success_handler(artifact)
        )
        try:
            for p in patchers:
                p.start()
            exit_code, payload, md_text = _run_main_and_read_latest_report(
                ["--refresh-coverage", "--window-days", "90", "--top-n", "10"],
                tmp_path,
            )
        finally:
            for p in patchers:
                p.stop()

        assert exit_code == 0
        assert payload.get("coverage_refresh") == "fresh", (
            "A successful refresh (returncode 0, artifact mtime advanced) "
            f"must mark coverage_refresh == 'fresh'. Got: "
            f"{payload.get('coverage_refresh')!r}."
        )
        assert "stale" not in md_text.lower(), (
            "A successful refresh must not carry a staleness marker in the "
            f"rendered Markdown. Found 'stale' in:\n{md_text[:2000]}"
        )


class TestDefaultPathCarriesNoStalenessMarker:
    """Without ``--refresh-coverage``, no refresh was attempted -- the report
    must not claim any freshness state at all."""

    def test_absent_flag_report_has_no_coverage_refresh_field(self, tmp_path: Path) -> None:
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_partial_cli_mocks(repo_root=tmp_path)
        mocks.subprocess_run.side_effect = _make_subprocess_side_effect(
            tmp_path, _unreachable_coverage_handler
        )
        try:
            for p in patchers:
                p.start()
            exit_code, payload, _md_text = _run_main_and_read_latest_report(
                ["--window-days", "90", "--top-n", "10"],
                tmp_path,
            )
        finally:
            for p in patchers:
                p.stop()

        assert exit_code == 0
        assert payload.get("coverage_refresh") is None, (
            "Without --refresh-coverage no refresh was attempted, so the "
            "report must not claim any freshness state at all -- absent, "
            f"not 'fresh'. Got: {payload.get('coverage_refresh')!r}."
        )
