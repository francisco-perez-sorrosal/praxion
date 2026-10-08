"""One spelling of a protected entry, and one owner for each worker file name.

The protected-set judgement and the deny rule the scaffold writes both read an entry, so they
must agree on which paths it covers. The worker's file names are built in one module only.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _goal_record import entry_path, is_protected  # noqa: E402
from _goal_scaffold import edit_rule  # noqa: E402

DIRECTORY, FILE = "foo", "CLAUDE.md"
ENTRIES = ("foo/", "foo/**", "foo/**/", "foo/*", "./foo", "foo::test_x", "CLAUDE.md")
PATHS = ("foo", "foo/a.py", "foo/b/c.py", "food.py", "CLAUDE.md")
RULE_PREFIX, RULE_SUFFIX, GLOB_TAIL = "Edit(/", ")", "/**"
FILE_OWNER = "_step_loop_files.py"
WORKER_NAME_PARTS = ("WORKER", ".started")
CLEANED_FOR_DIRECTORY = ("foo/", "foo/**", "foo/**/", "foo/*", "./foo", "foo::test_x")


@pytest.fixture
def repo(tmp_path):
    (tmp_path / DIRECTORY).mkdir()
    (tmp_path / FILE).write_text("rules\n", encoding="utf-8")
    return tmp_path


def _named_by(rule: str) -> str:
    return rule.removeprefix(RULE_PREFIX).removesuffix(RULE_SUFFIX).removesuffix(GLOB_TAIL)


def _lies_at_or_under(path: str, named: str) -> bool:
    return path == named or path.startswith(f"{named}/")


def _docstring_ids(tree: ast.AST) -> set[int]:
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    ids: set[int] = set()
    for node in ast.walk(tree):
        first = node.body[0] if isinstance(node, holders) and node.body else None
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            ids.add(id(first.value))
    return ids


def _string_constants(source: str) -> list[str]:
    tree = ast.parse(source)
    skipped = _docstring_ids(tree)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in skipped
    ]


def _production_modules() -> list[Path]:
    return [
        path
        for path in sorted(SCRIPT_DIR.glob("*.py"))
        if not path.name.startswith("test_") and "testkit" not in path.name
    ]


def _modules_naming_a_worker_file(part: str) -> list[str]:
    return [
        path.name
        for path in _production_modules()
        if path.name != FILE_OWNER
        and any(part in text for text in _string_constants(path.read_text("utf-8")))
    ]


def _goal_modules_containing(text: str) -> list[str]:
    return [
        path.name
        for path in sorted(SCRIPT_DIR.glob("_goal_*.py"))
        if text in path.read_text("utf-8")
    ]


@pytest.mark.parametrize("entry", list(ENTRIES))
@pytest.mark.parametrize("path", list(PATHS))
def test_the_rule_names_exactly_the_paths_the_judgement_protects(repo, entry, path):
    named = _named_by(edit_rule(entry, repo))

    assert is_protected(path, [entry]) == _lies_at_or_under(path, named)


@pytest.mark.parametrize("entry", list(CLEANED_FOR_DIRECTORY))
def test_every_spelling_of_a_directory_names_the_same_path(entry):
    assert entry_path(entry) == DIRECTORY


def test_a_file_entry_keeps_its_name():
    assert entry_path(FILE) == FILE


def test_trailing_glob_and_slash_marks_are_removed_until_none_remains():
    assert entry_path("foo/**/*/") == DIRECTORY


@pytest.mark.parametrize("gone", ["def _deny_rule", "def _entry_base", "noqa: PLC2701"])
def test_no_goal_module_keeps_a_second_spelling_or_a_private_import(gone):
    assert _goal_modules_containing(gone) == []


@pytest.mark.parametrize("part", list(WORKER_NAME_PARTS))
def test_only_the_file_adapter_builds_a_worker_file_name(part):
    assert _modules_naming_a_worker_file(part) == []
