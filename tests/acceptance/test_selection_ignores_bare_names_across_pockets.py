"""A file's bare name never pulls another pocket's tests into a change's scope.

A common file name such as `cli.py` exists in several pockets. A test in one pocket is
selected for a change in another pocket only through a connection that exists: an import
statement that can load the changed file from where it is written, a mention of the file
that includes a directory part, or a declared dependency. A bare-name mention, a test
named after a same-named file, or a short-name import that loads a different file selects
nothing across pockets. Inside one pocket every connection works as before, and a change
no remaining connection ties to a test still widens: narrowing removes only connections
that do not exist.

Scratch scenarios mirror the recorded case: a root pocket and an `eval` pocket, each with
its own runner configuration, sharing the names `cli.py` and `lineage.py`. Two scenarios
run the resolver over this repository itself, for the two recorded files.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.acceptance.drivers.scope_resolver import (
    RESOLVER,
    ScratchRepo,
    new_scratch_repo,
    pocket,
    resolve,
    selected_tests,
    unmapped_paths,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT_PYPROJECT = '[tool.pytest.ini_options]\ntestpaths = ["tests", "scripts"]\n'
EVAL_PYPROJECT = (
    '[project]\nname = "evals"\nversion = "0.0.0"\n\n'
    '[tool.pytest.ini_options]\ntestpaths = ["tests"]\npythonpath = ["src"]\n'
)
EVAL_CLI = "eval/src/evals/adherence/cli.py"
EVAL_LINEAGE = "eval/src/evals/adherence/lineage.py"
RECORDED_CLI = "eval/src/praxion_evals/adherence/cli.py"
RECORDED_LINEAGE = "eval/src/praxion_evals/adherence/lineage.py"


def _literal_holder(literal: str) -> str:
    return f'TARGET = "{literal}"\n\n\ndef test_names_its_target():\n    assert TARGET\n'


def _plain_test() -> str:
    return "def test_runs():\n    assert True\n"


@pytest.fixture
def repo(tmp_path: Path) -> ScratchRepo:
    """A root pocket and an `eval` pocket, each with tests and a same-named `cli.py`."""
    scratch = new_scratch_repo(tmp_path)
    scratch.write("pyproject.toml", ROOT_PYPROJECT)
    scratch.write("tests/test_smoke.py", _plain_test())
    scratch.write("scripts/cli.py", "def main():\n    return 0\n")
    scratch.write("eval/pyproject.toml", EVAL_PYPROJECT)
    scratch.write("eval/src/evals/__init__.py")
    scratch.write("eval/src/evals/adherence/__init__.py")
    scratch.write("eval/src/evals/adherence/cli.py", "def main():\n    return 1\n")
    scratch.write(
        "eval/tests/test_adherence_cli.py",
        "from evals.adherence import cli\n\n\ndef test_main():\n    assert cli.main() == 1\n",
    )
    return scratch


# -- A bare-name connection selects nothing in another pocket ----------------------------------


@pytest.mark.parametrize(
    ("holder", "text"),
    [
        ("tests/test_mentions_cli.py", _literal_holder("cli.py")),
        ("tests/test_cli.py", _plain_test()),
        ("scripts/test_cli.py", _plain_test()),
    ],
    ids=["bare-name-mention", "test-named-after-the-file", "sibling-named-after-the-file"],
)
def test_a_root_test_tied_only_by_the_bare_name_is_not_selected_for_an_eval_change(
    repo: ScratchRepo, holder: str, text: str
) -> None:
    repo.write(holder, text)
    repo.commit_all("seed")

    payload = resolve(repo, "--changed", EVAL_CLI)

    assert holder not in selected_tests(payload), (
        f"{holder} is tied to {EVAL_CLI} only by the name cli.py, yet was selected: "
        f"{sorted(selected_tests(payload))}"
    )


def test_an_eval_test_tied_only_by_the_bare_name_is_not_selected_for_a_root_change(
    repo: ScratchRepo,
) -> None:
    repo.write("eval/tests/test_mentions_cli.py", _literal_holder("cli.py"))
    repo.commit_all("seed")

    payload = resolve(repo, "--changed", "scripts/cli.py")

    assert "eval/tests/test_mentions_cli.py" not in selected_tests(payload), (
        f"an eval test naming only 'cli.py' was selected for scripts/cli.py: {payload}"
    )


def test_a_short_name_import_that_loads_a_sibling_is_not_tied_to_another_pockets_file(
    repo: ScratchRepo,
) -> None:
    repo.write(
        "scripts/test_entry.py", "import cli\n\n\ndef test_entry():\n    assert cli.main() == 0\n"
    )
    repo.commit_all("seed")

    payload = resolve(repo, "--changed", EVAL_CLI)

    assert "scripts/test_entry.py" not in selected_tests(payload), (
        f"`import cli` beside scripts/cli.py cannot load {EVAL_CLI}, yet selected the test: "
        f"{sorted(selected_tests(payload))}"
    )


def test_a_change_only_a_bare_name_reached_widens_naming_the_path(repo: ScratchRepo) -> None:
    repo.write(EVAL_LINEAGE, "def chain():\n    return []\n")
    repo.write("tests/test_mentions_lineage.py", _literal_holder("lineage.py"))
    repo.commit_all("seed")

    payload = resolve(repo, "--changed", EVAL_LINEAGE)

    assert EVAL_LINEAGE in unmapped_paths(payload), (
        f"no remaining connection ties {EVAL_LINEAGE} to a test, yet it did not widen: {payload}"
    )
    assert payload["decision"] == "widened"


# -- Connections that exist still select, in any pocket ----------------------------------------


@pytest.mark.parametrize(
    ("holder", "text"),
    [
        ("tests/test_names_the_path.py", _literal_holder("adherence/cli.py")),
        ("tests/test_names_the_full_path.py", _literal_holder(EVAL_CLI)),
    ],
    ids=["directory-part-mention", "full-path-mention"],
)
def test_a_root_test_naming_the_file_with_a_directory_part_is_selected(
    repo: ScratchRepo, holder: str, text: str
) -> None:
    repo.write(holder, text)
    repo.commit_all("seed")

    payload = resolve(repo, "--changed", EVAL_CLI)

    assert holder in selected_tests(payload), (
        f"{holder} names {EVAL_CLI} with a directory part, yet was not selected: {payload}"
    )


def test_a_root_test_declared_for_an_eval_file_is_selected(repo: ScratchRepo) -> None:
    repo.write("tests/test_reads_the_cli_contract.py", _plain_test())
    repo.write(
        "tests/declared-deps.toml",
        "schema = 1\n\n[[dep]]\n"
        f'paths = ["{EVAL_CLI}"]\n'
        'tests = ["tests/test_reads_the_cli_contract.py"]\n'
        'why = "reads the eval command line by convention"\n',
    )
    repo.commit_all("seed")

    payload = resolve(repo, "--changed", EVAL_CLI)

    assert "tests/test_reads_the_cli_contract.py" in selected_tests(payload), payload


def test_an_eval_test_loading_a_root_script_by_import_is_selected_when_the_script_changes(
    repo: ScratchRepo,
) -> None:
    repo.write("scripts/report_registry.py", "def tiers():\n    return ['standard']\n")
    repo.write(
        "eval/tests/test_uses_the_registry.py",
        "import importlib\nimport sys\nfrom pathlib import Path\n\n"
        "_SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'\n\n\n"
        "def test_tiers():\n"
        "    sys.path.insert(0, str(_SCRIPTS))\n"
        "    registry = importlib.import_module('report_registry')\n"
        "    assert registry.tiers()\n",
    )
    repo.commit_all("seed")

    payload = resolve(repo, "--changed", "scripts/report_registry.py")

    assert "eval/tests/test_uses_the_registry.py" in selected_tests(payload), (
        f"an eval test importing the root script was not selected: {payload}"
    )


def test_the_eval_pockets_own_importer_is_still_selected(repo: ScratchRepo) -> None:
    repo.commit_all("seed")

    payload = resolve(repo, "--changed", EVAL_CLI)

    assert "eval/tests/test_adherence_cli.py" in selected_tests(payload), payload


@pytest.mark.parametrize(
    ("holder", "text"),
    [
        ("tests/test_mentions_cli.py", _literal_holder("cli.py")),
        ("scripts/test_cli.py", _plain_test()),
        (
            "scripts/test_entry.py",
            "import cli\n\n\ndef test_entry():\n    assert cli.main() == 0\n",
        ),
    ],
    ids=["bare-name-mention", "sibling-named-after-the-file", "sibling-import"],
)
def test_inside_one_pocket_the_same_connections_still_select(
    repo: ScratchRepo, holder: str, text: str
) -> None:
    repo.write(holder, text)
    repo.commit_all("seed")

    payload = resolve(repo, "--changed", "scripts/cli.py")

    assert holder in selected_tests(payload), (
        f"{holder} reaches scripts/cli.py inside the root pocket, yet was not selected: {payload}"
    )


# -- The recorded case, over this repository ----------------------------------------------------


def _resolve_here(changed: str) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            str(RESOLVER),
            "--repo-root",
            str(REPO_ROOT),
            "--json",
            "--changed",
            changed,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("changed", [RECORDED_CLI, RECORDED_LINEAGE])
def test_a_recorded_eval_file_selects_no_root_test_by_its_name_alone(changed: str) -> None:
    payload = _resolve_here(changed)

    named_after_it = [
        test["path"]
        for test in pocket(payload, ".")["tests"]
        if Path(test["path"]).name == f"test_{Path(changed).name}"
    ]
    assert named_after_it == [], (
        f"root tests named after {Path(changed).name} were selected for {changed}: {named_after_it}"
    )


def test_this_repositorys_eval_test_importing_a_root_script_is_still_selected() -> None:
    payload = _resolve_here("scripts/artifact_registry.py")

    assert "eval/tests/test_harness_family1_task_manifest.py" in selected_tests(payload), (
        "the eval test that imports scripts/artifact_registry.py was not selected for it"
    )
