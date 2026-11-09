"""Every section and part the two process rules held at the pipeline base is still in its
file, and the audience manifest still classifies each one: the split lives only in what a
split recipient receives.
"""

from __future__ import annotations

import subprocess

import pytest
import yaml

from tests.acceptance.drivers import audience_split as split
from tests.acceptance.drivers.audience_split import AUDIENCE_MANIFEST, REPO_ROOT, SPLIT_UNITS

pytestmark = pytest.mark.skipif(
    not split.base_commit_available(),
    reason=f"the base commit {split.BASE_COMMIT} is not in this clone's history (shallow clone); "
    "fetch full history to compare the rules with the base",
)


def _at_base(rel: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show", f"{split.BASE_COMMIT}:{rel}"],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout


def _headings(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.startswith(("## ", "### ", "#### "))]


def _base_entries(unit: split.Unit) -> list[dict]:
    entries = yaml.safe_load(_at_base(AUDIENCE_MANIFEST))["entries"]
    return [e for e in entries if e["source"] == unit.source]


@pytest.mark.parametrize("unit", SPLIT_UNITS, ids=lambda u: u.id)
def test_every_section_heading_at_the_base_is_still_in_the_rule(unit: split.Unit) -> None:
    now = _headings((REPO_ROOT / unit.source).read_text(encoding="utf-8"))

    assert [h for h in _headings(_at_base(unit.source)) if h not in now] == []


@pytest.mark.parametrize("unit", SPLIT_UNITS, ids=lambda u: u.id)
def test_every_part_at_the_base_still_begins_a_line_of_the_rule(unit: split.Unit) -> None:
    lines = (REPO_ROOT / unit.source).read_text(encoding="utf-8").splitlines()
    prefixes = [e["part"] for e in _base_entries(unit) if e.get("part")]

    assert [p for p in prefixes if not any(ln.startswith(p) for ln in lines)] == []


@pytest.mark.parametrize("unit", SPLIT_UNITS, ids=lambda u: u.id)
def test_the_audience_manifest_still_classifies_every_section_and_part_of_the_base(
    unit: split.Unit,
) -> None:
    now = {(e["heading"], e.get("part")) for e in split.audience_entries(REPO_ROOT, unit) or []}

    assert [
        (e["heading"], e.get("part"))
        for e in _base_entries(unit)
        if (e["heading"], e.get("part")) not in now
    ] == []
