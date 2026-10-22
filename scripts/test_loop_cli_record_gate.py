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
import _step_loop_record_gate as gating  # noqa: E402
from _agent_transcript import Final, Missing, Read, Unreadable  # noqa: E402
from _loop_fields import ATTEMPT_CAP  # noqa: E402
from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_files import write_gate_block  # noqa: E402
from _step_loop_gate import GateRun  # noqa: E402
from _step_loop_io import (  # noqa: E402
    CommandRun,
    CommitInterrupted,
    CommitRefused,
    Committed,
    NothingToCommit,
    PocketScope,
    ScopeRuns,
    ScopeUnresolved,
    TreeDisturbed,
    TreeSnapshot,
)
from _step_loop_pocket_runs import (  # noqa: E402
    BoundSource,
    CutOff,
    Finished,
    NotStarted,
    PocketBound,
)
from _step_loop_render import RequestKey, spawn_request  # noqa: E402
from _step_loop_state import LoopInputs  # noqa: E402
from _step_schema import Counts, NoRun, mutation_block_reasons  # noqa: E402

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


def test_an_exited_session_is_taken_back_as_it_stands_without_waiting_for_an_end(monkeypatch):
    monkeypatch.setenv(rec.END_WAIT_VARIABLE, "0")
    monkeypatch.setattr(rec, "sight", lambda *_: sighting(ended=False))

    seen = rec.await_end(Path("."), REQUEST, AGENT, 100, sleep=lambda _: None, exited=True)

    assert seen.ended is False


@pytest.mark.parametrize(
    ("seen", "code"),
    [
        (sighting(path=None), "agent-not-found"),
        (sighting(first="Spawn request: s9-a1-implement"), "agent-not-for-request"),
    ],
)
def test_an_exited_session_whose_transcript_is_missing_or_another_request_is_refused_as_a_session(
    monkeypatch, seen, code
):
    monkeypatch.setenv(rec.END_WAIT_VARIABLE, "0")
    monkeypatch.setattr(rec, "sight", lambda *_: seen)

    with pytest.raises(rec.RecordRefusedError) as refused:
        rec.await_end(Path("."), REQUEST, AGENT, 100, sleep=lambda _: None, exited=True)

    assert (refused.value.code, "session" in refused.value.message) == (code, True)


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
def test_the_finished_runs_of_a_derived_scope_merge_into_one(runs, counts, failed, pending):
    merged = gating.merge_finished(runs)

    assert (merged.counts, merged.failed_ids, merged.pending_ids, merged.command) == (
        counts,
        failed,
        pending,
        "pytest a ; pytest a",
    )


# --- The derived scope, read pocket run by pocket run ------------------------------------------

REPO = Path("/repo")
LOGS = REPO / ".ai-work" / "demo" / "gate" / REQUEST
PASSED_OUTPUT = "== 3 passed in 0.10s =="
FAILED_OUTPUT = "FAILED t.py::test_x - assert 0\n== 1 failed, 2 passed in 0.10s =="
LATER = "t.py::test_later"


class PendingNodes:
    """A pending rule that owns exactly the nodes it is given."""

    def __init__(self, *nodes: str) -> None:
        self.nodes = nodes

    def is_pending(self, node_id: str) -> bool:
        return node_id in self.nodes

    def is_pending_error(self, node_id: str) -> bool:
        return False


NOTHING_PENDING = PendingNodes()
LATER_PENDING = PendingNodes(LATER)


def finished(pocket, output=PASSED_OUTPUT, number=1):
    return Finished(pocket, ("pytest", pocket), 0, output, LOGS / f"{number}.log")


def cut_off(pocket, seen=(), seconds=7.0, source: BoundSource = "override", number=2):
    bound = PocketBound(pocket, seconds, source)
    return CutOff(bound, ("pytest", pocket), tuple(seen), "", LOGS / f"{number}.log")


def scope(*pockets, widened=False, listed=1):
    return ScopeRuns(
        "selected", tuple(PocketScope(p, widened, listed, tuple(runs)) for p, *runs in pockets)
    )


def read(*pockets, rule=NOTHING_PENDING, widened=False, listed=1):
    return gating.read_scope(scope(*pockets, widened=widened, listed=listed), rule, REPO)


