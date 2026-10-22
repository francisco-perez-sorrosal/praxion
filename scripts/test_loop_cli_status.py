"""Tests for the position the step-loop command's `status --json` reports: the step the next
action concerns and the `record` call that follows a pending request
(``scripts/step_loop.py``, ``scripts/_step_loop_cli.py``).

Every case runs the real command over a small checkout built in ``tmp_path``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import step_loop  # noqa: E402

STEP = "Step "
SLUG = "demo"
SCRIPT = SCRIPT_DIR / "step_loop.py"
SELF_HOST = "python3 scripts/step_loop.py"
CHECK = "**Check**: `python3 -m pytest -q` expects pass>=1 fail=0"
HEADER = "# Plan\n\n## Steps\n\n"


def implement_block(number, *, heading=""):
    return (
        f"### {STEP}{number}: Do it{heading}\n\n**Assignee**: implementer\n"
        f"**Files**: `src/s{number}.py`\n{CHECK}\n\n"
    )


TWO_STEPS = HEADER + implement_block(1) + implement_block(2, heading=" [depends-on: 1]")
STUCK = HEADER + implement_block(1, heading=" [depends-on: 9]")
ORCHESTRATOR_ONLY = HEADER + f"### {STEP}1: Do it\n\n**Assignee**: orchestrator\n\n"
OPEN_PROGRESS = f"# WIP\n\n## Progress\n\n- [ ] {STEP}1: Do it\n- [ ] {STEP}2: Do it\n"
DONE_PROGRESS = f"# WIP\n\n## Progress\n\n- [x] {STEP}1: Do it\n"


@pytest.fixture(autouse=True)
def started_by_path_to_the_script(monkeypatch):
    """The command is run by explicit path, so its directory is not a `PATH` entry."""
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])


def build(tmp_path, plan=TWO_STEPS, progress=OPEN_PROGRESS):
    task = tmp_path / ".ai-work" / SLUG
    task.mkdir(parents=True)
    (task / "IMPLEMENTATION_PLAN.md").write_text(plan, encoding="utf-8")
    (task / "WIP.md").write_text(progress, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty"]
        + ["-m", "init"],
        cwd=tmp_path,
        check=True,
    )
    return tmp_path


def call(root, verb, *more):
    where = ["--repo-root", str(root), "--base-ref", "HEAD"]
    return step_loop.execute([verb, SLUG, *more, *where])


def test_a_pending_request_selects_its_step_and_carries_the_record_call(tmp_path):
    root = build(tmp_path)
    call(root, "next")

    status = call(root, "status", "--json").doc

    assert status["selected_step"] == "1"
    assert status["then"] == (
        f"{SELF_HOST} record {SLUG} --request s1-a1-implement"
        " --agent-id <agentId> --marker <complete|blocked|conflict|partial|none>"
    )


def test_the_then_equals_the_spawn_envelopes_for_the_same_request(tmp_path):
    root = build(tmp_path)
    spawned = call(root, "next").doc

    status = call(root, "status", "--json").doc

    assert status["pending_request"] == spawned["request"]["id"]
    assert status["then"] == spawned["then"]


def test_a_next_step_with_nothing_pending_is_selected_and_has_no_record_call(tmp_path):
    root = build(tmp_path)

    status = call(root, "status", "--json").doc

    assert (status["pending_request"], status["selected_step"], status["then"]) == (None, "1", None)


def test_a_stopped_loop_selects_the_stops_step(tmp_path):
    root = build(tmp_path, STUCK)

    status = call(root, "status", "--json").doc

    assert status["stop"]["step"] == "1"
    assert (status["selected_step"], status["then"]) == ("1", None)


def test_a_complete_loop_selects_nothing_and_has_no_record_call(tmp_path):
    root = build(tmp_path, ORCHESTRATOR_ONLY, DONE_PROGRESS)

    status = call(root, "status", "--json").doc

    assert (status["outcome"], status["selected_step"], status["then"]) == ("complete", None, None)


def test_the_new_keys_leave_the_existing_ones_in_place(tmp_path):
    root = build(tmp_path)

    status = call(root, "status", "--json").doc

    assert {"schema", "slug", "outcome", "pending_request", "iterations", "steps", "stop"} <= set(
        status
    )


def test_every_step_row_reports_the_cap_its_attempts_count_against(tmp_path):
    root = build(tmp_path)
    call(root, "next")

    rows = call(root, "status", "--json").doc["steps"]

    assert [row["attempt_cap"] for row in rows] == [2, 2]


def test_the_status_table_is_unchanged_for_a_pending_request(tmp_path):
    root = build(tmp_path)
    call(root, "next")

    table = call(root, "status").stdout

    assert table == (
        f"{SLUG} · iterations 0/4 · pending s1-a1-implement\n"
        "STEP  ASSIGNEE     VERDICT    ATTEMPTS  REVIEW  COMMIT\n"
        "1     implementer  in-flight  1/2       —       —\n"
        "2     implementer  pending    —         —       —\n"
        "next: the Agent call for s1-a1-implement is pending; record it when it ends\n"
    )


def test_a_step_done_outside_the_loop_shows_verified_complete(tmp_path):
    root = build(tmp_path, ORCHESTRATOR_ONLY, DONE_PROGRESS)

    status = call(root, "status", "--json").doc

    assert [row["verdict"] for row in status["steps"]] == ["verified-complete"]


def test_a_step_not_yet_run_shows_pending_in_the_json(tmp_path):
    root = build(tmp_path)

    status = call(root, "status", "--json").doc

    assert [row["verdict"] for row in status["steps"]] == ["pending", "pending"]
