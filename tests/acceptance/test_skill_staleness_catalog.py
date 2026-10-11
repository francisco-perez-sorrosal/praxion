"""The skill-authoring skill's drift-prone sections are tracked, and an untracked one is visible.

Every title the skill catalogs resolves to a heading with a dated marker, and the facts most
likely to drift are cataloged. A cataloged title whose heading is gone stays listed as withheld
by the staleness checker, and the sentinel and the refresh skill describe that outcome alike.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers.skill_pages import REPO_ROOT, read
from tests.acceptance.drivers.staleness_catalog import (
    catalog,
    findings_for,
    marker_below,
    resolve,
    run_checker,
    withheld_for,
)

SKILL = "skill-crafting"
SKILL_DIR = REPO_ROOT / "skills" / SKILL


@pytest.fixture(scope="module")
def repository_envelope() -> dict:
    return run_checker()


# --- the refreshed skill starts its staleness window current -----------------------------------


@pytest.mark.parametrize("check", ["F07", "F09"])
def test_the_staleness_checker_reports_no_missing_or_malformed_marker_for_the_skill(
    repository_envelope, check
):
    found = [f for f in findings_for(repository_envelope, SKILL) if f.get("check") == check]

    assert not found, found


def test_the_staleness_checker_withholds_no_cataloged_title_of_the_skill(repository_envelope):
    assert not withheld_for(repository_envelope, SKILL)


@pytest.mark.parametrize("title", catalog(SKILL_DIR))
def test_each_cataloged_title_resolves_to_a_heading_with_a_dated_marker(title):
    found = resolve(SKILL_DIR, title)

    assert found is not None, (
        f"{title!r} matches no h2/h3 heading on the entry, reference or context pages"
    )
    marker = marker_below(*found)
    assert marker is not None, f"{title!r} carries no last-verified marker"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", marker), (
        f"{title!r} carries marker {marker!r}, not a verification date"
    )


DRIFT_PRONE_FACTS = {
    "the frontmatter field set": r"field|frontmatter|schema|superset",
    "the runtime lifecycle facts": r"lifecycle|runtime",
    "argument substitution": r"argument",
    "per-host portability": r"portab|host",
    "the plugin eval runner": r"\beval",
}


@pytest.mark.parametrize("fact", sorted(DRIFT_PRONE_FACTS))
def test_each_section_stating_a_drift_prone_external_fact_is_cataloged(fact):
    titles = catalog(SKILL_DIR)

    assert any(re.search(DRIFT_PRONE_FACTS[fact], t, re.I) for t in titles), (
        f"no cataloged title covers {fact}: {titles}"
    )


# --- a cataloged title whose heading is gone ---------------------------------------------------


def scratch_skill_with_a_vanished_heading(tmp_path):
    skill_dir = tmp_path / "skills" / "drift-probe"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: drift-probe\ndescription: Use when probing staleness tracking.\n"
        'staleness_sensitive_sections:\n  - "Kept Heading"\n  - "Vanished Heading"\n---\n'
        "# Drift Probe\n\n## Kept Heading\n<!-- last-verified: permanent -->\n\nStill here.\n",
        encoding="utf-8",
    )
    return tmp_path


def test_a_cataloged_title_with_no_heading_is_listed_as_withheld_not_as_a_missing_marker(tmp_path):
    envelope = run_checker(scratch_skill_with_a_vanished_heading(tmp_path))
    f07 = [
        f
        for f in findings_for(envelope, "drift-probe")
        if "Vanished Heading" in f.get("entity", "")
    ]

    assert any(
        w.startswith("drift-probe::Vanished Heading") for w in withheld_for(envelope, "drift-probe")
    )
    assert not f07, f07


def staleness_rows() -> str:
    lines = read(REPO_ROOT / "agents" / "sentinel.md").splitlines()
    rows = [ln for ln in lines if re.match(r"^\|\s*F0[78]\s*\|", ln)]
    if len(rows) != 2:
        raise AssertionError(
            f"expected the F07 and F08 rows in the sentinel definition, found {rows}"
        )
    return " ".join(rows).replace("`", "")


def test_the_sentinel_staleness_rows_say_where_an_unresolved_title_surfaces():
    rows = staleness_rows()

    assert re.search(r"withheld", rows), "neither the F07 nor the F08 row names the withheld list"


def test_the_sentinel_staleness_rows_report_an_unresolved_title_as_a_likely_rename_or_deletion():
    rows = staleness_rows()

    assert re.search(r"renam", rows, re.I), rows
    assert re.search(r"delet", rows, re.I), rows


# --- the refresh skill gives the same account --------------------------------------------------


def refresh_skill() -> str:
    return read(REPO_ROOT / "skills" / "refresh-skill" / "SKILL.md").replace("`", "")


def no_heading_paragraph() -> str:
    paragraphs = re.split(r"\n\s*\n", refresh_skill())
    matching = [
        p
        for p in paragraphs
        if re.search(r"no matching heading|not found|matches no heading", p, re.I)
    ]
    if not matching:
        raise AssertionError("the refresh skill never says what happens to a title with no heading")
    return matching[0]


def test_the_refresh_skill_reports_a_title_with_no_heading_as_rename_or_deletion_drift_and_skips_it():
    paragraph = no_heading_paragraph()

    assert re.search(r"renam", paragraph, re.I), paragraph
    assert re.search(r"delet", paragraph, re.I), paragraph
    assert re.search(r"skip", paragraph, re.I), paragraph


def test_the_refresh_skill_says_the_sentinel_surfaces_that_title_where_the_sentinel_says_it_does():
    paragraph = no_heading_paragraph()

    assert re.search(r"sentinel", paragraph, re.I), paragraph
    assert re.search(r"withheld", paragraph), (
        f"the refresh skill does not name the withheld list: {paragraph}"
    )


@pytest.mark.parametrize("where", ["references/", "contexts/"])
def test_the_refresh_skill_still_locates_cataloged_sections_beyond_the_entry_page(where):
    assert where in refresh_skill()


def test_the_refresh_skill_still_never_bumps_a_marker_without_the_authors_explicit_choice():
    text = refresh_skill()

    assert re.search(r"never (modify|bump|change)[^.]*marker[^.]*explicit", text, re.I), (
        "no sentence forbids a marker change without the author's explicit choice"
    )
