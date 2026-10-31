"""Tests for the bound a step's `Check:` run is held to and its detached run in the gate.

The pocket a `Check:` command names (`uv run --project <dir>`) decides its bound, read the way a
gate run's is; the gate runs the check detached, so a `record` call that gives up while the check
is inside its bound leaves it for the next call to pick up, and a check past its bound is red
naming it. The detached runs are real processes under short bounds.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_record_gate as gating  # noqa: E402
from _step_loop_io import (  # noqa: E402
    CommandRun,
    check_bound,
    check_pocket,
    run_bounded_check,
    run_check,
)
from _step_loop_pocket_runs import (  # noqa: E402
    DEFAULT_BOUND_SECONDS,
    POCKET_TIMEOUTS_VARIABLE,
    PocketBound,
    StillRunning,
)

GUARD_SECONDS = 30.0
PYTHON = sys.executable
PRINTS_OK = f"{PYTHON} -c \"print('ok')\""
SLEEPS = f'{PYTHON} -c "import time; time.sleep(60)"'
ROOT_DECLARES_1500 = "[tool.praxion.step-loop]\ngate-timeout-seconds = 1500\n"
ONE_SECOND_AT_ROOT = {POCKET_TIMEOUTS_VARIABLE: ".=1"}


def declare(directory: Path, text: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "pyproject.toml").write_text(text, encoding="utf-8")


# --- Which pocket a check runs in ---


@pytest.mark.parametrize(
    ("command", "pocket"),
    [
        (("uv", "run", "python", "-m", "pytest", "-q"), "."),
        (("uv", "run", "--project", "eval", "pytest", "-q"), "eval"),
        (("uv", "run", "--project=eval", "pytest", "-q"), "eval"),
        (("uv", "run", "--directory", "dashboard_app", "npm", "test"), "dashboard_app"),
    ],
)
def test_a_check_runs_in_the_pocket_its_project_option_names_else_the_root(command, pocket):
    assert check_pocket(command) == pocket


def test_a_project_option_with_no_value_leaves_the_check_in_the_root_pocket():
    assert check_pocket(("uv", "run", "--project")) == "."


# --- The bound a check is held to ---


def test_a_root_check_is_held_to_the_root_pockets_declared_gate_bound(tmp_path):
    declare(tmp_path, ROOT_DECLARES_1500)

    bound = check_bound(tmp_path, ("uv", "run", "pytest"), {})

    assert bound == PocketBound(".", 1500.0, "declared")


def test_a_check_naming_a_pocket_is_held_to_that_pockets_bound_not_the_roots(tmp_path):
    declare(tmp_path, ROOT_DECLARES_1500)
    declare(tmp_path / "eval", "[tool.praxion.step-loop]\ngate-timeout-seconds = 1200\n")

    bound = check_bound(tmp_path, ("uv", "run", "--project", "eval", "pytest"), {})

    assert bound == PocketBound("eval", 1200.0, "declared")


def test_the_environment_override_beats_the_pockets_declaration_for_a_check(tmp_path):
    declare(tmp_path, ROOT_DECLARES_1500)

    bound = check_bound(tmp_path, ("pytest",), {POCKET_TIMEOUTS_VARIABLE: ".=90"})

    assert bound == PocketBound(".", 90.0, "override")


def test_a_check_in_a_pocket_that_declares_nothing_gets_the_default_bound(tmp_path):
    assert check_bound(tmp_path, ("pytest",), {}).seconds == DEFAULT_BOUND_SECONDS


def test_a_foreground_check_with_no_timeout_given_is_held_to_its_pockets_bound(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(POCKET_TIMEOUTS_VARIABLE, ".=1")

    run = run_check(tmp_path, SLEEPS)

    assert (run.returncode, run.problem) == (None, "timed out after 1s")


# --- The gate's detached check run ---


def test_a_check_that_finishes_inside_its_bound_comes_back_with_its_output(tmp_path):
    run = run_bounded_check(tmp_path, PRINTS_OK, tmp_path / "gate", {}, time.time() + GUARD_SECONDS)

    assert isinstance(run, CommandRun)
    assert (run.returncode, run.problem, run.output.splitlines()[-1]) == (0, None, "ok")


def test_a_check_still_inside_its_bound_when_the_call_gives_up_is_still_running(tmp_path):
    run_dir = tmp_path / "gate"

    first = run_bounded_check(tmp_path, SLEEPS, run_dir, ONE_SECOND_AT_ROOT, time.time())
    run_bounded_check(tmp_path, SLEEPS, run_dir, ONE_SECOND_AT_ROOT, time.time() + GUARD_SECONDS)

    assert isinstance(first, StillRunning)


def test_a_check_past_its_pockets_bound_is_a_run_that_outlived_it_naming_the_bound(tmp_path):
    run = run_bounded_check(
        tmp_path, SLEEPS, tmp_path / "gate", ONE_SECOND_AT_ROOT, time.time() + GUARD_SECONDS
    )

    assert isinstance(run, CommandRun)
    assert (run.returncode, run.problem) == (None, "outlived its pocket's bound (., 1s)")


def test_a_check_asked_again_with_the_same_directory_is_picked_up_not_started_again(tmp_path):
    run_dir = tmp_path / "gate"
    run_bounded_check(tmp_path, PRINTS_OK, run_dir, {}, time.time() + GUARD_SECONDS)

    again = run_bounded_check(tmp_path, PRINTS_OK, run_dir, {}, time.time() + GUARD_SECONDS)

    assert isinstance(again, CommandRun)
    assert (again.returncode, again.output.count("ok\n")) == (0, 1)
    assert len(list(run_dir.glob("*.start"))) == 1


def test_the_gate_leaves_a_check_still_inside_its_bound_for_the_next_call(tmp_path, monkeypatch):
    still = StillRunning(".", 600.0, PocketBound(".", 1500.0, "declared"))
    monkeypatch.setattr(gating, "run_bounded_check", lambda *_: still)

    with pytest.raises(gating.GateStillRunningError) as raised:
        gating.bounded_check(tmp_path, tmp_path / "gate", PRINTS_OK, time.time())

    assert raised.value.pockets == (". (the Check: run)",)
