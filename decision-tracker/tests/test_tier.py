"""Tests for decision_tracker.tier — tier detection from filesystem signals."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from decision_tracker.tier import detect_tier, is_gating_tier

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CALIBRATION_HEADER = (
    "| timestamp | task | signals | recommended tier | actual tier | source | retrospective |"
)
CALIBRATION_SEPARATOR = "|---|---|---|---|---|---|---|"


def _write_calibration_log(
    tmp_path: Path,
    tier: str,
    timestamp: datetime,
) -> Path:
    """Create a calibration_log.md with one data row."""
    log_dir = tmp_path / ".ai-state"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "calibration_log.md"
    ts = timestamp.isoformat()
    data_row = (
        f"| {ts} | Feature X | 5 files, 3 behaviors | standard | {tier} | user override | - |"
    )
    log_path.write_text(
        f"{CALIBRATION_HEADER}\n{CALIBRATION_SEPARATOR}\n{data_row}\n",
        encoding="utf-8",
    )
    return log_path


def _create_ai_work_file(tmp_path: Path, filename: str) -> Path:
    """Create a file under .ai-work/ in tmp_path."""
    ai_work = tmp_path / ".ai-work"
    ai_work.mkdir(parents=True, exist_ok=True)
    path = ai_work / filename
    path.write_text("# placeholder\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# detect_tier — priority: SYSTEMS_PLAN > IMPLEMENTATION_PLAN > calibration log > default
# ---------------------------------------------------------------------------


class TestSystemsPlanReturnsStandard:
    def test_systems_plan_exists_returns_standard(self, tmp_path: Path):
        _create_ai_work_file(tmp_path, "SYSTEMS_PLAN.md")

        assert detect_tier(tmp_path) == "standard"


class TestImplPlanReturnsStandard:
    def test_impl_plan_exists_returns_standard(self, tmp_path: Path):
        _create_ai_work_file(tmp_path, "IMPLEMENTATION_PLAN.md")

        assert detect_tier(tmp_path) == "standard"


class TestCalibrationLogRecentEntry:
    def test_recent_entry_returns_its_tier(self, tmp_path: Path):
        recent = datetime.now(UTC) - timedelta(hours=1)
        _write_calibration_log(tmp_path, tier="full", timestamp=recent)

        assert detect_tier(tmp_path) == "full"


class TestCalibrationLogStaleEntry:
    def test_stale_entry_returns_direct(self, tmp_path: Path):
        stale = datetime.now(UTC) - timedelta(hours=48)
        _write_calibration_log(tmp_path, tier="full", timestamp=stale)

        assert detect_tier(tmp_path) == "direct"


class TestNoSignalsReturnsDefault:
    def test_empty_directory_returns_direct(self, tmp_path: Path):
        assert detect_tier(tmp_path) == "direct"


class TestSystemsPlanTakesPriority:
    def test_systems_plan_wins_over_calibration_log(self, tmp_path: Path):
        _create_ai_work_file(tmp_path, "SYSTEMS_PLAN.md")
        recent = datetime.now(UTC) - timedelta(hours=1)
        _write_calibration_log(tmp_path, tier="direct", timestamp=recent)

        assert detect_tier(tmp_path) == "standard"


# ---------------------------------------------------------------------------
# is_gating_tier
# ---------------------------------------------------------------------------


class TestCalibrationLogEdgeCases:
    def test_missing_tier_column_returns_direct(self, tmp_path: Path):
        """Calibration log with no 'actual tier' or 'tier' column."""
        log_dir = tmp_path / ".ai-state"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "calibration_log.md"
        log_path.write_text(
            "| timestamp | task |\n|---|---|\n| 2026-03-19T12:00:00+00:00 | test |\n",
            encoding="utf-8",
        )
        assert detect_tier(tmp_path) == "direct"

    def test_invalid_tier_value_returns_direct(self, tmp_path: Path):
        """Calibration log with an unrecognized tier value."""
        recent = datetime.now(UTC) - timedelta(hours=1)
        _write_calibration_log(tmp_path, tier="mega", timestamp=recent)
        assert detect_tier(tmp_path) == "direct"

    def test_unparseable_timestamp_returns_direct(self, tmp_path: Path):
        """Calibration log with a malformed timestamp treats as stale."""
        log_dir = tmp_path / ".ai-state"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "calibration_log.md"
        log_path.write_text(
            f"{CALIBRATION_HEADER}\n{CALIBRATION_SEPARATOR}\n"
            "| not-a-date | Feature | signals | standard | full | user | - |\n",
            encoding="utf-8",
        )
        assert detect_tier(tmp_path) == "direct"

    def test_empty_calibration_file_returns_direct(self, tmp_path: Path):
        """Calibration log with header but no data rows."""
        log_dir = tmp_path / ".ai-state"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "calibration_log.md"
        log_path.write_text(
            f"{CALIBRATION_HEADER}\n{CALIBRATION_SEPARATOR}\n",
            encoding="utf-8",
        )
        assert detect_tier(tmp_path) == "direct"

    def test_header_with_tier_alias(self, tmp_path: Path):
        """Calibration log with 'tier' column (no 'actual tier')."""
        log_dir = tmp_path / ".ai-state"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "calibration_log.md"
        recent = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        log_path.write_text(
            f"| timestamp | tier |\n|---|---|\n| {recent} | standard |\n",
            encoding="utf-8",
        )
        assert detect_tier(tmp_path) == "standard"


class TestIsGatingTierStandard:
    def test_standard_is_gating(self):
        assert is_gating_tier("standard") is True


class TestIsGatingTierFull:
    def test_full_is_gating(self):
        assert is_gating_tier("full") is True


class TestIsGatingTierDirect:
    def test_direct_is_not_gating(self):
        assert is_gating_tier("direct") is False


class TestIsGatingTierLightweight:
    def test_lightweight_is_not_gating(self):
        assert is_gating_tier("lightweight") is False


class TestIsGatingTierSpike:
    def test_spike_is_not_gating(self):
        assert is_gating_tier("spike") is False
