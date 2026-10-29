"""The decision records a session leaves, read from its end state into closed sum types: file name,
id and category are classified so that a grader can fail one part of the rule alone."""

from __future__ import annotations

import ast
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from praxion_evals.adherence.moves import checks_adr, checks_git, declaration
from praxion_evals.adherence.moves.checks_adr import (
    BRANCH_REF,
    DECISION_CATEGORY,
    DRAFT_PLACEMENT,
    MALFORMED_ID,
    MALFORMED_NAME,
    NO_CATEGORY,
    NO_DISCONFIRMATION,
    NOT_UNDER_DRAFTS,
    SELF_NUMBERED,
    UNKNOWN_CATEGORY,
    DecisionRecord,
    DraftId,
    Fragment,
    NoId,
    NumberedId,
    NumberedName,
    OtherId,
    OtherName,
    baseline_paths,
    branch_segment,
    classify_id,
    classify_name,
    fixture_branch,
    grade,
    grade_records,
    read_records,
)
from praxion_evals.adherence.moves.model import Grade, NothingToGrade

BRANCH = "record-storage-choice"
DRAFTS = ".ai-state/decisions/drafts"
DRAFT_ID = "dec-draft-3f9a0c1e"  # id-citation-discipline:ignore
FRAGMENT = f"20261029-1430-fixture-author-{BRANCH}-adopt-sqlite.md"
LONG_BRANCH = "record-the-storage-choice-for-the-orders-service-cache"
ARCHITECTURAL_BODY = (
    "# Title\n\n## Disconfirmation\n\n- **Falsifier**: x\n"
    "- **Steelmanned runner-up**: y\n- **Reversal trigger**: z\n"
)


def _write(root: Path, path: str, text: str = "# note\n") -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _record(root: Path, path: str, text: str, branch: str = BRANCH) -> DecisionRecord:
    _write(root, path, text)
    (record,) = read_records(root, before=frozenset(), branch=branch)
    return record


# -- Names ------------------------------------------------------------------------------------


def test_a_stamp_user_branch_slug_name_is_a_fragment_carrying_its_stamp():
    assert classify_name(FRAGMENT, BRANCH) == Fragment(
        datetime(2026, 10, 29, 14, 30), f"fixture-author-{BRANCH}-adopt-sqlite"
    )


def test_a_name_led_by_a_record_number_is_a_numbered_name():
    assert classify_name("043-adopt-sqlite.md", BRANCH) == NumberedName(43, "adopt-sqlite")


@pytest.mark.parametrize(
    "filename",
    [
        pytest.param("adopt-sqlite.md", id="only-a-slug"),
        pytest.param("README.md", id="a-readme"),
        pytest.param(f"20261329-1430-fixture-author-{BRANCH}-adopt-sqlite.md", id="month-13"),
        pytest.param(f"20261029-2561-fixture-author-{BRANCH}-adopt-sqlite.md", id="minute-61"),
        pytest.param(
            "20261029-1430-fixture-author-other-branch-adopt-sqlite.md", id="other-branch"
        ),
        pytest.param(f"20261029-1430-{BRANCH}-adopt-sqlite.md", id="no-user-before-the-branch"),
        pytest.param(f"20261029-1430-fixture-author-{BRANCH}-.md", id="no-slug-after-the-branch"),
    ],
)
def test_a_name_that_is_neither_a_fragment_of_the_branch_nor_numbered_is_other(filename):
    assert classify_name(filename, BRANCH) == OtherName(filename)


def test_a_stamp_shaped_name_with_the_wrong_branch_is_other_not_numbered():
    wrong = "20261029-1430-fixture-author-main-adopt-sqlite.md"

    assert classify_name(wrong, BRANCH) == OtherName(wrong)


# -- The branch segment -----------------------------------------------------------------------


def test_the_segment_of_a_slashed_capitalised_branch_is_lowercase_with_one_hyphen_per_run():
    assert branch_segment("Feature/Record_Storage--Choice") == "feature-record-storage--choice"
    assert branch_segment("feat/sub/Task!") == "feat-sub-task"


