"""Canaries for the decision-record gate's pure core (`_decision_records.py`).

Every refused shape has a test that names the defect it must get, and every allowed shape has a
test that proves silence, so a judge that refuses everything or nothing fails here. The name and
id predicates are also held equal to finalize's own, so the gate refuses what finalize would
strand. Nothing touches the disk outside `tmp_path`.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import _decision_records as gate  # noqa: E402 -- after sys.path insertion
import finalize_adrs  # noqa: E402
import finalize_adrs_fragments  # noqa: E402
from _decision_records import (  # noqa: E402
    Allowed,
    Change,
    Context,
    Defect,
    Read,
    Refused,
)

DRAFTS = ".ai-state/decisions/drafts"
DECISIONS = ".ai-state/decisions"
FRAGMENT = "20261029-1430-fixture-person-record-storage-choice-adopt-sqlite.md"
DRAFT_PATH = f"{DRAFTS}/{FRAGMENT}"
DRAFT_HASH = "3f9a0c1e"


def draft_id(hash_: str = DRAFT_HASH) -> str:
    return f"dec-draft-{hash_}"


DRAFT_ID = draft_id()

ON_MAIN = Context(on_main=True, default_holds=frozenset())
ON_BRANCH = Context(on_main=False, default_holds=frozenset())


def record(id_: str | None = DRAFT_ID, category: str | None = "behavioral") -> str:
    fields = [f"id: {id_}"] if id_ is not None else []
    fields += ["title: Adopt SQLite", "status: proposed"]
    fields += [f"category: {category}"] if category is not None else []
    return "---\n" + "\n".join(fields) + "\n---\n\n# Adopt SQLite\n\nBody text.\n"


def created(path: str, text: str, context: Context = ON_BRANCH):
    return gate.judge_change(Change(path, None, text), context)


def edited(path: str, before: str, after: str, context: Context = ON_BRANCH):
    return gate.judge_change(Change(path, before, after), context)


def defects_of(verdict) -> tuple:
    assert isinstance(verdict, Refused), f"expected a refusal, got {verdict}"
    return verdict.defects


# -- Path classification: every path maps to exactly one variant -----------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/app.py", gate.Outside()),
        (".ai-state/TECH_DEBT_LEDGER.md", gate.Outside()),
        (".ai-state/decisions", gate.Outside()),
        ("../.ai-state/decisions/x.md", gate.Outside()),
        (f"{DECISIONS}/DECISIONS_INDEX.md", gate.NonRecord()),
        (f"{DECISIONS}/CLAUDE.md", gate.NonRecord()),
        (f"{DRAFTS}/CLAUDE.md", gate.NonRecord()),
        (f"{DECISIONS}/README.md", gate.NonRecord()),
        (f"{DRAFTS}/.finalize.lock", gate.NonRecord()),
        (f"{DECISIONS}/archive/CLAUDE.md", gate.NonRecord()),
        (DRAFT_PATH, gate.Draft(FRAGMENT)),
        (f"{DECISIONS}/041-keep-orders.md", gate.TopLevel("041-keep-orders.md")),
        (f"{DECISIONS}/archive/{FRAGMENT}", gate.Nested("archive", FRAGMENT)),
        (f"{DRAFTS}/old/{FRAGMENT}", gate.Nested("drafts/old", FRAGMENT)),
    ],
)
def test_a_path_maps_to_its_one_variant(path, expected):
    assert gate.classify_path(path) == expected


@pytest.mark.parametrize(
    "path",
    [
        f"./{DRAFT_PATH}",
        f"{DECISIONS}//drafts/{FRAGMENT}",
        f"{DECISIONS}/../decisions/drafts/{FRAGMENT}",
        f"{DECISIONS}\\drafts\\{FRAGMENT}",
    ],
)
def test_an_unnormalised_spelling_of_a_draft_path_is_still_a_draft(path):
    assert gate.classify_path(path) == gate.Draft(FRAGMENT)


def test_a_directory_traversal_out_of_the_decisions_directory_is_outside():
    assert gate.classify_path(f"{DECISIONS}/../../README.md") == gate.Outside()


def test_an_upper_case_markdown_suffix_is_still_a_record():
    assert gate.classify_path(f"{DECISIONS}/041-keep-orders.MD") == gate.TopLevel(
        "041-keep-orders.MD"
    )


def test_a_differently_cased_decisions_directory_is_still_the_decisions_directory():
    assert gate.classify_path(".AI-State/Decisions/041-x.md") == gate.TopLevel("041-x.md")


# -- Refused shapes -----------------------------------------------------------------------


def test_a_numbered_record_written_in_a_session_is_self_numbered():
    verdict = created(f"{DECISIONS}/043-adopt-sqlite.md", record("dec-043"))
    assert defects_of(verdict) == (Defect.SELF_NUMBERED,)


def test_a_fragment_named_file_outside_the_drafts_directory_is_misplaced():
    verdict = created(f"{DECISIONS}/{FRAGMENT}", record())
    assert defects_of(verdict) == (Defect.MISPLACED,)


def test_a_top_level_file_with_any_other_name_is_misplaced():
    verdict = created(f"{DECISIONS}/adopt-sqlite.md", record())
    assert defects_of(verdict) == (Defect.MISPLACED,)


def test_a_record_in_another_subdirectory_is_nested():
    verdict = created(f"{DECISIONS}/archive/{FRAGMENT}", record())
    assert defects_of(verdict) == (Defect.NESTED,)


def test_a_record_in_a_subdirectory_of_the_drafts_directory_is_nested():
    verdict = created(f"{DRAFTS}/old/{FRAGMENT}", record())
    assert defects_of(verdict) == (Defect.NESTED,)


def test_a_draft_without_the_fragment_name_is_malformed_named():
    verdict = created(f"{DRAFTS}/adopt-sqlite-for-the-cache.md", record())
    assert defects_of(verdict) == (Defect.MALFORMED_NAME,)


def test_a_draft_whose_stamp_is_no_real_date_is_malformed_named():
    name = "20261399-2599-fixture-person-branch-slug.md"
    assert defects_of(created(f"{DRAFTS}/{name}", record())) == (Defect.MALFORMED_NAME,)


def test_a_draft_with_too_few_name_tokens_is_malformed_named():
    name = "20261029-1430-user-slug.md"
    assert defects_of(created(f"{DRAFTS}/{name}", record())) == (Defect.MALFORMED_NAME,)


def test_a_draft_named_with_a_record_number_is_malformed_named():
    verdict = created(f"{DRAFTS}/043-adopt-sqlite.md", record())
    assert defects_of(verdict) == (Defect.MALFORMED_NAME,)


def test_a_draft_with_a_hash_that_is_not_eight_lowercase_hex_is_malformed_id():
    verdict = created(DRAFT_PATH, record("dec-draft-XYZ"))
    assert defects_of(verdict) == (Defect.MALFORMED_ID,)


def test_a_draft_with_no_id_is_malformed_id():
    assert defects_of(created(DRAFT_PATH, record(id_=None))) == (Defect.MALFORMED_ID,)


def test_a_draft_with_a_quoted_id_is_malformed_id_because_finalize_would_strand_it():
    verdict = created(DRAFT_PATH, record(f'"{DRAFT_ID}"'))
    assert defects_of(verdict) == (Defect.MALFORMED_ID,)


def test_a_draft_with_no_frontmatter_at_all_is_malformed_id_and_has_no_category():
    verdict = created(DRAFT_PATH, f"# Adopt SQLite\n\nid: {DRAFT_ID}\n")
    assert defects_of(verdict) == (Defect.MALFORMED_ID, Defect.NO_CATEGORY)


def test_a_draft_with_a_self_picked_number_is_self_picked_id():
    verdict = created(DRAFT_PATH, record("dec-043"))
    assert defects_of(verdict) == (Defect.SELF_PICKED_ID,)


def test_a_new_record_with_no_category_is_refused():
    verdict = created(DRAFT_PATH, record(category=None))
    assert defects_of(verdict) == (Defect.NO_CATEGORY,)


def test_a_new_record_with_an_empty_category_is_refused_as_missing():
    assert defects_of(created(DRAFT_PATH, record(category=""))) == (Defect.NO_CATEGORY,)


@pytest.mark.parametrize("category", ["strategic", "Architectural", "architectural, behavioral"])
def test_a_new_record_with_a_category_outside_the_four_is_refused(category):
    verdict = created(DRAFT_PATH, record(category=category))
    assert defects_of(verdict) == (Defect.INVALID_CATEGORY,)


def test_a_misplaced_record_with_no_category_carries_both_defects():
    verdict = created(f"{DECISIONS}/043-adopt-sqlite.md", record("dec-043", category=None))
    assert defects_of(verdict) == (Defect.SELF_NUMBERED, Defect.NO_CATEGORY)


def test_a_refusal_names_the_path_it_refused():
    verdict = created(f"{DECISIONS}/043-adopt-sqlite.md", record("dec-043"))
    assert verdict.path == f"{DECISIONS}/043-adopt-sqlite.md"


# -- Allowed shapes -----------------------------------------------------------------------


@pytest.mark.parametrize("category", list(gate.CATEGORIES))
def test_a_conforming_draft_is_allowed_with_each_valid_category(category):
    assert created(DRAFT_PATH, record(category=category)) == Allowed()


@pytest.mark.parametrize("spelling", ['"behavioral"', "'behavioral'", "behavioral  # why"])
def test_a_quoted_or_commented_category_is_read_as_its_value(spelling):
    assert created(DRAFT_PATH, record(category=spelling)) == Allowed()


def test_a_crlf_draft_is_read_like_an_lf_draft():
    assert created(DRAFT_PATH, record().replace("\n", "\r\n")) == Allowed()


@pytest.mark.parametrize(
    "path",
    [
        f"{DECISIONS}/DECISIONS_INDEX.md",
        f"{DECISIONS}/CLAUDE.md",
        f"{DRAFTS}/CLAUDE.md",
        f"{DECISIONS}/archive/CLAUDE.md",
        f"{DRAFTS}/.finalize.lock",
        "src/app.py",
        ".ai-state/TECH_DEBT_LEDGER.md",
    ],
)
def test_a_file_that_is_no_record_is_allowed_whatever_it_holds(path):
    assert created(path, "no frontmatter, no category\n") == Allowed()


def test_the_write_time_context_never_allows_a_numbered_record():
    path = f"{DECISIONS}/043-adopt-sqlite.md"
    verdict = gate.judge_change(Change(path, None, record("dec-043")), gate.WRITE_TIME_CONTEXT)
    assert defects_of(verdict) == (Defect.SELF_NUMBERED,)


# -- Existing records: debt is not judged -------------------------------------------------

OLDER_PATH = f"{DECISIONS}/041-keep-orders-in-postgres.md"
OLDER_NO_CATEGORY = record("dec-041", category=None)


def test_a_status_flip_on_an_older_record_without_category_is_allowed():
    after = OLDER_NO_CATEGORY.replace("proposed", "accepted")
    assert edited(OLDER_PATH, OLDER_NO_CATEGORY, after) == Allowed()


def test_a_cross_reference_edit_on_a_record_with_a_valid_category_is_allowed():
    before = record("dec-041", "architectural")
    assert edited(OLDER_PATH, before, before + "superseded_by: dec-050\n") == Allowed()


def test_an_existing_misplaced_record_is_not_judged_for_placement_name_or_id():
    path = f"{DECISIONS}/archive/old-notes.md"
    before = record("whatever", category=None)
    assert edited(path, before, before + "\nmore\n") == Allowed()


def test_an_existing_record_that_already_had_an_invalid_category_may_be_edited():
    before = record("dec-041", "strategic")
    assert edited(OLDER_PATH, before, before + "\nmore\n") == Allowed()


def test_an_edit_that_removes_a_valid_category_is_category_lost():
    before = record("dec-041", "behavioral")
    after = record("dec-041", category=None)
    assert defects_of(edited(OLDER_PATH, before, after)) == (Defect.CATEGORY_LOST,)


def test_an_edit_that_invalidates_a_valid_category_is_category_lost():
    before = record("dec-041", "behavioral")
    after = record("dec-041", "strategic")
    assert defects_of(edited(OLDER_PATH, before, after)) == (Defect.CATEGORY_LOST,)


def test_an_edit_that_changes_one_valid_category_to_another_is_allowed():
    before = record("dec-041", "behavioral")
    assert edited(OLDER_PATH, before, record("dec-041", "architectural")) == Allowed()


def test_an_edit_that_gives_a_record_its_first_category_is_allowed():
    assert edited(OLDER_PATH, OLDER_NO_CATEGORY, record("dec-041", "behavioral")) == Allowed()


def test_rewriting_an_existing_draft_without_its_category_is_category_lost():
    before = record(category="configuration")
    assert defects_of(edited(DRAFT_PATH, before, record(category=None))) == (Defect.CATEGORY_LOST,)


@pytest.mark.parametrize("empty", ["", "\n", "  \n\t\n"])
def test_a_write_over_an_empty_existing_file_is_judged_as_a_creation(empty):
    assert defects_of(edited(DRAFT_PATH, empty, record(id_="dec-043", category=None))) == (
        Defect.SELF_PICKED_ID,
        Defect.NO_CATEGORY,
    )


# -- Numbered records at commit time ------------------------------------------------------


def test_a_numbered_record_added_on_main_is_allowed():
    path = f"{DECISIONS}/043-adopt-sqlite.md"
    assert created(path, record("dec-043", category=None), ON_MAIN) == Allowed()


def test_a_numbered_record_the_default_branch_already_holds_is_allowed_on_a_branch():
    path = f"{DECISIONS}/041-keep-orders-in-postgres.md"
    held = Context(on_main=False, default_holds=frozenset({path}))
    assert created(path, OLDER_NO_CATEGORY, held) == Allowed()


def test_a_numbered_record_the_default_branch_does_not_hold_is_refused_on_a_branch():
    path = f"{DECISIONS}/043-adopt-sqlite.md"
    other = Context(on_main=False, default_holds=frozenset({f"{DECISIONS}/041-x.md"}))
    assert defects_of(created(path, record("dec-043"), other)) == (Defect.SELF_NUMBERED,)


def test_main_does_not_excuse_a_misplaced_fragment():
    verdict = created(f"{DECISIONS}/{FRAGMENT}", record(), ON_MAIN)
    assert defects_of(verdict) == (Defect.MISPLACED,)


def test_main_does_not_excuse_a_malformed_draft():
    verdict = created(f"{DRAFTS}/adopt.md", record(), ON_MAIN)
    assert defects_of(verdict) == (Defect.MALFORMED_NAME,)


# -- Reads ------------------------------------------------------------------------------


def test_a_whole_read_of_the_decisions_index_is_refused():
    verdict = gate.judge_read(Read(f"{DECISIONS}/DECISIONS_INDEX.md", bounded=False))
    assert defects_of(verdict) == (Defect.UNBOUNDED_INDEX_READ,)


def test_a_differently_cased_spelling_of_the_index_is_still_refused_when_unbounded():
    verdict = gate.judge_read(Read(f"{DECISIONS}/decisions_index.md", bounded=False))
    assert defects_of(verdict) == (Defect.UNBOUNDED_INDEX_READ,)


def test_a_bounded_read_of_the_decisions_index_is_allowed():
    assert gate.judge_read(Read(f"{DECISIONS}/DECISIONS_INDEX.md", bounded=True)) == Allowed()


@pytest.mark.parametrize(
    "path",
    [
        f"{DECISIONS}/041-keep-orders-in-postgres.md",
        DRAFT_PATH,
        "docs/DECISIONS_INDEX.md",
        f"{DECISIONS}/archive/DECISIONS_INDEX.md",
        "src/app.py",
    ],
)
def test_a_whole_read_of_any_other_file_is_allowed(path):
    assert gate.judge_read(Read(path, bounded=False)) == Allowed()


# -- The verdict type ---------------------------------------------------------------------


def test_a_refusal_with_no_defect_cannot_be_built():
    with pytest.raises(ValueError, match="at least one defect"):
        Refused("x.md", ())


def test_deciding_on_no_defects_is_allowed_and_on_some_is_refused():
    assert gate.decide("x.md", ()) == Allowed()
    assert gate.decide("x.md", (Defect.NESTED,)) == Refused("x.md", (Defect.NESTED,))


def test_the_defect_vocabulary_is_the_closed_set_consumers_key_on():
    assert sorted(d.value for d in Defect) == sorted(
        [
            "misplaced",
            "nested",
            "self-numbered",
            "malformed-name",
            "malformed-id",
            "self-picked-id",
            "no-category",
            "invalid-category",
            "category-lost",
            "unbounded-index-read",
        ]
    )


# -- Frontmatter reading ------------------------------------------------------------------


def test_the_first_occurrence_of_a_key_wins():
    front = gate.read_frontmatter(
        f"---\nid: {draft_id('aaaaaaaa')}\nid: {draft_id('bbbbbbbb')}\n---\n"
    )
    assert front.id == draft_id("aaaaaaaa")


def test_a_key_after_the_closing_fence_is_not_frontmatter():
    front = gate.read_frontmatter("---\ntitle: x\n---\ncategory: behavioral\n")
    assert front.category is None


def test_an_indented_key_is_not_a_top_level_field():
    assert gate.read_frontmatter("---\nmeta:\n  category: behavioral\n---\n").category is None


def test_a_byte_order_mark_before_the_fence_leaves_no_fields_as_the_index_generator_reads_it():
    assert gate.read_frontmatter("﻿---\ncategory: behavioral\n---\n") == gate.Frontmatter(None, None)


def test_a_frontmatter_block_never_closed_has_no_fields():
    unclosed = f"---\nid: {draft_id('aaaaaaaa')}\ncategory: behavioral\n"
    assert gate.read_frontmatter(unclosed) == gate.Frontmatter(None, None)


# -- Parity with finalize: the gate refuses exactly what finalize would strand ------------

NAME_TABLE = [
    FRAGMENT,
    "20261029-1430-u-b-s.md",
    "20261029-1430-user-slug.md",
    "20261029-1430-user.md",
    "20261029-1430-.md",
    "20261029-1430-u-b-s-.md",
    "20261029-1430-U-b-s.md",
    "20261029-1430-u_b-s.md",
    "20261029-1430-u.b-s.md",
    "20261399-2599-u-b-s.md",
    "20260230-1430-u-b-s.md",
    "20261029-2460-u-b-s.md",
    "2026102-1430-u-b-s.md",
    "202610299-1430-u-b-s.md",
    "20261029-143-u-b-s.md",
    "20261029-1430-u-b-s.txt",
    "20261029-1430-u-b-s",
    "043-adopt-sqlite.md",
    "adopt-sqlite-for-the-cache.md",
    "",
]


def finalize_promotes(name: str, tmp_path: Path) -> bool:
    """True iff finalize's own detection and parser accept the fragment name."""
    if not finalize_adrs.FRAGMENT_ADR_PATTERN.match(name):
        return False
    try:
        finalize_adrs_fragments.parse_fragment_filename(
            tmp_path / name,
            user_slug_hint=lambda: None,
            branch_slug_hint=lambda: None,
        )
    except ValueError:
        return False
    return True


