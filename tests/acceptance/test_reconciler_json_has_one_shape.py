"""The reconciler's machine output is the verdict array, whatever WIP.md holds.

An `Attempts:` line that names no step is still a human matter -- the reconciler
reports it and exits 2 -- but the report goes to stderr in both output modes, so every
consumer that parses stdout as an array of verdicts keeps working.
"""

from __future__ import annotations

import json

from tests.acceptance.drivers.reconciler_output import (
    run_reconciler,
    task_with_unnamed_attempts_line,
    task_without_unnamed_attempts_line,
)

NEEDS_A_HUMAN = 2


def test_json_output_is_the_verdict_array_even_with_an_unnamed_attempts_line(tmp_path):
    task = task_with_unnamed_attempts_line(tmp_path)

    run = run_reconciler(task, machine=True)

    verdicts = json.loads(run.stdout)
    assert isinstance(verdicts, list), f"stdout is not the verdict array: {run.stdout}"
    assert [v["step"] for v in verdicts] == ["Step " + "1"]


def test_an_unnamed_attempts_line_is_reported_on_stderr_and_exits_two_in_json_mode(tmp_path):
    task = task_with_unnamed_attempts_line(tmp_path)

    run = run_reconciler(task, machine=True)

    assert run.exit_code == NEEDS_A_HUMAN
    assert "Attempts" in run.stderr, run.stderr


def test_an_unnamed_attempts_line_is_reported_on_stderr_and_exits_two_in_human_mode(tmp_path):
    task = task_with_unnamed_attempts_line(tmp_path)

    run = run_reconciler(task, machine=False)

    assert run.exit_code == NEEDS_A_HUMAN
    assert "Attempts" in run.stderr, run.stderr


def test_json_output_is_the_verdict_array_when_every_attempts_line_names_its_step(tmp_path):
    task = task_without_unnamed_attempts_line(tmp_path)

    run = run_reconciler(task, machine=True)

    assert isinstance(json.loads(run.stdout), list), run.stdout