def test_the_segment_of_a_54_character_branch_is_cut_to_forty():
    assert len(LONG_BRANCH) == 54
    assert branch_segment(LONG_BRANCH) == LONG_BRANCH[:40]


def test_a_name_carrying_the_cut_segment_of_a_long_branch_is_a_fragment():
    cut = branch_segment(LONG_BRANCH)

    assert isinstance(
        classify_name(f"20261029-1430-fixture-author-{cut}-slug.md", LONG_BRANCH), Fragment
    )


def test_a_name_carrying_the_long_branch_uncut_is_other():
    uncut = f"20261029-1430-fixture-author-{LONG_BRANCH}-slug.md"

    assert classify_name(uncut, LONG_BRANCH) == OtherName(uncut)


def test_a_name_carrying_the_segment_of_a_slashed_branch_is_a_fragment():
    name = "20261029-1430-fixture-author-feature-record-storage-slug.md"

    assert isinstance(classify_name(name, "Feature/Record_Storage"), Fragment)


# -- Ids --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "form"),
    [
        pytest.param(DRAFT_ID, DraftId("3f9a0c1e"), id="a-draft-id"),
        pytest.param("dec-043", NumberedId(43), id="a-numbered-id"),
        pytest.param("dec-draft-3f9a0c", OtherId("dec-draft-3f9a0c"), id="six-hex"),
        pytest.param("dec-draft-zz9a0c1e", OtherId("dec-draft-zz9a0c1e"), id="not-hex"),
        pytest.param("adopt-sqlite", OtherId("adopt-sqlite"), id="text-of-no-form"),
        pytest.param(43, OtherId("43"), id="a-bare-number"),
        pytest.param(None, NoId(), id="no-id"),
    ],
)
def test_an_id_is_read_as_exactly_one_form(value, form):
    assert classify_id(value) == form


# -- Records ----------------------------------------------------------------------------------


def test_a_record_in_the_draft_directory_reads_its_name_id_category_and_disconfirmation(tmp_path):
    text = f"---\nid: {DRAFT_ID}\ncategory: architectural\n---\n{ARCHITECTURAL_BODY}"

    record = _record(tmp_path, f"{DRAFTS}/{FRAGMENT}", text)

    assert record == DecisionRecord(
        path=f"{DRAFTS}/{FRAGMENT}",
        in_drafts=True,
        name=classify_name(FRAGMENT, BRANCH),
        id=DraftId("3f9a0c1e"),
        category="architectural",
        disconfirmed=True,
    )


@pytest.mark.parametrize(
    ("path", "in_drafts"),
    [
        pytest.param(f"{DRAFTS}/{FRAGMENT}", True, id="directly-under-the-drafts"),
        pytest.param(f".ai-state/decisions/{FRAGMENT}", False, id="top-of-the-decision-directory"),
        pytest.param(f"{DRAFTS}/2026/{FRAGMENT}", False, id="a-subdirectory-of-the-drafts"),
    ],
)
def test_a_record_is_in_drafts_only_directly_under_the_draft_directory(tmp_path, path, in_drafts):
    assert _record(tmp_path, path, "---\nid: x\n---\n").in_drafts is in_drafts


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("no frontmatter at all\n", id="no-frontmatter"),
        pytest.param("---\nid: [unclosed\n---\nbody\n", id="yaml-that-does-not-parse"),
        pytest.param("---\n- a\n- list\n---\n", id="frontmatter-that-is-no-mapping"),
        pytest.param(f"---\nid: {DRAFT_ID}\nno closing fence\n", id="an-unclosed-fence"),
    ],
)
def test_frontmatter_that_cannot_be_read_is_no_id_and_no_category(tmp_path, text):
    record = _record(tmp_path, f"{DRAFTS}/{FRAGMENT}", text)

    assert (record.id, record.category) == (NoId(), None)


