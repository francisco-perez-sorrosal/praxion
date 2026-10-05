"""Tests for `record`'s pipeline over an agent that returned (``scripts/_step_loop_record.py``).

The whole call runs in the acceptance suite over a real checkout; these pin the parts whose
rules are easy to break and hard to see there: the end of an agent, the merge of a derived
scope's runs, the verdict a red run can never earn, the gate block read back for a replay, and
what each commit outcome means for the attempt.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_record as rec  # noqa: E402
from _agent_transcript import Final, Missing, Read, Unreadable  # noqa: E402
from _step_loop_files import write_gate_block  # noqa: E402
from _step_loop_gate import GateRun  # noqa: E402
from _step_loop_io import (  # noqa: E402
    CommitInterrupted,
    CommitRefused,
    Committed,
    NothingToCommit,
    TreeDisturbed,
    TreeSnapshot,
)
from _step_schema import Counts, NoRun  # noqa: E402

STEP = "Step "
REQUEST = "s1-a1-implement"
AGENT = "a1b2c3"
GREEN_LINE = "Result: pass=3 fail=0 skip=0 pending=0 by=step-loop"
RED_LINE = "Result: pass=3 fail=0 skip=0 error=1 pending=0 by=step-loop"
EMPTY_SNAPSHOT = TreeSnapshot(staged=(), unstaged=(), untracked=())


def run(passed=1, failed=0, errors=0, failed_ids=(), pending_ids=(), command="pytest a"):
    return GateRun(command, Counts(passed, failed, 0, errors), failed_ids, pending_ids)


# --- The end of an agent ----------------------------------------------------------------------


def sighting(path=Path("t.jsonl"), first="Spawn request: " + REQUEST, ended=True):
    reading = Read(4, first, Final("done"), False)
    return rec.Sighting(path, reading, False, "done", ended)


@pytest.mark.parametrize(
    ("seen", "code"),
    [
        (sighting(path=None), "agent-not-found"),
        (sighting(first="Spawn request: s9-a1-implement"), "agent-not-for-request"),
        (sighting(ended=False), "agent-running"),
    ],
)
def test_a_record_the_transcript_does_not_support_is_refused_with_its_code(monkeypatch, seen, code):
    monkeypatch.setenv(rec.END_WAIT_VARIABLE, "0")
    monkeypatch.setattr(rec, "sight", lambda *_: seen)

    with pytest.raises(rec.RecordRefusedError) as refused:
        rec.await_end(Path("."), REQUEST, AGENT, 100, sleep=lambda _: None)

    assert (refused.value.code, refused.value.message.startswith("record failed because")) == (
        code,
        True,
    )


def test_the_wait_polls_until_the_transcript_shows_the_end(monkeypatch):
    seen = iter([sighting(ended=False), sighting(ended=False), sighting()])
    monkeypatch.setattr(rec, "sight", lambda *_: next(seen))
    ticks = iter(range(100))

    ended = rec.await_end(
        Path("."), REQUEST, AGENT, 100, clock=lambda: next(ticks), sleep=lambda _: None
    )

    assert ended.ended is True


@pytest.mark.parametrize(
    ("raw", "seconds"),
    [("", rec.DEFAULT_END_WAIT_SECONDS), ("0", 0.0), ("2.5", 2.5), ("-3", 0.0), ("soon", 20.0)],
)
def test_the_bounded_wait_comes_from_the_environment(monkeypatch, raw, seconds):
    monkeypatch.setenv(rec.END_WAIT_VARIABLE, raw)

    assert rec.end_wait_seconds() == seconds


def transcript_lines(final_text, *, cut_off):
    user = {"type": "user", "message": {"role": "user", "content": "Spawn request: " + REQUEST}}
    said = {"type": "text", "text": final_text}
    final = {"type": "assistant", "requestId": "r1", "message": {"content": [said]}}
    lines = [json.dumps(user), "{broken", json.dumps(final)]
    return "\n".join([*lines, "{cut off"] if cut_off else lines) + "\n"


@pytest.mark.parametrize(("cut_off", "last_turn"), [(False, Final("[COMPLETE]")), (True, None)])
def test_an_unreadable_transcript_still_names_its_request_and_its_end_unless_cut_off(
    tmp_path, cut_off, last_turn
):
    path = tmp_path / "agent.jsonl"
    path.write_text(transcript_lines("[COMPLETE]", cut_off=cut_off), encoding="utf-8")

    reading = rec.salvaged(path, Unreadable(lines_ok=2, last_ok=not cut_off))

    assert reading == Read(None, "Spawn request: " + REQUEST, last_turn, True)


def test_a_readable_or_missing_transcript_passes_through_unchanged(tmp_path):
    readable = Read(3, "x", None, False)

    assert (rec.salvaged(tmp_path, readable), rec.salvaged(None, Missing())) == (
        readable,
        Missing(),
    )


def test_the_implementer_definition_declares_the_turn_cap_and_an_unknown_agent_none():
    assert (
        isinstance(rec.declared_max_turns("praxion:implementer"), int),
        rec.declared_max_turns("praxion:no-such-agent"),
    ) == (True, None)


# --- The gate ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("runs", "counts", "failed", "pending"),
    [
        (
            (run(2, 1, failed_ids=("a::f",)), run(3, 0, 1, failed_ids=("b::g",))),
            Counts(5, 1, 0, 1),
            ("a::f", "b::g"),
            (),
        ),
        (
            (run(1, pending_ids=("c::h",)), run(4, pending_ids=("c::h", "d::i"))),
            Counts(5, 0, 0, 0),
            (),
            ("c::h", "d::i"),
        ),
    ],
)
def test_a_derived_scope_of_several_runs_merges_into_one(runs, counts, failed, pending):
    merged = rec.merge_runs(runs)

    assert (merged.counts, merged.failed_ids, merged.pending_ids, merged.command) == (
        counts,
        failed,
        pending,
        "pytest a ; pytest a",
    )


def test_one_run_that_showed_no_summary_makes_the_merged_scope_no_run():
    merged = rec.merge_runs((run(9), GateRun("pytest b", NoRun("timed out"))))

    assert (merged.counts, merged.red) == (NoRun("timed out"), True)


def verdicts_of(word):
    return lambda *_, **__: [{"step": STEP + "1", "verdict": word, "decided_by": "check"}]


@pytest.mark.parametrize(
    ("red", "word", "read"),
    [
        (True, "verified-complete", rec.RED_RUN_VERDICT),
        (False, "verified-complete", "verified-complete"),
        (True, "pending", "pending"),
    ],
)
def test_a_red_run_fails_the_attempt_whatever_the_check_judged(monkeypatch, red, word, read):
    monkeypatch.setattr(rec, "reconcile", verdicts_of(word))
    task = SimpleNamespace(slug="s", repo=Path("."), work=Path("."), base_ref="HEAD")

    verdict = rec.read_verdict(task, "1", REQUEST, rec.Gate((GREEN_LINE,), red))

    assert verdict["verdict"] == read


@pytest.mark.parametrize(
    ("body", "red"),
    [
        (("Command: `pytest`", GREEN_LINE), False),
        (("Command: `pytest`", GREEN_LINE, RED_LINE), True),
        ((GREEN_LINE, "Result: none — the run timed out after 9s"), True),
    ],
)
def test_a_written_gate_block_is_read_back_whole_for_a_replay(tmp_path, body, red):
    results = tmp_path / rec.RESULTS_FILE
    write_gate_block(results, "1", REQUEST, body)
    write_gate_block(results, "1", "s1-a2-implement", (RED_LINE,))

    gate = rec.recorded_gate(results, rec.gate_heading("1", REQUEST))

    assert gate == rec.Gate(body, red)


def test_no_gate_block_for_the_request_means_the_gate_runs(tmp_path):
    results = tmp_path / rec.RESULTS_FILE
    write_gate_block(results, "1", "s1-a2-implement", (GREEN_LINE,))

    assert rec.recorded_gate(results, rec.gate_heading("1", REQUEST)) is None


def test_a_refused_commit_ends_the_block_on_a_no_result_line(tmp_path):
    results = tmp_path / rec.RESULTS_FILE
    write_gate_block(results, "1", REQUEST, (GREEN_LINE,))
    task = SimpleNamespace(dir=tmp_path)

    gate = rec.add_refusal(task, "1", REQUEST, rec.Gate((GREEN_LINE,), False), "hooks said no")

    assert (
        gate.red,
        gate.deciding,
        rec.recorded_gate(results, rec.gate_heading("1", REQUEST)),
    ) == (
        True,
        "Result: none — hooks said no",
        gate,
    )


# --- The commit -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("outcome", "sha", "failed", "stops"),
    [
        (Committed("abc1234", ("a.py",), ()), "abc1234", False, False),
        (NothingToCommit(()), None, False, False),
        (CommitRefused("pre-commit: ruff failed\nmore"), None, True, False),
        (CommitInterrupted("timed out", EMPTY_SNAPSHOT, True), None, True, True),
        (
            TreeDisturbed(EMPTY_SNAPSHOT, EMPTY_SNAPSHOT, ("x.py",), "def5678"),
            "def5678",
            True,
            True,
        ),
    ],
)
def test_each_commit_outcome_says_what_holds_the_work_and_whether_to_stop(
    tmp_path, outcome, sha, failed, stops
):
    task = SimpleNamespace(dir=tmp_path, repo=tmp_path)

    taken = rec.judge_commit(task, REQUEST, outcome)

    assert (taken.sha, taken.failure is not None, taken.disturbed is not None) == (
        sha,
        failed,
        stops,
    )


def test_a_disturbed_tree_saves_the_earlier_state_beside_the_task(tmp_path):
    before = TreeSnapshot(staged=(("notes.txt", "row"),), unstaged=(), untracked=())
    task = SimpleNamespace(dir=tmp_path, repo=tmp_path)

    taken = rec.judge_commit(task, REQUEST, TreeDisturbed(before, before, ("notes.txt",), None))

    saved = tmp_path / f"TREE_SNAPSHOT_{REQUEST}.patch"
    assert (str(saved) in taken.disturbed, "notes.txt" in saved.read_text()) == (True, True)


def git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty",
        "-m", f"subject\n\n{rec.TRAILER}{REQUEST}")  # fmt: skip
    return tmp_path


@pytest.mark.parametrize(("request_id", "found"), [(REQUEST, True), ("s1-a2-implement", False)])
def test_a_head_commit_naming_the_request_is_reused(repo, request_id, found):
    sha = rec.head_commit_for(repo, request_id)

    assert (sha == git(repo, "rev-parse", "HEAD")) is found


def test_a_left_index_lock_is_named_in_the_stop_text(repo):
    (repo / ".git" / "index.lock").write_text("", encoding="utf-8")

    assert "index.lock exists" in rec._lock_note(repo)


# --- The checklist ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("wip", "after", "wrote"),
    [
        (f"- [ ] {STEP}1: Do it\n- [ ] {STEP}2: Next\n", f"- [x] {STEP}1: Do it\n", True),
        (f"- [x] {STEP}1: Do it\n- [ ] {STEP}2: Next\n", f"- [x] {STEP}1: Do it\n", False),
    ],
)
def test_the_step_line_is_ticked_once_and_no_other(tmp_path, wip, after, wrote):
    path = tmp_path / rec.WIP_FILE
    path.write_text(wip, encoding="utf-8")

    ticked = rec.tick_step(path, "1")

    assert (ticked, path.read_text(encoding="utf-8")) == (wrote, after + f"- [ ] {STEP}2: Next\n")