def test_a_scope_whose_runs_all_finished_is_read_as_their_merged_counts():
    reading = read((".", finished(".")), ("eval", finished("eval", number=2)))

    assert (reading.deciding.counts, reading.deciding.command, reading.kept, reading.notes) == (
        Counts(6, 0, 0, 0),
        "pytest . ; pytest eval",
        (),
        (),
    )


def test_a_run_past_its_bound_makes_the_scope_red_and_names_its_pocket_and_bound():
    reading = read((".", finished(".")), ("eval", cut_off("eval")))

    assert (reading.deciding.red, reading.deciding.counts, reading.notes) == (
        True,
        NoRun("eval cut off after 7s (override)"),
        ("Cut off: eval after 7s (override)",),
    )


def test_the_counts_and_failures_of_the_runs_that_finished_stay_beside_a_cut_off_one():
    reading = read(
        (".", finished(".", FAILED_OUTPUT)), ("eval", cut_off("eval", seen=("e.py::a", "e.py::b")))
    )

    assert (reading.kept[0].counts, reading.notes) == (
        Counts(2, 1, 0, 0),
        (
            "Cut off: eval after 7s (override)",
            "Failed: t.py::test_x",
            "Failed: e.py::a",
            "Failed: e.py::b",
        ),
    )


def test_a_failure_seen_before_the_cut_that_a_later_step_owns_is_not_this_steps_failure():
    reading = read(("eval", cut_off("eval", seen=("e.py::a", LATER))), rule=LATER_PENDING)

    assert reading.notes == ("Cut off: eval after 7s (override)", "Failed: e.py::a")


def test_a_failure_shown_by_two_runs_is_listed_once():
    reading = read(
        (".", finished(".", FAILED_OUTPUT)), ("eval", cut_off("eval", seen=("t.py::test_x",)))
    )

    assert reading.notes.count("Failed: t.py::test_x") == 1


def test_twenty_failures_are_listed_and_the_rest_are_counted_with_where_they_are_kept():
    seen = [f"e.py::t{n:02d}" for n in range(27)]

    reading = read(("eval", cut_off("eval", seen=seen)))

    failed = [line for line in reading.notes if line.startswith("Failed:")]
    assert (len(failed), failed[0], failed[-2], failed[-1]) == (
        21,
        "Failed: e.py::t00",
        "Failed: e.py::t19",
        f"Failed: … 7 more in {LOGS.relative_to(REPO)}",
    )


def test_a_run_that_ended_without_a_summary_is_a_red_run_that_keeps_the_others_counts():
    reading = read((".", finished(".")), ("eval", finished("eval", "it crashed", number=2)))

    assert (reading.deciding.counts, reading.kept[0].counts, reading.notes) == (
        NoRun("eval: the output holds no pytest summary line"),
        Counts(3, 0, 0, 0),
        (),
    )


def test_a_run_that_never_started_is_a_red_run_naming_its_pocket():
    reading = read(("eval", NotStarted("eval", "no run was started")))

    assert (reading.deciding.counts, reading.kept) == (
        NoRun("eval did not run (no run was started)"),
        (),
    )


def test_several_unfinished_runs_are_all_named_in_the_one_deciding_line():
    reading = read(("a", cut_off("a")), ("b", NotStarted("b", "gone")))

    assert reading.deciding.counts == NoRun("a cut off after 7s (override); b did not run (gone)")


VERBOSE_PASSES = "a.py::t1 PASSED  [ 50%]\nb.py::t1 PASSED  [ 75%]\nb.py::t2 PASSED  [100%]\n== 3 passed in 0.10s =="
HEAD = "0123456789abcdef0123456789abcdef01234567"


def test_each_pocket_that_finished_gets_a_line_with_its_files_tests_and_how_it_was_selected():
    reading = read((".", finished(".", number=1)), ("eval", finished("eval", number=2)), listed=3)

    assert reading.scopes == (
        "Scope: . files=3 tests=3 narrow",
        "Scope: eval files=3 tests=3 narrow",
    )


def test_a_widened_pocket_names_no_files_so_they_are_counted_from_its_log():
    reading = read(("eval", finished("eval", VERBOSE_PASSES)), widened=True, listed=0)

    assert reading.scopes == ("Scope: eval files=2 tests=3 widened",)


