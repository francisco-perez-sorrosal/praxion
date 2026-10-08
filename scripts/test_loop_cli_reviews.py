"""Tests for the light-review half of the step-loop command: the request a verified step marked
for review gets, and what `record` takes back from the reviewer
(``scripts/step_loop.py``, ``scripts/_step_loop_record.py``, ``scripts/_step_loop_review.py``).

The whole loop runs in the acceptance suite over a real checkout; these pin the parts whose
rules are easy to break and hard to see there: the commit range a review is told to read, the
stop for a review with nothing to read, the one ledger record a reviewer's return leaves and
what it copies from the work reviewed, and the verdict word that comes back. Every case runs
the real command over a small checkout in ``tmp_path``; the one double is the wait for the
reviewer's transcript, because the harness writes that file and the tests cannot.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parent / "hooks"))

import _step_loop_record as rec  # noqa: E402
import step_loop  # noqa: E402
from _agent_transcript import Final, Read  # noqa: E402
from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_render import RequestKey  # noqa: E402
from iteration_ledger import IterationRecord, append_record, read_ledger  # noqa: E402

STEP = "Step "
SLUG = "demo"
SCRIPT = SCRIPT_DIR / "step_loop.py"
SOURCE = "src/one.py"
CHECK = "**Check**: `python3 -m pytest -q` expects pass>=1 fail=0"
FORCED = "**review**: force"
PLAN = (
    "# Plan\n\n## Steps\n\n"
    f"### {STEP}1: Do it\n\n**Assignee**: implementer\n**Files**: `{SOURCE}`\n{CHECK}\n{FORCED}\n\n"
    f"### {STEP}2: Then this [depends-on: 1]\n\n**Assignee**: implementer\n"
    f"**Files**: `src/two.py`\n{CHECK}\n"
)
WIP = f"# WIP\n\n## Progress\n\n- [ ] {STEP}1: Do it\n- [ ] {STEP}2: Then this\n"
THE_STEP = parse_plan_steps(PLAN)[0]
GATE = "Result: pass=3 fail=0 skip=0 pending=0 by=step-loop"
VERIFIED, ACCEPT, REVISE, UNFINISHED = "verified-complete", "accept", "revise", "partial"
REVIEW_FILE = "LIGHT_REVIEW_step-1.md"
REVIEWER_REQUESTS = 6
REVIEW_REQUEST, SECOND_REVIEW_REQUEST = "s1-a1-review-r1", "s1-a1-review-r2"
GIT = ("git", "-c", "user.name=t", "-c", "user.email=t@t")


@pytest.fixture(autouse=True)
def started_by_path_to_the_script(monkeypatch):
    """The command is run by explicit path, so its directory is not a `PATH` entry."""
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])


def git(root, *args):
    done = subprocess.run([*GIT, *args], cwd=root, check=True, capture_output=True, text=True)
    return done.stdout.strip()


def build(tmp_path, wip=WIP):
    task = tmp_path / ".ai-work" / SLUG
    task.mkdir(parents=True)
    (task / "IMPLEMENTATION_PLAN.md").write_text(PLAN, encoding="utf-8")
    (task / "WIP.md").write_text(wip, encoding="utf-8")
    git(tmp_path, "init", "-q")
    git(tmp_path, "commit", "-q", "--allow-empty", "-m", "init")
    return tmp_path


def commit_work(root, text):
    """Commit a new version of the step's file; return the commit's sha."""
    (root / SOURCE).parent.mkdir(exist_ok=True)
    (root / SOURCE).write_text(text, encoding="utf-8")
    git(root, "add", SOURCE)
    git(root, "commit", "-q", "-m", text)
    return git(root, "rev-parse", "HEAD")


def returned(kind, sha, *, attempt=1, round_=None, verdict=VERIFIED):
    """The ledger record of an implement or revise return that left `sha`."""
    key = RequestKey("1", attempt, kind, 1, round_)
    return IterationRecord(
        step=f"{STEP}1",
        attempt=attempt,
        agent_id=f"agent-{key.id}",
        verdict=verdict,
        decided_by="check",
        test_result=GATE,
        commit=sha,
        stop_reason="completed",
        request=key.id,
        step_digest=THE_STEP.digest,
        turns=40,
        max_turns=80,
    )


def verified_work(root, *records):
    for record in records:
        append_record(root / ".ai-work" / SLUG, record)


def where(root):
    return ["--repo-root", str(root), "--base-ref", "HEAD"]


def call(root, verb, *more):
    return step_loop.execute([verb, SLUG, *more, *where(root)])


def record_return(root, request, marker="complete"):
    relay = ("--request", request, "--agent-id", "reviewer-1", "--marker", marker)
    return call(root, "record", *relay)


def reviewer_ends(monkeypatch, request, final="[COMPLETE]"):
    """The wait for the reviewer's transcript finds it ended, with `final` as its last text."""
    reading = Read(REVIEWER_REQUESTS, f"Spawn request: {request}", Final(final), False)
    seen = rec.Sighting(Path("reviewer.jsonl"), reading, False, final, True)
    monkeypatch.setattr(rec, "await_end", lambda *_: seen)


