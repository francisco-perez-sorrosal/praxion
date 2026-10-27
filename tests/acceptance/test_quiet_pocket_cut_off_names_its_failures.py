"""A gate run cut off in a quiet pocket still names its failing tests for the next attempt.

A pocket is quiet when its own runner configuration lowers pytest's verbosity (`-q` or
`-qq` in `addopts`). A cut-off run there names, in the next attempt's `Failed:` evidence,
each test that had failed before the cut, pocket first, exactly as the same run in a pocket
that is not quiet does. The pocket's committed configuration is left as it is, a finished
quiet run keeps today's counts and failures, and a cut-off quiet run with no failure before
the cut reads as cut off with no `Failed:` line, never as green.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from tests.acceptance.drivers import pocket_gate
from tests.acceptance.drivers.pocket_gate import gate_block, pocket_config, prompt_of
from tests.acceptance.drivers.step_loop import (
    LoopTask,
    Step,
    Work,
    build_loop,
    git,
    next_action,
    record,
    work_on,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
POCKET = "eval"
POCKET_CONFIG = f"{POCKET}/pyproject.toml"
SLOW_TESTS = f"{POCKET}/tests/test_slow_pocket.py"
BOUND_SECONDS = 5
HANGS = "def test_hangs_past_the_bound():\n    import time\n    time.sleep(600)\n"
FAILS_TWICE = (
    "def test_first_slow_failure():\n    assert 1 == 2\n\n\n"
    "def test_second_slow_failure():\n    assert 'a' == 'b'\n"
)
QUIET_OPTIONS = ["-q", "-qq"]


def _config(addopts: str | None) -> str:
    text = pocket_config("evals")
    return text if addopts is None else text + f'addopts = "{addopts}"\n'


def _gate(workspace: Path, addopts: str | None, tests_text: str) -> tuple[LoopTask, str]:
    """One gate over a step that changed the pocket's tests; returns the task and request id."""
    task = build_loop(
        workspace, Step("1", more_files=(SLOW_TESTS,)), base_files={POCKET_CONFIG: _config(addopts)}
    )
    pocket_gate.bound_pocket_run(task, POCKET, BOUND_SECONDS)
    asked = next_action(task)
    assert asked.request is not None, asked.doc
    agent_id = work_on(task, asked.request, Work(other_edits=((SLOW_TESTS, tests_text),)))
    record(task, asked.request["id"], agent_id=agent_id, marker="complete")
    return task, asked.request["id"]


def _pocket_failed_lines(text: str) -> list[str]:
    return sorted(
        line for line in text.splitlines() if line.startswith("Failed:") and POCKET in line
    )


def _evidence_lines(block: str) -> list[str]:
    """The block's lines that carry what the run showed: scope, failures, results."""
    return [
        line for line in block.splitlines() if line.startswith(("Scope:", "Failed:", "Result:"))
    ]


@pytest.mark.parametrize("quiet", QUIET_OPTIONS)
def test_a_cut_off_quiet_run_names_its_failures_as_a_plain_pocket_run_does(
    tmp_path: Path, quiet: str
) -> None:
    plain, _ = _gate(tmp_path / "plain", None, FAILS_TWICE + "\n\n" + HANGS)
    expected = _pocket_failed_lines(prompt_of(next_action(plain)))
    assert len(expected) == 2, f"the plain pocket's run named {expected}"

    quiet_task, _ = _gate(tmp_path / "quiet", quiet, FAILS_TWICE + "\n\n" + HANGS)

    assert _pocket_failed_lines(prompt_of(next_action(quiet_task))) == expected


@pytest.mark.parametrize("quiet", QUIET_OPTIONS)
def test_the_quiet_pockets_committed_configuration_is_left_as_it_is(
    tmp_path: Path, quiet: str
) -> None:
    task, _ = _gate(tmp_path, quiet, FAILS_TWICE + "\n\n" + HANGS)

    assert (task.root / POCKET_CONFIG).read_text(encoding="utf-8") == _config(quiet)
    assert git(task, "status", "--porcelain", "--", POCKET_CONFIG) == ""


def test_the_chronograph_pocket_stays_quiet_for_a_developers_own_runs() -> None:
    config = tomllib.loads((REPO_ROOT / "task-chronograph-mcp" / "pyproject.toml").read_text())

    addopts = config["tool"]["pytest"]["ini_options"]["addopts"]

    options = addopts.split() if isinstance(addopts, str) else list(addopts)
    assert "-q" in options or "-qq" in options, addopts


@pytest.mark.parametrize("quiet", QUIET_OPTIONS)
def test_a_finished_quiet_run_keeps_the_counts_and_failures_a_plain_run_shows(
    tmp_path: Path, quiet: str
) -> None:
    plain, plain_request = _gate(tmp_path / "plain", None, FAILS_TWICE)
    expected = _evidence_lines(gate_block(plain, plain_request))

    task, request_id = _gate(tmp_path / "quiet", quiet, FAILS_TWICE)

    assert _evidence_lines(gate_block(task, request_id)) == expected


@pytest.mark.parametrize("quiet", QUIET_OPTIONS)
def test_a_cut_off_quiet_run_with_no_failure_reads_cut_off_with_no_failed_line(
    tmp_path: Path, quiet: str
) -> None:
    task, request_id = _gate(tmp_path, quiet, HANGS)

    block = gate_block(task, request_id)
    assert "cut off" in block.lower(), block
    assert [line for line in block.splitlines() if line.startswith("Failed:")] == [], block
    assert _pocket_failed_lines(prompt_of(next_action(task))) == []
