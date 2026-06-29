"""Tests for check_readiness_feedback.py -- readiness-feedback detector.

Gate-liveness contract (rules/swe/gate-liveness.md): this is a CODE gate
detecting a below-floor agent-readiness level (adjusted_level < 3). It ships
canaries — tests that feed a known-bad JSON with adjusted_level: 2 and assert
the gate bites (exit 1 / below_threshold: true). A detector that only passes
when the level is acceptable is indistinguishable from no gate.

All tests are hermetic: each builds a temporary directory tree with an injected
.ai-state/metrics_reports/ directory containing a synthetic METRICS_REPORT_*.json.
The real Praxion metrics reports are never read; both the failing and the passing
states are exercised via injected fixtures.

Import strategy: deferred per-test-body via importlib.util so pytest collection
succeeds before the module exists (BDD/TDD concurrent-execution RED handshake).
Each test fails individually with FileNotFoundError until the implementation lands.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parent / "check_readiness_feedback.py"

# Minimal METRICS_REPORT_*.json shape with a readiness block.
_REPORT_FILENAME = "METRICS_REPORT_2026-01-15_12-00-00.json"


# -- Module loading -----------------------------------------------------------


def _load_module() -> Any:
    """Load check_readiness_feedback.py without requiring it on sys.path."""
    sys.modules.pop("check_readiness_feedback", None)
    spec = importlib.util.spec_from_file_location("check_readiness_feedback", _SCRIPT_PATH)
    assert spec is not None, f"Could not locate {_SCRIPT_PATH} — the detector script must exist"
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_readiness_feedback"] = mod
    spec.loader.exec_module(mod)
    return mod


# -- Fixture helpers ----------------------------------------------------------


def _write_report(tmp_path: Path, readiness_data: dict[str, object]) -> Path:
    """Write a synthetic metrics report to tmp_path/.ai-state/metrics_reports/."""
    reports_dir = tmp_path / ".ai-state" / "metrics_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = {"readiness": {"data": readiness_data}, "status": "ok"}
    report_path = reports_dir / _REPORT_FILENAME
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return report_path


# -- Tests --------------------------------------------------------------------


def test_canary_below_floor_level_2_bites(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Gate-liveness canary: adjusted_level=2 must set below_threshold=true and exit 1 with --check.

    This is the CODE-gate liveness proof. A gate that never fires on a known-bad
    input is indistinguishable from no gate (rules/swe/gate-liveness.md).
    The fixture represents Praxion's own disk state (adjusted_level=2, mechanical-only).
    """
    _write_report(tmp_path, {"adjusted_level": 2, "level": 2, "note": "mechanical-only"})

    mod = _load_module()
    with pytest.raises(SystemExit) as exc:
        mod.main(["--repo-root", str(tmp_path), "--check"])

    assert (
        exc.value.code == 1
    ), "adjusted_level=2 (< floor 3) must set below_threshold=true and --check must exit 1"


