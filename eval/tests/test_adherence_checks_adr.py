"""The ADR fragment clauses a decision-making role shares, on violations and on clean sessions."""

from __future__ import annotations

import pytest

from praxion_evals.adherence.checks_adr import (
    CATEGORY,
    CITED,
    DISCONFIRMATION,
    FILE_NAME,
    ID_FROM_NAME,
    NO_NUMBER,
    adr_row,
    derived_id,
    frontmatter_field,
)
from praxion_evals.adherence.checks_common import (
    ArtifactJudgedCheck,
    judge_check,
    synthetic_evidence,
)
from praxion_evals.adherence.model import Failed, NotApplicable, Passed, Withheld

ROLE = "systems-architect"
SLUG = "adr-task"
NAME = "20261011-0930-fixture-main-cache-layer.md"
DRAFT = f".ai-state/decisions/drafts/{NAME}"
LEARNINGS = f".ai-work/{SLUG}/LEARNINGS.md"
DISCONFIRMED = (
    "\n## Disconfirmation\n\n- **Falsifier**: a miss rate above 40%.\n"
    "- **Steelmanned runner-up**: no cache.\n- **Reversal trigger**: traffic halves.\n"
)


def _text(adr_id: str, category: str = "implementation", body: str = "") -> str:
    return f"---\nid: {adr_id}\ncategory: {category}\n---\n\n## Context\nx\n{body}"


def _clause(template: str, role: str = ROLE):
    return next(c for c in adr_row(role) if c.name == template.format(role=role))


def _outcome(template: str, files: dict[str, str], role: str = ROLE):
    return _clause(template, role).evaluate(synthetic_evidence(role, slug=SLUG, files=files))


GOOD = _text(derived_id(NAME), "architectural", DISCONFIRMED)


def test_a_sound_fragment_cited_in_the_learnings_passes_every_mechanical_clause():
    files = {DRAFT: GOOD, LEARNINGS: f"### Decisions Made\n\n- Cache ({derived_id(NAME)})\n"}

    for template in (FILE_NAME, ID_FROM_NAME, NO_NUMBER, DISCONFIRMATION, CITED):
        assert _outcome(template, files) == Passed(), template


def test_a_session_that_wrote_no_fragment_is_not_applicable_on_every_clause():
    evidence = synthetic_evidence(ROLE, slug=SLUG)
    for check in adr_row(ROLE):
        judged = isinstance(check, ArtifactJudgedCheck)
        outcome = judge_check(check, evidence, None) if judged else check.evaluate(evidence)
        assert isinstance(outcome, NotApplicable), check.name


def test_a_fragment_with_no_judge_leaves_the_category_withheld():
    evidence = synthetic_evidence(ROLE, slug=SLUG, files={DRAFT: GOOD})

    assert isinstance(judge_check(_clause(CATEGORY), evidence, None), Withheld)


def test_every_clause_names_its_role_and_the_row_has_six_clauses():
    names = [c.name for c in adr_row("implementation-planner")]

    assert len(names) == 6
    assert all(name.startswith("implementation-planner: ") for name in names)


def test_a_file_name_that_is_not_a_timestamped_slug_fails():
    files = {".ai-state/decisions/drafts/cache-layer.md": GOOD}

    assert isinstance(_outcome(FILE_NAME, files), Failed)


def test_an_id_that_is_not_the_hash_of_the_file_name_fails_and_says_what_it_should_be():
    outcome = _outcome(
        ID_FROM_NAME,
        {DRAFT: _text("dec-draft-0badc0de")},  # id-citation-discipline:ignore
    )  # id-citation-discipline:ignore

    assert isinstance(outcome, Failed)
    assert derived_id(NAME) in outcome.detail


@pytest.mark.parametrize(
    "files",
    [
        {DRAFT: _text("dec-901")},
        {".ai-state/decisions/901-cache-layer.md": _text("dec-901")},
    ],
)
def test_a_self_assigned_number_fails_in_a_draft_and_as_a_numbered_record(files):
    assert isinstance(_outcome(NO_NUMBER, files), Failed)


def test_an_architectural_fragment_without_the_three_sub_items_fails():
    partial = _text(derived_id(NAME), "architectural", "\n## Disconfirmation\n\n**Falsifier**: x\n")

    outcome = _outcome(DISCONFIRMATION, {DRAFT: partial})

    assert isinstance(outcome, Failed)
    assert "Steelmanned runner-up" in outcome.detail
    assert "Falsifier" not in outcome.detail


def test_a_fragment_of_another_category_needs_no_disconfirmation():
    outcome = _outcome(DISCONFIRMATION, {DRAFT: _text(derived_id(NAME), "behavioral")})

    assert isinstance(outcome, NotApplicable)


@pytest.mark.parametrize(
    "learnings",
    [
        None,
        "### Gotchas\n\nx\n",
        "### Decisions Made\n\n- Cache (dec-draft-00000000)\n",  # id-citation-discipline:ignore
    ],  # id-citation-discipline:ignore
)
def test_learnings_that_do_not_cite_the_draft_id_under_decisions_made_fail(learnings):
    files = {DRAFT: GOOD, **({LEARNINGS: learnings} if learnings else {})}

    assert isinstance(_outcome(CITED, files), Failed)


def test_the_category_clause_is_judged_and_does_not_apply_without_a_fragment():
    check = _clause(CATEGORY)

    assert isinstance(check, ArtifactJudgedCheck)
    assert not check.produced(synthetic_evidence(ROLE, slug=SLUG))
    assert check.produced(synthetic_evidence(ROLE, slug=SLUG, files={DRAFT: GOOD}))


def test_the_golden_cases_differ_only_in_the_category_the_judge_must_catch():
    check = _clause(CATEGORY)

    assert "category: architectural" in check.golden_bad_case
    assert "category: behavioral" in check.golden_good_case
    assert check.golden_bad_case.replace("architectural", "behavioral") == check.golden_good_case


@pytest.mark.parametrize(
    ("text", "key", "expected"),
    [
        (
            "---\nid: dec-draft-1234abcd\n---\n",  # id-citation-discipline:ignore
            "id",
            "dec-draft-1234abcd",  # id-citation-discipline:ignore
        ),  # id-citation-discipline:ignore
        (
            '---\nid: "dec-draft-1234abcd"\n---\n',  # id-citation-discipline:ignore
            "id",
            "dec-draft-1234abcd",  # id-citation-discipline:ignore
        ),  # id-citation-discipline:ignore
        ("---\nid:\n---\n", "id", None),
        ("no frontmatter\nid: x\n", "id", None),
    ],
)
def test_frontmatter_fields_are_read_from_the_leading_block_only(text, key, expected):
    assert frontmatter_field(text, key) == expected
