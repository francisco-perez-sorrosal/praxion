"""Tests for the loop's checkpoint run (``scripts/_step_loop_checkpoint_run.py``) and the `next`
call that makes it (``scripts/step_loop.py``).

Every case runs over a throwaway repository with one pytest pocket at its root holding one test
file: the test scope's answer, the detached runs, their bounds and the results file are the real
ones. The pocket's test appends a line to a log outside the repository each time it runs, so a
case counts the whole-suite runs a call started.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import step_loop  # noqa: E402
from _step_loop_checkpoint import WaitingPocket, deferred_line, waiting_pockets  # noqa: E402
from _step_loop_checkpoint_run import (  # noqa: E402
    CheckpointGreen,
    CheckpointRed,
    CheckpointRunning,
    run_checkpoint,
    run_directory,
)
from _step_loop_files import gate_heading  # noqa: E402
from _step_loop_pocket_runs import POCKET_TIMEOUTS_VARIABLE  # noqa: E402
from iteration_ledger import IterationRecord, append_record  # noqa: E402

SLUG = "demo"
STEP = "Step "
ROOT = "."
TEST_FILE = "tests/test_suite.py"
NODE = f"{TEST_FILE}::test_the_suite"
CALL_WAIT_SECONDS = 60.0  # well past a one-file suite's run: only a held one is still running
RELEASE_WAIT_SECONDS = 60.0
NO_WAIT = 0.0
SHORT_BOUND = {POCKET_TIMEOUTS_VARIABLE: f"{ROOT}=2"}
GREEN_LINE = "Result: pass=1 fail=0 skip=0 pending=0 by=step-loop"


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


def suite_text(runs_log: Path, *, passes: bool = True, hold: Path | None = None) -> str:
    """A test that logs its run, waits while `hold` exists, then passes or fails."""
    wait = f"    while Path({str(hold)!r}).exists():\n        time.sleep(0.05)\n" if hold else ""
    return (
        "import time\nfrom pathlib import Path\n\n\ndef test_the_suite():\n"
        f"    with Path({str(runs_log)!r}).open('a') as log:\n        log.write('ran\\n')\n"
        f"{wait}    assert {passes}\n"
    )


@pytest.fixture
def runs_log(tmp_path: Path) -> Path:
    return tmp_path / "runs.log"


@pytest.fixture
def hold(tmp_path: Path) -> Iterator[Path]:
    """A file the suite waits on while it exists; removed at teardown, so a failing assertion
    never leaves a held run alive until its bound."""
    path = tmp_path / "hold"
    path.touch()
    yield path
    path.unlink(missing_ok=True)


def build_repo(tmp_path: Path, runs_log: Path, **suite) -> Path:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0"\n', "utf-8")
    (repo / TEST_FILE).write_text(suite_text(runs_log, **suite), "utf-8")
    (repo / ".gitignore").write_text(".ai-work/\n", "utf-8")
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    (repo / ".ai-work" / SLUG).mkdir(parents=True)
    return repo


def whole_suite_runs(runs_log: Path) -> int:
    return len(runs_log.read_text("utf-8").splitlines()) if runs_log.exists() else 0


def task_dir(repo: Path) -> Path:
    return repo / ".ai-work" / SLUG


def committed(step_id: str, commit: str = "c0ffee0") -> IterationRecord:
    return IterationRecord(
        step=f"Step {step_id}",
        attempt=1,
        agent_id="a1",
        verdict="verified-complete",
        decided_by="check",
        test_result=GREEN_LINE,
        commit=commit,
        stop_reason="completed",
        request=f"s{step_id}-a1-implement",
    )


def deferring_blocks(*step_ids: str) -> str:
    """The gate blocks of committed steps that each left the root pocket for the checkpoint."""
    return "".join(
        f"{gate_heading(step_id, f's{step_id}-a1-implement')}\n\n"
        f"{deferred_line(ROOT)}\n{GREEN_LINE}\n\n"
        for step_id in step_ids
    )


def wait_for(steps: tuple[str, ...]) -> tuple[WaitingPocket, ...]:
    return (WaitingPocket(ROOT, steps),)


def checkpoint(repo: Path, steps=("41",), *, wait=CALL_WAIT_SECONDS, environ=None):
    records = tuple(committed(step_id) for step_id in steps)
    return run_checkpoint(
        repo, task_dir(repo), wait_for(steps), records, time.time() + wait, environ or {}
    )


def results(repo: Path) -> str:
    path = task_dir(repo) / "TEST_RESULTS.md"
    return path.read_text("utf-8") if path.is_file() else ""


def checkpoint_blocks(text: str) -> list[str]:
    return ["## Checkpoint " + part for part in text.split("## Checkpoint ")[1:]]


# --- A green run --------------------------------------------------------------------------------


def test_a_green_run_writes_its_block_and_the_pocket_stops_waiting(tmp_path, runs_log):
    repo = build_repo(tmp_path, runs_log)
    (task_dir(repo) / "TEST_RESULTS.md").write_text(deferring_blocks("41"), "utf-8")

    outcome = checkpoint(repo)

    assert outcome == CheckpointGreen()
    assert waiting_pockets(results(repo), (committed("41"),)) == ()


def test_the_block_names_the_pocket_the_counts_and_the_covered_steps(tmp_path, runs_log):
    repo = build_repo(tmp_path, runs_log)
    head = git(repo, "rev-parse", "--short=7", "HEAD")

    checkpoint(repo, ("41", "42"))

    (block,) = checkpoint_blocks(results(repo))
    lines = [line for line in block.splitlines() if line.strip()]
    assert lines[0] == f"## Checkpoint {ROOT} at {head}"
    assert f"Covers: {STEP}41, {STEP}42" in lines
    assert any(line.startswith(f"Scope: {ROOT} ") and "widened" in line for line in lines), block
    assert lines[-1] == GREEN_LINE


def test_two_waiting_steps_give_one_run(tmp_path, runs_log):
    repo = build_repo(tmp_path, runs_log)

    checkpoint(repo, ("41", "42"))

    assert whole_suite_runs(runs_log) == 1


# --- A red run ----------------------------------------------------------------------------------


def test_a_red_run_keeps_the_pocket_waiting_and_names_the_failing_test(tmp_path, runs_log):
    repo = build_repo(tmp_path, runs_log, passes=False)
    (task_dir(repo) / "TEST_RESULTS.md").write_text(deferring_blocks("41", "42"), "utf-8")

    outcome = checkpoint(repo, ("41", "42"))

    assert isinstance(outcome, CheckpointRed), outcome
    assert NODE in outcome.evidence
    assert f"{STEP}41, {STEP}42" in outcome.evidence
    assert f"Failed: {NODE}" in checkpoint_blocks(results(repo))[0]
    records = (committed("41"), committed("42"))
    assert waiting_pockets(results(repo), records) == wait_for(("41", "42"))


def test_a_run_past_its_bound_is_red_and_says_it_was_cut_off(tmp_path, runs_log, hold):
    repo = build_repo(tmp_path, runs_log, hold=hold)

    outcome = checkpoint(repo, environ=SHORT_BOUND)

    assert isinstance(outcome, CheckpointRed), outcome
    assert "cut off" in outcome.evidence.lower()
    assert checkpoint_blocks(results(repo))[0].count("Cut off: ") == 1


def test_a_finished_run_asked_again_adds_no_block_and_starts_no_run(tmp_path, runs_log):
    repo = build_repo(tmp_path, runs_log, passes=False)
    first = checkpoint(repo)

    again = checkpoint(repo)

    assert again == first
    assert len(checkpoint_blocks(results(repo))) == 1
    assert whole_suite_runs(runs_log) == 1


# --- A run longer than one call -----------------------------------------------------------------


def test_a_run_inside_its_bound_is_still_running_and_the_next_call_attaches_to_it(
    tmp_path, runs_log, hold
):
    repo = build_repo(tmp_path, runs_log, hold=hold)

    held = checkpoint(repo, wait=NO_WAIT)
    hold.unlink()
    finished = checkpoint(repo, wait=RELEASE_WAIT_SECONDS)

    assert isinstance(held, CheckpointRunning), held
    assert ROOT in held.description
    assert finished == CheckpointGreen()
    assert whole_suite_runs(runs_log) == 1
    assert len(checkpoint_blocks(results(repo))) == 1


def test_a_still_running_call_writes_no_block(tmp_path, runs_log, hold):
    repo = build_repo(tmp_path, runs_log, hold=hold)

    checkpoint(repo, wait=NO_WAIT)

    assert checkpoint_blocks(results(repo)) == []


# --- Where a run lives ----------------------------------------------------------------------------


def test_the_run_directory_changes_with_head_and_with_the_waiting_steps(tmp_path):
    pocket, records = WaitingPocket(ROOT, ("41",)), (committed("41"), committed("42"))
    two = WaitingPocket(ROOT, ("41", "42"))

    here = run_directory(tmp_path, pocket, "aaaaaaa", records)

    assert here == run_directory(tmp_path, pocket, "aaaaaaa", records)
    assert here != run_directory(tmp_path, pocket, "bbbbbbb", records)
    assert here != run_directory(tmp_path, two, "aaaaaaa", records)
    assert here.parent == tmp_path / "gate"
    assert here.name.startswith("checkpoint-")


def test_a_remedy_commit_starts_a_fresh_run(tmp_path, runs_log):
    repo = build_repo(tmp_path, runs_log, passes=False)
    checkpoint(repo)
    (repo / TEST_FILE).write_text(suite_text(runs_log), "utf-8")
    git(repo, "commit", "-q", "-am", "remedy")

    outcome = checkpoint(repo)

    assert outcome == CheckpointGreen()
    assert whole_suite_runs(runs_log) == 2
    assert len(checkpoint_blocks(results(repo))) == 2


def test_the_run_module_imports_the_gate_and_the_gate_does_not_import_it():
    def imported(name: str) -> set[str]:
        tree = ast.parse((SCRIPT_DIR / f"{name}.py").read_text("utf-8"))
        return {
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        } | {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }

    assert "_step_loop_record_gate" in imported("_step_loop_checkpoint_run")
    assert "_step_loop_checkpoint_run" not in imported("_step_loop_record_gate")
    assert "_step_loop_checkpoint_run" not in imported("_step_loop_checkpoint")


# --- `next` with every step done and a pocket waiting --------------------------------------------

DONE_PLAN = (
    f"# Plan\n\n## Steps\n\n### {STEP}41: Do it\n\n**Assignee**: orchestrator\n**Files**: none\n"
)
DONE_WIP = f"# WIP\n\n## Progress\n\n- [x] {STEP}41: Do it\n"


def waiting_task(repo: Path) -> None:
    """Every step done, and step 41's committed gate block left the root pocket waiting."""
    directory = task_dir(repo)
    (directory / "IMPLEMENTATION_PLAN.md").write_text(DONE_PLAN, "utf-8")
    (directory / "WIP.md").write_text(DONE_WIP, "utf-8")
    (directory / "TEST_RESULTS.md").write_text(deferring_blocks("41"), "utf-8")
    append_record(directory, committed("41", git(repo, "rev-parse", "HEAD")))