def test_a_category_written_in_any_case_is_kept_as_written(tmp_path):
    record = _record(tmp_path, f"{DRAFTS}/{FRAGMENT}", "---\ncategory: Architectural\n---\n")

    assert record.category == "Architectural"


@pytest.mark.parametrize(
    ("body", "disconfirmed"),
    [
        pytest.param(ARCHITECTURAL_BODY, True, id="all-three-items"),
        pytest.param(ARCHITECTURAL_BODY.upper(), True, id="any-letter-case"),
        pytest.param(
            "## Disconfirmation\n- Falsifier: x\n- Reversal trigger: z\n", False, id="no-runner-up"
        ),
        pytest.param(
            "## Consequences\n- Falsifier: x\n- Steelmanned runner-up\n- Reversal trigger\n",
            False,
            id="items-outside-the-section",
        ),
        pytest.param(
            "## Disconfirmation\n- Falsifier\n## Next\n- Steelmanned runner-up\n- Reversal trigger\n",
            False,
            id="items-past-the-next-heading",
        ),
        pytest.param(
            "## Disconfirmation\n### Falsifier\nx\n### Steelmanned runner-up\ny\n### Reversal trigger\nz\n",
            True,
            id="items-as-subheadings",
        ),
        pytest.param(
            "Falsifier, Steelmanned runner-up, Reversal trigger\n", False, id="no-heading"
        ),
    ],
)
def test_a_record_is_disconfirmed_when_a_disconfirmation_section_names_all_three_items(
    tmp_path, body, disconfirmed
):
    record = _record(tmp_path, f"{DRAFTS}/{FRAGMENT}", f"---\nid: x\n---\n{body}")

    assert record.disconfirmed is disconfirmed


# -- Discovery --------------------------------------------------------------------------------


def test_discovery_leaves_out_what_the_baseline_held_and_what_is_not_markdown(tmp_path):
    _write(tmp_path, ".ai-state/decisions/001-first.md")
    _write(tmp_path, f"{DRAFTS}/{FRAGMENT}")
    _write(tmp_path, "src/code.py", "x = 1\n")

    found = read_records(
        tmp_path, before=frozenset({".ai-state/decisions/001-first.md"}), branch=BRANCH
    )

    assert [record.path for record in found] == [f"{DRAFTS}/{FRAGMENT}"]


def test_discovery_leaves_out_the_git_and_ai_work_trees_at_the_root_only(tmp_path):
    _write(tmp_path, ".git/NOTE.md")
    _write(tmp_path, ".ai-work/slug/PLAN.md")
    _write(tmp_path, "docs/.ai-work/kept.md")

    found = read_records(tmp_path, before=frozenset(), branch=BRANCH)

    assert [record.path for record in found] == ["docs/.ai-work/kept.md"]


def test_discovery_ignores_gitignore_so_a_record_under_an_ignored_path_is_found(tmp_path):
    _write(tmp_path, ".gitignore", ".ai-state/\n")
    _write(tmp_path, f"{DRAFTS}/{FRAGMENT}")

    found = read_records(tmp_path, before=frozenset(), branch=BRANCH)

    assert f"{DRAFTS}/{FRAGMENT}" in [record.path for record in found]


# -- Reading the fixture's refs ---------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        check=True,
        capture_output=True,
    )


def test_the_baseline_tree_and_the_fixture_branch_are_read_from_their_refs(tmp_path):
    _git(tmp_path, "init", "-b", "main")
    _write(tmp_path, ".ai-state/decisions/001-first.md")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "Baseline")
    _git(tmp_path, "update-ref", checks_git.BASELINE_REF, "HEAD")
    _git(tmp_path, "symbolic-ref", BRANCH_REF, "refs/heads/Feature/Storage")

    assert baseline_paths(tmp_path) == {".ai-state/decisions/001-first.md"}
    assert fixture_branch(tmp_path) == "Feature/Storage"


