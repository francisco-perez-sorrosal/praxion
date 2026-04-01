"""Tier detection from filesystem signals."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from decision_tracker.schema import TierType

AI_WORK_DIR = ".ai-work"
SYSTEMS_PLAN_NAME = "SYSTEMS_PLAN.md"
IMPLEMENTATION_PLAN_NAME = "IMPLEMENTATION_PLAN.md"
CALIBRATION_LOG_PATH = ".ai-state/calibration_log.md"

DEFAULT_TIER: TierType = "direct"
GATING_TIERS: frozenset[TierType] = frozenset({"standard", "full"})
STALENESS_THRESHOLD = timedelta(hours=24)


def _has_pipeline_doc(cwd: Path, doc_name: str) -> bool:
    """Check whether *doc_name* exists in any task-scoped subdirectory of .ai-work/.

    Searches `.ai-work/<task-slug>/<doc_name>` for all task-slug subdirectories.
    Falls back to `.ai-work/<doc_name>` for legacy flat layouts.
    """
    ai_work = cwd / AI_WORK_DIR
    if not ai_work.is_dir():
        return False
    # Check task-scoped subdirectories
    if any(ai_work.glob(f"*/{doc_name}")):
        return True
    # Fallback: legacy flat layout
    return (ai_work / doc_name).is_file()


def detect_tier(cwd: Path) -> TierType:
    """Detect the pipeline tier from filesystem signals in *cwd*.

    Priority order:
    1. Presence of SYSTEMS_PLAN.md (in any task-scoped dir) -> "standard"
    2. Presence of IMPLEMENTATION_PLAN.md (in any task-scoped dir) -> "standard"
    3. Recent entry in calibration_log.md -> that entry's tier
    4. Default -> "direct"
    """
    if _has_pipeline_doc(cwd, SYSTEMS_PLAN_NAME):
        return "standard"

    if _has_pipeline_doc(cwd, IMPLEMENTATION_PLAN_NAME):
        return "standard"

    tier = _tier_from_calibration_log(cwd / CALIBRATION_LOG_PATH)
    if tier is not None:
        return tier

    return DEFAULT_TIER


def is_gating_tier(tier: str) -> bool:
    """Return True when *tier* requires gating (user review of decisions)."""
    return tier in GATING_TIERS


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _tier_from_calibration_log(path: Path) -> TierType | None:
    """Parse the most recent calibration log entry and return its tier if fresh.

    Returns ``None`` when the file is missing, has no data rows, cannot be
    parsed, or the entry is older than :data:`STALENESS_THRESHOLD`.
    """
    if not path.is_file():
        return None

    lines = path.read_text(encoding="utf-8").splitlines()
    header_index, tier_column = _find_tier_column(lines)
    if header_index is None or tier_column is None:
        return None

    last_row = _find_last_data_row(lines, after=header_index)
    if last_row is None:
        return None

    cells = _parse_row_cells(last_row)
    if tier_column >= len(cells):
        return None

    tier_value = cells[tier_column].strip().lower()
    if tier_value not in {"direct", "lightweight", "standard", "full", "spike"}:
        return None

    timestamp_str = cells[0].strip() if cells else None
    if timestamp_str and _is_stale(timestamp_str):
        return None

    return tier_value  # type: ignore[return-value]


def _find_tier_column(lines: list[str]) -> tuple[int | None, int | None]:
    """Locate the header row and the column index for 'actual tier'.

    Falls back to a column named 'tier' if 'actual tier' is not found.
    Returns (header_line_index, column_index) or (None, None).
    """
    for i, line in enumerate(lines):
        if "|" not in line:
            continue
        cells = _parse_row_cells(line)
        normalized = [c.strip().lower() for c in cells]
        if "actual tier" in normalized:
            return i, normalized.index("actual tier")
        if "tier" in normalized:
            return i, normalized.index("tier")
    return None, None


def _find_last_data_row(lines: list[str], *, after: int) -> str | None:
    """Return the last non-empty, non-separator row after the header."""
    last: str | None = None
    for line in lines[after + 1 :]:
        stripped = line.strip()
        if not stripped or "|" not in stripped:
            continue
        # Skip separator rows (e.g. |---|---|---|)
        content = stripped.replace("|", "").replace("-", "").strip()
        if not content:
            continue
        last = stripped
    return last


def _parse_row_cells(row: str) -> list[str]:
    """Split a pipe-delimited row into cells, stripping leading/trailing pipes."""
    stripped = row.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return stripped.split("|")


def _is_stale(timestamp_str: str) -> bool:
    """Return True when *timestamp_str* is older than the staleness threshold."""
    try:
        entry_time = datetime.fromisoformat(timestamp_str)
        if entry_time.tzinfo is None:
            entry_time = entry_time.replace(tzinfo=UTC)
        return datetime.now(UTC) - entry_time > STALENESS_THRESHOLD
    except ValueError:
        # Unparseable timestamp — treat as stale so we fall through to default
        return True
