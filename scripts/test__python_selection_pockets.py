"""Tests for `_python_selection` pockets: a bare name, a single-segment stem and a layout
pairing connect only within one pocket, while slash literals, globs, dotted imports and declared
dependencies still cross pockets.

The loader and the file builders are shared with ``scripts/test__python_selection.py``, which
holds the graph's other edges.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from test__python_selection import (  # noqa: E402
    NO_DEPS,
    _via,
    _write,
    declared_deps,
    python_selection,
)

# -- Pockets: a bare name, a single-segment stem and a layout pairing stay inside one --------

POCKETS = (".", "eval")
EVAL_CLI = "eval/src/evals/adherence/cli.py"
PLAIN_TEST = "def test_runs():\n    assert True\n"


def _derive_in_pockets(
    root: Path,
    changed: str,
    files: dict[str, str],
    deps: Any = NO_DEPS,
    pocket_roots: tuple[str, ...] = POCKETS,
) -> Any:
    for rel, text in files.items():
        _write(root, rel, text)
    return python_selection.derive(
        root, [changed], deps, files=tuple(files), pocket_roots=pocket_roots
    )


def _selected(derivation: Any) -> set[str]:
    return {test.path for test in derivation.tests}


def test_a_layout_pairing_never_crosses_a_pocket(tmp_path: Path) -> None:
    derivation = _derive_in_pockets(
        tmp_path,
        EVAL_CLI,
        {EVAL_CLI: "def main():\n    return 1\n", "scripts/test_cli.py": PLAIN_TEST},
    )

    assert _selected(derivation) == set()
    assert derivation.mapped == frozenset()


def test_a_layout_pairing_inside_one_pocket_still_selects(tmp_path: Path) -> None:
    derivation = _derive_in_pockets(
        tmp_path,
        "scripts/cli.py",
        {
            "scripts/cli.py": "def main():\n    return 0\n",
            "scripts/test_cli.py": PLAIN_TEST,
        },
    )

    assert _selected(derivation) == {"scripts/test_cli.py"}


def test_a_layout_pairing_picks_among_candidates_of_its_own_pocket_only(tmp_path: Path) -> None:
    derivation = _derive_in_pockets(
        tmp_path,
        EVAL_CLI,
        {
            EVAL_CLI: "def main():\n    return 1\n",
            "scripts/adherence/test_cli.py": PLAIN_TEST,
            "eval/tests/test_cli.py": PLAIN_TEST,
        },
    )

    assert _selected(derivation) == {"eval/tests/test_cli.py"}


_BARE_NAME_HOLDER = 'TARGET = "cli.py"\n\n\ndef test_names_its_target():\n    assert TARGET\n'


def test_a_bare_name_literal_never_crosses_a_pocket(tmp_path: Path) -> None:
    derivation = _derive_in_pockets(
        tmp_path,
        EVAL_CLI,
        {EVAL_CLI: "def main():\n    return 1\n", "tests/test_mentions_cli.py": _BARE_NAME_HOLDER},
    )

    assert _selected(derivation) == set()
    assert derivation.mapped == frozenset()


def test_a_bare_name_literal_inside_one_pocket_still_selects(tmp_path: Path) -> None:
    derivation = _derive_in_pockets(
        tmp_path,
        "scripts/cli.py",
        {
            "scripts/cli.py": "def main():\n    return 0\n",
            "tests/test_mentions_cli.py": _BARE_NAME_HOLDER,
            "eval/tests/test_mentions_cli.py": _BARE_NAME_HOLDER,
        },
    )

    assert _selected(derivation) == {"tests/test_mentions_cli.py"}
    assert _via(derivation.tests, "tests/test_mentions_cli.py") == "path-literal"


def test_a_slash_literal_still_crosses_a_pocket(tmp_path: Path) -> None:
    holder = 'TARGET = "adherence/cli.py"\n\n\ndef test_it():\n    assert TARGET\n'
    derivation = _derive_in_pockets(
        tmp_path,
        EVAL_CLI,
        {EVAL_CLI: "def main():\n    return 1\n", "tests/test_names_the_path.py": holder},
    )

    assert _selected(derivation) == {"tests/test_names_the_path.py"}


def test_a_glob_literal_still_crosses_a_pocket(tmp_path: Path) -> None:
    holder = 'TARGET = "eval/src/**/cli.py"\n\n\ndef test_it():\n    assert TARGET\n'
    derivation = _derive_in_pockets(
        tmp_path,
        EVAL_CLI,
        {EVAL_CLI: "def main():\n    return 1\n", "tests/test_globs_it.py": holder},
    )

    assert _selected(derivation) == {"tests/test_globs_it.py"}


def test_a_declared_dependency_still_crosses_a_pocket(tmp_path: Path) -> None:
    deps = declared_deps.DeclaredDeps(
        deps=(
            declared_deps.DepEntry(
                paths=(EVAL_CLI,),
                tests=("tests/test_reads_the_contract.py",),
                why="reads the eval command line by convention",
            ),
        ),
        inert=(),
    )

    derivation = _derive_in_pockets(
        tmp_path,
        EVAL_CLI,
        {EVAL_CLI: "def main():\n    return 1\n", "tests/test_reads_the_contract.py": PLAIN_TEST},
        deps,
    )

    assert _via(derivation.tests, "tests/test_reads_the_contract.py") == "declared"


_SHARED_STEM_POCKETS = (".", "eval", "other")
_SHARED_STEM_FILES = {
    "eval/src/cli.py": "def main():\n    return 1\n",
    "other/src/cli.py": "def main():\n    return 2\n",
}


def test_a_short_name_import_never_reaches_a_shared_name_in_another_pocket(tmp_path: Path) -> None:
    importer = "import cli\n\n\ndef test_main():\n    assert cli.main()\n"
    derivation = _derive_in_pockets(
        tmp_path,
        "eval/src/cli.py",
        {**_SHARED_STEM_FILES, "scripts/test_entry.py": importer},
        pocket_roots=_SHARED_STEM_POCKETS,
    )

    assert _selected(derivation) == set()
    assert derivation.mapped == frozenset()


def test_a_short_name_import_reaches_every_match_in_its_own_pocket(tmp_path: Path) -> None:
    importer = "import cli\n\n\ndef test_main():\n    assert cli.main()\n"
    files = {
        "eval/one/cli.py": "def main():\n    return 1\n",
        "eval/two/cli.py": "def main():\n    return 2\n",
        "eval/tests/test_entry.py": importer,
    }

    first = _derive_in_pockets(tmp_path, "eval/one/cli.py", files)
    second = python_selection.derive(
        tmp_path, ["eval/two/cli.py"], NO_DEPS, files=tuple(files), pocket_roots=POCKETS
    )

    assert _selected(first) == _selected(second) == {"eval/tests/test_entry.py"}


def test_a_short_name_import_reaches_a_name_only_one_file_in_the_repository_bears(
    tmp_path: Path,
) -> None:
    importer = (
        "import importlib\n\n\ndef test_tiers():\n"
        "    assert importlib.import_module('report_registry')\n"
    )
    derivation = _derive_in_pockets(
        tmp_path,
        "scripts/report_registry.py",
        {
            "scripts/report_registry.py": "def tiers():\n    return []\n",
            "eval/tests/test_uses_the_registry.py": importer,
        },
    )

    assert _via(derivation.tests, "eval/tests/test_uses_the_registry.py") == "import"


def test_a_dotted_multi_segment_import_still_crosses_a_pocket(tmp_path: Path) -> None:
    importer = "import adherence.cli\n\n\ndef test_main():\n    assert adherence.cli.main()\n"
    derivation = _derive_in_pockets(
        tmp_path,
        EVAL_CLI,
        {
            EVAL_CLI: "def main():\n    return 1\n",
            "other/src/pkg/cli.py": "def main():\n    return 2\n",
            "scripts/test_entry.py": importer,
        },
        pocket_roots=(".", "eval", "other"),
    )

    assert _via(derivation.tests, "scripts/test_entry.py") == "import"


def test_a_path_whose_only_connections_cross_pockets_is_not_mapped(tmp_path: Path) -> None:
    derivation = _derive_in_pockets(
        tmp_path,
        EVAL_CLI,
        {
            EVAL_CLI: "def main():\n    return 1\n",
            "scripts/test_cli.py": PLAIN_TEST,
            "tests/test_mentions_cli.py": _BARE_NAME_HOLDER,
        },
    )

    assert EVAL_CLI not in derivation.mapped