@pytest.mark.parametrize("name", NAME_TABLE)
def test_the_fragment_name_predicate_equals_finalizes(name, tmp_path):
    gate_accepts = isinstance(gate.classify_name(name), gate.Fragment)
    assert gate_accepts == finalize_promotes(name, tmp_path)


@pytest.mark.parametrize(
    "name", ["041-keep-orders.md", "043-x.md", "1000-x.md", "04-x.md", "041.md"]
)
def test_the_numbered_name_predicate_equals_finalizes(name):
    gate_accepts = isinstance(gate.classify_name(name), gate.Numbered)
    assert gate_accepts == bool(finalize_adrs.FINALIZED_ADR_PATTERN.match(name))


ID_TABLE = [
    DRAFT_ID,
    draft_id("3F9A0C1E"),
    "dec-draft-3f9a0c1",
    "dec-draft-3f9a0c1ee",
    "dec-draft-XYZ",
    "dec-draft-",
    "dec-043",
    "dec-0430",
    f'"{DRAFT_ID}"',
    f"{DRAFT_ID} # note",
    "draft-3f9a0c1e",
    "",
]


@pytest.mark.parametrize("value", ID_TABLE)
def test_the_draft_id_predicate_equals_finalizes(value):
    gate_accepts = isinstance(gate.parse_id(value), gate.DraftId)
    finalize_accepts = bool(finalize_adrs.FRONTMATTER_ID_PATTERN.search(f"id: {value}\n"))
    assert gate_accepts == finalize_accepts