def test_a_pocket_with_several_invocations_is_one_line_summing_their_tests():
    reading = read(("eval", finished("eval", number=1), finished("eval", number=2)), listed=4)

    assert reading.scopes == ("Scope: eval files=4 tests=6 narrow",)


def test_a_pocket_that_did_not_finish_has_no_scope_line_and_the_others_keep_theirs():
    reading = read((".", finished(".")), ("eval", cut_off("eval")))

    assert reading.scopes == ("Scope: . files=1 tests=3 narrow",)


def test_a_pocket_whose_files_are_unknown_leaves_the_count_out():
    reading = read(("dashboard_app", finished("dashboard_app", "Tests  3 passed (3)")), listed=0)

    assert reading.scopes == ("Scope: dashboard_app tests=3 narrow",)


def run_the_gate_over(monkeypatch, tmp_path, *pockets):
    monkeypatch.setattr(gating, "head_sha", lambda _repo: HEAD)
    monkeypatch.setattr(gating, "paths_differing_from_head", lambda *_: ("a.py",))
    monkeypatch.setattr(gating, "run_check", lambda *_: PASSED)
    monkeypatch.setattr(gating, "run_derived_scope", lambda *_: scope(*pockets))
    task = gate_task(tmp_path, gate_plan("**Files**: `a.py`\n", CHECK_LINE))
    return gating.run_gate(task, task.inputs.steps[0], REQUEST)


def test_a_cut_off_run_ends_the_block_on_a_red_result_line_whatever_the_check_showed(
    monkeypatch, tmp_path
):
    gate = run_the_gate_over(
        monkeypatch, tmp_path, (".", finished(".", FAILED_OUTPUT)), ("eval", cut_off("eval"))
    )

    body = "\n".join(gate.body)
    assert (gate.red, gate.deciding) == (True, "Result: none — eval cut off after 7s (override)")
    assert "Cut off: eval after 7s (override)" in body
    assert "Failed: t.py::test_x" in body
    assert "Result: pass=2 fail=1 skip=0 pending=0 by=step-loop" in body


def test_a_cut_off_block_is_read_back_red(monkeypatch, tmp_path):
    gate = run_the_gate_over(monkeypatch, tmp_path, ("eval", cut_off("eval")))

    again = gating.recorded_gate(tmp_path / gating.RESULTS_FILE, gating.gate_heading("1", REQUEST))

    assert again == gate
    assert again is not None
    assert again.red


def verdicts_of(word):
    return lambda *_, **__: [{"step": STEP + "1", "verdict": word, "decided_by": "check"}]


@pytest.mark.parametrize(
    ("red", "word", "read"),
    [
        (True, "verified-complete", gating.RED_RUN_VERDICT),
        (False, "verified-complete", "verified-complete"),
        (True, "pending", "pending"),
    ],
)
def test_a_red_run_fails_the_attempt_whatever_the_check_judged(monkeypatch, red, word, read):
    monkeypatch.setattr(gating, "reconcile", verdicts_of(word))
    task = SimpleNamespace(slug="s", repo=Path("."), work=Path("."), base_ref="HEAD")

    verdict = gating.read_verdict(task, "1", REQUEST, gating.Gate((GREEN_LINE,), red))

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
    results = tmp_path / gating.RESULTS_FILE
    write_gate_block(results, "1", REQUEST, body)
    write_gate_block(results, "1", "s1-a2-implement", (RED_LINE,))

    gate = gating.recorded_gate(results, gating.gate_heading("1", REQUEST))

    assert gate == gating.Gate(body, red)


def test_no_gate_block_for_the_request_means_the_gate_runs(tmp_path):
    results = tmp_path / gating.RESULTS_FILE
    write_gate_block(results, "1", "s1-a2-implement", (GREEN_LINE,))

    assert gating.recorded_gate(results, gating.gate_heading("1", REQUEST)) is None


