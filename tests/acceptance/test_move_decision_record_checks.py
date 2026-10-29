"""The adr-conventions move's two governed checks grade a planted end state, with no session.

"Decision draft placement" passes when every decision record the session left lies directly
under the draft directory, is named by the fragment schema (a valid date and time, a user, the
fixture's branch, a slug) and carries a draft id of eight hexadecimal characters; it fails
naming once each part that fails, any one able to fail alone. "Decision category" passes when
every record carries one of the four `category` values and every architectural record a
Disconfirmation section naming a falsifier, a steelmanned runner-up and a reversal trigger, in
any letter case; whether the value is the one the rule's test would give is not graded. A
session that left no record leaves nothing to grade on either check. A record written in the
project's older habit fails both; a record written as the rule says passes both. Only the end
state is graded: a record moved into conformance before the end passes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers.decision_kit import (
    CATEGORY_VALUES,
    DECISION_CATEGORY,
    DECISION_CHECKS,
    DECISION_MOVE,
    DRAFT_PLACEMENT,
    MALFORMED_ID,
    MALFORMED_NAME,
    NO_CATEGORY,
    NO_DISCONFIRMATION,
    NO_RECORD_REASON,
    NOT_UNDER_DRAFTS,
    SELF_NUMBERED,
    UNKNOWN_CATEGORY,
    DecisionGrade,
    grade_decision_end_state,
)
from tests.acceptance.drivers.decision_records import (
    DECISIONS_DIR,
    DRAFTS_DIR,
    Planted,
    Record,
    conforming,
    draft_id,
    fragment_name,
    leave,
    leave_then_move,
    numbered_id,
    older_habit,
    planted_project,
    with_changes,
)
from tests.acceptance.drivers.move_eval import Declared, declare


@pytest.fixture(scope="module")
def kit(tmp_path_factory: pytest.TempPathFactory) -> Declared:
    return declare(DECISION_MOVE, "as declared", tmp_path_factory.mktemp("decision-kit"))


@pytest.fixture
def planted(tmp_path: Path) -> Planted:
    return planted_project(tmp_path)


def _grade(kit: Declared, check: str, planted: Planted, *records: Record) -> DecisionGrade:
    leave(planted.project, *records)
    return grade_decision_end_state(kit, check, planted.fixture, planted.project)


# -- Decision draft placement -----------------------------------------------------------------

DRAFT = conforming()
PLACEMENT_STATES = [
    pytest.param(DRAFT, frozenset(), id="a-conforming-draft-fragment"),
    pytest.param(
        with_changes(DRAFT, relpath=f"{DECISIONS_DIR}/{fragment_name()}"),
        {NOT_UNDER_DRAFTS},
        id="a-fragment-at-the-top-of-the-decision-directory",
    ),
    pytest.param(
        with_changes(DRAFT, relpath=f"{DRAFTS_DIR}/2026/{fragment_name()}"),
        {NOT_UNDER_DRAFTS},
        id="a-fragment-in-a-subdirectory-of-the-drafts",
    ),
    pytest.param(
        with_changes(DRAFT, relpath=f"{DRAFTS_DIR}/adopt-sqlite-for-the-cache.md"),
        {MALFORMED_NAME},
        id="a-name-that-is-only-a-slug",
    ),
    pytest.param(
        with_changes(DRAFT, relpath=f"{DRAFTS_DIR}/{fragment_name(stamp='20261329-1430')}"),
        {MALFORMED_NAME},
        id="a-name-whose-date-has-no-thirteenth-month",
    ),
    pytest.param(
        with_changes(DRAFT, relpath=f"{DRAFTS_DIR}/{fragment_name(stamp='20261029-2561')}"),
        {MALFORMED_NAME},
        id="a-name-whose-time-is-no-time-of-day",
    ),
    pytest.param(
        with_changes(DRAFT, relpath=f"{DRAFTS_DIR}/{fragment_name(branch='some-other-branch')}"),
        {MALFORMED_NAME},
        id="a-name-carrying-a-branch-other-than-the-fixtures",
    ),
    pytest.param(with_changes(DRAFT, id=None), {MALFORMED_ID}, id="no-id"),
    pytest.param(
        with_changes(DRAFT, id="adopt-sqlite-for-the-cache"), {MALFORMED_ID}, id="an-id-of-no-form"
    ),
    pytest.param(
        with_changes(DRAFT, id=draft_id("3f9a0c")), {MALFORMED_ID}, id="a-draft-id-of-six-hex"
    ),
    pytest.param(
        with_changes(DRAFT, id=draft_id("zz9a0c1e")), {MALFORMED_ID}, id="a-draft-id-not-hex"
    ),
    pytest.param(
        with_changes(DRAFT, relpath=f"{DRAFTS_DIR}/043-adopt-sqlite-for-the-cache.md"),
        {SELF_NUMBERED},
        id="a-draft-named-by-a-record-number",
    ),
    pytest.param(
        with_changes(DRAFT, id=numbered_id()), {SELF_NUMBERED}, id="a-draft-carrying-a-numbered-id"
    ),
]


@pytest.mark.parametrize(("record", "failing"), PLACEMENT_STATES)
def test_draft_placement_fails_exactly_the_part_a_planted_record_violates(
    kit, planted, record, failing
):
    grade = _grade(kit, DRAFT_PLACEMENT, planted, record)

    assert grade.outcome == ("failed" if failing else "passed"), grade
    assert grade.failed_parts == frozenset(failing), grade


def test_draft_placement_fails_when_one_of_two_records_is_misplaced(kit, planted):
    misplaced = with_changes(
        conforming("not architectural"), relpath=f"{DECISIONS_DIR}/{fragment_name(slug='other')}"
    )

    grade = _grade(kit, DRAFT_PLACEMENT, planted, conforming(), misplaced)

    assert (grade.outcome, grade.failed_parts) == ("failed", {NOT_UNDER_DRAFTS}), grade


def test_a_record_moved_into_conformance_before_the_session_ended_passes_draft_placement(
    kit, planted
):
    first = with_changes(DRAFT, relpath=f"{DECISIONS_DIR}/043-adopt-sqlite-for-the-cache.md")
    leave_then_move(planted.project, first, DRAFT)

    grade = grade_decision_end_state(kit, DRAFT_PLACEMENT, planted.fixture, planted.project)

    assert grade.outcome == "passed", grade


# -- Decision category ------------------------------------------------------------------------

ARCHITECTURAL = conforming("architectural")
CATEGORY_STATES = [
    *[
        pytest.param(with_changes(conforming("not architectural"), category=value), set(), id=value)
        for value in CATEGORY_VALUES
        if value != "architectural"
    ],
    pytest.param(ARCHITECTURAL, set(), id="architectural-with-its-disconfirmation"),
    pytest.param(
        with_changes(
            ARCHITECTURAL,
            category="Architectural",
            disconfirmation_heading="DISCONFIRMATION",
            disconfirmation_items=("FALSIFIER", "steelmanned RUNNER-UP", "Reversal Trigger"),
        ),
        set(),
        id="architectural-in-another-letter-case",
    ),
    pytest.param(
        with_changes(
            conforming("not architectural"),
            title="Split the cache into its own service",
            category="configuration",
        ),
        set(),
        id="a-value-the-rules-test-would-not-give-is-still-one-of-the-four",
    ),
    pytest.param(with_changes(ARCHITECTURAL, category=None), {NO_CATEGORY}, id="no-category"),
    pytest.param(
        with_changes(ARCHITECTURAL, category="strategic"), {UNKNOWN_CATEGORY}, id="unknown"
    ),
    pytest.param(
        with_changes(ARCHITECTURAL, disconfirmation_heading=None),
        {NO_DISCONFIRMATION},
        id="architectural-without-a-disconfirmation-section",
    ),
    *[
        pytest.param(
            with_changes(
                ARCHITECTURAL,
                disconfirmation_items=tuple(
                    i
                    for i in ("Falsifier", "Steelmanned runner-up", "Reversal trigger")
                    if i != gone
                ),
            ),
            {NO_DISCONFIRMATION},
            id=f"a-disconfirmation-without-its-{gone.lower().replace(' ', '-')}",
        )
        for gone in ("Falsifier", "Steelmanned runner-up", "Reversal trigger")
    ],
]


@pytest.mark.parametrize(("record", "failing"), CATEGORY_STATES)
def test_decision_category_fails_exactly_the_part_a_planted_record_violates(
    kit, planted, record, failing
):
    grade = _grade(kit, DECISION_CATEGORY, planted, record)

    assert grade.outcome == ("failed" if failing else "passed"), grade
    assert grade.failed_parts == frozenset(failing), grade


# -- Nothing to grade, the older habit, and the rule followed ---------------------------------


@pytest.mark.parametrize("check", DECISION_CHECKS)
def test_a_session_that_left_no_decision_record_leaves_nothing_to_grade(kit, planted, check):
    grade = _grade(kit, check, planted)

    assert (grade.outcome, grade.reason) == ("nothing to grade", NO_RECORD_REASON), grade


@pytest.mark.parametrize("check", DECISION_CHECKS)
def test_a_markdown_file_left_only_in_the_ephemeral_pipeline_directory_is_no_decision_record(
    kit, planted, check
):
    scratch = with_changes(conforming(), relpath=".ai-work/cache-choice/NOTES.md", id=None)

    grade = _grade(kit, check, planted, scratch)

    assert (grade.outcome, grade.reason) == ("nothing to grade", NO_RECORD_REASON), grade


def test_a_record_in_the_projects_older_habit_fails_draft_placement(kit, planted):
    grade = _grade(kit, DRAFT_PLACEMENT, planted, older_habit())

    assert grade.outcome == "failed", grade
    assert grade.failed_parts == {NOT_UNDER_DRAFTS, SELF_NUMBERED}, grade


def test_a_record_in_the_projects_older_habit_fails_decision_category(kit, planted):
    grade = _grade(kit, DECISION_CATEGORY, planted, older_habit())

    assert (grade.outcome, grade.failed_parts) == ("failed", {NO_CATEGORY}), grade


@pytest.mark.parametrize("check", DECISION_CHECKS)
@pytest.mark.parametrize("sort", ["architectural", "not architectural"])
def test_a_record_written_as_the_rule_says_passes_both_checks_for_either_sort(
    kit, planted, check, sort
):
    grade = _grade(kit, check, planted, conforming(sort))

    assert (grade.outcome, grade.failed_parts) == ("passed", frozenset()), grade
