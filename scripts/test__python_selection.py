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

import ast
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


# -- Literal classes and basename-pattern readers ------------------------------


@pytest.mark.parametrize(
    ("literal", "expected"),
    [
        ("", "ignored"),
        (".", "ignored"),
        ("*", "ignored"),
        ("**", "ignored"),
        ("?", "ignored"),
        ("?*", "ignored"),
        (".*", "ignored"),
        ("*.*", "ignored"),
        ("[a-z]*", "ignored"),
        ("[abc]", "ignored"),
        ("settings.yaml", "exact-basename"),
        ("Makefile", "exact-basename"),
        ("*.md", "basename-pattern"),
        ("report_??.csv", "basename-pattern"),
        ("[abc]_case.json", "basename-pattern"),
        ("v2*", "basename-pattern"),
        ("docs/*.md", "path-glob"),
        ("**/*", "path-glob"),
        ("docs/guide.md", "path-suffix"),
    ],
)
def test_a_literal_lands_in_exactly_one_class(literal: str, expected: str) -> None:
    """Letters inside a bracket class do not count as letters outside the wildcards."""
    assert python_selection._literal_class(literal) == expected


def _index_of(**modules: str) -> Any:
    """A literal index holding one module per keyword: `name="<python source>"`."""
    index = python_selection._LiteralIndex()
    for name, source in modules.items():
        index.add_module(f"{name}.py", ast.parse(source))
    return index


def test_pattern_readers_match_the_basename_at_any_depth() -> None:
    index = _index_of(reader='GLOB = "*.md"\n')

    assert index.pattern_readers("README.md") == {"reader.py"}
    assert index.pattern_readers("docs/deep/er/guide.md") == {"reader.py"}
    assert index.pattern_readers("docs/guide.txt") == set()


def test_a_pattern_matches_the_whole_basename_not_a_part_of_it() -> None:
    index = _index_of(reader='GLOB = "report_??.csv"\n')

    assert index.pattern_readers("data/report_01.csv") == {"reader.py"}
    assert index.pattern_readers("data/report_001.csv") == set()
    assert index.pattern_readers("data/old_report_01.csv") == set()


def test_a_module_is_never_its_own_pattern_reader() -> None:
    index = _index_of(reader='GLOB = "*.py"\n')

    assert index.pattern_readers("reader.py") == set()
    assert index.pattern_readers("other.py") == {"reader.py"}


def test_a_pattern_that_does_not_compile_is_ignored() -> None:
    index = _index_of(reader='ODD = "a[b-a]*"\n')

    assert index.pattern_readers("ab.txt") == set()


def test_letterless_wildcards_name_no_file() -> None:
    index = _index_of(reader='ALL = ["*", "**", "?", ".*", "*.*", "[a-z]*"]\n')

    assert index.pattern_readers("data.md") == set()
    assert index.pattern_readers("a.b") == set()
    assert index.modules_matching("data.md") == set()


def test_pattern_readers_never_include_a_holder_of_a_named_literal() -> None:
    index = _index_of(
        exact='NAME = "guide.md"\n',
        suffix='PATH = "docs/guide.md"\n',
        glob='GLOB = "docs/*.md"\n',
    )

    assert index.pattern_readers("docs/guide.md") == set()
    assert index.modules_matching("docs/guide.md") == {"exact.py", "suffix.py", "glob.py"}


def test_modules_matching_never_returns_a_pattern_holder() -> None:
    index = _index_of(reader='GLOB = "*.md"\n')

    assert index.modules_matching("README.md") == set()


def test_the_graph_lists_pattern_readers_sorted(tmp_path: Path) -> None:
    _write(tmp_path, "b_reader.py", 'GLOB = "*.md"\n')
    _write(tmp_path, "a_reader.py", 'GLOB = "READ*"\n')
    _write(tmp_path, "README.md", "# x\n")
    files = ("b_reader.py", "a_reader.py", "README.md")

    graph = python_selection.Graph(tmp_path, files, ["README.md"], NO_DEPS, (".",))

    assert graph.pattern_readers("README.md") == ("a_reader.py", "b_reader.py")
    assert graph.dependents("README.md", "path-literal") == ()


# -- Basename patterns select their readers ------------------------------------

_READS_EVERY_MARKDOWN = 'GLOB = "*.md"\n\n\ndef test_reads():\n    assert True\n'
_READS_EVERY_PYTHON = 'GLOB = "*.py"\n\n\ndef test_reads():\n    assert True\n'


def test_a_data_file_selects_its_pattern_reader_and_is_accounted_for(tmp_path: Path) -> None:
    _write(tmp_path, "docs/guide.md", "# guide\n")
    _write(tmp_path, "tests/test_reads_docs.py", _READS_EVERY_MARKDOWN)

    derivation = python_selection.derive(tmp_path, ["docs/guide.md"], NO_DEPS)

    (test,) = derivation.tests
    assert (test.path, test.via, test.because) == (
        "tests/test_reads_docs.py",
        "path-literal",
        "docs/guide.md",
    )
    assert derivation.mapped == {"docs/guide.md"}


