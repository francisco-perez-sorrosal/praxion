"""A step whose `Check:` cannot collect is refused before its series' first request.

`scripts/_step_loop_gate.py` reads a `--collect-only` summary, `scripts/_step_loop_record_gate.py`
asks the check to collect as written, and `scripts/step_loop.py` stops before the request goes out.
The runs here are pytest's own, in a scratch directory: the refusal is read off what a real
collection prints, and a doubtful run is never a stop.
"""

from __future__ import annotations

import shlex
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import step_loop  # noqa: E402
from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_action import HUMAN_CAUSES, Spawn  # noqa: E402
from _step_loop_gate import collected  # noqa: E402
from _step_loop_record_gate import check_collects  # noqa: E402
from _step_loop_render import RequestKey  # noqa: E402

ABSENT_PLUGIN = "pytest-absent-unit-plugin"
NEEDS_AN_ABSENT_PLUGIN = (
    '[project]\nname = "demo"\nversion = "0.0.0"\n\n'
    f'[tool.pytest.ini_options]\nrequired_plugins = ["{ABSENT_PLUGIN}"]\n'
)
PASSING_TEST = "def test_it():\n    assert True\n"
STEP_ONE = "Step 1"  # id-citation-discipline:ignore (plan heading format)
PYTEST = f"{shlex.quote(sys.executable)} -m pytest"


def step_checking(command):
    block = f"**Check**: `{command}` expects pass>=1 fail=0"
    plan = f"# Plan\n\n## Steps\n\n### {STEP_ONE}: Do it\n\n**Assignee**: implementer\n{block}\n"
    return parse_plan_steps(plan)[0]


def repo_with(tmp_path, **files):
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    ("output", "shown"),
    [
        pytest.param("a.py::test_x\n\n3 tests collected in 0.02s\n", True, id="tests-collected"),
        pytest.param("no tests collected in 0.00s\n", True, id="nothing-selected"),
        pytest.param("no tests collected, 1 error in 0.05s\n", True, id="collection-error"),
        pytest.param("2/3 tests collected (1 deselected) in 0.01s\n", True, id="deselected"),
        pytest.param("ERROR: Missing required plugins: x\n", False, id="stopped-before-collecting"),
        pytest.param("ERROR a.py - ImportError in 3s\n", False, id="a-node-line-is-no-summary"),
        pytest.param("", False, id="no-output"),
    ],
)
def test_a_collect_only_summary_is_read_off_its_last_duration_line(output, shown):
    assert collected(output) is shown


def test_a_missing_plugin_refuses_naming_the_check_and_what_collection_printed(tmp_path):
    repo = repo_with(tmp_path, **{"pyproject.toml": NEEDS_AN_ABSENT_PLUGIN})
    command = f"{PYTEST} -q"

    why = check_collects(repo, step_checking(command))

    assert why is not None
    assert command in why
    assert ABSENT_PLUGIN in why


def test_a_check_that_collects_is_not_refused(tmp_path):
    repo = repo_with(tmp_path, **{"test_ok.py": PASSING_TEST})

    assert check_collects(repo, step_checking(f"{PYTEST} test_ok.py -q")) is None


def test_a_test_file_the_step_has_yet_to_write_is_not_refused(tmp_path):
    assert check_collects(tmp_path, step_checking(f"{PYTEST} test_later.py -q")) is None


def test_a_module_that_fails_to_import_is_a_red_check_not_a_refused_one(tmp_path):
    repo = repo_with(tmp_path, **{"test_red.py": "import not_written_yet\n"})

    assert check_collects(repo, step_checking(f"{PYTEST} test_red.py -q")) is None


@pytest.mark.parametrize("operator", ["|", "&&", "||", ";"])
def test_a_check_with_a_shell_operator_word_is_not_probed(tmp_path, operator):
    repo = repo_with(tmp_path, **{"pyproject.toml": NEEDS_AN_ABSENT_PLUGIN})

    assert check_collects(repo, step_checking(f"{PYTEST} -q {operator} true")) is None


def test_a_check_that_is_not_pytest_is_never_run_by_the_probe(tmp_path):
    marker = tmp_path / "ran"
    code = f"import pathlib, sys; pathlib.Path({str(marker)!r}).touch(); sys.exit(3)"
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"

    assert check_collects(tmp_path, step_checking(command)) is None
    assert not marker.exists()


def stand_in_pytest(tmp_path, body):
    script = tmp_path / "pytest"
    script.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


@pytest.mark.parametrize(
    "body",
    [
        pytest.param("exit 0", id="silent-success"),
        pytest.param("echo odd; exit 0", id="odd-success"),
    ],
)
def test_a_run_that_exits_clean_is_never_a_refusal_whatever_it_printed(tmp_path, body):
    script = stand_in_pytest(tmp_path, body)

    assert check_collects(tmp_path, step_checking(f"{script} -q")) is None


def test_a_run_that_exits_without_a_summary_is_refused_with_its_exit_when_silent(tmp_path):
    script = stand_in_pytest(tmp_path, "exit 3")

    why = check_collects(tmp_path, step_checking(f"{script} -q"))

    assert why is not None
    assert "exit 3, no output" in why


def test_only_the_series_first_implement_request_is_asked_to_collect(tmp_path):
    repo = repo_with(tmp_path, **{"pyproject.toml": NEEDS_AN_ABSENT_PLUGIN})
    step = step_checking(f"{PYTEST} -q")
    task = SimpleNamespace(repo=repo)
    first = Spawn(step, RequestKey("1", 1, "implement"))

    refused = step_loop._first_request_refused(task, first)

    assert refused is not None
    assert refused.cause in HUMAN_CAUSES
    assert refused.step == "1"
    for later in (
        Spawn(step, RequestKey("1", 2, "implement")),
        Spawn(step, RequestKey("1", 1, "review", round=1)),
        Spawn(step, RequestKey("1", 1, "revise", round=1)),
        Spawn(step, RequestKey("1", 1, "implement"), reissued=True),
    ):
        assert step_loop._first_request_refused(task, later) is None
