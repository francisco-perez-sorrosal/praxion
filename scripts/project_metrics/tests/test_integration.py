"""End-to-end integration tests for the ``/project-metrics`` pipeline.

Each test invokes :func:`scripts.project_metrics.cli.main` directly against a
fixture repository copied into ``tmp_path``. The CLI resolves its repo-root
via ``git rev-parse --show-toplevel`` on the current working directory, so
the tests ``monkeypatch.chdir`` into the copied fixture to redirect every
write under the fixture's ``.ai-state/`` — there is no ``--ai-state-dir``
CLI flag, and this keeps the production code untouched by test-only plumbing.

Fixture isolation:
    ``shutil.copytree`` duplicates the fixture repo (git history + working
    tree) into ``tmp_path`` so the session-scoped committed fixtures at
    ``scripts/project_metrics/tests/fixtures/`` are never mutated by a test
    run. Pytest's ``tmp_path`` cleanup takes care of removal.

Timestamp determinism:
    The pipeline stamps ``aggregate.timestamp`` inside the runner
    (``scripts.project_metrics.runner.datetime``) and derives report
    filenames from ``scripts.project_metrics.cli.datetime``. Two back-to-back
    runs can collide on a single-second ``strftime``, and the trend module
    selects priors by embedded ``aggregate.timestamp``. Both sites are
    patched with ``unittest.mock.patch`` to yield deterministic values for
    the two-run delta scenario.

PATH manipulation:
    The stdlib-only scenario rebuilds ``PATH`` to ``/usr/bin:/bin`` so
    optional tools (``scc``, ``uvx``, ``npx``) resolve as ``Unavailable``
    while ``git`` + ``python3`` remain visible via the system install.
    The interpreter's own bin dir is deliberately excluded — in a pyenv
    environment ``uvx`` co-locates with ``python3`` and would be re-exposed.
    ``shutil.which`` does not cache results, so
    ``monkeypatch.setenv("PATH", ...)`` at test start is sufficient.

The integration surface here validates that the composition layers
(runner / hotspot / trends / report / logappend) wire together correctly
end-to-end. Unit-level invariants of each layer are verified in their own
test modules; this file only asserts composition behavior that cannot be
reached from a single-module test.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from scripts.project_metrics.cli import main
from scripts.project_metrics.schema import AGGREGATE_COLUMNS

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def _copy_fixture(fixture_name: str, destination: Path) -> Path:
    """Copy a committed fixture repository tree into ``destination``.

    The source tree (under ``scripts/project_metrics/tests/fixtures/<name>/``)
    includes a real ``.git/`` directory that the session-autouse builder
    populates. Using ``shutil.copytree`` with ``symlinks=True`` preserves git
    internals byte-for-byte so ``git rev-parse`` on the copy returns the
    same SHA as the source.
    """

    source = _FIXTURES_DIR / fixture_name
    target = destination / fixture_name
    shutil.copytree(source, target, symlinks=True)
    return target


def _read_report_json(ai_state_dir: Path) -> dict[str, Any]:
    """Return the parsed JSON for the single ``METRICS_REPORT_*.json`` file."""

    candidates = sorted(ai_state_dir.glob("METRICS_REPORT_*.json"))
    assert len(candidates) == 1, (
        f"Expected exactly one METRICS_REPORT_*.json under {ai_state_dir}; "
        f"found {[p.name for p in candidates]}"
    )
    return json.loads(candidates[0].read_text(encoding="utf-8"))


def _read_all_report_jsons(ai_state_dir: Path) -> list[dict[str, Any]]:
    """Return all ``METRICS_REPORT_*.json`` files sorted by filename."""

    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(ai_state_dir.glob("METRICS_REPORT_*.json"))
    ]


def _read_report_md(ai_state_dir: Path) -> str:
    """Return the single ``METRICS_REPORT_*.md`` file contents."""

    candidates = sorted(ai_state_dir.glob("METRICS_REPORT_*.md"))
    assert len(candidates) >= 1, (
        f"Expected at least one METRICS_REPORT_*.md under {ai_state_dir}; found none"
    )
    # Most-recent by filename ordering — suffices since the timestamp prefix
    # is lexically ordered.
    return candidates[-1].read_text(encoding="utf-8")


def _build_fake_datetime(fixed_strftime: str, fixed_iso: str) -> MagicMock:
    """Build a MagicMock that mimics :class:`datetime.datetime` for patching.

    ``fixed_strftime`` is returned by ``datetime.now(UTC).strftime(...)`` —
    the CLI uses this to build report filenames.
    ``fixed_iso`` is returned by ``datetime.now(timezone.utc).isoformat()`` —
    the runner stamps this on ``aggregate.timestamp``.
    """

    dt_module = MagicMock(name="fake_datetime_module")
    now_mock = MagicMock(name="fake_datetime_now")
    now_mock.strftime.return_value = fixed_strftime
    now_mock.isoformat.return_value = fixed_iso
    dt_module.now.return_value = now_mock
    return dt_module


# ---------------------------------------------------------------------------
# Scenario 1 — full pipeline on minimal_repo (happy path).
# ---------------------------------------------------------------------------


def test_full_pipeline_on_minimal_repo_produces_three_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invoking ``main`` against ``minimal_repo`` produces the expected
    artifact triple (JSON + MD + log), and the JSON payload matches the
    frozen schema contract."""

    repo_copy = _copy_fixture("minimal_repo", tmp_path)
    monkeypatch.chdir(repo_copy)

    exit_code = main(["--window-days", "30", "--top-n", "5"])

    assert exit_code == 0, (
        f"CLI must exit 0 on the minimal_repo happy path; got {exit_code}"
    )
    ai_state = repo_copy / ".ai-state"
    assert ai_state.is_dir(), "CLI must create .ai-state/ under the repo root"

    json_files = sorted(ai_state.glob("METRICS_REPORT_*.json"))
    md_files = sorted(ai_state.glob("METRICS_REPORT_*.md"))
    log_file = ai_state / "METRICS_LOG.md"

    assert len(json_files) == 1, (
        f"Expected exactly 1 JSON report; found {[p.name for p in json_files]}"
    )
    assert len(md_files) == 1, (
        f"Expected exactly 1 MD report; found {[p.name for p in md_files]}"
    )
    assert log_file.is_file(), "METRICS_LOG.md must be written on happy path"

    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert "aggregate" in payload, "JSON payload must carry an 'aggregate' block"
    assert set(payload["aggregate"].keys()) == set(AGGREGATE_COLUMNS), (
        f"aggregate keys must equal AGGREGATE_COLUMNS exactly; "
        f"got {sorted(payload['aggregate'].keys())!r}, "
        f"expected {sorted(AGGREGATE_COLUMNS)!r}"
    )

    log_content = log_file.read_text(encoding="utf-8")
    log_lines = [line for line in log_content.splitlines() if line.strip()]
    assert len(log_lines) == 3, (
        "METRICS_LOG.md must contain a 2-line header (header + separator) "
        f"plus one data row; got {len(log_lines)} lines:\n{log_content!r}"
    )


