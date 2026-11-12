"""Tests for `tests/support/pty_scripted_run.py`, the pty harness the shell
suites drive interactive prompts through.

The behaviour is pinned through the command line (what the shell tests rely on);
the answer-selection seam is pinned directly because it decides what a prompt
receives.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parent / "support" / "pty_scripted_run.py"
SPEC = importlib.util.spec_from_file_location("pty_scripted_run", RUNNER)
assert SPEC is not None
assert SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)

TIMEOUT_EXIT = 124


def run_runner(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), *args], capture_output=True, text=True, timeout=30
    )


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["--answers", "3", "--", "cmd"], ["", "", ""]),
        (["--answer", "", "--answer", "2", "--", "cmd"], ["", "2"]),
        (["--answers", "3", "--answer", "x", "--", "cmd"], ["x"]),
    ],
)
def test_explicit_answers_take_over_the_blank_default_count(argv, expected) -> None:
    assert runner.scripted_answers(runner.parse_args(argv)) == expected


def test_the_separator_before_the_command_is_not_part_of_the_command() -> None:
    assert runner.command_from(runner.parse_args(["--", "echo", "hi"])) == ["echo", "hi"]


def test_a_scripted_answer_reaches_a_prompt_on_a_real_tty() -> None:
    result = run_runner(
        "--timeout", "10", "--answer", "hi", "--", "sh", "-c", "[ -t 0 ] && read x && echo got:$x"
    )

    assert (result.returncode, "got:hi" in result.stdout) == (0, True)


def test_the_childs_exit_code_is_the_runners_exit_code() -> None:
    assert run_runner("--timeout", "10", "--", "sh", "-c", "exit 3").returncode == 3


def test_a_child_that_outlives_the_timeout_is_killed_and_reported_as_124() -> None:
    result = run_runner("--timeout", "1", "--", "sleep", "30")

    assert (result.returncode, "TIMEOUT" in result.stderr) == (TIMEOUT_EXIT, True)


def test_a_missing_command_is_refused_with_exit_2() -> None:
    assert run_runner("--timeout", "1", "--").returncode == 2
