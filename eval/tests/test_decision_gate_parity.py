"""The gate and the eval's grader read a decision record the same way.

The commit gate (``scripts/_decision_records.py``) must be stdlib-only because the ambient
``python3`` runs it; the eval grades the same record shapes with its own parser and is not shipped.
Two encodings of one set of shapes drift unless something holds them together, so each record
fixture below is read by both and must come out the same on placement, name, id and category.

The two are not identical by design, and no fixture here relies on that: the grader also demands
the branch in a fragment name and compares a category without regard to case, where the gate
needs only three tokens after the stamp and the category exactly.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from praxion_evals.adherence.moves import checks_adr

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_MODULE = "_decision_records_under_parity"
BRANCH = "main"
DRAFT_DIR = ".ai-state/decisions/drafts"
DECISIONS_DIR = ".ai-state/decisions"
FRAGMENT = "20261029-1430-fixture-person-main-a-slug.md"
NAME_KINDS = {"Fragment": "fragment", "Numbered": "numbered", "NumberedName": "numbered"}
ID_KINDS = {"DraftId": "draft", "NumberedId": "numbered", "OtherId": "other", "NoId": "none"}


def _record(identifier: str | None, category: str | None) -> str:
    fields = [
        f"id: {identifier}" if identifier else "",
        f"category: {category}" if category else "",
    ]
    return "---\n" + "".join(f"{field}\n" for field in fields if field) + "---\n\n## Context\n"


DRAFT_ID = "dec-draft-0a1b2c3d"  # id-citation-discipline:ignore -- a fixture literal
WELL_FORMED = _record(DRAFT_ID, "behavioral")

# (what the fixture shows, repo-relative path, text)
FIXTURES = [
    ("a well-formed draft", f"{DRAFT_DIR}/{FRAGMENT}", WELL_FORMED),
    (
        "a numbered record at the top",
        f"{DECISIONS_DIR}/041-keep-orders.md",
        _record("dec-041", "behavioral"),
    ),
    ("a record at the top that is not numbered", f"{DECISIONS_DIR}/keep-orders.md", WELL_FORMED),
    ("a draft in a subdirectory", f"{DRAFT_DIR}/old/{FRAGMENT}", WELL_FORMED),
    (
        "a draft numbered by its author",
        f"{DRAFT_DIR}/041-keep-orders.md",
        _record("dec-041", "behavioral"),
    ),
    (
        "a stamp with an impossible month",
        f"{DRAFT_DIR}/20261329-1430-fixture-person-main-a-slug.md",
        WELL_FORMED,
    ),
    ("a stamp followed by too few tokens", f"{DRAFT_DIR}/20261029-1430-a-b.md", WELL_FORMED),
    (
        "a draft id with a non-hex hash",
        f"{DRAFT_DIR}/{FRAGMENT}",
        _record("dec-draft-nothexxx", "behavioral"),
    ),
    (
        "a draft id one digit short",
        f"{DRAFT_DIR}/{FRAGMENT}",
        _record("dec-draft-0a1b2c3", "behavioral"),
    ),
    ("a draft with no id", f"{DRAFT_DIR}/{FRAGMENT}", _record(None, "behavioral")),
    ("a draft with no category", f"{DRAFT_DIR}/{FRAGMENT}", _record(DRAFT_ID, None)),
    ("a draft with an unknown category", f"{DRAFT_DIR}/{FRAGMENT}", _record(DRAFT_ID, "wizardry")),
    (
        "a draft with an architectural category",
        f"{DRAFT_DIR}/{FRAGMENT}",
        _record(DRAFT_ID, "architectural"),
    ),
    ("a draft with no frontmatter", f"{DRAFT_DIR}/{FRAGMENT}", "## Context\n"),
]
FIXTURE_IDS = [shown for shown, _, _ in FIXTURES]


@pytest.fixture(scope="module")
def gate() -> Iterator[ModuleType]:
    """The gate's module, loaded by path as the ambient interpreter would run it."""
    spec = importlib.util.spec_from_file_location(
        GATE_MODULE, REPO_ROOT / "scripts" / "_decision_records.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[GATE_MODULE] = module  # dataclasses resolve their annotations through sys.modules
    spec.loader.exec_module(module)
    yield module
    del sys.modules[GATE_MODULE]


def _graded(tmp_path: Path, path: str, text: str) -> checks_adr.DecisionRecord:
    (tmp_path / path).parent.mkdir(parents=True)
    (tmp_path / path).write_text(text, encoding="utf-8")
    (record,) = checks_adr.read_records(tmp_path, before=frozenset(), branches=frozenset({BRANCH}))
    return record


@pytest.mark.parametrize(("shown", "path", "text"), FIXTURES, ids=FIXTURE_IDS)
def test_both_place_a_record_directly_under_the_drafts_directory_alike(
    gate, tmp_path, shown, path, text
):
    graded = _graded(tmp_path, path, text)

    assert isinstance(gate.classify_path(path), gate.Draft) == graded.in_drafts


@pytest.mark.parametrize(("shown", "path", "text"), FIXTURES, ids=FIXTURE_IDS)
def test_both_name_a_record_as_the_same_kind_of_file(gate, tmp_path, shown, path, text):
    graded = _graded(tmp_path, path, text)

    gated = gate.classify_name(Path(path).name)

    assert NAME_KINDS.get(type(gated).__name__, "other") == NAME_KINDS.get(
        type(graded.name).__name__, "other"
    )


@pytest.mark.parametrize(("shown", "path", "text"), FIXTURES, ids=FIXTURE_IDS)
def test_both_read_a_records_id_as_the_same_kind_of_id(gate, tmp_path, shown, path, text):
    graded = _graded(tmp_path, path, text)

    gated = gate.parse_id(gate.read_frontmatter(text).id)

    assert ID_KINDS[type(gated).__name__] == ID_KINDS[type(graded.id).__name__]


@pytest.mark.parametrize(("shown", "path", "text"), FIXTURES, ids=FIXTURE_IDS)
def test_both_judge_a_records_category_valid_missing_or_unknown_alike(
    gate, tmp_path, shown, path, text
):
    graded = _graded(tmp_path, path, text)

    gated = gate.parse_category(gate.read_frontmatter(text).category)

    assert type(gated).__name__ == _grader_category_form(graded.category)


def _grader_category_form(category: str | None) -> str:
    if not category:
        return "MissingCategory"
    valid = category.casefold() in checks_adr.CATEGORY_VALUES
    return "ValidCategory" if valid else "InvalidCategory"


def test_both_hold_the_same_four_categories(gate):
    assert set(gate.CATEGORIES) == checks_adr.CATEGORY_VALUES


def test_both_hold_the_same_draft_directory(gate):
    gate_drafts = "/".join((*gate.DECISIONS_PARTS, gate.DRAFTS_SUBDIR))

    assert gate_drafts == checks_adr.DRAFTS_DIR


def test_both_read_the_same_stamp_format(gate):
    assert gate.STAMP_FORMAT == checks_adr._STAMP_FORMAT
