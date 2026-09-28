"""Tests for `_python_selection` -- the four-edge Python derivation graph.

The graph's failure mode is under-selection: a source change whose dependent
test the graph fails to see is a regression that ships silently. Each edge
kind (layout, import, path-literal, declared) is tested in isolation, then
union/attribution and reverse reachability are tested against a mix, per
The ordering contract: all four sources contribute, but the brief's
order (layout, import, path-literal, declared) governs only the `via`
attribution when more than one source reaches the same test.

`scripts/_python_selection.py` does not exist yet; collection fails at
`_load()`'s `exec_module` call with `FileNotFoundError` -- the correct RED
state for this step.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


python_selection = _load("_python_selection")
declared_deps = _load("_declared_deps")

NO_DEPS = declared_deps.DeclaredDeps(deps=(), inert=())


def _write(root: Path, rel: str, content: str = "") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _via(selection: Any, path: str) -> str:
    """The `via` attribution for a single selected test path."""
    matches = [s for s in selection if s.path == path]
    assert matches, f"{path} was not selected: {selection}"
    return matches[0].via


# -- Layout edges -------------------------------------------------------------


def test_co_located_test_depends_on_its_source_via_layout(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/foo.py", "value = 1\n")
    _write(tmp_path, "pkg/test_foo.py", "def test_value():\n    assert True\n")

    selection = python_selection.select(tmp_path, ["pkg/foo.py"], NO_DEPS)

    assert _via(selection, "pkg/test_foo.py") == "layout"


def test_mirrored_test_matches_by_basename_across_directories(tmp_path: Path) -> None:
    _write(tmp_path, "src/foo.py", "value = 1\n")
    _write(tmp_path, "tests/test_foo.py", "def test_value():\n    assert True\n")

    selection = python_selection.select(tmp_path, ["src/foo.py"], NO_DEPS)

    assert _via(selection, "tests/test_foo.py") == "layout"


def test_conftest_is_depended_on_by_every_test_under_its_directory(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/conftest.py", "import pytest\n")
    _write(tmp_path, "pkg/test_a.py", "def test_a():\n    assert True\n")
    _write(tmp_path, "pkg/sub/test_b.py", "def test_b():\n    assert True\n")

    selection = python_selection.select(tmp_path, ["pkg/conftest.py"], NO_DEPS)

    selected_paths = {s.path for s in selection}
    assert {"pkg/test_a.py", "pkg/sub/test_b.py"} <= selected_paths


# -- Import edges -------------------------------------------------------------


def test_absolute_import_reaches_the_importing_test(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/helper.py", "def h():\n    return 1\n")
    _write(
        tmp_path,
        "pkg/test_uses_helper.py",
        "import helper\n\n\ndef test_h():\n    assert helper.h() == 1\n",
    )

    selection = python_selection.select(tmp_path, ["pkg/helper.py"], NO_DEPS)

    assert _via(selection, "pkg/test_uses_helper.py") == "import"


def test_relative_import_reaches_the_importing_test(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/helper.py", "def h():\n    return 1\n")
    _write(
        tmp_path,
        "pkg/test_relative.py",
        "from . import helper\n\n\ndef test_h():\n    assert helper.h() == 1\n",
    )

    selection = python_selection.select(tmp_path, ["pkg/helper.py"], NO_DEPS)

    assert _via(selection, "pkg/test_relative.py") == "import"


def test_importlib_import_module_literal_reaches_the_importing_test(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/helper.py", "def h():\n    return 1\n")
    _write(
        tmp_path,
        "pkg/test_dynamic.py",
        "import importlib\n\n\n"
        "def test_h():\n"
        '    mod = importlib.import_module("helper")\n'
        "    assert mod.h() == 1\n",
    )

    selection = python_selection.select(tmp_path, ["pkg/helper.py"], NO_DEPS)

    assert _via(selection, "pkg/test_dynamic.py") == "import"


def test_import_graph_is_transitive_through_a_non_test_module(tmp_path: Path) -> None:
    """The graph's "reverse reachability" is a traversal, not a one-hop
    lookup: `test_x` imports `helper`, `helper` imports `foo`. Changing
    `foo.py` must still reach `test_x.py` even though no edge points from the
    test directly to the changed file."""
    _write(tmp_path, "pkg/foo.py", "value = 1\n")
    _write(tmp_path, "pkg/helper.py", "import foo\n")
    _write(tmp_path, "pkg/test_x.py", "import helper\n\n\ndef test_it():\n    assert True\n")

    selection = python_selection.select(tmp_path, ["pkg/foo.py"], NO_DEPS)

    assert "pkg/test_x.py" in {s.path for s in selection}


# -- Path-literal edges -------------------------------------------------------


def test_path_literal_with_slash_matches_as_a_suffix(tmp_path: Path) -> None:
    _write(tmp_path, "tests/fixtures/data.json", "{}\n")
    _write(
        tmp_path,
        "tests/test_reads_fixture.py",
        'def test_reads():\n    open("tests/fixtures/data.json")\n',
    )

    selection = python_selection.select(tmp_path, ["tests/fixtures/data.json"], NO_DEPS)

    assert _via(selection, "tests/test_reads_fixture.py") == "path-literal"


def test_path_literal_glob_matches_a_wildcard_reference(tmp_path: Path) -> None:
    _write(tmp_path, "tests/fixtures/data.json", "{}\n")
    _write(
        tmp_path,
        "tests/test_reads_any_fixture.py",
        'GLOB = "tests/fixtures/*.json"\n\n\ndef test_reads():\n    assert True\n',
    )

    selection = python_selection.select(tmp_path, ["tests/fixtures/data.json"], NO_DEPS)

    assert _via(selection, "tests/test_reads_any_fixture.py") == "path-literal"


def test_path_literal_without_slash_matches_only_an_exact_basename(tmp_path: Path) -> None:
    _write(tmp_path, "scripts/praxion-sidecar", "#!/bin/sh\n")
    _write(
        tmp_path,
        "scripts/test_sidecar_cli.py",
        'BINARY = "praxion-sidecar"\n\n\ndef test_cli():\n    assert True\n',
    )

    selection = python_selection.select(tmp_path, ["scripts/praxion-sidecar"], NO_DEPS)

    assert _via(selection, "scripts/test_sidecar_cli.py") == "path-literal"


def test_path_literal_basename_match_does_not_fire_on_a_substring(tmp_path: Path) -> None:
    """Inverse guard: `praxion-sidecar` must not match as a substring of a
    longer literal -- only an exact basename counts."""
    _write(tmp_path, "scripts/praxion-sidecar", "#!/bin/sh\n")
    _write(
        tmp_path,
        "scripts/test_unrelated.py",
        'NAME = "my-praxion-sidecar-extra"\n\n\ndef test_it():\n    assert True\n',
    )

    selection = python_selection.select(tmp_path, ["scripts/praxion-sidecar"], NO_DEPS)

    assert "scripts/test_unrelated.py" not in {s.path for s in selection}


# -- Declared edges ------------------------------------------------------------


def test_declared_dep_reaches_its_listed_test(tmp_path: Path) -> None:
    _write(tmp_path, ".ai-state/decisions/001-x.md", "# x\n")
    _write(
        tmp_path,
        "tests/test_adr_frontmatter_parseable.py",
        "def test_it():\n    assert True\n",
    )
    deps = declared_deps.DeclaredDeps(
        deps=(
            declared_deps.DepEntry(
                paths=(".ai-state/decisions/*.md",),
                tests=("tests/test_adr_frontmatter_parseable.py",),
                why="parses every ADR's frontmatter",
            ),
        ),
        inert=(),
    )

    selection = python_selection.select(tmp_path, [".ai-state/decisions/001-x.md"], deps)

    assert _via(selection, "tests/test_adr_frontmatter_parseable.py") == "declared"


# -- Union, not first match ----------------------------------------------------


def test_a_test_reachable_by_two_sources_is_attributed_to_the_higher_priority_one(
    tmp_path: Path,
) -> None:
    """`foo.py` and `test_foo.py` are co-located (a layout edge) AND
    `test_foo.py` also imports `foo` (an import edge). The source order --
    layout, import, path-literal, declared -- governs attribution; the test
    must appear exactly once, tagged `layout`."""
    _write(tmp_path, "pkg/foo.py", "value = 1\n")
    _write(
        tmp_path,
        "pkg/test_foo.py",
        "import foo\n\n\ndef test_value():\n    assert foo.value == 1\n",
    )

    selection = python_selection.select(tmp_path, ["pkg/foo.py"], NO_DEPS)

    matches = [s for s in selection if s.path == "pkg/test_foo.py"]
    assert len(matches) == 1
    assert matches[0].via == "layout"


# -- Self edge ------------------------------------------------------------------


def test_a_changed_test_file_selects_itself(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/test_standalone.py", "def test_it():\n    assert True\n")

    selection = python_selection.select(tmp_path, ["pkg/test_standalone.py"], NO_DEPS)

    assert _via(selection, "pkg/test_standalone.py") == "self"


# -- Serial threshold -----------------------------------------------------------


def test_serial_below_tests_constant_is_twenty() -> None:
    assert python_selection.SERIAL_BELOW_TESTS == 20


@pytest.mark.parametrize(
    ("test_count", "xdist_enabled", "expected"),
    [
        (19, True, True),
        (20, True, True),
        (21, True, False),
        (5, False, False),
    ],
)
def test_needs_serial_applies_at_or_below_the_threshold_only_when_xdist_is_enabled(
    test_count: int, xdist_enabled: bool, expected: bool
) -> None:
    assert python_selection.needs_serial(test_count, xdist_enabled) is expected


def test_count_tests_counts_sync_and_async_test_functions() -> None:
    source = (
        "def test_a():\n    assert True\n\n\n"
        "async def test_b():\n    assert True\n\n\n"
        "def helper():\n    return 1\n"
    )

    assert python_selection.count_tests(source) == 2
