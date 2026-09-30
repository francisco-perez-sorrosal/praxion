"""Tests for `_test_inventory` -- pocket discovery and collection scope.

GL07's uncollected-test check reads this module's output: a test file is
"collected" when it sits in a pocket's configured collection scope, or when a
CI workflow passes a matching path/glob literal to a runner. A test file
matching neither is a test that runs nowhere -- the class of bug this module
exists to make visible.

`scripts/_test_inventory.py` does not exist yet; collection fails at
`_load_module()`'s `exec_module` call with `FileNotFoundError` -- the correct
RED state for this step.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent
_MODULE_PATH = _SCRIPTS_DIR / "_test_inventory.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("_test_inventory", _MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


test_inventory = _load_module()


# -- Pocket discovery -----------------------------------------------------


def test_discovers_a_python_pocket_at_repo_root(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["scripts", "tests"]\n',
        encoding="utf-8",
    )

    pockets = test_inventory.discover_pockets(tmp_path)

    assert len(pockets) == 1
    assert pockets[0].ecosystem == "python"
    assert pockets[0].root == "."


def test_a_directory_with_no_ecosystem_marker_yields_no_pocket(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# empty project\n", encoding="utf-8")

    pockets = test_inventory.discover_pockets(tmp_path)

    assert pockets == ()


# -- Per-ecosystem naming conventions ---------------------------------------


@pytest.mark.parametrize(
    ("path", "ecosystem", "expected"),
    [
        ("scripts/test_foo.py", "python", True),
        ("scripts/foo_test.py", "python", True),
        ("scripts/foo.py", "python", False),
        ("src/foo.test.ts", "typescript", True),
        ("src/foo.spec.ts", "typescript", True),
        ("src/foo.ts", "typescript", False),
        ("tests/foo.rs", "rust", True),
        ("src/foo.rs", "rust", False),
        ("pkg/foo_test.go", "go", True),
        ("pkg/foo.go", "go", False),
    ],
)
def test_is_test_file_matches_the_ecosystem_naming_convention(
    path: str, ecosystem: str, expected: bool
) -> None:
    assert test_inventory.is_test_file(path, ecosystem) is expected


# -- Collection-scope predicate: pytest config ------------------------------


def test_pytest_collection_scope_reads_testpaths_via_tomllib(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[tool.pytest.ini_options]\n"
        'testpaths = ["scripts", "tests"]\n'
        'python_files = ["test_*.py"]\n',
        encoding="utf-8",
    )

    scope = test_inventory.pytest_collection_scope(pyproject)

    assert scope.covers("scripts/test_foo.py")
    assert scope.covers("tests/test_bar.py")
    assert not scope.covers("fitness/test_baz.py")


def test_pytest_collection_scope_on_an_absent_pyproject_covers_nothing(
    tmp_path: Path,
) -> None:
    absent = tmp_path / "pyproject.toml"

    scope = test_inventory.pytest_collection_scope(absent)

    assert not scope.covers("scripts/test_foo.py")


# -- Collection-scope predicate: CI workflow literals -----------------------


def test_workflow_collection_scope_covers_path_and_glob_literals_passed_to_a_runner(
    tmp_path: Path,
) -> None:
    """The collection-scope example: `fitness/` and `tests/*.sh` are covered only
    because a workflow passes them to a runner, not because any pytest
    config names them."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "test.yml").write_text(
        "jobs:\n"
        "  fitness:\n"
        "    steps:\n"
        "      - run: pytest fitness/\n"
        "  shell-tests:\n"
        "    steps:\n"
        "      - run: bash tests/foo.sh && bash tests/bar.sh\n",
        encoding="utf-8",
    )

    scope = test_inventory.workflow_collection_scope(workflows)

    assert scope.covers("fitness/test_something.py")
    assert scope.covers("tests/foo.sh")


def test_workflow_collection_scope_on_an_absent_workflows_dir_covers_nothing(
    tmp_path: Path,
) -> None:
    absent = tmp_path / ".github" / "workflows"

    scope = test_inventory.workflow_collection_scope(absent)

    assert not scope.covers("fitness/test_something.py")


