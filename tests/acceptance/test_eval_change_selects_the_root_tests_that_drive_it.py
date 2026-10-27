"""A change to the eval selects the root tests that drive the eval in a child process.

Some root-pocket tests never import the eval package: they start it in a separate process
under the eval project's own environment. A change to any file of the eval package, to the
eval pocket's runner configuration or to its lockfile selects every such root test, each
naming the changed path that selected it, while a configuration or lockfile change still
widens the eval pocket to its full suite. A root test added later that drives the eval the
same way is selected with no listing written by hand. A change touching no eval file, and a
project with no root test driving another pocket, get exactly today's answer.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.acceptance.drivers.gate_liveness import make_copy
from tests.acceptance.drivers.scope_resolver import (
    RESOLVER,
    ScratchRepo,
    new_scratch_repo,
    pocket,
    resolve,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN = Path(__file__).resolve().parent / "fixtures" / "eval_driving_selection_before.json"

EVAL_PACKAGE_FILE = "eval/src/praxion_evals/adherence/report.py"
EVAL_CONFIG = "eval/pyproject.toml"
EVAL_LOCKFILE = "eval/uv.lock"
ROOT_TESTS_DRIVING_THE_EVAL = (
    "tests/acceptance/test_adherence_partial_output_check.py",
    "tests/e2e/test_adherence_spend_and_results.py",
    "tests/acceptance/test_adherence_eval_tests_start_no_claude.py",
)


def _resolve_here(root: Path, changed: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(RESOLVER), "--repo-root", str(root), "--json", "--changed", changed],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _root_selection(payload: dict) -> dict[str, str]:
    """Each test the root pocket selected, mapped to the changed path that selected it."""
    return {test["path"]: test["because"] for test in pocket(payload, ".")["tests"]}


# -- This repository: the recorded tests ------------------------------------------------------


@pytest.mark.parametrize("changed", [EVAL_PACKAGE_FILE, EVAL_CONFIG, EVAL_LOCKFILE])
@pytest.mark.parametrize("driving_test", ROOT_TESTS_DRIVING_THE_EVAL)
def test_an_eval_change_selects_each_root_test_that_drives_the_eval(
    changed: str, driving_test: str
) -> None:
    payload = _resolve_here(REPO_ROOT, changed)

    selected = _root_selection(payload)

    assert driving_test in selected, (
        f"{driving_test} drives the eval in a child process, yet {changed} did not select it; "
        f"root selection: {sorted(selected)[:40]}"
    )
    assert selected[driving_test] == changed, (
        f"{driving_test} names {selected[driving_test]!r}, not the path that selected it"
    )


@pytest.mark.parametrize("changed", [EVAL_CONFIG, EVAL_LOCKFILE])
def test_an_eval_configuration_or_lockfile_change_still_widens_the_eval_pocket(
    changed: str,
) -> None:
    payload = _resolve_here(REPO_ROOT, changed)

    widened = [
        entry
        for entry in payload["widen"]
        if entry["reason"] == "pocket-config-changed" and changed in entry["paths"]
    ]
    assert widened, f"no pocket-config-changed widen names {changed}: {payload['widen']}"
    assert pocket(payload, "eval")["selection"] == "full", pocket(payload, "eval")


def test_a_root_test_added_later_that_drives_the_eval_is_selected_with_no_other_edit(
    tmp_path: Path,
) -> None:
    copy = make_copy(tmp_path / "copy")
    planted = "tests/acceptance/test_planted_eval_suite_run.py"
    copy.write(
        planted,
        "from tests.acceptance.drivers.adherence_eval import run_eval_suite_under_tripwire\n\n\n"
        "def test_the_eval_suite_runs_under_the_tripwire(tmp_path):\n"
        "    assert run_eval_suite_under_tripwire(tmp_path) is not None\n",
    )
    copy.commit("a new root test that drives the eval like the existing ones")

    selected = _root_selection(_resolve_here(copy.root, EVAL_PACKAGE_FILE))

    assert selected.get(planted) == EVAL_PACKAGE_FILE, (
        f"the planted test was not selected for {EVAL_PACKAGE_FILE}: {selected.get(planted)!r}"
    )


# -- A managed project with its own eval pocket -----------------------------------------------

ROOT_PYPROJECT = '[tool.pytest.ini_options]\ntestpaths = ["tests", "scripts"]\n'
EVAL_PYPROJECT = (
    '[project]\nname = "praxion-evals"\nversion = "0.0.0"\n\n'
    '[tool.pytest.ini_options]\ntestpaths = ["tests"]\npythonpath = ["src"]\n'
)
EVAL_RUNNER = '''"""Runs the eval package in a child process under the eval project's own environment."""

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
EVAL_PROJECT = REPO_ROOT / "eval"
EVAL_PYTHON = "3.13"


def run_in_eval(code: str) -> str:
    uv = shutil.which("uv")
    result = subprocess.run(
        [uv, "run", "--quiet", "--python", EVAL_PYTHON, "--project", str(EVAL_PROJECT)]
        + ["python", "-c", code],
        capture_output=True,
        text=True,
        cwd=EVAL_PROJECT,
        timeout=600,
    )
    return result.stdout