def call_next(repo: Path) -> step_loop.Reply:
    return step_loop.execute(["next", SLUG, "--repo-root", str(repo), "--base-ref", "HEAD"])


def test_next_runs_the_waiting_pocket_and_prints_complete_once_it_is_green(tmp_path, runs_log):
    repo = build_repo(tmp_path, runs_log)
    waiting_task(repo)

    reply = call_next(repo)

    assert reply.doc["outcome"] == "complete", reply.doc
    assert whole_suite_runs(runs_log) == 1
    assert call_next(repo).doc["outcome"] == "complete"
    assert whole_suite_runs(runs_log) == 1


def test_next_over_a_red_pocket_stops_naming_it_its_test_and_its_steps(tmp_path, runs_log):
    repo = build_repo(tmp_path, runs_log, passes=False)
    waiting_task(repo)
    head = git(repo, "rev-parse", "HEAD")

    reply = call_next(repo)

    assert (reply.exit, reply.doc["outcome"]) == (2, "needs-human"), reply.doc
    stop = reply.doc["stop"]
    assert (stop["cause"], stop["step"]) == ("checkpoint-red", None)
    assert NODE in stop["evidence"]
    assert f"{STEP}41" in stop["evidence"]
    assert (task_dir(repo) / "HANDOFF.md").is_file()
    assert git(repo, "rev-parse", "HEAD") == head
    assert (task_dir(repo) / "WIP.md").read_text("utf-8") == DONE_WIP


def test_next_over_a_run_still_inside_its_bound_answers_gate_running(
    tmp_path, runs_log, monkeypatch, hold
):
    repo = build_repo(tmp_path, runs_log, hold=hold)
    waiting_task(repo)
    monkeypatch.setenv("PRAXION_STEP_LOOP_GATE_WAIT_SECONDS", "0")

    held = call_next(repo)
    hold.unlink()
    monkeypatch.setenv("PRAXION_STEP_LOOP_GATE_WAIT_SECONDS", str(RELEASE_WAIT_SECONDS))
    finished = call_next(repo)

    assert (held.exit, held.doc["error"]["code"]) == (4, "gate-running"), held.doc
    assert "run the same call again" in held.doc["error"]["message"]
    assert finished.doc["outcome"] == "complete", finished.doc
    assert whole_suite_runs(runs_log) == 1
