"""The refactoring grade is a comparison with the workspace's root commit, never with ``HEAD``.

A session may commit its change; a staged pool workspace holds no manifest. Workspaces are built
as the other grade tests build them, then the end state is committed or the manifest handed over.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from praxion_evals.adherence import checks_refactoring, refactoring_tasks, tasks
from tests.test_refactoring_grades_implementer import (
    CLAIMS_SUCCESS,
    ITEMS,
    TEMPLATE,
    _copy_tree,
    _git,
    _slug,
    _workspace,
)
from tests.test_refactoring_grades_test_engineer import COME_FIRST, PIN_PUBLIC
from tests.test_refactoring_grades_test_engineer import TEMPLATES as TEST_ENGINEER_TEMPLATES
from tests.test_refactoring_grades_test_engineer import _workspace as _test_engineer_workspace


def _commit_everything(workspace: Path) -> None:
    _git(workspace, "add", "-A")
    _git(workspace, "commit", "-q", "-m", "the session's change")


def _grade(workspace: Path, **options):
    return checks_refactoring.grade_workspace("implementer", workspace, CLAIMS_SUCCESS, **options)


def test_a_session_that_commits_its_clean_change_is_graded_on_it(tmp_path):
    workspace = _workspace(tmp_path, "clean")
    _commit_everything(workspace)

    assert _grade(workspace).passed


@pytest.mark.parametrize("item", ITEMS)
def test_a_committed_change_that_breaks_one_item_fails_that_item(tmp_path, item):
    workspace = _workspace(tmp_path, _slug(item))
    _commit_everything(workspace)

    assert _grade(workspace).failed == (item,)


def test_committing_the_change_does_not_alter_the_grade(tmp_path):
    uncommitted = _workspace(tmp_path / "a", "no-dead-code-remains")
    committed = _workspace(tmp_path / "b", "no-dead-code-remains")
    _commit_everything(committed)

    assert _grade(committed) == _grade(uncommitted)


@pytest.mark.parametrize("template", TEST_ENGINEER_TEMPLATES, ids=lambda t: t.directory.name)
def test_tests_a_session_committed_still_count_as_the_tests_it_added(tmp_path, template):
    workspace = _test_engineer_workspace(tmp_path, template)
    _commit_everything(workspace)

    grade = checks_refactoring.grade_workspace("test-engineer", workspace, "")

    assert grade.passed


@pytest.mark.parametrize("template", TEST_ENGINEER_TEMPLATES, ids=lambda t: t.directory.name)
def test_a_committed_change_outside_the_tests_still_breaks_the_order(tmp_path, template):
    workspace = _test_engineer_workspace(tmp_path, template, _slug(COME_FIRST))
    _commit_everything(workspace)

    grade = checks_refactoring.grade_workspace("test-engineer", workspace, "")

    assert grade.failed == (COME_FIRST,)
    assert PIN_PUBLIC not in grade.failed


def _staged_pool_workspace(tmp_path: Path) -> tuple[Path, Path]:
    """A pool task staged without its manifest, ended on its clean state; the manifest kept apart."""
    task = refactoring_tasks.pool_tasks("implementer", 0)[0]
    workspace = tmp_path / "staged"
    refactoring_tasks.stage_pool_task(task, workspace)
    template = (
        tasks.FIXTURES_DIR / "implementer" / refactoring_tasks.POOL_DIRNAME / task.template_id
    )
    for entry in workspace.iterdir():
        if entry.name != ".git":
            shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
    _copy_tree(template / "end_states" / "clean", workspace)
    manifest = template / refactoring_tasks.START_DIRNAME / checks_refactoring.MANIFEST
    return workspace, manifest


def test_a_staged_workspace_without_a_manifest_is_refused_unless_one_is_given(tmp_path):
    workspace, manifest = _staged_pool_workspace(tmp_path)

    with pytest.raises(ValueError, match=checks_refactoring.MANIFEST):
        _grade(workspace)
    assert _grade(workspace, manifest=manifest).passed


def test_a_manifest_given_as_a_file_is_the_one_read_and_not_the_root_commits(tmp_path):
    workspace = _workspace(tmp_path / "repo", "clean")
    broken = tmp_path / "broken.toml"
    broken.write_text('source = "src/a.py"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="lacks a string for target, tests"):
        _grade(workspace, manifest=broken)


def test_the_root_commits_manifest_is_the_fallback_when_none_is_given(tmp_path):
    workspace = _workspace(tmp_path, "clean")
    manifest = TEMPLATE / "start" / checks_refactoring.MANIFEST

    assert _grade(workspace) == _grade(workspace, manifest=manifest)


def test_a_workspace_with_two_root_commits_has_no_one_starting_point(tmp_path):
    workspace = _workspace(tmp_path, "clean")
    _git(workspace, "checkout", "-q", "--orphan", "other")
    _git(workspace, "commit", "-q", "--allow-empty", "-m", "another root")
    _git(workspace, "merge", "-q", "--allow-unrelated-histories", "-m", "join", "main")

    with pytest.raises(ValueError, match="2 root commits"):
        _grade(workspace)
