"""Tests for check_adr_reciprocity.py -- DL06's back-link reciprocity check.

Cites: rules/swe/gate-liveness.md -- a CODE gate ships a canary proving it
bites on a known-bad input, not merely that it passes on the current good
state.

The golden bad-case is drawn straight from the check's own docstring: a
decision superseding three predecessors, where only one of the three records
the back-link. Reading `supersedes` as one opaque value (instead of iterating
every element) passes this fixture unread -- that is the specific defect the
fixture exists to catch.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import check_adr_reciprocity as car


def _adr(root: Path, n: int, *, extra_fields: dict | None = None) -> Path:
    """Write a finalized ADR carrying arbitrary relation-field frontmatter."""
    d = root / ".ai-state" / "decisions"
    d.mkdir(parents=True, exist_ok=True)
    lines = [
        f"id: dec-{n:03d}",
        "title: A decision",
        "status: accepted",
        "category: architectural",
        "date: 2026-01-01",
        "summary: s",
        "tags: [t]",
        "made_by: agent",
    ]
    for key, value in (extra_fields or {}).items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {v}" for v in value)
        else:
            lines.append(f"{key}: {value}")
    body = "---\n" + "\n".join(lines) + "\n---\n\n# Body\n"
    path = d / f"{n:03d}-slug.md"
    path.write_text(body, encoding="utf-8")
    return path


def _messages(report: dict) -> list[str]:
    return [f["message"] for f in report["findings"]]


# -- Golden bad-case and inverse guard -----------------------------------------


def test_golden_bad_case_warns_on_every_unreciprocated_supersedes_target_by_name(
    tmp_path: Path,
) -> None:
    """`supersedes: [A, B, C]` where only A sets `superseded_by` must WARN on B and C."""
    _adr(tmp_path, 1, extra_fields={"supersedes": ["dec-002", "dec-003", "dec-004"]})
    _adr(tmp_path, 2, extra_fields={"superseded_by": "dec-001"})
    _adr(tmp_path, 3)
    _adr(tmp_path, 4)

    report = car.classify(tmp_path)

    messages = _messages(report)
    assert len(report["findings"]) == 2
    assert all(f["entity"] == "dec-001" for f in report["findings"])
    assert any("dec-003" in m for m in messages)
    assert any("dec-004" in m for m in messages)
    assert not any("dec-002" in m for m in messages)


def test_retired_by_only_relation_produces_zero_findings(tmp_path: Path) -> None:
    """Inverse guard: `retired_by` is exempt and never flagged -- one-directional by design."""
    _adr(tmp_path, 1, extra_fields={"retired_by": ["dec-002"]})
    _adr(tmp_path, 2)
    assert car.classify(tmp_path)["findings"] == []


# -- Bidirectional pairs: checked from both sides ------------------------------


def test_reverse_direction_catches_a_superseded_by_with_no_reciprocal_supersedes(
    tmp_path: Path,
) -> None:
    """Only `superseded_by` set, target's `supersedes` silent -- the other half of the pair."""
    _adr(tmp_path, 1, extra_fields={"superseded_by": "dec-002"})
    _adr(tmp_path, 2)

    report = car.classify(tmp_path)

    assert len(report["findings"]) == 1
    assert report["findings"][0]["entity"] == "dec-001"
    assert "dec-002" in report["findings"][0]["message"]


def test_supersedes_in_part_missing_back_link_is_warned(tmp_path: Path) -> None:
    _adr(tmp_path, 1, extra_fields={"supersedes_in_part": ["dec-002"]})
    _adr(tmp_path, 2)

    report = car.classify(tmp_path)

    assert len(report["findings"]) == 1
    assert report["findings"][0]["entity"] == "dec-001"


def test_correctly_reciprocated_supersedes_in_part_pair_emits_zero_findings(
    tmp_path: Path,
) -> None:
    _adr(tmp_path, 1, extra_fields={"supersedes_in_part": ["dec-002"]})
    _adr(tmp_path, 2, extra_fields={"superseded_in_part_by": ["dec-001"]})
    assert car.classify(tmp_path)["findings"] == []


# -- re_affirms: one-directional by design -------------------------------------


def test_re_affirms_without_reciprocal_re_affirmed_by_is_warned(tmp_path: Path) -> None:
    _adr(tmp_path, 1, extra_fields={"re_affirms": "dec-002"})
    _adr(tmp_path, 2)

    report = car.classify(tmp_path)

    assert len(report["findings"]) == 1
    assert report["findings"][0]["entity"] == "dec-001"