# ---------------------------------------------------------------------------
# Scenario 2 — stdlib-only path (optional tools hidden from PATH).
# ---------------------------------------------------------------------------


def test_pipeline_completes_when_optional_tools_are_hidden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With ``scc``, ``uvx``, ``npx`` hidden from ``PATH``, the pipeline
    still produces the three artifacts and the MD renders ``_not computed_``
    markers for optional collectors."""

    repo_copy = _copy_fixture("minimal_stdlib_repo", tmp_path)
    monkeypatch.chdir(repo_copy)

    # Rebuild PATH to contain only system dirs — ``/usr/bin`` exposes ``git``
    # and ``python3`` on macOS + most Linuxes, while excluding ``uvx`` /
    # ``scc`` / ``npx`` which typically live under user-local paths
    # (``~/.local/bin``, ``~/.pyenv/versions/*/bin``, ``~/.cargo/bin``, etc.).
    # Deliberately do NOT append the running interpreter's bin directory —
    # in a pyenv-managed environment uvx ships inside the same ``python3``
    # bin dir and would be re-exposed, defeating the stdlib-only premise.
    minimal_path = os.pathsep.join(["/usr/bin", "/bin"])
    monkeypatch.setenv("PATH", minimal_path)

    exit_code = main(["--window-days", "30", "--top-n", "5"])

    assert exit_code == 0, (
        f"Pipeline must complete even when optional tools are absent; "
        f"got exit {exit_code}"
    )

    ai_state = repo_copy / ".ai-state"
    json_files = sorted(ai_state.glob("METRICS_REPORT_*.json"))
    md_files = sorted(ai_state.glob("METRICS_REPORT_*.md"))
    log_file = ai_state / "METRICS_LOG.md"
    assert len(json_files) == 1, "JSON report must be produced"
    assert len(md_files) == 1, "MD report must be produced"
    assert log_file.is_file(), "METRICS_LOG.md must be produced"

    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    tool_availability = payload.get("tool_availability", {})
    # Every optional collector must appear in tool_availability — the
    # graceful-degradation ADR requires per-tool resolution outcome for
    # every registered collector, not just the ones that resolved.
    optional_collectors = ("scc", "lizard", "complexipy", "pydeps", "coverage")
    for name in optional_collectors:
        assert name in tool_availability, (
            f"tool_availability must contain an entry for '{name}' even when "
            f"the tool is unavailable; got keys {sorted(tool_availability.keys())!r}"
        )
        status = tool_availability[name].get("status")
        assert status != "available", (
            f"'{name}' must NOT resolve as 'available' when its tool is hidden "
            f"from PATH; got status={status!r}"
        )

    md_content = md_files[0].read_text(encoding="utf-8")
    assert "_not computed" in md_content, (
        "MD report must contain at least one '_not computed — ...' skip marker "
        "when optional collectors are unavailable"
    )


# ---------------------------------------------------------------------------
# Scenario 3 — shipped-artifact isolation check across the feature surface.
# ---------------------------------------------------------------------------


def test_shipped_artifact_isolation_passes_on_feature_surface() -> None:
    """The feature's shipped surfaces (command file) must not reference
    project-specific ``.ai-state/`` or ``.ai-work/`` entries."""

    # Only include paths that actually fall under SHIPPED_ROOTS
    # (commands/, rules/, skills/, agents/, claude/config/).
    # Docs and scripts are out of scope per SHIPPED_ROOTS (see
    # scripts/check_shipped_artifact_isolation.py).
    script = _REPO_ROOT / "scripts" / "check_shipped_artifact_isolation.py"
    command_file = _REPO_ROOT / "commands" / "project-metrics.md"
    completed = subprocess.run(
        [sys.executable, str(script), "--files", str(command_file)],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, (
        "Shipped-artifact isolation check must pass on commands/project-metrics.md; "
        f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Scenario 4 — second run computes a delta against the first.
# ---------------------------------------------------------------------------


def test_second_run_computes_delta_against_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two back-to-back runs on the same fixture produce a computed trend
    block on the second run, and the MD carries a delta table."""

    repo_copy = _copy_fixture("minimal_repo", tmp_path)
    monkeypatch.chdir(repo_copy)

    # Run 1 — stamp with an earlier timestamp so it is lexically + ISO
    # comparable as "prior" to the second run.
    run1_dt = _build_fake_datetime(
        fixed_strftime="2026-04-23_10-00-00",
        fixed_iso="2026-04-23T10:00:00+00:00",
    )
    with (
        patch("scripts.project_metrics.cli.datetime", run1_dt),
        patch("scripts.project_metrics.runner.datetime", run1_dt),
    ):
        exit_code_run1 = main(["--window-days", "30", "--top-n", "5"])
    assert exit_code_run1 == 0, f"First run must succeed; got {exit_code_run1}"

    # Run 2 — later timestamp; the trend layer should discover run 1 as prior.
    run2_dt = _build_fake_datetime(
        fixed_strftime="2026-04-23_11-00-00",
        fixed_iso="2026-04-23T11:00:00+00:00",
    )
    with (
        patch("scripts.project_metrics.cli.datetime", run2_dt),
        patch("scripts.project_metrics.runner.datetime", run2_dt),
    ):
        exit_code_run2 = main(["--window-days", "30", "--top-n", "5"])
    assert exit_code_run2 == 0, f"Second run must succeed; got {exit_code_run2}"

    ai_state = repo_copy / ".ai-state"
    payloads = _read_all_report_jsons(ai_state)
    assert len(payloads) == 2, (
        f"Two runs must produce two JSON files; found {len(payloads)}"
    )

    # The second-run JSON is the most recent by filename ordering.
    second = payloads[-1]
    trends = second.get("trends", {})
    # NOTE: implementation uses "computed" for the normal delta branch;
    # task-prompt prose referencing "normal" is plan-drift from the actual
    # TrendBlock status vocabulary (first_run / schema_mismatch / computed /
    # no_prior_readable) defined in scripts/project_metrics/trends.py.
    assert trends.get("status") == "computed", (
        f"Second run must yield trends.status == 'computed'; "
        f"got {trends.get('status')!r}. Full trends block: {trends!r}"
    )

    md_content = _read_report_md(ai_state)
    assert "| Metric | Current | Prior | Delta | Delta % |" in md_content, (
        "Second-run MD must render the computed-delta table header; "
        f"got MD:\n{md_content!r}"
    )


