"""Tests for check_specialist_dispositions.py — P07 gate-liveness canary.

Gate-liveness contract (rules/swe/gate-liveness.md): this is a CODE gate, so
it ships canaries that feed a known-bad fixture and assert the gate fires.

The real P07 substrate is `.ai-work/<slug>/`, which is globally gitignored --
a fixture committed there would never reach a fresh checkout / CI. Every
canary below therefore builds its input under `tmp_path/.ai-work/<slug>/` at
runtime, using the *content* of the pre-existing committed fixtures at
`tests/fixtures/sentinel/{challenge,consult}_no_disposition/` (verified below
to still match this script's docstring) rather than pointing the script at
that fixture directory directly (`rules/swe/testing-conventions.md § Fixtures
Under Gitignored Paths`).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_specialist_dispositions import CHECK_IDS, classify  # noqa: E402

_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "sentinel"
_CHALLENGE_FIXTURES = _FIXTURE_ROOT / "challenge_no_disposition"
_CONSULT_FIXTURES = _FIXTURE_ROOT / "consult_no_disposition"


def _copy_into_slug(tmp_path: Path, slug: str, filename: str, source: Path) -> Path:
    slug_dir = tmp_path / ".ai-work" / slug
    slug_dir.mkdir(parents=True, exist_ok=True)
    target = slug_dir / filename
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def test_check_ids_declares_p07_only() -> None:
    assert CHECK_IDS == ("P07",)


def test_missing_ai_work_is_skipped(tmp_path: Path) -> None:
    report = classify(tmp_path)
    assert report["skipped"]["P07"] is not None
    assert report["skipped"]["P07"]["reason"] == "substrate-absent"
    assert report["findings"] == []


def test_undisposed_architecture_challenges_is_flagged(tmp_path: Path) -> None:
    """Golden bad-case: a non-empty ## Architecture Challenges with no disposition."""
    _copy_into_slug(
        tmp_path,
        "token-refresh-api",
        "INTERFACE_DESIGN.md",
        _CHALLENGE_FIXTURES / "INTERFACE_DESIGN.md",
    )
    report = classify(tmp_path)
    assert report["skipped"]["P07"] is None
    assert len(report["findings"]) == 1
    finding = report["findings"][0]
    assert finding["check"] == "P07"
    assert finding["severity"] == "important"
    assert "INTERFACE_DESIGN.md" in finding["entity"]


def test_design_doc_without_challenges_section_is_not_flagged(tmp_path: Path) -> None:
    """No-false-positive control: no ## Architecture Challenges section at all."""
    _copy_into_slug(
        tmp_path,
        "health-check",
        "INTERFACE_DESIGN.md",
        _CHALLENGE_FIXTURES / "INTERFACE_DESIGN_no_challenge.md",
    )
    report = classify(tmp_path)
    assert report["findings"] == []


def test_consult_placeholder_disposition_is_flagged(tmp_path: Path) -> None:
    """Golden bad-case: CH-01's Disposition is still the convener placeholder."""
    _copy_into_slug(
        tmp_path,
        "caching-benchmark-claim",
        "CONSULT_statistician.md",
        _CONSULT_FIXTURES / "CONSULT_statistician.md",
    )
    report = classify(tmp_path)
    assert len(report["findings"]) == 1
    assert "CH-01" in report["findings"][0]["entity"]


def test_consult_omitted_disposition_field_is_flagged(tmp_path: Path) -> None:
    """Second bad case: both entries omit the per-entry Disposition field entirely,
    substituting a trailing summary table -- absent must count as undisposed."""
    _copy_into_slug(
        tmp_path,
        "caching-benchmark-claim",
        "CONSULT_evidence-appraiser.md",
        _CONSULT_FIXTURES / "CONSULT_evidence-appraiser.md",
    )
    report = classify(tmp_path)
    assert len(report["findings"]) == 2
    ids = {f["entity"].rsplit("#", 1)[-1] for f in report["findings"]}
    assert ids == {"CH-01", "CH-02"}


def test_consult_with_no_challenges_section_is_not_flagged(tmp_path: Path) -> None:
    """No-false-positive control: nothing raised."""
    _copy_into_slug(
        tmp_path,
        "multidisciplinary-identities",
        "CONSULT_statistician_no_challenge.md",
        _CONSULT_FIXTURES / "CONSULT_statistician_no_challenge.md",
    )
    report = classify(tmp_path)
    assert report["findings"] == []


def test_consult_fully_dispositioned_is_not_flagged(tmp_path: Path) -> None:
    """No-false-positive control: every entry carries a real Disposition + Rationale."""
    _copy_into_slug(
        tmp_path,
        "caching-benchmark-claim",
        "CONSULT_statistician_dispositioned.md",
        _CONSULT_FIXTURES / "CONSULT_statistician_dispositioned.md",
    )
    report = classify(tmp_path)
    assert report["findings"] == []