def test_correctly_reciprocated_re_affirms_pair_emits_zero_findings(tmp_path: Path) -> None:
    _adr(tmp_path, 1, extra_fields={"re_affirms": "dec-002"})
    _adr(tmp_path, 2, extra_fields={"re_affirmed_by": ["dec-001"]})
    assert car.classify(tmp_path)["findings"] == []


def test_re_affirmed_by_without_a_reciprocal_re_affirms_is_not_flagged(tmp_path: Path) -> None:
    """One-directional by design: the protocol writes both sides together, so a lone
    `re_affirmed_by` with no matching `re_affirms` anywhere is out of this check's scope.
    """
    _adr(tmp_path, 1, extra_fields={"re_affirmed_by": ["dec-002"]})
    _adr(tmp_path, 2)
    assert car.classify(tmp_path)["findings"] == []


# -- Unknown targets and draft-stage pointers ----------------------------------


def test_a_pointer_to_an_unknown_id_is_not_flagged_here(tmp_path: Path) -> None:
    """DL04's job, not this one's -- an unresolved target is silently skipped."""
    _adr(tmp_path, 1, extra_fields={"supersedes": ["dec-999"]})
    assert car.classify(tmp_path)["findings"] == []


def test_draft_stage_pointers_are_checked_for_reciprocity_too(tmp_path: Path) -> None:
    """Draft-stage `dec-draft-<hash>` ids resolve the same way finalized ids do."""
    drafts = tmp_path / ".ai-state" / "decisions" / "drafts"
    drafts.mkdir(parents=True)
    # Fixture literals, not real drafts under `.ai-state/decisions/drafts/`; the
    # shape is what the test exercises (id-citation-discipline:ignore x4 below).
    (drafts / "20260101-0000-user-branch-slug-a.md").write_text(
        "---\nid: dec-draft-aaaaaaaa\ntitle: t\nstatus: proposed\ncategory: architectural\n"  # id-citation-discipline:ignore
        "date: 2026-01-01\nsummary: s\ntags: [t]\nmade_by: agent\n"
        "re_affirms: dec-draft-bbbbbbbb\n---\n\n# Body\n",  # id-citation-discipline:ignore
        encoding="utf-8",
    )
    (drafts / "20260101-0001-user-branch-slug-b.md").write_text(
        "---\nid: dec-draft-bbbbbbbb\ntitle: t\nstatus: proposed\ncategory: architectural\n"  # id-citation-discipline:ignore
        "date: 2026-01-01\nsummary: s\ntags: [t]\nmade_by: agent\n---\n\n# Body\n",
        encoding="utf-8",
    )

    report = car.classify(tmp_path)

    assert len(report["findings"]) == 1
    assert report["findings"][0]["entity"] == "dec-draft-aaaaaaaa"  # id-citation-discipline:ignore


# -- Substrate and unreadable frontmatter ---------------------------------------


def test_missing_decisions_directory_is_a_skip_not_a_finding(tmp_path: Path) -> None:
    report = car.classify(tmp_path)
    assert report["skipped"] is not None
    assert report["skipped"]["reason"] == "substrate-absent"
    assert report["findings"] == []


def test_unreadable_frontmatter_is_withheld_not_raised(tmp_path: Path) -> None:
    d = tmp_path / ".ai-state" / "decisions"
    d.mkdir(parents=True)
    (d / "001-broken.md").write_text("not frontmatter at all\n", encoding="utf-8")

    report = car.classify(tmp_path)

    assert report["withheld"]
    assert report["findings"] == []


# -- CLI contract ----------------------------------------------------------------


def test_exits_zero_by_default_even_with_findings(tmp_path: Path) -> None:
    """Advisory by construction -- it reports, it does not gate, unless asked to."""
    _adr(tmp_path, 1, extra_fields={"supersedes": "dec-002"})
    _adr(tmp_path, 2)
    rc = subprocess.run(
        [sys.executable, str(Path(car.__file__)), "--json", "--repo-root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rc.returncode == 0
    assert '"warn"' in rc.stdout


def test_check_flag_exits_one_on_findings(tmp_path: Path) -> None:
    _adr(tmp_path, 1, extra_fields={"supersedes": "dec-002"})
    _adr(tmp_path, 2)
    rc = subprocess.run(
        [sys.executable, str(Path(car.__file__)), "--check", "--repo-root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rc.returncode == 1
