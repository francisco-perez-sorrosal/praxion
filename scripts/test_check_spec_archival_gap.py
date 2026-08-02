"""Tests for check_spec_archival_gap.py -- spec-archival gap detector.

Gate-liveness contract: this is a CODE gate detecting when a feature ships without
archiving its behavioral spec. Tests include a canary that feeds a known-gap fixture
and asserts the detector flags it (proves the gate bites on bad input).

Import strategy mirrors test_clean_work_safety.py: load via importlib.util so the
script need not be on sys.path. All filesystem state is built under pytest's
tmp_path; no git calls are made (--repo-root bypasses repo-root resolution).

`now` is injected as a fixed datetime for determinism — the detector computes
`spec_age_days` and ADR recency relative to `now`, not wall-clock.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parent / "check_spec_archival_gap.py"
_FIXTURE_ROOT = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sentinel" / "spec_archival_gap"
)

# Fixed "now" used in every test — decouples assertions from wall-clock.
_NOW = datetime(2026, 6, 26, tzinfo=timezone.utc)

# Thresholds mirroring the script's defaults (kept local to avoid import coupling).
_N_DAYS = 90
_K_ADRS = 3

# Fixture dates chosen so gap arithmetic is unambiguous at _NOW:
#   STALE_SPEC_DATE:  2025-01-01  → 541 days before _NOW
#   FRESH_SPEC_DATE:  2026-06-20  →   6 days before _NOW  (spec is NEWER than ADRs)
#   RECENT_ADR_DATE:  2026-05-01  →  56 days before _NOW  (485 days after stale spec)
_STALE_SPEC_DATE = "2025-01-01"
_FRESH_SPEC_DATE = "2026-06-20"
_RECENT_ADR_DATE = "2026-05-01"


# -- Module loader ------------------------------------------------------------


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("check_spec_archival_gap", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)  # FileNotFoundError when script absent → RED at collection
    return mod


# Module-level load: collection fails with FileNotFoundError when
# check_spec_archival_gap.py does not yet exist (concurrent BDD/TDD RED handshake).
csag = _load_module()


# -- Helpers ------------------------------------------------------------------


def _adr_content(idx: int, date: str = _RECENT_ADR_DATE, tags: list[str] | None = None) -> str:
    """Minimal valid ADR frontmatter + body for a test fixture."""
    tags = tags or ["feature"]
    tag_lines = "\n".join(f"  - {t}" for t in tags)
    return (
        f"---\n"
        f"id: dec-{idx:03d}\n"
        f"title: Decision {idx}\n"
        f"status: accepted\n"
        f"category: architectural\n"
        f"date: {date}\n"
        f"summary: Test decision {idx}.\n"
        f"tags:\n"
        f"{tag_lines}\n"
        f"made_by: agent\n"
        f"---\n\n"
        f"## Context\n\nTest decision {idx}.\n\n"
        f"## Decision\n\nAccepted.\n"
    )


def _spec_content(slug: str, date: str) -> str:
    return f"# SPEC: {slug}\n\nArchived on {date}.\n"


def _make_repo(
    base: Path,
    specs: dict[str, str] | None = None,
    adrs: list[dict[str, Any]] | None = None,
) -> Path:
    """Populate a fake repo directory with .ai-state/specs/ and/or .ai-state/decisions/.

    specs  — {slug: date_str} pairs → writes SPEC_<slug>_<date>.md files
    adrs   — list of {"date": str, "tags": list[str]} dicts (index 1-based)
    """
    if specs is not None:
        specs_dir = base / ".ai-state" / "specs"
        specs_dir.mkdir(parents=True, exist_ok=True)
        for slug, date in specs.items():
            (specs_dir / f"SPEC_{slug}_{date}.md").write_text(
                _spec_content(slug, date), encoding="utf-8"
            )

    if adrs is not None:
        decisions_dir = base / ".ai-state" / "decisions"
        decisions_dir.mkdir(parents=True, exist_ok=True)
        for i, adr in enumerate(adrs, start=1):
            (decisions_dir / f"{i:03d}-decision.md").write_text(
                _adr_content(i, date=adr.get("date", _RECENT_ADR_DATE), tags=adr.get("tags")),
                encoding="utf-8",
            )

    return base


# -- Tests --------------------------------------------------------------------


def test_reports_gap_when_specs_stale_against_adr_cluster(tmp_path: Path) -> None:
    """Stale SPEC with ≥K recent ADRs sharing a tag triggers gap detection."""
    repo = _make_repo(
        tmp_path,
        specs={"old-feature": _STALE_SPEC_DATE},
        adrs=[{"date": _RECENT_ADR_DATE, "tags": ["feature"]} for _ in range(_K_ADRS)],
    )
    result = csag.detect_gap(repo_root=repo, now=_NOW)
    assert result["gap"] is True
    assert result["recent_adr_count"] >= _K_ADRS


def test_no_gap_when_spec_is_fresh(tmp_path: Path) -> None:
    """A SPEC archived close to or after the ADR cluster reports no gap (no-false-positive)."""
    # Fresh spec (2026-06-20) is NEWER than the ADR cluster (2026-05-01) — gap < 0 days.
    repo = _make_repo(
        tmp_path,
        specs={"fresh-feature": _FRESH_SPEC_DATE},
        adrs=[{"date": _RECENT_ADR_DATE, "tags": ["feature"]} for _ in range(_K_ADRS)],
    )
    result = csag.detect_gap(repo_root=repo, now=_NOW)
    assert result["gap"] is False


def test_skips_when_no_specs_directory(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Missing .ai-state/specs/ causes exit 0 with no gap finding (skip-with-INFO)."""
    # No specs dir — only optional decisions dir present to confirm the skip is specs-specific.
    _make_repo(
        tmp_path,
        specs=None,
        adrs=[{"date": _RECENT_ADR_DATE, "tags": ["feature"]} for _ in range(_K_ADRS)],
    )
    with pytest.raises(SystemExit) as exc:
        csag.main(["--repo-root", str(tmp_path), "--check"])
    assert exc.value.code == 0