def test_the_two_ref_names_are_each_defined_once():
    assert BRANCH_REF == "refs/fixture/branch"
    assert checks_adr.BASELINE_REF is checks_git.BASELINE_REF


def test_the_module_imports_no_kit():
    tree = ast.parse(Path(checks_adr.__file__).read_text(encoding="utf-8"))
    imported = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}

    assert not {name for name in imported if ".kit_" in name or name.endswith(".kits")}


# -- Grading the records ----------------------------------------------------------------------

FRAGMENT_PATH = f"{DRAFTS}/{FRAGMENT}"
OLDER_HABIT_PATH = ".ai-state/decisions/044-adopt-sqlite.md"


def _text(
    id_: str | None = DRAFT_ID, category: str | None = "behavioral", body: str = "# T\n"
) -> str:
    fields = [f"id: {id_}" if id_ else None, f"category: {category}" if category else None]
    return "---\n" + "".join(f"{line}\n" for line in fields if line) + "---\n" + body


def _graded(check: str, root: Path, *records: tuple[str, str]) -> Grade | NothingToGrade:
    for path, text in records:
        _write(root, path, text)
    return grade_records(check, frozenset(), BRANCH, root)


def _failed(check: str, root: Path, *records: tuple[str, str]) -> set[str]:
    answer = _graded(check, root, *records)
    assert isinstance(answer, Grade)
    return set(answer.failed_parts)


@pytest.mark.parametrize(
    ("path", "text", "failing"),
    [
        pytest.param(FRAGMENT_PATH, _text(), set(), id="a-conforming-fragment"),
        pytest.param(
            f".ai-state/decisions/{FRAGMENT}", _text(), {NOT_UNDER_DRAFTS}, id="not-under-drafts"
        ),
        pytest.param(
            f"{DRAFTS}/2026/{FRAGMENT}", _text(), {NOT_UNDER_DRAFTS}, id="in-a-drafts-subdirectory"
        ),
        pytest.param(f"{DRAFTS}/adopt-sqlite.md", _text(), {MALFORMED_NAME}, id="name-of-a-slug"),
        pytest.param(
            f"{DRAFTS}/{FRAGMENT.replace('20261029', '20261329')}",
            _text(),
            {MALFORMED_NAME},
            id="name-with-no-such-date",
        ),
        pytest.param(FRAGMENT_PATH, _text(id_=None), {MALFORMED_ID}, id="no-id"),
        pytest.param(
            FRAGMENT_PATH, _text(id_="dec-draft-3f9a0c"), {MALFORMED_ID}, id="six-hex-draft-id"
        ),
        pytest.param(
            f"{DRAFTS}/043-adopt-sqlite.md", _text(), {SELF_NUMBERED}, id="name-by-record-number"
        ),
        pytest.param(FRAGMENT_PATH, _text(id_="dec-043"), {SELF_NUMBERED}, id="numbered-id"),
    ],
)
def test_draft_placement_fails_exactly_the_part_a_planted_record_violates(
    tmp_path, path, text, failing
):
    assert _failed(DRAFT_PLACEMENT, tmp_path, (path, text)) == failing


@pytest.mark.parametrize(
    ("category", "body", "failing"),
    [
        pytest.param("behavioral", "# T\n", set(), id="a-non-architectural-value"),
        pytest.param("Architectural", ARCHITECTURAL_BODY, set(), id="architectural-in-any-case"),
        pytest.param(None, "# T\n", {NO_CATEGORY}, id="no-category"),
        pytest.param("strategic", "# T\n", {UNKNOWN_CATEGORY}, id="unknown-category"),
        pytest.param("architectural", "# T\n", {NO_DISCONFIRMATION}, id="no-disconfirmation"),
    ],
)
def test_decision_category_fails_exactly_the_part_a_planted_record_violates(
    tmp_path, category, body, failing
):
    record = (FRAGMENT_PATH, _text(category=category, body=body))

    assert _failed(DECISION_CATEGORY, tmp_path, record) == failing


