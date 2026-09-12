"""Tests for check_staleness_markers.py — F07/F08/F09 gate-liveness canary.

Each test builds a minimal `skills/<name>/SKILL.md` (plus, where the case needs
it, `references/*.md`) under `tmp_path` — the substrate `check_staleness_markers`
walks lives inside the project checkout (git-tracked), so no gitignored-path
concern applies here (unlike P07's `.ai-work/` substrate).
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_staleness_markers import CHECK_IDS, classify  # noqa: E402

_TODAY = dt.date.today()


def _frontmatter(name: str, sections: list[str], threshold: int | None = None) -> str:
    lines = ["---", f"name: {name}", "description: test", "staleness_sensitive_sections:"]
    lines.extend(f'  - "{s}"' for s in sections)
    if threshold is not None:
        lines.append(f"staleness_threshold_days: {threshold}")
    lines.append("---")
    return "\n".join(lines)


def _make_skill(
    tmp_path: Path,
    name: str,
    body: str,
    sections: list[str],
    threshold: int | None = None,
) -> Path:
    skill_dir = tmp_path / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        _frontmatter(name, sections, threshold) + "\n\n" + body, encoding="utf-8"
    )
    return skill_dir


def _marker(days_ago: int | None = None, *, token: str | None = None) -> str:
    if token is not None:
        value = token
    else:
        value = (_TODAY - dt.timedelta(days=days_ago)).isoformat()
    return f"<!-- last-verified: {value} -->"


def test_check_ids_declares_the_three_freshness_checks() -> None:
    assert CHECK_IDS == ("F07", "F08", "F09")


def test_no_skills_dir_is_skipped(tmp_path: Path) -> None:
    report = classify(tmp_path)
    for check_id in CHECK_IDS:
        assert report["skipped"][check_id]["reason"] == "substrate-absent"
        assert report["examined"][check_id] is None
    assert report["findings"] == []


def test_f07_missing_marker_is_flagged(tmp_path: Path) -> None:
    """Canary: a cataloged heading with no marker line below it WARNs F07."""
    _make_skill(
        tmp_path,
        "sample-skill",
        "## Volatile Section\n\nNo marker here at all.\n",
        sections=["Volatile Section"],
    )
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "F07"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "warn"


def test_f08_marker_older_than_threshold_warns(tmp_path: Path) -> None:
    """Canary: a marker past the threshold but within 2x WARNs F08."""
    _make_skill(
        tmp_path,
        "sample-skill",
        f"## Volatile Section\n{_marker(days_ago=130)}\n\nBody.\n",
        sections=["Volatile Section"],
        threshold=120,
    )
    report = classify(tmp_path)
    f08 = [f for f in report["findings"] if f["check"] == "F08"]
    assert len(f08) == 1
    assert f08[0]["severity"] == "warn"


def test_f08_marker_past_double_threshold_fails(tmp_path: Path) -> None:
    """Canary: a marker past 2x the threshold escalates F08 to FAIL."""
    _make_skill(
        tmp_path,
        "sample-skill",
        f"## Volatile Section\n{_marker(days_ago=250)}\n\nBody.\n",
        sections=["Volatile Section"],
        threshold=120,
    )
    report = classify(tmp_path)
    f08 = [f for f in report["findings"] if f["check"] == "F08"]
    assert len(f08) == 1
    assert f08[0]["severity"] == "fail"


def test_f09_invalid_date_format_is_rejected(tmp_path: Path) -> None:
    """Canary: an unparseable date FAILs F09."""
    _make_skill(
        tmp_path,
        "sample-skill",
        "## Volatile Section\n<!-- last-verified: not-a-date -->\n\nBody.\n",
        sections=["Volatile Section"],
    )
    report = classify(tmp_path)
    f09 = [f for f in report["findings"] if f["check"] == "F09"]
    assert len(f09) == 1
    assert f09[0]["severity"] == "fail"


def test_f09_future_dated_marker_is_rejected(tmp_path: Path) -> None:
    """Canary: a marker dated in the future FAILs F09."""
    _make_skill(
        tmp_path,
        "sample-skill",
        f"## Volatile Section\n{_marker(days_ago=-5)}\n\nBody.\n",
        sections=["Volatile Section"],
    )
    report = classify(tmp_path)
    f09 = [f for f in report["findings"] if f["check"] == "F09"]
    assert len(f09) == 1


def test_permanent_marker_never_ages(tmp_path: Path) -> None:
    """No-false-positive control: `permanent` is exempt from F07/F08/F09."""
    _make_skill(
        tmp_path,
        "sample-skill",
        f"## Naming Conventions\n{_marker(token='permanent')}\n\nBody.\n",
        sections=["Naming Conventions"],
    )
    report = classify(tmp_path)
    assert report["findings"] == []


def test_template_placeholder_in_underscore_reference_is_excluded(tmp_path: Path) -> None:
    """The `[YYYY-MM-DD]` placeholder in a `_`-prefixed references/ template is not a finding."""
    skill_dir = _make_skill(
        tmp_path,
        "sample-skill",
        "No cataloged heading lives in SKILL.md for this test.\n",
        sections=["Volatile Specifics"],
    )
    references = skill_dir / "references"
    references.mkdir()
    (references / "_template.md").write_text(
        "## Volatile Specifics\n<!-- last-verified: [YYYY-MM-DD] -->\n\nFill in per provider.\n",
        encoding="utf-8",
    )
    report = classify(tmp_path)
    assert report["findings"] == []
    assert report["withheld"] == []


def test_placeholder_outside_underscore_template_is_malformed(tmp_path: Path) -> None:
    """The same placeholder token in a non-`_`-prefixed file is a genuine F09 FAIL."""
    _make_skill(
        tmp_path,
        "sample-skill",
        "## Volatile Section\n<!-- last-verified: [YYYY-MM-DD] -->\n\nBody.\n",
        sections=["Volatile Section"],
    )
    report = classify(tmp_path)
    f09 = [f for f in report["findings"] if f["check"] == "F09"]
    assert len(f09) == 1


def test_heading_resolves_via_references_when_absent_from_skill_md(tmp_path: Path) -> None:
    """Progressive disclosure: a cataloged heading living only in references/ still resolves."""
    skill_dir = _make_skill(
        tmp_path,
        "sample-skill",
        "No matching heading in SKILL.md.\n",
        sections=["Deep Detail"],
    )
    references = skill_dir / "references"
    references.mkdir()
    (references / "deep.md").write_text(
        f"## Deep Detail\n{_marker(days_ago=10)}\n\nBody.\n", encoding="utf-8"
    )
    report = classify(tmp_path)
    assert report["findings"] == []
    assert report["withheld"] == []
    assert report["examined"]["F07"]["sections"] == 1


def test_unresolvable_heading_is_withheld_not_flagged(tmp_path: Path) -> None:
    """A cataloged heading found nowhere is withheld, not a false F07."""
    _make_skill(
        tmp_path,
        "sample-skill",
        "Nothing here matches.\n",
        sections=["Ghost Section"],
    )
    report = classify(tmp_path)
    assert report["findings"] == []
    assert len(report["withheld"]) == 1
    assert "Ghost Section" in report["withheld"][0]
