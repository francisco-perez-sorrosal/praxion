"""Tests for what `record` leaves on a step's `Attempts:` line (``scripts/_step_loop_settle.py``
and ``scripts/_step_loop_record.py``).

The whole call runs in the acceptance suite over a real checkout; these pin the parts whose
rules are easy to break and hard to see there: the replan line the capped attempt leaves, the
series that does and does not earn it, and the line a withdrawn request restores.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_record as rec  # noqa: E402
import _step_loop_settle as settle  # noqa: E402
import step_loop  # noqa: E402
from _loop_fields import ATTEMPT_CAP, Attempt, OutstandingAttempt  # noqa: E402
from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_render import RequestKey  # noqa: E402
from _step_loop_state import LoopInputs  # noqa: E402
from iteration_ledger import IterationRecord, append_record  # noqa: E402

STEP = "Step "
SLUG = "demo"
SCRIPT = SCRIPT_DIR / "step_loop.py"
CHECK = "**Check**: `python3 -m pytest -q` expects pass>=1 fail=0"
PLAN = f"# Plan\n\n## Steps\n\n### {STEP}1: Do it\n\n**Assignee**: implementer\n{CHECK}\n"
WIP = f"# WIP\n\n## Progress\n\n- [ ] {STEP}1: Do it\n"
GATE = "Result: pass=0 fail=1 skip=0 pending=0 by=step-loop"
COMMIT = "c" * 40
FIRST = f"{STEP}1"
UNVERIFIED, MARKED = "mismatch", "blocked"
THE_STEP = parse_plan_steps(PLAN)[0]


def record(attempt, *, verdict=UNVERIFIED, stop="completed", commit=None, kind="implement"):
    key = RequestKey("1", attempt, kind, 1, None if kind == "implement" else 1)
    return IterationRecord(
        step=FIRST,
        attempt=attempt,
        agent_id=f"agent-{attempt}",
        verdict=verdict,
        decided_by="check",
        test_result=GATE,
        commit=commit,
        stop_reason=stop,
        request=key.id,
        step_digest=THE_STEP.digest,
    )


def inputs(*records, attempt=None):
    attempts = {} if attempt is None else {"1": attempt}
    return LoopInputs((THE_STEP,), attempts, tuple(records), {})


def wip_with(tmp_path, line=None):
    path = tmp_path / "WIP.md"
    path.write_text(WIP + (f"  - Attempts: {STEP}1 {line}\n" if line else ""), encoding="utf-8")
    return path


def attempts_lines(path):
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if "Attempts:" in line
    ]


# --- The replan line the capped attempt leaves -------------------------------------------------


def test_the_replan_text_is_one_line_naming_each_attempt_its_stop_evidence_and_commit():
    attempts = (record(1, stop="turn-cap"), record(2, commit=COMMIT))

    text = settle.replan_text(attempts)

    assert text == (
        f"attempt 1: turn-cap; {GATE}; no commit | attempt 2: completed; {GATE}; {COMMIT}"
    )


def test_an_exhausted_series_is_written_as_a_replan_on_the_attempts_line(tmp_path):
    wip = wip_with(tmp_path, f"count={ATTEMPT_CAP} request=s1-a{ATTEMPT_CAP}-implement")
    ended = inputs(*(record(n) for n in range(1, ATTEMPT_CAP + 1)))

    wrote = settle.settle_replan(wip, ended, THE_STEP, f"s1-a{ATTEMPT_CAP}-implement")

    (line,) = attempts_lines(wip)
    assert (wrote, line.startswith(f"- Attempts: {STEP}1 count={ATTEMPT_CAP} request=")) == (
        True,
        True,
    )
    assert f"[BLOCKED] replan: attempt 1: completed; {GATE}; no commit | attempt 2" in line


def test_the_same_series_settles_to_the_same_line_and_writes_nothing_the_second_time(tmp_path):
    wip = wip_with(tmp_path, f"count={ATTEMPT_CAP} request=s1-a{ATTEMPT_CAP}-implement")
    ended = inputs(*(record(n) for n in range(1, ATTEMPT_CAP + 1)))
    last = f"s1-a{ATTEMPT_CAP}-implement"
    settle.settle_replan(wip, ended, THE_STEP, last)
    after_first = wip.read_text(encoding="utf-8")

    wrote = settle.settle_replan(
        wip, replace(ended, attempts={"1": Attempt(2, "x", last)}), THE_STEP, last
    )

    assert (wrote, wip.read_text(encoding="utf-8")) == (False, after_first)


@pytest.mark.parametrize(
    "ended",
    [
        pytest.param(inputs(record(1)), id="under-the-cap"),
        pytest.param(inputs(record(1), record(2, verdict="verified-complete")), id="verified"),
        pytest.param(inputs(record(1), record(2, stop=MARKED)), id="marked-at-the-cap"),
    ],
)
def test_a_series_that_is_not_exhausted_leaves_the_line_alone(tmp_path, ended):
    wip = wip_with(tmp_path, "count=2 request=s1-a2-implement")
    before = wip.read_text(encoding="utf-8")

    wrote = settle.settle_replan(wip, ended, THE_STEP, "s1-a2-implement")

    assert (wrote, wip.read_text(encoding="utf-8")) == (False, before)


# --- The line a withdrawn request restores -----------------------------------------------------


@pytest.mark.parametrize(
    ("count", "kind", "restored"),
    [
        (1, "implement", []),
        (2, "implement", [f"- Attempts: {STEP}1 count=1"]),
        (2, "review", [f"- Attempts: {STEP}1 count=2"]),
        (1, "revise", [f"- Attempts: {STEP}1 count=1"]),
    ],
    ids=["first-attempt", "second-attempt", "review", "revise"],
)
def test_a_withdrawn_request_restores_the_count_the_write_ahead_replaced(
    tmp_path, count, kind, restored
):
    wip = wip_with(tmp_path, f"count={count} request=s1-a{count}-{kind}")

    settle.withdraw_line(wip, "1", OutstandingAttempt(count, f"s1-a{count}-{kind}"), kind)

    assert attempts_lines(wip) == restored


# --- The withdrawal through the command --------------------------------------------------------


def build(tmp_path, ledger=()):
    task = tmp_path / ".ai-work" / SLUG
    task.mkdir(parents=True)
    (task / "IMPLEMENTATION_PLAN.md").write_text(PLAN, encoding="utf-8")
    (task / "WIP.md").write_text(WIP, encoding="utf-8")
    for earlier in ledger:
        append_record(task, earlier)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty"]
        + ["-m", "init"],
        cwd=tmp_path,
        check=True,
    )
    return tmp_path


def where(root):
    return ["--repo-root", str(root), "--base-ref", "HEAD"]


def call(root, verb, *more):
    return step_loop.execute([verb, SLUG, *more, *where(root)])


def task_of(root):
    args = argparse.Namespace(repo_root=str(root), worktree_root=None, base_ref="HEAD", slug=SLUG)
    return step_loop.read_task(args)


@pytest.fixture(autouse=True)
def started_by_path_to_the_script(monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])


def test_a_withdrawn_first_request_removes_the_line_and_the_prompt_it_wrote(tmp_path):
    root = build(tmp_path)
    request = call(root, "next").doc["request"]
    prompt = Path(request["prompt_path"])

    took = rec.withdraw_request(task_of(root), request["id"])

    assert (took.recorded["stop_reason"], prompt.exists()) == ("not-started", False)
    assert attempts_lines(root / ".ai-work" / SLUG / "WIP.md") == []


def test_a_withdrawn_second_request_is_issued_again_byte_for_byte(tmp_path):
    first = record(1)
    root = build(tmp_path, ledger=[first])
    asked = call(root, "next").doc["request"]
    prompt = Path(asked["prompt_path"])
    written = prompt.read_bytes()

    rec.withdraw_request(task_of(root), asked["id"])
    assert attempts_lines(root / ".ai-work" / SLUG / "WIP.md") == [f"- Attempts: {STEP}1 count=1"]
    again = call(root, "next").doc["request"]

    assert (again["id"], again["reissued"], prompt.read_bytes()) == (asked["id"], False, written)
    assert "previous-attempts" in written.decode("utf-8")


def test_the_withdrawal_envelope_is_the_next_action_with_a_recorded_object_and_no_ledger(tmp_path):
    root = build(tmp_path)
    request = call(root, "next").doc["request"]

    reply = call(root, "record", "--request", request["id"], "--not-started", "the call failed")

    ledger = root / ".ai-work" / SLUG / "ITERATION_LEDGER.jsonl"
    assert (reply.exit, reply.doc["recorded"]["stop_reason"], ledger.exists()) == (
        0,
        "not-started",
        False,
    )
    assert json.loads(reply.stdout)["request"]["id"] == request["id"]


def test_a_replay_of_the_capped_attempt_settles_the_replan_and_the_stop_carries_it(tmp_path):
    capped = f"s1-a{ATTEMPT_CAP}-implement"
    ledger = [record(n) for n in range(1, ATTEMPT_CAP + 1)]
    root = build(tmp_path, ledger=ledger)
    wip = root / ".ai-work" / SLUG / "WIP.md"
    wip.write_text(f"{WIP}  - Attempts: {STEP}1 count={ATTEMPT_CAP} request={capped}\n", "utf-8")

    reply = call(root, "record", "--request", capped, "--agent-id", "gone", "--marker", "complete")

    (line,) = attempts_lines(wip)
    stop = reply.doc["stop"]
    assert (reply.exit, reply.doc["recorded"]["replayed"], stop["cause"]) == (
        2,
        True,
        "attempts-exhausted",
    )
    assert line.endswith(f"[BLOCKED] replan: {stop['replan_request']}")


# --- A disturbed tree keeps the loop stopped through the command -------------------------------


def disturbed_task(tmp_path):
    first = record(1, commit=COMMIT)
    root = build(tmp_path, ledger=[first])
    task = task_of(root)
    task.dir.joinpath(f"TREE_SNAPSHOT_{first.request}.patch").write_text("# held\n", "utf-8")
    return root, first


@pytest.mark.parametrize("verb", ["next", "status"])
def test_a_disturbed_tree_repeats_the_same_stop_byte_for_byte_until_the_snapshot_is_deleted(
    tmp_path, verb
):
    root, first = disturbed_task(tmp_path)

    again = [call(root, verb) for _ in range(2)]

    assert again[0] == again[1]
    assert ("commit-disturbed-tree" in again[0].stdout, first.request in again[0].lines[0]) == (
        True,
        True,
    )


@pytest.mark.parametrize("verb", ["next", "status"])
def test_deleting_the_snapshot_clears_the_disturbed_stop(tmp_path, verb):
    root, first = disturbed_task(tmp_path)
    (root / ".ai-work" / SLUG / f"TREE_SNAPSHOT_{first.request}.patch").unlink()

    cleared = call(root, verb)

    assert (cleared.exit, "commit-disturbed-tree" in cleared.stdout) == (0, False)
