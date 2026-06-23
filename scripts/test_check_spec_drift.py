"""Tests for check_spec_drift (SH07 wrapper) — flag-and-exit logic + gate-liveness canary.

The SH07 gate scans archived specs under ``.ai-state/specs/`` and surfaces any
non-orphaned drift finding, exiting non-zero when actionable findings exist.

Note on the canary seam: ``check_spec_drift`` delegates detection to
``spec_drift.detect_drift``, whose archived-scope branch (``_detect_archived``)
is presently a stub returning ``[]`` — so no real archived spec can currently
make the gate bite. The canary therefore injects a known-bad finding at the
``detect_drift`` collaborator boundary (the gate's own dependency, not the unit
under test) to prove the wrapper's flag-and-exit-1 path fires on drift. When
``_detect_archived`` is implemented, replace the injection with a real drifting
archived-spec fixture.

Run: ``python3 scripts/test_check_spec_drift.py`` or ``pytest``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import check_spec_drift as csd  # noqa: E402


def _make_specs_dir(repo_root: Path) -> None:
    """Create .ai-state/specs/ with one archived spec so run_sh07 iterates."""
    specs = repo_root / ".ai-state" / "specs"
    specs.mkdir(parents=True)
    (specs / "SPEC_demo_2026-06-22.md").write_text("# archived spec\n", encoding="utf-8")


def _finding(kind: str, severity: str = "important") -> dict:
    """A minimal detect_drift finding carrying the fields run_sh07 reads."""
    return {
        "kind": kind,
        "severity": severity,
        "req": "r-alpha",
        "pointer": "traceability.yml",
        "rationale": "spec clause changed but dependent not updated",
    }


def test_returns_empty_when_specs_dir_absent(tmp_path: Path) -> None:
    """Graceful degradation: no .ai-state/specs/ dir → no findings, no error."""
    assert csd.run_sh07(tmp_path) == []


def test_filters_orphaned_edge_findings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Orphaned-edge findings are deferred to SH01/SH04, not surfaced by SH07."""
    _make_specs_dir(tmp_path)
    monkeypatch.setattr(
        csd,
        "detect_drift",
        lambda scope, repo_root, base_sha: [
            _finding("orphaned-edge"),
            _finding("stale-dependent"),
        ],
    )
    findings = csd.run_sh07(tmp_path)
    assert len(findings) == 1
    assert findings[0]["check"] == "SH07"


def test_flags_drift_finding_with_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Canary: an actionable drift finding is surfaced and exits non-zero.

    Feeds a known-bad input (an important stale-dependent finding) and asserts
    the gate flags it — proving SH07 bites rather than merely passing clean.
    """
    _make_specs_dir(tmp_path)
    monkeypatch.setattr(
        csd,
        "detect_drift",
        lambda scope, repo_root, base_sha: [_finding("stale-dependent", "important")],
    )

    findings = csd.run_sh07(tmp_path)
    assert findings, "run_sh07 must surface an important drift finding"
    assert findings[0]["severity"] == "important"

    exit_code = csd.main(["--repo-root", str(tmp_path)])
    assert exit_code == 1, "an actionable finding must drive a non-zero exit"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
