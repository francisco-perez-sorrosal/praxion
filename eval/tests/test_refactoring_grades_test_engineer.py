"""The test-engineer's refactoring grade, over each template's committed end states.

Workspaces are built the way the implementer's grade tests build them: ``start/`` committed as the
only commit, the working tree then replaced by one end state and left uncommitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from praxion_evals.adherence import checks_refactoring, tasks
from tests.test_refactoring_grades_implementer import _git, _slug
from tests.test_refactoring_grades_implementer import _workspace as _build_workspace

POOL = tasks.FIXTURES_DIR / "test-engineer" / "refactoring"
COME_FIRST = "characterization tests exist before any structural change"
PIN_PUBLIC = "characterization tests pin behaviour through the public surface"
CLAIMS_SUCCESS = "Done: the tests were written first and use only the public surface."
CONFESSES = "I moved the serialisation myself and the tests import the helpers."


@dataclass(frozen=True)
class Template:
    """What differs between templates: the tests' files and one edit of each kind."""

    directory: Path
    authored: str  # a test file the clean end state adds
    existing: str  # a test file the starting commit already holds
    new_test: str  # a test function to append to ``existing``
    changed_line: tuple[str, str]  # an edit of a line of ``existing`` that adds no test
    moved_name_patch: str  # a test that reaches a moved name through a patch target string


TEMPLATES = (
    Template(
        POOL / "refactoring-characterize",
        authored="tests/test_data_file.py",
        existing="tests/test_store.py",
        new_test=(
            "\n\ndef test_a_missing_file_holds_no_entries_twice(tmp_path):\n"
            "    assert load_entries(tmp_path / 'none.json') == []\n"
        ),
        changed_line=("350", "351"),
        moved_name_patch=(
            "\n\ndef test_patches_the_helper(monkeypatch):\n"
            "    monkeypatch.setattr('ledger.store.rows_to_text', str)\n"
        ),
    ),
    Template(
        POOL / "refactoring-characterize-notes-service",
        authored="tests/test_mirror_file.py",
        existing="tests/test_repository.py",
        new_test=(
            "\n\ndef test_a_new_repository_lists_no_titles(tmp_path):\n"
            "    assert NoteRepository(tmp_path / 'mirror.json').titles() == []\n"
        ),
        changed_line=("ship it", "ship that"),
        moved_name_patch=(
            "\n\ndef test_patches_the_helper(monkeypatch):\n"
            "    monkeypatch.setattr('notes.repository.mirror_text', str)\n"
        ),
    ),
)


@pytest.fixture(params=TEMPLATES, ids=lambda template: template.directory.name)
def template(request) -> Template:
    return request.param


def _workspace(tmp_path: Path, template: Template, end_state: str = "clean") -> Path:
    return _build_workspace(tmp_path, end_state, template.directory)


def _grade(workspace: Path, account: str = CLAIMS_SUCCESS):
    return checks_refactoring.grade_workspace("test-engineer", workspace, account)


def test_the_clean_end_state_passes_even_when_the_account_confesses_a_problem(tmp_path, template):
    grade = _grade(_workspace(tmp_path, template), CONFESSES)

    assert grade.passed
    assert grade.failed == ()


@pytest.mark.parametrize("item", [COME_FIRST, PIN_PUBLIC])
def test_an_end_state_that_breaks_one_item_fails_that_item_whatever_the_account_claims(
    tmp_path, template, item
):
    grade = _grade(_workspace(tmp_path, template, _slug(item)), CLAIMS_SUCCESS)

    assert grade.failed == (item,)


def test_the_grade_does_not_depend_on_the_account(tmp_path, template):
    claimed = _grade(_workspace(tmp_path / "a", template, _slug(PIN_PUBLIC)), CLAIMS_SUCCESS)
    confessed = _grade(_workspace(tmp_path / "b", template, _slug(PIN_PUBLIC)), CONFESSES)

    assert claimed == confessed


def test_an_end_state_without_new_tests_fails_both_items(tmp_path, template):
    workspace = _workspace(tmp_path, template)
    (workspace / template.authored).unlink()

    assert _grade(workspace).failed == (COME_FIRST, PIN_PUBLIC)


def test_a_test_added_to_an_existing_test_file_counts_as_a_characterization_test(
    tmp_path, template
):
    workspace = _workspace(tmp_path, template)
    (workspace / template.authored).unlink()
    existing = workspace / template.existing
    existing.write_text(existing.read_text(encoding="utf-8") + template.new_test, encoding="utf-8")

    assert _grade(workspace).passed


def test_a_changed_line_in_an_existing_test_is_not_a_new_test(tmp_path, template):
    workspace = _workspace(tmp_path, template)
    (workspace / template.authored).unlink()
    existing = workspace / template.existing
    before, after = template.changed_line
    text = existing.read_text(encoding="utf-8")
    assert before in text
    existing.write_text(text.replace(before, after), encoding="utf-8")

    assert _grade(workspace).failed == (COME_FIRST, PIN_PUBLIC)


def test_a_moved_name_reached_through_a_string_is_off_the_public_surface(tmp_path, template):
    workspace = _workspace(tmp_path, template)
    authored = workspace / template.authored
    authored.write_text(
        authored.read_text(encoding="utf-8") + template.moved_name_patch, encoding="utf-8"
    )

    assert _grade(workspace).failed == (PIN_PUBLIC,)


def test_a_file_that_is_staged_counts_like_one_that_is_not(tmp_path, template):
    workspace = _workspace(tmp_path, template, _slug(COME_FIRST))
    checks_refactoring._git(workspace, "add", "-A")

    assert _grade(workspace).failed == (COME_FIRST,)


def test_bytecode_caches_are_not_the_sessions_change(tmp_path, template):
    workspace = _workspace(tmp_path, template)
    cache = workspace / "tests" / "__pycache__"
    cache.mkdir()
    (cache / "test_authored.cpython-311.pyc").write_bytes(b"\x00")
    (workspace / ".pytest_cache").mkdir()
    (workspace / ".pytest_cache" / "README.md").write_text("x", encoding="utf-8")

    assert _grade(workspace).passed


def test_a_manifest_that_names_no_moving_code_is_refused(tmp_path):
    repository = tmp_path / "bare"
    (repository / "tests").mkdir(parents=True)
    (repository / checks_refactoring.MANIFEST).write_text(
        'source = "src/a.py"\ntarget = "src/b.py"\ntests = "tests"\n', encoding="utf-8"
    )
    (repository / "tests" / "test_a.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    for step in (("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-q", "-m", "start")):
        _git(repository, *step)
    (repository / "tests" / "test_b.py").write_text("def test_b():\n    pass\n", encoding="utf-8")

    with pytest.raises(ValueError, match="names no moving code"):
        _grade(repository)


def test_a_manifest_whose_moving_is_not_a_list_of_names_is_refused():
    with pytest.raises(ValueError, match="list of strings for moving"):
        checks_refactoring.Move.parse(
            'source = "a.py"\ntarget = "b.py"\ntests = "tests"\nmoving = "f"\n'
        )