def test_a_refused_commit_ends_the_block_on_a_no_result_line(tmp_path):
    results = tmp_path / gating.RESULTS_FILE
    write_gate_block(results, "1", REQUEST, (GREEN_LINE,))
    task = SimpleNamespace(dir=tmp_path)

    gate = gating.add_refusal(
        task, "1", REQUEST, gating.Gate((GREEN_LINE,), False), "hooks said no"
    )

    assert (
        gate.red,
        gate.deciding,
        gating.recorded_gate(results, gating.gate_heading("1", REQUEST)),
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

    assert (taken.sha, taken.failure is not None, snapshot_of(tmp_path).exists()) == (
        sha,
        failed,
        stops,
    )


def test_a_disturbed_tree_saves_the_earlier_state_beside_the_task(tmp_path):
    before = TreeSnapshot(staged=(("notes.txt", "row"),), unstaged=(), untracked=())
    task = SimpleNamespace(dir=tmp_path, repo=tmp_path)

    taken = rec.judge_commit(task, REQUEST, TreeDisturbed(before, before, ("notes.txt",), None))

    saved = snapshot_of(tmp_path)
    assert (taken.failure in saved.read_text(), "notes.txt" in saved.read_text()) == (True, True)


def snapshot_of(task_dir):
    return task_dir / f"TREE_SNAPSHOT_{REQUEST}.patch"


@pytest.mark.parametrize(
    "error",
    [
        rec.GitCommandError("fatal: bad object"),
        rec.GitUnavailableError("git is not on PATH"),
        rec.OutsideRepoError("../x leaves the repository"),
    ],
    ids=["git-refused", "git-unavailable", "path-outside-the-repository"],
)
def test_a_commit_that_could_not_run_leaves_a_snapshot_naming_why_and_no_sha(
    repo, monkeypatch, error
):
    def raising(*_):
        raise error

    monkeypatch.setattr(rec, "commit_paths", raising)
    task = SimpleNamespace(dir=repo, repo=repo, slug=SLUG, inputs=SimpleNamespace(steps=()))
    step = parse_plan_steps(gate_plan())[0]
    asked = spawn_request(SLUG, step, RequestKey("1", 2, "implement", 1), ATTEMPT_CAP, str(repo))

    taken = rec.commit_attempt(task, step, asked, GREEN_LINE)

    saved = (repo / "TREE_SNAPSHOT_s1-a2-implement.patch").read_text()
    assert (taken.sha, taken.failure in saved, str(error) in saved) == (None, True, True)


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


# --- The mutation line a tagged step carries into the driver's block ---------------------------

SLUG = "demo"
STEP_HEAD = f"## Steps\n\n### {STEP}1: Do it\n\n**Assignee**: implementer\n"
CHECK_LINE = "**Check**: `python3 -m pytest -q` expects pass>=1 fail=0\n"
MUTATION_TAG = "**mutation**: on\n"
RAN = "Mutation: survivors=0 mutants=5 targets=[a] (a: 0)"
LAYOUT = "Mutation: unavailable reason=not-flat-layout (the tests are nested)"
SENSOR_DOWN = "Mutation: unavailable reason=toolchain-missing (uv is absent)"
PASSED = CommandRun(("python3", "-m", "pytest", "-q"), ".", "3 passed in 0.1s", 0)


def gate_plan(*lines):
    return STEP_HEAD + "".join(lines)


def gate_task(tmp_path, plan):
    inputs = LoopInputs(tuple(parse_plan_steps(plan)), {}, (), {})
    return SimpleNamespace(
        slug=SLUG, repo=tmp_path, work=tmp_path, dir=tmp_path, base_ref="HEAD", inputs=inputs
    )


def run_the_gate(monkeypatch, tmp_path, plan, *, changed=(), decision=None):
    monkeypatch.setattr(gating, "head_sha", lambda _repo: HEAD)
    monkeypatch.setattr(gating, "paths_differing_from_head", lambda *_: changed)
    monkeypatch.setattr(gating, "run_check", lambda *_: PASSED)
    monkeypatch.setattr(gating, "run_derived_scope", lambda *_: ScopeRuns(decision, ()))
    task = gate_task(tmp_path, plan)
    return gating.run_gate(task, task.inputs.steps[0], REQUEST)


@pytest.mark.parametrize(
    ("earlier", "blocked"),
    [
        pytest.param([RAN], {}, id="a-ran-line-verifies"),
        pytest.param([LAYOUT], {}, id="the-declared-layout-limit-verifies"),
        pytest.param([], {f"{STEP}1": "no Mutation: line"}, id="no-line-stays-blocked"),
        pytest.param(
            [SENSOR_DOWN],
            {f"{STEP}1": "refused, reason=toolchain-missing"},
            id="another-refusal-stays-blocked",
        ),
        pytest.param(
            ["Mutation: survivors=x"],
            {f"{STEP}1": "unreadable Mutation: line"},
            id="an-unreadable-line-stays-blocked",
        ),
    ],
)
def test_the_driver_block_repeats_the_implementers_mutation_line_for_the_reconciler(
    monkeypatch, tmp_path, earlier, blocked
):
    plan = gate_plan(MUTATION_TAG, CHECK_LINE)
    results = tmp_path / gating.RESULTS_FILE
    results.write_text(
        "\n".join([f"## {STEP}1 — implementer", "", *earlier, GREEN_LINE, ""]), "utf-8"
    )

    gate = run_the_gate(monkeypatch, tmp_path, plan)

    assert (
        gate.deciding.startswith("Result: pass="),
        mutation_block_reasons(plan, results.read_text("utf-8")),
    ) == (
        True,
        blocked,
    )


def test_the_mutation_line_sits_before_the_result_lines_so_the_block_ends_on_the_deciding_line(
    monkeypatch, tmp_path
):
    results = tmp_path / gating.RESULTS_FILE
    results.write_text(f"## {STEP}1 — implementer\n\n{RAN}\n{GREEN_LINE}\n", "utf-8")

    gate = run_the_gate(monkeypatch, tmp_path, gate_plan(CHECK_LINE))

    assert (gate.body[-2], gate.body[-1].startswith("Result:")) == (RAN, True)


# --- A derived scope the resolver says needs no test is not a red run --------------------------

README_STEP = ("**Files**: `README.md`\n",)


@pytest.mark.parametrize(
    ("lines", "red", "deciding"),
    [
        pytest.param((*README_STEP, CHECK_LINE), False, "Result: pass=3", id="the-check-decides"),
        pytest.param(
            README_STEP, True, f"Result: none — {gating.NOTHING_SELECTED}", id="no-check-no-test"
        ),
    ],
)
def test_a_scope_that_needs_no_test_leaves_the_decision_to_the_check_or_to_nothing(
    monkeypatch, tmp_path, lines, red, deciding
):
    gate = run_the_gate(
        monkeypatch, tmp_path, gate_plan(*lines), changed=("README.md",), decision="nothing-to-run"
    )

    assert (gate.red, gate.deciding.startswith(deciding)) == (red, True)


def test_a_scope_that_selects_but_lists_no_invocation_is_still_a_red_run(monkeypatch, tmp_path):
    gate = run_the_gate(
        monkeypatch,
        tmp_path,
        gate_plan(*README_STEP, CHECK_LINE),
        changed=("README.md",),
        decision="selected",
    )

    assert (gate.red, "the test scope selects no test" in gate.deciding) == (True, True)


def test_a_green_block_summarises_the_scope_and_keeps_only_the_checks_own_command(
    monkeypatch, tmp_path
):
    gate = run_the_gate_over(monkeypatch, tmp_path, (".", finished(".")))

    assert gate.body == (
        "Scope: . files=1 tests=3 narrow",
        "Derived from: 1 declared files differing from 0123456",
        "Command: `python3 -m pytest -q`",
        "Result: pass=3 fail=0 skip=0 pending=0 by=step-loop",
        "Result: pass=3 fail=0 skip=0 pending=0 by=step-loop",
    )


def test_a_scope_that_did_not_resolve_still_says_what_it_was_derived_from(monkeypatch, tmp_path):
    monkeypatch.setattr(gating, "head_sha", lambda _repo: HEAD)
    monkeypatch.setattr(gating, "paths_differing_from_head", lambda *_: ("a.py", "b.py"))
    monkeypatch.setattr(gating, "run_check", lambda *_: PASSED)
    monkeypatch.setattr(gating, "run_derived_scope", lambda *_: ScopeUnresolved(PASSED))
    task = gate_task(tmp_path, gate_plan("**Files**: `a.py`\n", CHECK_LINE))

    gate = gating.run_gate(task, task.inputs.steps[0], REQUEST)

    assert "Derived from: 2 declared files differing from 0123456" in gate.body