def test_the_projects_older_habit_fails_both_checks_on_the_parts_it_violates(tmp_path):
    older = (OLDER_HABIT_PATH, _text(id_="dec-044", category=None))

    assert _failed(DRAFT_PLACEMENT, tmp_path, older) == {NOT_UNDER_DRAFTS, SELF_NUMBERED}
    assert _failed(DECISION_CATEGORY, tmp_path) == {NO_CATEGORY}


def test_a_part_that_two_records_fail_is_named_once(tmp_path):
    other = f"{DRAFTS}/20261029-1430-fixture-author-{BRANCH}-other.md"
    records = [(FRAGMENT_PATH, _text(id_=None)), (other, _text(id_=None))]

    answer = _graded(DRAFT_PLACEMENT, tmp_path, *records)

    assert isinstance(answer, Grade)
    assert answer.failed_parts == (MALFORMED_ID,)


def test_one_misplaced_record_among_conforming_ones_fails_the_check(tmp_path):
    misplaced = (f".ai-state/decisions/{FRAGMENT.replace('sqlite', 'redis')}", _text())

    assert _failed(DRAFT_PLACEMENT, tmp_path, (FRAGMENT_PATH, _text()), misplaced) == {
        NOT_UNDER_DRAFTS
    }


def test_a_record_moved_into_conformance_before_the_end_passes(tmp_path):
    _write(tmp_path, OLDER_HABIT_PATH, _text(id_="dec-044"))
    (tmp_path / OLDER_HABIT_PATH).unlink()

    assert _failed(DRAFT_PLACEMENT, tmp_path, (FRAGMENT_PATH, _text())) == set()


@pytest.mark.parametrize("check", [DRAFT_PLACEMENT, DECISION_CATEGORY])
def test_no_record_left_is_nothing_to_grade(tmp_path, check):
    assert _graded(check, tmp_path) == NothingToGrade("no decision record written")


@pytest.mark.parametrize("check", [DRAFT_PLACEMENT, DECISION_CATEGORY])
def test_a_markdown_file_under_ai_work_is_no_decision_record(tmp_path, check):
    answer = _graded(check, tmp_path, (".ai-work/slug/NOTES.md", _text(id_=None)))

    assert answer == NothingToGrade("no decision record written")


def test_a_check_this_module_does_not_grade_is_refused(tmp_path):
    with pytest.raises(ValueError, match="no grader"):
        grade_records("commit message form", frozenset(), BRANCH, tmp_path)


def _planted_repo(root: Path, *session: tuple[str, str]) -> Path:
    _git(root, "init", "-b", "main")
    _write(root, ".ai-state/decisions/001-first.md", _text(id_="dec-001"))
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "Baseline")
    _git(root, "update-ref", checks_git.BASELINE_REF, "HEAD")
    _git(root, "symbolic-ref", BRANCH_REF, f"refs/heads/{BRANCH}")
    for path, text in session:
        _write(root, path, text)
    return root


def test_the_run_adapter_reads_the_baseline_and_branch_refs_and_grades_the_new_records(tmp_path):
    repo = _planted_repo(tmp_path, (FRAGMENT_PATH, _text()))
    adr = declaration.kit("adr-conventions")

    answers = [grade(adr, check.name, repo, (), ()) for check in adr.checks.checks]

    assert answers == [Grade("passed", ())] * len(answers)


def test_the_run_adapter_leaves_the_baseline_records_ungraded(tmp_path):
    adr = declaration.kit("adr-conventions")

    answer = grade(adr, DRAFT_PLACEMENT, _planted_repo(tmp_path), ())

    assert answer == NothingToGrade("no decision record written")


def test_the_run_adapter_refuses_a_check_the_declaration_does_not_govern(tmp_path):
    adr = declaration.kit("adr-conventions")

    with pytest.raises(ValueError, match="governs no check"):
        grade(adr, "commit message form", _planted_repo(tmp_path), ())