# ---------------------------------------------------------------------------
# Scenario 5 — schema mismatch when the prior report uses an older schema.
# ---------------------------------------------------------------------------


def test_schema_mismatch_surfaced_when_prior_report_has_older_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-seeded prior report with schema ``0.9.0`` triggers the
    ``schema_mismatch`` trend branch on the current run."""

    repo_copy = _copy_fixture("minimal_repo", tmp_path)
    monkeypatch.chdir(repo_copy)

    ai_state = repo_copy / ".ai-state"
    ai_state.mkdir(parents=True, exist_ok=True)

    # Plant a prior report whose schema is older than the current. Every
    # aggregate column present so trends.py does not reject it as
    # no_prior_readable.
    prior_aggregate = {
        "schema_version": "0.9.0",
        "timestamp": "2026-04-22T10:00:00+00:00",
        "commit_sha": "0" * 40,
        "window_days": 30,
        "sloc_total": 0,
        "file_count": 0,
        "language_count": 0,
        "ccn_p95": None,
        "cognitive_p95": None,
        "cyclic_deps": None,
        "churn_total_90d": 0,
        "change_entropy_90d": 0.0,
        "truck_factor": 0,
        "hotspot_top_score": 0.0,
        "hotspot_gini": 0.0,
        "coverage_line_pct": None,
    }
    prior_payload = {
        "schema_version": "0.9.0",
        "aggregate": prior_aggregate,
        "tool_availability": {},
        "collectors": {},
    }
    prior_path = ai_state / "METRICS_REPORT_2026-04-22_10-00-00.json"
    prior_path.write_text(json.dumps(prior_payload, sort_keys=True), encoding="utf-8")

    exit_code = main(["--window-days", "30", "--top-n", "5"])
    assert exit_code == 0, f"Pipeline must still succeed; got {exit_code}"

    # The just-written report carries the CURRENT schema; pick the newest
    # file that is NOT the planted prior.
    current_candidates = [
        p
        for p in sorted(ai_state.glob("METRICS_REPORT_*.json"))
        if p.name != prior_path.name
    ]
    assert len(current_candidates) == 1, (
        "A single new JSON report must be written alongside the planted prior; "
        f"found additional candidates: {[p.name for p in current_candidates]}"
    )
    current_payload = json.loads(current_candidates[0].read_text(encoding="utf-8"))
    trends = current_payload.get("trends", {})
    assert trends.get("status") == "schema_mismatch", (
        f"Older prior schema must yield trends.status == 'schema_mismatch'; "
        f"got {trends.get('status')!r}. Full trends: {trends!r}"
    )
    # Diagnostic fields should identify both versions for the reader.
    assert trends.get("prior_schema") == "0.9.0", (
        f"trends.prior_schema must surface the prior's version; "
        f"got {trends.get('prior_schema')!r}"
    )
    assert trends.get("current_schema", "").startswith("1."), (
        f"trends.current_schema must surface the current version; "
        f"got {trends.get('current_schema')!r}"
    )


# ---------------------------------------------------------------------------
# Self-check — the committed fixture directory names are what we expect.
# Guards against a rename that would make copy_fixture silently crash.
# ---------------------------------------------------------------------------


def test_integration_fixtures_are_buildable() -> None:
    """Sanity check: every fixture directory this module references exists
    on disk after the session-autouse builder runs."""

    for fixture_name in ("minimal_repo", "minimal_stdlib_repo"):
        target = _FIXTURES_DIR / fixture_name
        assert (target / ".git").is_dir(), (
            f"Fixture '{fixture_name}' at {target} must contain a built "
            ".git/ directory (session-autouse builder should have run)"
        )
