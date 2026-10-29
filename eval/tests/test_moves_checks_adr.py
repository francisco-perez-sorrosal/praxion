"""The decision records a session leaves, read from its end state into closed sum types: file name,
id and category are classified so that a grader can fail one part of the rule alone."""

from __future__ import annotations

import ast
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from praxion_evals.adherence.moves import checks_adr, checks_git
from praxion_evals.adherence.moves.checks_adr import (
    BRANCH_REF,
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
    read_records,
)

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