def test_canary_json_output_below_threshold_true(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Gate-liveness canary: --json output must have below_threshold=true for level 2."""
    _write_report(tmp_path, {"adjusted_level": 2, "level": 2, "note": "mechanical-only"})

    mod = _load_module()
    with pytest.raises(SystemExit):
        mod.main(["--repo-root", str(tmp_path), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert (
        payload["below_threshold"] is True
    ), "adjusted_level=2 (< floor 3) must produce below_threshold: true in JSON output"
    assert payload["adjusted_level"] == 2
    assert payload["threshold"] == 3


def test_no_false_positive_at_floor_level_3(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No-false-positive control: adjusted_level=3 (at floor) must not flag below_threshold.

    Level 3 is the Practiced floor — the gate must not fire when the project
    meets or exceeds the production threshold.
    """
    _write_report(tmp_path, {"adjusted_level": 3, "level": 3})

    mod = _load_module()
    with pytest.raises(SystemExit) as exc:
        mod.main(["--repo-root", str(tmp_path), "--check"])

    assert (
        exc.value.code == 0
    ), "adjusted_level=3 (at floor) must not trigger below_threshold — no false positive"


def test_no_false_positive_above_floor_level_4(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No-false-positive control: adjusted_level=4 (above floor) must exit 0."""
    _write_report(tmp_path, {"adjusted_level": 4, "level": 4})

    mod = _load_module()
    with pytest.raises(SystemExit) as exc:
        mod.main(["--repo-root", str(tmp_path), "--check"])

    assert exc.value.code == 0, "adjusted_level=4 (above floor) must not trigger below_threshold"


def test_substrate_absent_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Absent metrics_reports/ triggers skip-with-INFO, not a below_threshold flag.

    Conditional-activation: a project that has never run /project-metrics has no
    readiness signal. The detector must exit 0 (INFO note only) — no false-positive.
    """
    # Do NOT create .ai-state/metrics_reports/ — substrate is absent.

    mod = _load_module()
    with pytest.raises(SystemExit) as exc:
        mod.main(["--repo-root", str(tmp_path), "--check"])

    assert (
        exc.value.code == 0
    ), "Absent metrics_reports/ must exit 0 (skip-with-INFO) — no substrate means no verdict"


def test_substrate_absent_json_shows_null_level(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Absent substrate: --json output must show adjusted_level=null and below_threshold=false."""
    mod = _load_module()
    with pytest.raises(SystemExit):
        mod.main(["--repo-root", str(tmp_path), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["below_threshold"] is False
    assert payload["adjusted_level"] is None


def test_mechanical_only_annotation_in_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """mechanical_only=true is set when note='mechanical-only' and level is below threshold."""
    _write_report(tmp_path, {"adjusted_level": 2, "level": 2, "note": "mechanical-only"})

    mod = _load_module()
    with pytest.raises(SystemExit):
        mod.main(["--repo-root", str(tmp_path), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert (
        payload["mechanical_only"] is True
    ), "note='mechanical-only' must set mechanical_only=true in the JSON output"
    assert payload["note"] == "mechanical-only"
    # The details text must mention the mechanical-only annotation.
    assert (
        "mechanical-only" in payload["details"].lower() or "mechanical" in payload["details"]
    ), "finding details must annotate the mechanical-only verdict"


def test_mechanical_only_false_when_note_differs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """mechanical_only=false when note is absent or has a different value.

    Strict equality check — 'note' must equal the exact string 'mechanical-only'.
    """
    _write_report(tmp_path, {"adjusted_level": 2, "level": 2, "note": "some-other-note"})

    mod = _load_module()
    with pytest.raises(SystemExit):
        mod.main(["--repo-root", str(tmp_path), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert (
        payload["mechanical_only"] is False
    ), "note='some-other-note' (not 'mechanical-only') must leave mechanical_only=false"


def test_fallback_to_level_when_adjusted_level_absent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fallback path: when adjusted_level is absent, detector uses readiness.data.level.

    The fallback ensures older reports (before adjusted_level was added) still trigger
    the gate correctly when level < 3.
    """
    # JSON only has 'level', no 'adjusted_level'.
    _write_report(tmp_path, {"level": 2})

    mod = _load_module()
    with pytest.raises(SystemExit) as exc:
        mod.main(["--repo-root", str(tmp_path), "--check"])

    assert (
        exc.value.code == 1
    ), "Fallback to readiness.data.level=2 (< 3) must still trigger below_threshold"


def test_fallback_level_no_false_positive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fallback path: readiness.data.level=3 (no adjusted_level) must exit 0."""
    _write_report(tmp_path, {"level": 3})

    mod = _load_module()
    with pytest.raises(SystemExit) as exc:
        mod.main(["--repo-root", str(tmp_path), "--check"])

    assert exc.value.code == 0, "Fallback readiness.data.level=3 must not trigger below_threshold"


def test_plugin_cache_refusal(tmp_path: Path) -> None:
    """Plugin-cache path must exit 2 without reading any report."""
    _write_report(tmp_path, {"adjusted_level": 2, "level": 2})

    mod = _load_module()
    with patch.object(mod, "is_plugin_cache_path", return_value=True):
        with pytest.raises(SystemExit) as exc:
            mod.main(["--repo-root", str(tmp_path)])

    assert (
        exc.value.code == 2
    ), "Plugin-cache path must exit 2 (refusal) to protect shared plugin state"


def test_latest_report_resolved_by_filename_sort(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Chronological filename sort: the lexicographically newest file is used, not mtime.

    Creates two reports: an older one (level=2) and a newer one (level=3).
    The detector must read the newer file and exit 0.
    """
    reports_dir = tmp_path / ".ai-state" / "metrics_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Older report (bad: level 2) — sorts first alphabetically.
    old_report = {"readiness": {"data": {"adjusted_level": 2, "level": 2}}, "status": "ok"}
    (reports_dir / "METRICS_REPORT_2026-01-01_00-00-00.json").write_text(
        json.dumps(old_report), encoding="utf-8"
    )

    # Newer report (good: level 3) — sorts last alphabetically.
    new_report = {"readiness": {"data": {"adjusted_level": 3, "level": 3}}, "status": "ok"}
    (reports_dir / "METRICS_REPORT_2026-06-01_00-00-00.json").write_text(
        json.dumps(new_report), encoding="utf-8"
    )

    mod = _load_module()
    with pytest.raises(SystemExit) as exc:
        mod.main(["--repo-root", str(tmp_path), "--check"])

    assert (
        exc.value.code == 0
    ), "Must read the newest file (level=3) by filename sort, not the older file (level=2)"
