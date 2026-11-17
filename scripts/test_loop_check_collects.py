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

import _step_loop_record_gate  # noqa: E402
import step_loop  # noqa: E402
from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_action import Spawn  # noqa: E402
from _step_loop_gate import collected  # noqa: E402
from _step_loop_record_gate import (  # noqa: E402
    COLLECTION_TIMEOUT_SECONDS,
    DEFAULT_GATE_WAIT_SECONDS,
    _is_plain_pytest,
    check_collects,
)
from _step_loop_render import RequestKey  # noqa: E402

ABSENT_PLUGIN = "pytest-absent-unit-plugin"
NEEDS_AN_ABSENT_PLUGIN = (
    '[project]\nname = "demo"\nversion = "0.0.0"\n\n'
    f'[tool.pytest.ini_options]\nrequired_plugins = ["{ABSENT_PLUGIN}"]\n'
)
PASSING_TEST = "def test_it():\n    assert True\n"
STEP_ONE = "Step 1"  # id-citation-discipline:ignore (plan heading format)
PYTEST = f"{shlex.quote(sys.executable)} -m pytest"
CHECK_CANNOT_COLLECT = "check-cannot-collect"
CALL_CEILING_SECONDS = 600  # what a caller's shell allows one `record` call
CALL_MARGIN_SECONDS = 60  # left over for the commit and the ledger record after both waits


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
        pytest.param("no tests ran in 0.00s\n", True, id="absent-path-on-an-older-pytest"),
        pytest.param(
            "no tests collected in 0.00s\nInstalled 3 packages in 1.50s\n",
            True,
            id="runner-line-after",
        ),
        pytest.param("ERROR: Missing required plugins: x\n", False, id="stopped-before-collecting"),
        pytest.param("Installed 3 packages in 1.50s\n", False, id="only-a-runner-line"),
        pytest.param("ERROR a.py - ImportError in 3s\n", False, id="a-node-line-is-no-summary"),
        pytest.param("", False, id="no-output"),
    ],
)
def test_a_collect_only_summary_is_read_off_any_duration_line(output, shown):
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


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("uv run --with pytest python -c pass", id="pytest-is-an-added-package"),
        pytest.param("PYTEST -qq", id="quietest-prints-no-summary"),
    ],
)
def test_a_check_whose_summary_cannot_be_read_is_not_probed(tmp_path, command):
    repo = repo_with(tmp_path, **{"pyproject.toml": NEEDS_AN_ABSENT_PLUGIN})

    assert check_collects(repo, step_checking(command.replace("PYTEST", PYTEST))) is None


@pytest.mark.parametrize(
    "command",
    [
        "pytest -q",
        "/venv/bin/pytest -q tests",
        "python3 -m pytest -q",
        "python3.13 -u -m pytest -q",
        "uv run pytest -q",
        "uv run --project scripts pytest -q",
        "uv run --with extra --directory scripts python -m pytest -q",
        "uv run -q python3 -m pytest -q",
        "TERM=dumb uv run pytest -q",
    ],
)
def test_the_command_itself_being_pytest_counts_alone_or_after_a_runner(command):
    assert _is_plain_pytest(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "python3 scripts/check_x.py --runner pytest",
        "python3 scripts/check_x.py -m pytest",
        "python3 -c 'import sys' pytest",
        "uv run python scripts/check_x.py --runner pytest",
        "uv run --with pytest python -c pass",
        "echo pytest",
        "make pytest",
        "uv pytest",
        "uv run",
        "",
    ],
)
def test_a_command_that_only_mentions_pytest_is_not_pytest(command):
    assert _is_plain_pytest(command) is False


def test_a_check_that_only_names_pytest_as_an_argument_is_never_run_by_the_probe(tmp_path):
    script = tmp_path / "check_x.py"
    script.write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
    command = f"{shlex.quote(sys.executable)} {script} --runner pytest"

    assert check_collects(tmp_path, step_checking(command)) is None


def test_the_probe_bound_and_the_gate_wait_leave_a_margin_under_the_calls_ceiling():
    waits = DEFAULT_GATE_WAIT_SECONDS + COLLECTION_TIMEOUT_SECONDS

    assert waits <= CALL_CEILING_SECONDS - CALL_MARGIN_SECONDS


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


def test_a_collection_that_could_not_start_is_never_a_refusal(tmp_path):
    command = f"{tmp_path / 'absent' / 'pytest'} -q"

    assert check_collects(tmp_path, step_checking(command)) is None


def test_a_collection_that_outlives_its_bound_is_never_a_refusal(tmp_path, monkeypatch):
    monkeypatch.setattr(_step_loop_record_gate, "COLLECTION_TIMEOUT_SECONDS", 0.3)
    script = stand_in_pytest(tmp_path, "sleep 5; exit 3")

    assert check_collects(tmp_path, step_checking(f"{script} -q")) is None


@pytest.fixture
def refusing_task(tmp_path):
    repo = repo_with(tmp_path, **{"pyproject.toml": NEEDS_AN_ABSENT_PLUGIN})
    return SimpleNamespace(repo=repo), step_checking(f"{PYTEST} -q")


def test_the_series_first_implement_request_is_refused_before_it_goes_out(refusing_task):
    task, step = refusing_task

    refused = step_loop._first_request_refused(task, Spawn(step, RequestKey("1", 1, "implement")))

    assert refused is not None
    assert refused.cause == CHECK_CANNOT_COLLECT
    assert refused.step == "1"


@pytest.mark.parametrize(
    ("key", "reissued"),
    [
        pytest.param(RequestKey("1", 2, "implement"), False, id="a-later-attempt"),
        pytest.param(RequestKey("1", 1, "review", round=1), False, id="a-review"),
        pytest.param(RequestKey("1", 1, "revise", round=1), False, id="a-revision"),
        pytest.param(RequestKey("1", 1, "implement"), True, id="a-reissued-request"),
    ],
)
def test_a_request_that_is_not_the_series_first_is_not_asked_to_collect(
    refusing_task, key, reissued
):
    task, step = refusing_task

    assert step_loop._first_request_refused(task, Spawn(step, key, reissued=reissued)) is None