def leave_verdict(root, text):
    (root / ".ai-work" / SLUG / REVIEW_FILE).write_text(text, encoding="utf-8")


def ledger(root):
    return read_ledger(root / ".ai-work" / SLUG)


def attempts_lines(root):
    text = (root / ".ai-work" / SLUG / "WIP.md").read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if "Attempts:" in line]


def verified_and_reviewed(tmp_path, monkeypatch, verdict_text, final="[COMPLETE]"):
    """A step verified at one commit, its review asked for and answered with `verdict_text`."""
    root = build(tmp_path)
    verified_work(root, returned("implement", commit_work(root, "one")))
    call(root, "next")
    reviewer_ends(monkeypatch, REVIEW_REQUEST, final)
    leave_verdict(root, verdict_text)
    return root


# --- The request ------------------------------------------------------------------------------


def test_a_verified_step_marked_for_review_gets_a_review_request_naming_the_diff_of_its_work(
    tmp_path,
):
    root = build(tmp_path)
    sha = commit_work(root, "one")
    verified_work(root, returned("implement", sha))

    reply = call(root, "next")

    prompt = (root / ".ai-work" / SLUG / f"PROMPT_{REVIEW_REQUEST}.md").read_text(encoding="utf-8")
    assert (reply.exit, reply.doc["request"]["kind"]) == (0, "review")
    assert f"git diff {sha}^..{sha} -- {SOURCE}" in prompt


def test_the_second_review_reads_from_the_first_commit_to_the_revisions_commit(tmp_path):
    root = build(tmp_path)
    first, last = commit_work(root, "one"), commit_work(root, "two")
    leave_verdict(root, "verdict: revise\n")
    review = returned("review", None, round_=1)
    verified_work(root, returned("implement", first), review)
    verified_work(root, returned("revise", last, round_=1))

    reply = call(root, "next")

    prompt = (root / ".ai-work" / SLUG / f"PROMPT_{SECOND_REVIEW_REQUEST}.md").read_text("utf-8")
    assert reply.doc["request"]["id"] == SECOND_REVIEW_REQUEST
    assert f"git diff {first}^..{last} -- {SOURCE}" in prompt


def test_a_review_due_over_work_that_holds_no_commit_stops_for_a_human_and_writes_nothing(tmp_path):
    root = build(tmp_path)
    verified_work(root, returned("implement", None))

    reply = call(root, "next")

    assert (reply.exit, reply.doc["outcome"], reply.doc["stop"]["cause"]) == (
        2,
        "needs-human",
        "loop-state-defect",
    )
    assert (attempts_lines(root), list((root / ".ai-work" / SLUG).glob("PROMPT_*"))) == ([], [])


def test_status_reports_the_same_stop_for_a_review_with_nothing_to_read(tmp_path):
    root = build(tmp_path)
    verified_work(root, returned("implement", None))

    reply = call(root, "status", "--json")

    assert (reply.exit, reply.doc["stop"]["cause"]) == (2, "loop-state-defect")


def test_an_outstanding_review_request_is_reissued_and_never_a_defect(tmp_path):
    root = build(tmp_path)
    verified_work(root, returned("implement", commit_work(root, "one")))

    asked, again = call(root, "next"), call(root, "next")

    assert (asked.doc["request"]["reissued"], again.doc["request"]["reissued"]) == (False, True)
    assert again.doc["request"]["id"] == REVIEW_REQUEST
    assert attempts_lines(root) == [f"- Attempts: {STEP}1 count=1 request={REVIEW_REQUEST}"]


# --- The return -------------------------------------------------------------------------------


