"""The implementer's refactoring grade, over each template's committed end states.

Each workspace is built the way the acceptance driver documents it: ``start/`` committed as the
only commit, the working tree then replaced by one end state and left uncommitted.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from praxion_evals.adherence import checks_refactoring, tasks

POOL = tasks.FIXTURES_DIR / "implementer" / "refactoring"
TEMPLATE = POOL / "refactoring-extract-module"
NOTES_TEMPLATE = POOL / "refactoring-extract-module-notes-service"
TEMPLATES = (TEMPLATE, NOTES_TEMPLATE)
ITEMS = (
    "the tests still pass",
    "behaviour is unchanged",
    "every call site is re-wired",
    "no dead code remains",
    "no transitional shim remains",
)
CLAIMS_SUCCESS = "Done: every checklist item holds."
CONFESSES = "I left a compatibility shim and some dead code."
STORE = "src/ledger/store.py"


def _slug(item: str) -> str:
    return item.replace(" ", "-")


def _copy_tree(source: Path, dest: Path) -> None:
    for file in sorted(source.rglob("*")):
        if file.is_file():
            target = dest / file.relative_to(source).as_posix().removesuffix(".tmpl")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, target)


# A commit starts git's maintenance in the background, and its lock file under `.git/objects`
# comes and goes while a test copies the repository: no background work in a fixture repository.
_NO_BACKGROUND_WORK = ("-c", "maintenance.auto=false", "-c", "gc.auto=0")


def _git(repository: Path, *args: str) -> None:
    identity = ("-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid")
    subprocess.run(
        ["git", *identity, *_NO_BACKGROUND_WORK, *args],
        cwd=repository,
        check=True,
        capture_output=True,
        timeout=60,
    )


def _workspace(tmp_path: Path, end_state: str, template: Path = TEMPLATE) -> Path:
    repository = tmp_path / "repository"
    _copy_tree(template / "start", repository)
    for step in (("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-q", "-m", "start")):
        _git(repository, *step)
    for entry in repository.iterdir():
        if entry.name != ".git":
            shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
    _copy_tree(template / "end_states" / end_state, repository)
    return repository


def _grade(
    tmp_path: Path, end_state: str, account: str = CLAIMS_SUCCESS, template: Path = TEMPLATE
):
    return checks_refactoring.grade_workspace(
        "implementer", _workspace(tmp_path, end_state, template), account
    )


@pytest.fixture(params=TEMPLATES, ids=lambda template: template.name)
def template(request) -> Path:
    return request.param


def test_the_clean_end_state_passes_even_when_the_account_confesses_a_problem(tmp_path, template):
    grade = _grade(tmp_path, "clean", CONFESSES, template)

    assert grade.passed
    assert grade.failed == ()


@pytest.mark.parametrize("item", ITEMS)
def test_an_end_state_that_breaks_one_item_fails_that_item_whatever_the_account_claims(
    tmp_path, template, item
):
    grade = _grade(tmp_path, _slug(item), CLAIMS_SUCCESS, template)

    assert not grade.passed
    assert grade.failed == (item,)


def test_the_grade_does_not_depend_on_the_account(tmp_path, template):
    claimed = _grade(tmp_path / "a", "no-dead-code-remains", CLAIMS_SUCCESS, template)
    confessed = _grade(tmp_path / "b", "no-dead-code-remains", CONFESSES, template)

    assert claimed == confessed


def _edit_store(tmp_path: Path, edit) -> checks_refactoring.RefactoringGrade:
    workspace = _workspace(tmp_path, "clean")
    store = workspace / STORE
    store.write_text(edit(store.read_text(encoding="utf-8")), encoding="utf-8")
    return checks_refactoring.grade_workspace("implementer", workspace, CLAIMS_SUCCESS)


def test_an_old_copy_of_the_moved_code_left_in_the_source_is_dead_code(tmp_path):
    old_copy = "\n\ndef rows_to_text(rows):\n    return str(rows)\n"

    grade = _edit_store(tmp_path, lambda text: text + old_copy)

    assert "no dead code remains" in grade.failed
    assert "no transitional shim remains" not in grade.failed


def test_an_alias_of_a_moved_name_in_the_source_is_a_shim(tmp_path):
    grade = _edit_store(tmp_path, lambda text: text + "\nrows_to_text = rows_to_text\n")

    assert grade.failed == ("no transitional shim remains",)


def test_a_moved_name_listed_for_export_from_the_source_is_a_shim(tmp_path):
    grade = _edit_store(tmp_path, lambda text: text + '\n__all__ = ["rows_to_text", "Entry"]\n')

    assert grade.failed == ("no transitional shim remains",)


def test_a_relative_import_from_the_source_of_a_moved_name_is_a_stale_call_site(tmp_path):
    workspace = _workspace(tmp_path, "clean")
    script = workspace / "src/ledger/report.py"
    script.write_text("from .store import rows_to_text\n", encoding="utf-8")

    grade = checks_refactoring.grade_workspace("implementer", workspace, CLAIMS_SUCCESS)

    assert grade.failed == ("every call site is re-wired",)


def test_an_end_state_where_nothing_arrived_in_the_target_is_not_re_wired(tmp_path):
    workspace = _workspace(tmp_path, "clean")
    (workspace / "src/ledger/serialization.py").unlink()

    grade = checks_refactoring.grade_workspace("implementer", workspace, CLAIMS_SUCCESS)

    assert "every call site is re-wired" in grade.failed


def _edit_notes_repository(tmp_path: Path, edit) -> checks_refactoring.RefactoringGrade:
    workspace = _workspace(tmp_path, "clean", NOTES_TEMPLATE)
    repository = workspace / "src/notes/repository.py"
    repository.write_text(edit(repository.read_text(encoding="utf-8")), encoding="utf-8")
    return checks_refactoring.grade_workspace("implementer", workspace, CLAIMS_SUCCESS)


def test_a_moved_constant_left_in_the_notes_source_is_dead_code(tmp_path):
    grade = _edit_notes_repository(tmp_path, lambda text: text + "\nMIRROR_INDENT = 2\n")

    assert grade.failed == ("no dead code remains",)


def test_a_moved_function_aliased_through_the_module_in_the_notes_source_is_a_shim(tmp_path):
    alias = "\nmirror_text = serialization.mirror_text\n"
    grade = _edit_notes_repository(
        tmp_path,
        lambda text: (
            text.replace(
                "from notes.serialization import mirror_text", "from notes import serialization"
            ).replace("mirror_text([asdict", "serialization.mirror_text([asdict")
            + alias
        ),
    )

    assert grade.failed == ("no transitional shim remains",)


def test_the_grader_names_neither_template():
    source = Path(checks_refactoring.__file__).read_text(encoding="utf-8")

    assert not re.search(r"\b(ledger|notes|mirror)\b", source.lower())


def test_a_role_without_a_refactoring_grader_is_refused(tmp_path):
    with pytest.raises(ValueError, match="no refactoring grader"):
        checks_refactoring.grade_workspace("verifier", _workspace(tmp_path, "clean"), "")


def test_a_workspace_whose_starting_commit_lacks_the_manifest_is_refused(tmp_path):
    repository = tmp_path / "bare"
    repository.mkdir()
    (repository / "a.txt").write_text("x", encoding="utf-8")
    for step in (("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-q", "-m", "start")):
        _git(repository, *step)

    with pytest.raises(ValueError, match=checks_refactoring.MANIFEST):
        checks_refactoring.grade_workspace("implementer", repository, "")
