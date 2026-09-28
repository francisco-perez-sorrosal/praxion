"""Tests for `_declared_deps` -- the parser for `tests/declared-deps.toml`.

The declared-deps list is the escape hatch for non-code test dependencies the
resolver cannot derive from layout, imports or path literals. Its six
invariants are all enforced by `parse()` as a smart constructor: a violation
must raise `DeclaredDepsError` naming what was wrong, never silently drop the
entry -- a silently dropped entry is a test dependency the resolver stops
tracking without anyone noticing.

This module does not exist yet (`scripts/_declared_deps.py` lands in the
paired implementation step). Collection therefore fails at
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
_MODULE_PATH = _SCRIPTS_DIR / "_declared_deps.py"


def _load_module() -> Any:
    """Load `_declared_deps.py` without requiring it on sys.path."""
    spec = importlib.util.spec_from_file_location("_declared_deps", _MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


declared_deps = _load_module()


VALID_TOML = """\
schema = 1

[[dep]]
paths = [".ai-state/decisions/*.md"]
tests = ["tests/test_adr_frontmatter_parseable.py"]
why = "parses every ADR's frontmatter"

[[inert]]
paths = ["docs/independent-analysis/**"]
why = "frozen historical analysis; no test reads it"
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "declared-deps.toml"
    path.write_text(text, encoding="utf-8")
    return path


# -- Valid parse ----------------------------------------------------------


def test_valid_two_variant_toml_parses_to_a_value(tmp_path: Path) -> None:
    path = _write(tmp_path, VALID_TOML)

    result = declared_deps.parse(path)

    assert len(result.deps) == 1
    assert result.deps[0].paths == (".ai-state/decisions/*.md",)
    assert result.deps[0].tests == ("tests/test_adr_frontmatter_parseable.py",)
    assert result.deps[0].why == "parses every ADR's frontmatter"
    assert len(result.inert) == 1
    assert result.inert[0].paths == ("docs/independent-analysis/**",)
    assert result.inert[0].why == "frozen historical analysis; no test reads it"


def test_missing_file_parses_as_an_empty_list(tmp_path: Path) -> None:
    """The resolver treats an absent `declared-deps.toml` as no declarations,
    not as an error -- a project may not have written one yet."""
    absent = tmp_path / "declared-deps.toml"

    result = declared_deps.parse(absent)

    assert result.deps == ()
    assert result.inert == ()


# -- Invariants 1-4: schema, unknown keys, non-empty lists, non-empty why ----


@pytest.mark.parametrize(
    ("toml_text", "expected_violation"),
    [
        pytest.param(
            '[[dep]]\npaths = ["a.py"]\ntests = ["tests/test_a.py"]\nwhy = "x"\n',
            "schema",
            id="missing-schema",
        ),
        pytest.param(
            'schema = 2\n[[dep]]\npaths = ["a.py"]\ntests = ["tests/test_a.py"]\nwhy = "x"\n',
            "schema",
            id="wrong-schema-version",
        ),
        pytest.param(
            "schema = 1\n"
            'unexpected = "x"\n'
            "[[dep]]\n"
            'paths = ["a.py"]\n'
            'tests = ["tests/test_a.py"]\n'
            'why = "x"\n',
            "unexpected",
            id="unknown-top-level-key",
        ),
        pytest.param(
            "schema = 1\n"
            "[[dep]]\n"
            'paths = ["a.py"]\n'
            'tests = ["tests/test_a.py"]\n'
            'why = "x"\n'
            'unexpected = "x"\n',
            "unexpected",
            id="unknown-dep-key",
        ),
        pytest.param(
            'schema = 1\n[[inert]]\npaths = ["a.py"]\nwhy = "x"\nunexpected = "x"\n',
            "unexpected",
            id="unknown-inert-key",
        ),
        pytest.param(
            'schema = 1\n[[dep]]\npaths = []\ntests = ["tests/test_a.py"]\nwhy = "x"\n',
            "paths",
            id="empty-paths-list",
        ),
        pytest.param(
            'schema = 1\n[[dep]]\npaths = ["a.py"]\ntests = []\nwhy = "x"\n',
            "tests",
            id="empty-tests-list",
        ),
        pytest.param(
            'schema = 1\n[[dep]]\npaths = ["/a.py"]\ntests = ["tests/test_a.py"]\nwhy = "x"\n',
            "a.py",
            id="absolute-path-rejected",
        ),
        pytest.param(
            'schema = 1\n[[dep]]\npaths = ["../a.py"]\ntests = ["tests/test_a.py"]\nwhy = "x"\n',
            "a.py",
            id="dot-dot-segment-rejected",
        ),
        pytest.param(
            'schema = 1\n[[dep]]\npaths = [""]\ntests = ["tests/test_a.py"]\nwhy = "x"\n',
            "paths",
            id="empty-string-path-rejected",
        ),
        pytest.param(
            'schema = 1\n[[dep]]\npaths = ["a.py"]\ntests = ["tests/test_a.py"]\nwhy = ""\n',
            "why",
            id="empty-why-rejected-on-dep",
        ),
        pytest.param(
            'schema = 1\n[[inert]]\npaths = ["a.py"]\nwhy = ""\n',
            "why",
            id="empty-why-rejected-on-inert",
        ),
    ],
)
def test_invalid_toml_raises_naming_the_violation(
    tmp_path: Path, toml_text: str, expected_violation: str
) -> None:
    path = _write(tmp_path, toml_text)

    with pytest.raises(declared_deps.DeclaredDepsError, match=expected_violation):
        declared_deps.parse(path)


# -- Invariant 6: a path matched by both dep and inert resolves to dep ------


def test_path_matched_by_both_dep_and_inert_resolves_to_dep() -> None:
    value = declared_deps.DeclaredDeps(
        deps=(declared_deps.DepEntry(paths=("shared/**",), tests=("tests/test_x.py",), why="x"),),
        inert=(declared_deps.InertEntry(paths=("shared/**",), why="y"),),
    )

    assert declared_deps.classify_path(value, "shared/file.md") == "dep"


def test_path_matched_only_by_inert_classifies_as_inert() -> None:
    value = declared_deps.DeclaredDeps(
        deps=(), inert=(declared_deps.InertEntry(paths=("frozen/**",), why="y"),)
    )

    assert declared_deps.classify_path(value, "frozen/file.md") == "inert"


def test_unmatched_path_classifies_as_none() -> None:
    value = declared_deps.DeclaredDeps(deps=(), inert=())

    assert declared_deps.classify_path(value, "anything.py") is None


# -- Invariant 5: every `tests` glob matches at least one tracked test file --


def test_tests_glob_matching_no_tracked_file_raises_naming_the_glob() -> None:
    value = declared_deps.DeclaredDeps(
        deps=(
            declared_deps.DepEntry(paths=("a.py",), tests=("tests/test_nonexistent.py",), why="x"),
        ),
        inert=(),
    )

    with pytest.raises(declared_deps.DeclaredDepsError, match="test_nonexistent.py"):
        declared_deps.validate_against_inventory(value, tracked_test_files=("tests/test_real.py",))


def test_tests_glob_matching_a_tracked_file_is_accepted() -> None:
    value = declared_deps.DeclaredDeps(
        deps=(declared_deps.DepEntry(paths=("a.py",), tests=("tests/test_real.py",), why="x"),),
        inert=(),
    )

    declared_deps.validate_against_inventory(
        value, tracked_test_files=("tests/test_real.py",)
    )  # must not raise
