"""The `Command:` line of a gate block is capped, and the whole command is kept in a file.

A step's `Check:` command can run to hundreds of characters; copied whole into a block it pushes a
green section past its shape ceiling. The block names a file that holds the whole command instead.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_record_gate as gating  # noqa: E402
from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_io import CommandRun  # noqa: E402
from _step_loop_state import LoopInputs  # noqa: E402

SLUG = "widget"
REQUEST = "s1-a1-implement"
HEAD = "0123456789abcdef0123456789abcdef01234567"
LINE_CEILING = 200
POINTER = f".ai-work/{SLUG}/gate/{REQUEST}/command.txt"
SUFFIX = f" ... (whole command: {POINTER})`"
PASSED_OUTPUT = "== 3 passed in 0.10s =="
STEP_HEAD = "# Plan\n\n## Steps\n\n### Step 1: Widget\n\n**Assignee**: implementer\n"  # id-citation-discipline:ignore
LONG_TEST_PATHS = " ".join(f"tests/test_widget_behaviour_{n:03d}.py" for n in range(20))


def check_line(command: str) -> str:
    return f"**Check**: `{command}` expects pass>=1 fail=0\n"


def gate_over(monkeypatch, tmp_path: Path, command: str, slug: str = SLUG) -> gating.Gate:
    passed = CommandRun(tuple(command.split()), ".", PASSED_OUTPUT, 0)
    monkeypatch.setattr(gating, "head_sha", lambda _repo: HEAD)
    monkeypatch.setattr(gating, "paths_differing_from_head", lambda *_: ())
    monkeypatch.setattr(gating, "run_bounded_check", lambda *_: passed)
    inputs = LoopInputs(tuple(parse_plan_steps(STEP_HEAD + check_line(command))), {}, (), {})
    task = SimpleNamespace(
        slug=slug, repo=tmp_path, work=tmp_path, dir=tmp_path, base_ref="HEAD", inputs=inputs
    )
    return gating.run_gate(cast(gating.TaskView, task), inputs.steps[0], REQUEST)


def command_lines(gate: gating.Gate) -> list[str]:
    return [line for line in gate.body if line.startswith("Command:")]


def test_a_command_over_the_ceiling_is_cut_and_points_at_the_file(monkeypatch, tmp_path):
    command = f"python3 -m pytest {LONG_TEST_PATHS} -q"

    gate = gate_over(monkeypatch, tmp_path, command)

    (line,) = command_lines(gate)
    assert (len(line), line.endswith(SUFFIX), line.startswith("Command: `python3 -m pytest")) == (
        LINE_CEILING,
        True,
        True,
    )


def test_the_file_beside_the_run_logs_holds_the_whole_command_and_ends_its_line(
    monkeypatch, tmp_path
):
    command = f"python3 -m pytest {LONG_TEST_PATHS} -q"

    gate_over(monkeypatch, tmp_path, command)

    kept = tmp_path / gating.GATE_DIRECTORY / REQUEST / gating.COMMAND_FILE
    assert kept.read_text(encoding="utf-8") == command + "\n"


def test_a_command_that_fits_is_written_whole_and_leaves_no_file(monkeypatch, tmp_path):
    gate = gate_over(monkeypatch, tmp_path, "python3 -m pytest -q")

    assert command_lines(gate) == ["Command: `python3 -m pytest -q`"]
    assert not (tmp_path / gating.GATE_DIRECTORY / REQUEST / gating.COMMAND_FILE).exists()


def test_the_same_command_always_renders_the_same_line(monkeypatch, tmp_path):
    command = f"python3 -m pytest {LONG_TEST_PATHS} -q"

    first = command_lines(gate_over(monkeypatch, tmp_path / "one", command))
    second = command_lines(gate_over(monkeypatch, tmp_path / "two", command))

    assert first == second


@pytest.mark.parametrize(("over", "is_cut"), [(0, False), (1, True)])
def test_a_line_exactly_at_the_ceiling_is_not_cut_and_one_over_is(
    monkeypatch, tmp_path, over, is_cut
):
    command = "x" * (LINE_CEILING - len("Command: ``") + over)

    (line,) = command_lines(gate_over(monkeypatch, tmp_path, command))

    assert (len(line), line.endswith(SUFFIX), command in line) == (
        LINE_CEILING,
        is_cut,
        not is_cut,
    )


def test_a_pointer_too_long_for_the_line_keeps_its_tail_and_the_ceiling(monkeypatch, tmp_path):
    command = f"python3 -m pytest {LONG_TEST_PATHS} -q"

    (line,) = command_lines(gate_over(monkeypatch, tmp_path, command, slug="w" * 300))

    assert (
        len(line),
        line.endswith(f"/gate/{REQUEST}/command.txt)`"),
        "(whole command: …" in line,
    ) == (
        LINE_CEILING,
        True,
        True,
    )


def test_a_block_written_with_the_old_full_line_reads_back_as_before(tmp_path):
    results = tmp_path / gating.RESULTS_FILE
    whole = f"python3 -m pytest {LONG_TEST_PATHS} -q"
    heading = gating.gate_heading("1", REQUEST)
    results.write_text(
        f"{heading}\n\nCommand: `{whole}`\nResult: pass=3 fail=0 skip=0 pending=0 by=step-loop\n",
        encoding="utf-8",
    )

    gate = gating.recorded_gate(results, heading)

    assert gate is not None
    assert (gate.red, gate.body[0]) == (False, f"Command: `{whole}`")
