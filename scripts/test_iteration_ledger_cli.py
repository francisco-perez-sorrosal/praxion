"""Tests for the iteration ledger's command line (``scripts/iteration_ledger.py``).

A fixture task directory is built under ``tmp_path`` with a plan, a ``WIP.md``
and a ``TEST_RESULTS.md``; ``main`` runs against it (``tmp_path`` is not a
checkout, so the reconciler sees no changed files and decides from the recorded
check alone). The two process-level facts, that ``--help`` runs and that the
file ships executable, are checked on the real file.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import iteration_ledger as ledger  # noqa: E402

SLUG = "ledger-task"
LABEL = "Step "
GREEN = "Result: pass=3 fail=0 skip=0"
RED = "Result: pass=0 fail=2 skip=0"


def step(number: int) -> str:
    return f"{LABEL}{number}"


PLAN = f"""# Plan

### {step(1)}: Write the widget

**Files**: src/widget.py
**Check**: `pytest -q` expects pass>=1 fail=0
"""
WIP = f"# WIP\n\n## Progress\n\n- [x] {step(1)}: Write the widget [COMPLETE]\n"


def results_block(number: int, *result_lines: str) -> str:
    return f"## {step(number)} — a block\n\n" + "\n".join(result_lines) + "\n"


def build_task(root: Path, *result_lines: str) -> Path:
    task_dir = root / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    (task_dir / "IMPLEMENTATION_PLAN.md").write_text(PLAN)
    (task_dir / "WIP.md").write_text(WIP)
    if result_lines:
        (task_dir / "TEST_RESULTS.md").write_text(results_block(1, *result_lines))
    return task_dir


def append_args(root: Path, overrides: dict | None = None, flags: tuple = ()) -> list[str]:
    """The `append` command line; an override of None drops that option."""
    options = {
        "--step": "1",
        "--attempt": "1",
        "--agent-id": "a3f9c2e17b",
        "--stop-reason": "completed",
        "--commit": "04569546",
        **(overrides or {}),
    }
    pairs = [part for key, value in options.items() if value is not None for part in (key, value)]
    return ["append", SLUG, "--repo-root", str(root), *pairs, *flags]


def read_args(root: Path, *extra: str) -> list[str]:
    return ["read", SLUG, "--repo-root", str(root), *extra]


def add_raw_line(task_dir: Path, text: str) -> None:
    with (task_dir / ledger.LEDGER_FILE).open("a") as handle:
        handle.write(text + "\n")


# --- append: verdict, decided_by and test_result come from the evidence ---


def test_append_derives_verdict_decided_by_and_test_result_from_the_evidence(tmp_path, capsys):
    task_dir = build_task(tmp_path, GREEN)

    assert ledger.main(append_args(tmp_path)) == 0

    (written,) = ledger.read_ledger(task_dir).records
    assert (written.verdict, written.decided_by, written.test_result) == (
        "verified-complete",
        "check",
        GREEN,
    )
    assert "verified-complete" in capsys.readouterr().out


def test_an_unmet_recorded_check_is_recorded_as_a_mismatch_whatever_the_caller_hopes(tmp_path):
    task_dir = build_task(tmp_path, RED)

    ledger.main(append_args(tmp_path))

    (written,) = ledger.read_ledger(task_dir).records
    assert (written.verdict, written.test_result) == ("mismatch", RED)


def test_a_step_with_no_recorded_result_records_a_declared_no_run(tmp_path):
    task_dir = build_task(tmp_path)

    assert ledger.main(append_args(tmp_path, {"--stop-reason": "turn-cap"})) == 0

    (written,) = ledger.read_ledger(task_dir).records
    assert written.test_result == ledger.NO_RESULT_RECORDED
    assert written.stop_reason == "turn-cap"


def test_no_commit_records_an_explicit_none_and_a_commit_records_its_sha(tmp_path):
    task_dir = build_task(tmp_path, GREEN)

    ledger.main(append_args(tmp_path, {"--commit": None}, ("--no-commit",)))
    ledger.main(append_args(tmp_path, {"--attempt": "2"}))

    assert [r.commit for r in ledger.read_ledger(task_dir).records] == [None, "04569546"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"--step": "9"},
        {"--step": "one"},
        {"--commit": "NOTHEX1"},
        {"--attempt": "0"},
        {"--agent-id": " "},
    ],
)
def test_an_append_that_cannot_be_recorded_exits_2_and_leaves_no_ledger(
    tmp_path, capsys, overrides
):
    task_dir = build_task(tmp_path, GREEN)

    assert ledger.main(append_args(tmp_path, overrides)) == 2

    assert not (task_dir / ledger.LEDGER_FILE).exists()
    assert capsys.readouterr().err.startswith("iteration_ledger: ")


def test_commit_and_no_commit_cannot_be_combined(tmp_path):
    build_task(tmp_path, GREEN)

    with pytest.raises(SystemExit) as stopped:
        ledger.main(append_args(tmp_path, flags=("--no-commit",)))

    assert stopped.value.code == 2


def test_the_state_root_can_differ_from_the_repo_root(tmp_path):
    repo, state = tmp_path / "repo", tmp_path / "state"
    repo.mkdir()
    task_dir = build_task(state, GREEN)
    args = [*append_args(repo), "--worktree-root", str(state)]

    assert ledger.main(args) == 0

    assert len(ledger.read_ledger(task_dir).records) == 1


def test_a_plugin_cache_repo_root_is_refused(tmp_path):
    cache_root = tmp_path / "plugins" / "cache" / "praxion"
    build_task(cache_root, GREEN)

    assert ledger.main(append_args(cache_root)) == 2


# --- the result line ---

FIRST = "Result: pass=1 fail=0 skip=0"
SECOND = "Result: pass=2 fail=0 skip=0"
OTHER_STEP = "Result: pass=9 fail=0 skip=0"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (results_block(1, FIRST, SECOND), SECOND),
        (results_block(1, FIRST) + "\n" + results_block(2, OTHER_STEP), FIRST),
        (results_block(1, FIRST, "Result: garbage"), FIRST),
        (results_block(1, FIRST, "Result: none — docs only"), "Result: none — docs only"),
        (results_block(1, FIRST) + "\n" + results_block(1, SECOND), SECOND),
    ],
    ids=["later-wins", "other-step-ignored", "malformed-ignored", "no-run-counts", "blocks-merge"],
)
def test_the_latest_well_formed_result_line_of_the_step_is_taken_as_written(text, expected):
    assert ledger.latest_result_line(step(1), text) == expected


def test_no_block_for_the_step_means_no_result_recorded():
    assert (
        ledger.latest_result_line(step(1), results_block(2, OTHER_STEP))
        == ledger.NO_RESULT_RECORDED
    )


# --- read ---


def test_read_exits_0_on_a_clean_ledger_and_lists_each_record(tmp_path, capsys):
    build_task(tmp_path, GREEN)
    ledger.main(append_args(tmp_path))
    capsys.readouterr()

    assert ledger.main(read_args(tmp_path)) == 0

    printed = capsys.readouterr().out
    assert step(1) in printed
    assert "verified-complete" in printed
    assert "commit=04569546" in printed


def test_read_of_an_absent_ledger_exits_0_with_no_history(tmp_path, capsys):
    build_task(tmp_path, GREEN)

    assert ledger.main(read_args(tmp_path)) == 0

    assert capsys.readouterr().out.strip() == "no iteration records"


def test_read_exits_1_when_a_line_is_a_finding_and_still_lists_the_valid_records(tmp_path, capsys):
    task_dir = build_task(tmp_path, GREEN)
    ledger.main(append_args(tmp_path))
    add_raw_line(task_dir, "{broken")
    capsys.readouterr()

    assert ledger.main(read_args(tmp_path)) == 1

    printed = capsys.readouterr().out
    assert "verified-complete" in printed
    assert "FINDING at record 2: not valid JSON" in printed


def test_read_json_is_one_object_with_records_in_the_ledger_shape_and_findings(tmp_path, capsys):
    task_dir = build_task(tmp_path, GREEN)
    ledger.main(append_args(tmp_path))
    add_raw_line(task_dir, "[1]")
    (written,) = ledger.read_ledger(task_dir).records
    capsys.readouterr()

    code = ledger.main(read_args(tmp_path, "--json"))

    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["records"] == [json.loads(ledger.render_record_line(written))]
    assert payload["findings"] == [{"position": 2, "reason": "not a JSON object"}]


def test_read_of_a_task_that_does_not_exist_exits_2(tmp_path, capsys):
    assert ledger.main(["read", "no-such-task", "--repo-root", str(tmp_path)]) == 2

    assert "no task directory" in capsys.readouterr().err


# --- the shipped file ---


def test_the_script_ships_as_an_executable_regular_file_with_a_shebang():
    path = SCRIPT_DIR / "iteration_ledger.py"

    mode = path.stat().st_mode

    assert stat.S_ISREG(mode)
    assert mode & stat.S_IXUSR
    assert os.access(path, os.X_OK)
    assert path.read_text().startswith("#!/usr/bin/env python3\n")


def test_help_exits_0_when_the_script_is_run_directly():
    done = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "iteration_ledger.py"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert done.returncode == 0
    assert "append" in done.stdout
    assert "read" in done.stdout