# -- Parsed values: the forms carry what they were read from ------------------------------


def test_a_fragment_name_carries_its_stamp():
    assert gate.classify_name(FRAGMENT) == gate.Fragment(datetime(2026, 10, 29, 14, 30))


def test_a_numbered_name_carries_its_number():
    assert gate.classify_name("041-keep-orders.md") == gate.Numbered(41)


def test_any_other_name_carries_its_text():
    assert gate.classify_name("notes.md") == gate.OtherName("notes.md")


def test_a_draft_id_carries_its_hash():
    assert gate.parse_id(DRAFT_ID) == gate.DraftId(DRAFT_HASH)


def test_a_numbered_id_carries_its_number():
    assert gate.parse_id("dec-043") == gate.NumberedId(43)


def test_any_other_id_carries_its_text():
    assert gate.parse_id("whatever") == gate.OtherId("whatever")


def test_an_empty_or_absent_id_is_no_id():
    assert gate.parse_id("") == gate.NoId()
    assert gate.parse_id(None) == gate.NoId()


def test_a_valid_category_carries_its_value():
    assert gate.parse_category("configuration") == gate.ValidCategory("configuration")


def test_an_invalid_category_carries_its_text():
    assert gate.parse_category("strategic") == gate.InvalidCategory("strategic")