def test_no_gap_below_adr_cluster_threshold(tmp_path: Path) -> None:
    """Stale SPEC with fewer than K ADRs sharing a tag does not trigger gap detection."""
    repo = _make_repo(
        tmp_path,
        specs={"old-feature": _STALE_SPEC_DATE},
        # K_ADRS - 1 = below threshold; each is individually stale vs spec but cluster is thin
        adrs=[{"date": _RECENT_ADR_DATE, "tags": ["feature"]} for _ in range(_K_ADRS - 1)],
    )
    result = csag.detect_gap(repo_root=repo, now=_NOW)
    assert result["gap"] is False


def test_canary_known_gap_fixture_flags_gap() -> None:
    """Golden bad-case fixture must be detected as a gap (gate liveness proof).

    The fixture at tests/fixtures/sentinel/spec_archival_gap/ contains:
      - SPEC_old-auth-feature_2025-01-01.md  (stale spec)
      - 3 ADRs dated 2026-05-xx to 2026-06-xx sharing the 'auth' tag

    This is the PROMPT gate's golden bad-case that sentinel SH08 must flag.
    This canary proves the CODE-level detector bites on that same input.
    """
    assert _FIXTURE_ROOT.is_dir(), f"Fixture directory missing: {_FIXTURE_ROOT}"
    result = csag.detect_gap(repo_root=_FIXTURE_ROOT, now=_NOW)
    assert result["gap"] is True, (
        f"Golden bad-case fixture did not trigger gap detection. "
        f"result={result!r}. "
        f"Fixture path: {_FIXTURE_ROOT}"
    )
    assert result["recent_adr_count"] >= _K_ADRS, (
        f"Expected ≥{_K_ADRS} qualifying ADRs in fixture, got {result['recent_adr_count']}"
    )