# -- Combined predicate: a file is collected by any scope --------------------


def test_file_outside_pytest_scope_but_covered_by_a_workflow_glob_is_collected() -> None:
    pytest_scope = test_inventory.CollectionScope(patterns=("scripts/**", "tests/**"))
    workflow_scope = test_inventory.CollectionScope(patterns=("fitness/**",))

    assert test_inventory.is_collected("fitness/test_x.py", [pytest_scope, workflow_scope])


def test_file_matching_no_scope_is_uncollected() -> None:
    pytest_scope = test_inventory.CollectionScope(patterns=("scripts/**",))

    assert not test_inventory.is_collected("orphan/test_x.py", [pytest_scope])


# -- JavaScript test-file suffixes ---------------------------------------------

_JS_SCRIPT_SUFFIXES = ("ts", "tsx", "js", "jsx", "mjs", "cjs", "mts", "cts")


@pytest.mark.parametrize("suffix", _JS_SCRIPT_SUFFIXES)
def test_a_dot_test_file_in_each_javascript_script_suffix_is_a_typescript_test(
    suffix: str,
) -> None:
    assert test_inventory.is_test_file(f"src/x.test.{suffix}", "typescript") is True


@pytest.mark.parametrize("suffix", ["vue", "svelte"])
def test_a_dot_test_component_file_is_not_a_test_file(suffix: str) -> None:
    """Components are modules a test imports, never tests themselves."""
    assert test_inventory.is_test_file(f"src/x.test.{suffix}", "typescript") is False


# -- Source-code table ---------------------------------------------------------

_ALL_SOURCE_SUFFIXES = [
    suffix for suffixes in test_inventory.SOURCE_SUFFIXES.values() for suffix in suffixes
]


def test_the_source_table_names_exactly_the_ecosystems_that_have_sources() -> None:
    assert set(test_inventory.SOURCE_SUFFIXES) == set(test_inventory.ECOSYSTEMS) - {"monorepo"}


@pytest.mark.parametrize("suffix", _ALL_SOURCE_SUFFIXES)
def test_every_source_suffix_is_a_lowercase_dotted_suffix(suffix: str) -> None:
    assert suffix.startswith(".")
    assert suffix == suffix.lower()
    assert len(suffix) > 1


def test_no_source_suffix_appears_twice_in_the_table() -> None:
    assert len(_ALL_SOURCE_SUFFIXES) == len(set(_ALL_SOURCE_SUFFIXES))


def test_the_source_table_cannot_be_mutated() -> None:
    with pytest.raises(TypeError):
        test_inventory.SOURCE_SUFFIXES["ruby"] = (".rb",)


@pytest.mark.parametrize("suffix", _JS_SCRIPT_SUFFIXES)
def test_the_javascript_script_suffixes_are_part_of_the_typescript_row(suffix: str) -> None:
    assert f".{suffix}" in test_inventory.SOURCE_SUFFIXES["typescript"]


@pytest.mark.parametrize(
    "path",
    [
        "src/app.py",
        "web/src/app.tsx",
        "web/src/App.vue",
        "web/src/Widget.svelte",
        "crate/src/lib.rs",
        "cmd/main.go",
        "service/src/Main.java",
        "service/src/Main.kt",
        "pkg.v2/module.py",
    ],
)
def test_is_source_code_recognises_every_pocket_ecosystems_sources(path: str) -> None:
    assert test_inventory.is_source_code(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "docs/guide.md",
        "settings.yaml",
        "data/report.csv",
        "package.json",
        "Makefile",
        "src.py/data.json",
        "notes.py.txt",
        "SRC/APP.PY",
    ],
)
def test_is_source_code_rejects_data_and_case_variants(path: str) -> None:
    """A dotted directory does not make a file source, and the suffix test is case-sensitive."""
    assert test_inventory.is_source_code(path) is False