'''
DRIVING_TEST = (
    "from tests.acceptance.drivers.eval_runner import run_in_eval\n\n\n"
    "def test_the_eval_reports_its_version():\n"
    "    assert run_in_eval('from praxion_evals import core; print(core.version())')\n"
)
SELF_DRIVING_TEST = (
    "import shutil\nimport subprocess\nfrom pathlib import Path\n\n"
    'EVAL_PROJECT = Path(__file__).resolve().parents[1] / "eval"\n\n\n'
    "def test_the_eval_reports_its_version():\n"
    "    result = subprocess.run(\n"
    '        [shutil.which("uv"), "run", "--project", str(EVAL_PROJECT), "python", "-c",\n'
    '         "from praxion_evals import core; print(core.version())"],\n'
    "        capture_output=True, text=True, timeout=600,\n"
    "    )\n"
    "    assert result.stdout\n"
)
PROJECT_EVAL_FILE = "eval/src/praxion_evals/core.py"
PROJECT_DRIVING_TEST = "tests/acceptance/test_drives_the_eval.py"


def build_project(workspace: Path, *, drives_the_eval: bool) -> ScratchRepo:
    """A root pocket and an `eval` pocket; optionally a root test driving the eval."""
    repo = new_scratch_repo(workspace)
    repo.write("pyproject.toml", ROOT_PYPROJECT)
    repo.write("tests/test_smoke.py", "def test_runs():\n    assert True\n")
    repo.write("scripts/tool.py", "def tool():\n    return 1\n")
    repo.write(
        "scripts/test_tool.py", "from tool import tool\n\n\ndef test_tool():\n    assert tool()\n"
    )
    repo.write(EVAL_CONFIG, EVAL_PYPROJECT)
    repo.write("eval/src/praxion_evals/__init__.py")
    repo.write(PROJECT_EVAL_FILE, "def version():\n    return '1'\n")
    repo.write(
        "eval/tests/test_core.py",
        "from praxion_evals import core\n\n\ndef test_version():\n    assert core.version()\n",
    )
    if drives_the_eval:
        repo.write("tests/acceptance/drivers/eval_runner.py", EVAL_RUNNER)
        repo.write(PROJECT_DRIVING_TEST, DRIVING_TEST)
    repo.commit_all("seed")
    return repo


def raw_answer(repo: ScratchRepo, changed: str) -> str:
    """The resolver's `--json` stdout, byte for byte."""
    result = subprocess.run(
        [sys.executable, str(RESOLVER), "--repo-root", str(repo.root), "--json"]
        + ["--changed", changed],
        cwd=repo.root,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def frozen_answer(case: str) -> str:
    """Today's answer for `case`, frozen from the resolver at the base commit."""
    return json.loads(FROZEN.read_text(encoding="utf-8"))[case]


def test_a_managed_projects_root_test_driving_its_eval_pocket_is_selected(
    tmp_path: Path,
) -> None:
    repo = build_project(tmp_path, drives_the_eval=True)

    payload = resolve(repo, "--changed", PROJECT_EVAL_FILE)

    selected = {test["path"]: test["because"] for test in pocket(payload, ".")["tests"]}
    assert selected.get(PROJECT_DRIVING_TEST) == PROJECT_EVAL_FILE, (
        f"the root test driving the eval was not selected for {PROJECT_EVAL_FILE}: {selected}"
    )


def test_a_managed_projects_root_test_that_itself_starts_the_eval_is_selected(
    tmp_path: Path,
) -> None:
    repo = build_project(tmp_path, drives_the_eval=False)
    repo.write("tests/test_starts_the_eval.py", SELF_DRIVING_TEST)
    repo.commit_all("a root test that starts the eval itself")

    payload = resolve(repo, "--changed", PROJECT_EVAL_FILE)

    selected = {test["path"]: test["because"] for test in pocket(payload, ".")["tests"]}
    assert selected.get("tests/test_starts_the_eval.py") == PROJECT_EVAL_FILE, (
        f"the root test starting the eval itself was not selected: {selected}"
    )


# Each case: whether the project has a root test driving the eval, and the changed path.
UNCHANGED_CASES = {
    "driving-project-root-change": (True, "scripts/tool.py"),
    "driving-project-root-test-change": (True, "tests/test_smoke.py"),
    "plain-project-eval-file-change": (False, PROJECT_EVAL_FILE),
    "plain-project-eval-config-change": (False, EVAL_CONFIG),
}


@pytest.mark.parametrize("case", sorted(UNCHANGED_CASES))
def test_without_the_condition_the_answer_is_byte_identical_to_todays(
    tmp_path: Path, case: str
) -> None:
    drives_the_eval, changed = UNCHANGED_CASES[case]
    repo = build_project(tmp_path, drives_the_eval=drives_the_eval)

    answer = raw_answer(repo, changed)

    assert answer == frozen_answer(case), f"{case}: today's answer changed:\n{answer}"