def test_a_review_return_appends_one_record_that_copies_the_work_reviewed(tmp_path, monkeypatch):
    root = verified_and_reviewed(tmp_path, monkeypatch, "verdict: accept\n")

    reply = record_return(root, REVIEW_REQUEST)

    reviewed, written = ledger(root).records
    assert (written.request, written.attempt, written.commit) == (REVIEW_REQUEST, 1, None)
    assert (written.verdict, written.decided_by, written.test_result) == (
        reviewed.verdict,
        reviewed.decided_by,
        reviewed.test_result,
    )
    assert (written.stop_reason, written.turns) == ("completed", REVIEWER_REQUESTS)
    assert (written.max_turns, written.agent_id) == (
        rec.declared_max_turns("praxion:verifier"),
        "reviewer-1",
    )
    assert (reply.doc["recorded"]["request"], ledger(root).findings) == (REVIEW_REQUEST, ())


def test_an_accepted_review_is_recorded_as_accept_and_the_loop_moves_to_the_next_step(
    tmp_path, monkeypatch
):
    root = verified_and_reviewed(tmp_path, monkeypatch, "verdict: [PARTIAL]\nverdict: accept\n")

    reply = record_return(root, REVIEW_REQUEST)

    assert reply.doc["recorded"]["review_verdict"] == ACCEPT
    assert (reply.exit, reply.doc["request"]["id"]) == (0, "s2-a1-implement")


def test_a_revise_verdict_is_recorded_as_revise_and_the_next_request_is_the_revision(
    tmp_path, monkeypatch
):
    root = verified_and_reviewed(tmp_path, monkeypatch, "verdict: revise\n- fix the thing\n")

    reply = record_return(root, REVIEW_REQUEST)

    assert reply.doc["recorded"]["review_verdict"] == REVISE
    assert (reply.doc["request"]["kind"], reply.doc["request"]["step"]) == ("revise", "1")


@pytest.mark.parametrize(
    ("text", "word"),
    [("verdict: [PARTIAL]\n- half a finding\n", UNFINISHED), ("- findings, no verdict\n", None)],
    ids=["partial", "no-verdict-line"],
)
def test_a_review_without_a_finished_verdict_is_never_an_accept(tmp_path, monkeypatch, text, word):
    root = verified_and_reviewed(tmp_path, monkeypatch, text)

    reply = record_return(root, REVIEW_REQUEST)

    assert reply.doc["recorded"]["review_verdict"] == word
    assert (reply.exit, reply.doc["stop"]["cause"]) == (2, "review-unfinished")


def test_a_reviewer_that_ends_on_partial_leaves_a_partial_stop_reason(tmp_path, monkeypatch):
    root = verified_and_reviewed(tmp_path, monkeypatch, "verdict: [PARTIAL]\n", "[PARTIAL]")

    reply = record_return(root, REVIEW_REQUEST, marker="partial")

    assert (reply.doc["recorded"]["stop_reason"], ledger(root).records[-1].stop_reason) == (
        "partial",
        "partial",
    )


def test_a_review_return_runs_no_gate_and_makes_no_commit(tmp_path, monkeypatch):
    root = verified_and_reviewed(tmp_path, monkeypatch, "verdict: accept\n")
    head = git(root, "rev-parse", "HEAD")

    reply = record_return(root, REVIEW_REQUEST)

    assert git(root, "rev-parse", "HEAD") == head
    assert not (root / ".ai-work" / SLUG / "TEST_RESULTS.md").exists()
    assert reply.doc["recorded"]["commit"] is None


def test_recording_the_same_review_twice_appends_nothing_the_second_time(tmp_path, monkeypatch):
    root = verified_and_reviewed(tmp_path, monkeypatch, "verdict: revise\n")
    record_return(root, REVIEW_REQUEST)
    before = ledger(root).records

    again = record_return(root, REVIEW_REQUEST)

    assert (again.doc["recorded"]["replayed"], ledger(root).records) == (True, before)


def test_a_review_request_that_reviews_no_verified_work_is_refused_and_records_nothing(tmp_path):
    waiting = f"  - Attempts: {STEP}1 count=1 request={REVIEW_REQUEST}\n"
    root = build(tmp_path, wip=WIP + waiting)

    reply = record_return(root, REVIEW_REQUEST)

    assert (reply.exit, reply.doc["error"]["code"]) == (4, "request-not-pending")
    assert "reviews no verified work" in reply.doc["error"]["message"]
    assert ledger(root).records == ()