def test_a_source_file_reached_only_by_a_pattern_selects_the_reader_but_is_not_accounted_for(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/tool.py", "value = 1\n")
    _write(tmp_path, "tests/test_scan.py", _READS_EVERY_PYTHON)

    derivation = python_selection.derive(tmp_path, ["pkg/tool.py"], NO_DEPS)

    assert [t.path for t in derivation.tests] == ["tests/test_scan.py"]
    assert derivation.mapped == frozenset()


def test_a_source_file_with_a_named_edge_is_accounted_for_and_keeps_every_reader(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/foo.py", "value = 1\n")
    _write(tmp_path, "pkg/test_foo.py", "def test_value():\n    assert True\n")
    _write(tmp_path, "tests/test_scan.py", _READS_EVERY_PYTHON)

    derivation = python_selection.derive(tmp_path, ["pkg/foo.py"], NO_DEPS)

    assert _via(derivation.tests, "pkg/test_foo.py") == "layout"
    assert _via(derivation.tests, "tests/test_scan.py") == "path-literal"
    assert derivation.mapped == {"pkg/foo.py"}


def test_a_data_file_and_a_source_file_in_one_change_are_judged_separately(tmp_path: Path) -> None:
    _write(tmp_path, "docs/guide.md", "# guide\n")
    _write(tmp_path, "pkg/tool.py", "value = 1\n")
    _write(tmp_path, "tests/test_scan.py", 'GLOB = ["*.md", "*.py"]\n\n\ndef test_x():\n    pass\n')

    derivation = python_selection.derive(tmp_path, ["docs/guide.md", "pkg/tool.py"], NO_DEPS)

    assert derivation.mapped == {"docs/guide.md"}


def test_a_pattern_is_a_first_hop_only_and_never_connects_through_a_module(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/lib.py", "value = 1\n")
    _write(tmp_path, "pkg/helper.py", "import lib\n")
    _write(tmp_path, "pkg/test_helper.py", "def test_helper():\n    assert True\n")
    _write(tmp_path, "tests/test_pat.py", 'GLOB = "helper*"\n\n\ndef test_x():\n    pass\n')

    selection = python_selection.select(tmp_path, ["pkg/lib.py"], NO_DEPS)

    assert "pkg/test_helper.py" in {s.path for s in selection}
    assert "tests/test_pat.py" not in {s.path for s in selection}


def test_a_test_importing_a_non_test_pattern_holder_is_not_selected(tmp_path: Path) -> None:
    """Fan-out through production modules that hold `*.md` selected most of the suite."""
    _write(tmp_path, "docs/guide.md", "# guide\n")
    _write(tmp_path, "pkg/scan.py", 'GLOB = "*.md"\n')
    _write(tmp_path, "tests/test_scan.py", "import scan\n\n\ndef test_x():\n    pass\n")

    derivation = python_selection.derive(tmp_path, ["docs/guide.md"], NO_DEPS)

    assert derivation.tests == ()
    assert derivation.mapped == frozenset()


def test_a_non_test_holder_beside_a_test_holder_adds_nothing(tmp_path: Path) -> None:
    _write(tmp_path, "docs/guide.md", "# guide\n")
    _write(tmp_path, "pkg/scan.py", 'GLOB = "*.md"\n')
    _write(tmp_path, "tests/test_scan.py", "import scan\n\n\ndef test_x():\n    pass\n")
    _write(tmp_path, "tests/test_reads_docs.py", _READS_EVERY_MARKDOWN)

    derivation = python_selection.derive(tmp_path, ["docs/guide.md"], NO_DEPS)

    assert [t.path for t in derivation.tests] == ["tests/test_reads_docs.py"]
    assert derivation.mapped == {"docs/guide.md"}


def test_nothing_propagates_from_a_test_holder_of_a_pattern(tmp_path: Path) -> None:
    """The holder is found directly and never expanded: its own importers are not selected."""
    _write(tmp_path, "docs/guide.md", "# guide\n")
    _write(tmp_path, "tests/test_reads_docs.py", _READS_EVERY_MARKDOWN)
    _write(
        tmp_path,
        "tests/test_imports_reader.py",
        "import test_reads_docs\n\n\ndef test_y():\n    pass\n",
    )

    derivation = python_selection.derive(tmp_path, ["docs/guide.md"], NO_DEPS)

    assert [t.path for t in derivation.tests] == ["tests/test_reads_docs.py"]


def test_a_source_file_matched_by_a_non_test_holder_only_still_widens(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/tool.py", "value = 1\n")
    _write(tmp_path, "pkg/scan.py", 'GLOB = "*.py"\n')

    derivation = python_selection.derive(tmp_path, ["pkg/tool.py"], NO_DEPS)

    assert derivation.tests == ()
    assert derivation.mapped == frozenset()


def test_a_named_edge_outranks_the_pattern_that_also_reaches_the_test(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/foo.py", "value = 1\n")
    _write(tmp_path, "pkg/test_foo.py", 'GLOB = "*.py"\n\n\ndef test_value():\n    pass\n')

    selection = python_selection.select(tmp_path, ["pkg/foo.py"], NO_DEPS)

    assert _via(selection, "pkg/test_foo.py") == "layout"


def test_a_changed_test_holding_a_matching_pattern_stays_self(tmp_path: Path) -> None:
    _write(tmp_path, "tests/test_scan.py", _READS_EVERY_PYTHON)

    derivation = python_selection.derive(tmp_path, ["tests/test_scan.py"], NO_DEPS)

    (test,) = derivation.tests
    assert (test.path, test.via, test.because) == (
        "tests/test_scan.py",
        "self",
        "tests/test_scan.py",
    )


def test_letterless_wildcards_select_nothing_and_account_for_nothing(tmp_path: Path) -> None:
    _write(tmp_path, "docs/guide.md", "# guide\n")
    _write(
        tmp_path,
        "tests/test_scan.py",
        'ALL = ["*", "**", "?", ".*", "*.*"]\n\n\ndef test_x():\n    pass\n',
    )

    derivation = python_selection.derive(tmp_path, ["docs/guide.md"], NO_DEPS)

    assert derivation.tests == ()
    assert derivation.mapped == frozenset()


def test_an_unrunnable_pattern_reader_is_neither_selected_nor_accounted_for(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "docs/guide.md", "# guide\n")
    _write(tmp_path, "tests/test_reads_docs.py", _READS_EVERY_MARKDOWN)

    derivation = python_selection.derive(
        tmp_path, ["docs/guide.md"], NO_DEPS, is_runnable=lambda _path: False
    )

    assert derivation.tests == ()
    assert derivation.mapped == frozenset()


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


# -- A graph built once serves every derivation ---------------------------------------


MIXED_FILES = {
    "pkg/foo.py": "value = 1\n",
    "pkg/test_foo.py": "def test_value():\n    assert True\n",
    "lib/helper.py": "value = 2\n",
    "tests/test_uses_helper.py": "import helper\n\n\ndef test_it():\n    assert True\n",
    "data/table.csv": "a,b\n",
    "tests/test_reads_table.py": 'NAME = "table.csv"\n\n\ndef test_it():\n    pass\n',
    "docs/guide.md": "# guide\n",
    "tests/test_reads_docs.py": _READS_EVERY_MARKDOWN,
    "orphan.py": "value = 3\n",
}


def _mixed_repo(root: Path) -> tuple[str, ...]:
    """One path per edge source, so a shared graph is exercised on each."""
    for rel, text in MIXED_FILES.items():
        _write(root, rel, text)
    return tuple(MIXED_FILES)


def _counting_graph(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Record every graph construction made by `derive`, whatever its caller."""
    built: list[int] = []
    original_init = python_selection.Graph.__init__

    def counting_init(self: object, *args: object, **kwargs: object) -> None:
        built.append(1)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(python_selection.Graph, "__init__", counting_init)
    return built


@pytest.mark.parametrize("path", [*MIXED_FILES, "pkg/missing.py"])
def test_a_prebuilt_graph_derives_exactly_what_a_fresh_build_derives(
    tmp_path: Path, path: str
) -> None:
    files = _mixed_repo(tmp_path)
    graph = python_selection.build_graph(tmp_path, files, NO_DEPS)

    fresh = python_selection.derive(tmp_path, [path], NO_DEPS, files=files)
    shared = python_selection.derive(tmp_path, [path], NO_DEPS, files=files, graph=graph)

    assert shared == fresh


def test_a_prebuilt_graph_is_built_once_however_many_paths_it_serves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = _mixed_repo(tmp_path)
    built = _counting_graph(monkeypatch)

    graph = python_selection.build_graph(tmp_path, files, NO_DEPS)
    derived = [
        python_selection.derive(tmp_path, [path], NO_DEPS, files=files, graph=graph)
        for path in files
    ]

    assert len(derived) == len(files)
    assert len(built) == 1


def test_a_changed_path_the_prebuilt_graph_does_not_know_gets_its_own_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A deleted or new path joins the node set of a single-path derivation; a graph
    # built without it would answer differently, so the shared one must not be used.
    files = _mixed_repo(tmp_path)
    graph = python_selection.build_graph(tmp_path, files, NO_DEPS)
    built = _counting_graph(monkeypatch)

    python_selection.derive(tmp_path, ["pkg/deleted.py"], NO_DEPS, files=files, graph=graph)

    assert len(built) == 1