def test_an_empty_or_absent_category_is_missing():
    assert gate.parse_category("") == gate.MissingCategory()
    assert gate.parse_category(None) == gate.MissingCategory()


def test_a_refusal_of_a_read_names_the_path_read():
    path = f"{DECISIONS}/DECISIONS_INDEX.md"
    assert gate.judge_read(Read(path, bounded=False)) == Refused(
        path, (Defect.UNBOUNDED_INDEX_READ,)
    )


# -- Frontmatter edges: fences, whitespace, quotes -----------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("---  \ncategory: behavioral\n---\n", "behavioral"),
        ("---\ncategory: behavioral\n---  \ncategory: configuration\n", "behavioral"),
        ("---\ncategory:\tbehavioral\t\n---\n", "behavioral"),
        ("---\ncategory:behavioral\n---\n", "behavioral"),
        ('---\ncategory: ""\n---\n', None),
        ("---\ncategory: ''\n---\n", None),
        ("---\ncategory: # to be decided\n---\n", None),
        ('---\ncategory: "\n---\n', '"'),
        ('---\ncategory: "behavioral\n---\n', '"behavioral'),
        ("---\ncategory: \"behavioral'\n---\n", "\"behavioral'"),
        ("---\ncategory: behavioral # a # b\n---\n", "behavioral"),
        ("category: behavioral\n", None),
        ("", None),
    ],
)
def test_the_category_is_read_the_way_a_yaml_reader_would(text, expected):
    assert gate.read_frontmatter(text).category == expected


def test_an_id_keeps_its_raw_text_so_a_quote_or_comment_reads_as_not_a_draft_id():
    front = gate.read_frontmatter(f'---\nid: "{DRAFT_ID}"\n---\n')
    assert front.id == f'"{DRAFT_ID}"'


def test_a_record_without_a_leading_fence_is_read_as_having_no_fields():
    assert gate.read_frontmatter("title: x\n---\nid: dec-043\n") == gate.Frontmatter(None, None)
