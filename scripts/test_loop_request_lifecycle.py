"""The outstanding request's lifecycle: read once against the plan, withdrawn plan-independently.

The reading is a pure function of the loop's inputs, so its arms are a table of attempts lines;
the withdrawal and the refusals go through the command, which owns the files they write.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_cli as cli  # noqa: E402
import step_loop  # noqa: E402
from _loop_fields import Attempt, OutstandingAttempt  # noqa: E402
from _loop_state_testkit import FILES, IMPL, PLAIN_STEP, SECOND, STEP, one, read, rec  # noqa: E402
from _step_loop_action import (  # noqa: E402
    Current,
    Malformed,
    Miscounted,
    NoneOut,
    Several,
    Superseded,
    next_action,
    read_outstanding,
)
from _step_loop_files import with_checklist_line  # noqa: E402
from _step_loop_render import RequestKey  # noqa: E402
from _step_loop_state import LoopInputs, series_states  # noqa: E402
from iteration_ledger import IterationRecord, append_record  # noqa: E402

SLUG = "demo"
REVISED = one(IMPL, FILES, "Revised wording.")
OLD_SERIES = rec(PLAIN_STEP, 1)  # attempt 1 under the block before its revision
CHECK = "**Check**: `python3 -m pytest -q` expects pass>=1 fail=0"
WIP = f"# WIP\n\n## Progress\n\n- [ ] {STEP}2: Do it\n"


@pytest.fixture(autouse=True)
def no_agent_transcripts(tmp_path, monkeypatch):
    """A withdrawal looks for a transcript naming the request: none exists here."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "config"))


def out(count, request, step="1"):
    return {STEP + step: OutstandingAttempt(count, request)}


@pytest.mark.parametrize(
    ("steps", "attempts", "records", "reading"),
    [
        pytest.param([PLAIN_STEP], {}, (), NoneOut(), id="none-out"),
        pytest.param([PLAIN_STEP], {STEP + "1": Attempt(1)}, (), NoneOut(), id="recorded-count"),
        pytest.param(
            [PLAIN_STEP, SECOND],
            {**out(1, "s1-a1-implement"), **out(1, "s2-a1-implement", "2")},
            (),
            Several((("1", "s1-a1-implement"), ("2", "s2-a1-implement"))),
            id="several",
        ),
        pytest.param([PLAIN_STEP], out(1, "review"), (), Malformed("1", "review"), id="no-id"),
        pytest.param(
            [PLAIN_STEP], out(1, "s2-a1-implement"), (), Malformed("1", "s2-a1-implement"),
            id="another-step",
        ),
        pytest.param(
            [PLAIN_STEP], out(1, "s1-p2-a1-implement"), (), Malformed("1", "s1-p2-a1-implement"),
            id="series-not-reached",
        ),
        pytest.param(
            [PLAIN_STEP], out(2, "s1-a1-implement"), (), Miscounted("1", "s1-a1-implement", 2),
            id="miscounted",
        ),
        pytest.param(
            [PLAIN_STEP], out(1, "s1-a1-implement"), (),
            Current("1", RequestKey("1", 1, "implement", 1)), id="current",
        ),
        pytest.param(
            [PLAIN_STEP, SECOND], out(1, "s2-a1-implement", "2"), (),
            Superseded(
                "2", RequestKey("2", 1, "implement", 1), f"the plan now issues {STEP}1 first", True
            ),
            id="another-step-first",
        ),
        pytest.param(
            [REVISED], out(2, "s1-a2-implement"), (OLD_SERIES,),
            Superseded(
                "1", RequestKey("1", 2, "implement", 1),
                f"the block of {STEP}1 was revised after the request's series", False,
            ),
            id="block-revised",
        ),
        pytest.param(
            [SECOND], out(1, "s1-a1-implement"), (),
            Superseded(
                "1", RequestKey("1", 1, "implement", 1), f"{STEP}1 is no longer in the plan", False
            ),
            id="left-the-plan",
        ),
    ],
)  # fmt: skip
def test_an_attempts_line_reads_as_one_arm_of_the_outstanding_request(
    steps, attempts, records, reading
):
    assert read_outstanding(read(steps, attempts=attempts, records=records)) == reading


@pytest.mark.parametrize(
    ("attempts", "cause"),
    [
        pytest.param(out(2, "s1-a1-implement"), "attempts-disagree", id="miscounted"),
        pytest.param(out(1, "s2-a1-implement", "2"), "request-outstanding", id="superseded"),
    ],
)
def test_a_request_the_plan_no_longer_issues_stops_and_issues_nothing(attempts, cause):
    action = next_action(read([PLAIN_STEP, SECOND], attempts=attempts))

    assert action.cause == cause


def test_a_miscounted_line_is_named_with_its_request_and_its_count():
    action = next_action(read([PLAIN_STEP], attempts=out(2, "s1-a1-implement")))

    assert (action.step, action.evidence) == (
        "1",
        f"the Attempts: line of {STEP}1 names s1-a1-implement, whose attempt is not the line's"
        " own count=2",
    )


# --- `status`'s pending request ------------------------------------------------------------


@pytest.mark.parametrize(
    ("steps", "attempts", "pending"),
    [
        pytest.param([PLAIN_STEP], {}, None, id="none-out"),
        pytest.param([PLAIN_STEP], out(1, "s1-a1-implement"), "s1-a1-implement", id="current"),
        pytest.param(
            [PLAIN_STEP, SECOND], out(1, "s2-a1-implement", "2"), "s2-a1-implement",
            id="superseded",
        ),
        pytest.param([PLAIN_STEP], out(2, "s1-a1-implement"), None, id="miscounted"),
    ],
)  # fmt: skip
def test_status_names_the_request_the_reading_holds_out(steps, attempts, pending):
    inputs = read(steps, attempts=attempts)
    status = cli.status_object(
        SLUG, inputs, series_states(inputs), next_action(inputs), None, "step_loop.py"
    )

    assert status["pending_request"] == pending


def test_status_names_a_reissued_request_the_base_driver_wrote_as_it_did():
    inputs = LoopInputs.read([PLAIN_STEP], out(1, "s1-a1-implement"), (), ())
    action = next_action(inputs)
    status = cli.status_object(SLUG, inputs, series_states(inputs), action, None, "step_loop.py")

    assert (action.reissued, status["pending_request"]) == (True, action.key.id)


# --- The withdrawal, through the command ----------------------------------------------------


def plan(*numbers):
    blocks = "".join(
        f"### {STEP}{n}: Do it\n\n{IMPL}\n**Files**: `src/{n}.py`\n{CHECK}\n\n" for n in numbers
    )
    return "# Plan\n\n## Steps\n\n" + blocks


def build(tmp_path, plan_text, wip, ledger=()):
    task = tmp_path / ".ai-work" / SLUG
    task.mkdir(parents=True)
    (task / "IMPLEMENTATION_PLAN.md").write_text(plan_text, encoding="utf-8")
    (task / "WIP.md").write_text(wip, encoding="utf-8")
    for record in ledger:
        append_record(task, record)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty"]
        + ["-m", "init"],
        cwd=tmp_path,
        check=True,
    )
    return tmp_path


def call(root, verb, *more):
    location = ("--repo-root", str(root), "--base-ref", "HEAD")
    return step_loop.execute([verb, SLUG, *more, *location])


def with_line(line):
    return WIP + f"  - Attempts: {STEP}2 {line}\n"


def withdraw(root, request):
    return call(root, "record", "--request", request, "--not-started", "the call failed")


def wip_text(root):
    return (root / ".ai-work" / SLUG / "WIP.md").read_text(encoding="utf-8")


def test_a_current_request_is_withdrawn_and_nothing_is_issued(tmp_path):
    root = build(tmp_path, plan(2), with_line("count=1 request=s2-a1-implement"))

    reply = withdraw(root, "s2-a1-implement")

    assert (reply.exit, reply.doc["outcome"], "request" in reply.doc) == (0, "withdrawn", False)
    assert "request=" not in wip_text(root)


def test_a_request_superseded_by_a_step_put_ahead_is_withdrawn(tmp_path):
    root = build(tmp_path, plan(1, 2), with_line("count=1 request=s2-a1-implement"))

    reply = withdraw(root, "s2-a1-implement")

    assert reply.doc["outcome"] == "withdrawn"
    assert "request=" not in wip_text(root)


def test_a_request_whose_block_was_revised_is_withdrawn_to_its_earlier_count(tmp_path):
    first = IterationRecord(
        step=f"{STEP}2", attempt=1, agent_id="a", verdict="mismatch", decided_by="check",
        test_result="Result: none", commit=None, stop_reason="completed",
        request="s2-a1-implement", step_digest="0" * 12,
    )  # fmt: skip
    root = build(tmp_path, plan(2), with_line("count=2 request=s2-a2-implement"), [first])

    reply = withdraw(root, "s2-a2-implement")

    assert reply.doc["outcome"] == "withdrawn"
    assert f"- Attempts: {STEP}2 count=1\n" in wip_text(root)


def test_a_member_of_several_naming_its_own_step_is_withdrawn(tmp_path):
    wip = (
        f"# WIP\n\n## Progress\n\n- [ ] {STEP}1: Do it\n  - Attempts: {STEP}1 count=1"
        f" request=s1-a1-implement\n- [ ] {STEP}2: Do it\n  - Attempts: {STEP}2 count=1"
        " request=s2-a1-implement\n"
    )
    root = build(tmp_path, plan(1, 2), wip)

    reply = withdraw(root, "s2-a1-implement")
    after = call(root, "next")

    assert reply.doc["outcome"] == "withdrawn"
    assert after.doc["request"]["id"] == "s1-a1-implement"


@pytest.mark.parametrize(
    ("line", "named", "said"),
    [
        pytest.param("count=2 request=s2-a1-implement", "s2-a1-implement", "count=2", id="miscounted"),
        pytest.param("count=1 request=s2-p3-a1-implement", "s2-p3-a1-implement", "count=1", id="malformed"),
    ],
)  # fmt: skip
def test_a_line_that_disagrees_with_itself_refuses_the_withdrawal_naming_step_id_and_count(
    tmp_path, line, named, said
):
    root = build(tmp_path, plan(2), with_line(line))
    before = wip_text(root)

    reply = withdraw(root, named)

    message = reply.doc["error"]["message"]
    assert (reply.exit, reply.doc["error"]["code"]) == (4, "request-not-pending")
    assert (f"{STEP}2" in message, named in message, said in message) == (True, True, True), message
    assert wip_text(root) == before


def several(second_line):
    return (
        f"# WIP\n\n## Progress\n\n- [ ] {STEP}1: Do it\n  - Attempts: {STEP}1 count=1"
        f" request=s1-a1-implement\n- [ ] {STEP}2: Do it\n  - Attempts: {STEP}2 {second_line}\n"
    )


def test_a_miscounted_member_of_several_refuses_the_withdrawal_as_a_lone_line_does(tmp_path):
    root = build(tmp_path, plan(1, 2), several("count=2 request=s2-a1-implement"))
    before = wip_text(root)

    reply = withdraw(root, "s2-a1-implement")

    message = reply.doc["error"]["message"]
    assert (reply.exit, reply.doc["error"]["code"]) == (4, "request-not-pending")
    assert (f"{STEP}2" in message, "count=2" in message) == (True, True), message
    assert wip_text(root) == before


def test_a_return_met_by_several_outstanding_requests_is_refused_naming_each_of_them(tmp_path):
    root = build(tmp_path, plan(1, 2), several("count=1 request=s2-a1-implement"))
    before = wip_text(root)

    reply = call(
        root, "record", "--request", "s2-a1-implement", "--agent-id", "a", "--marker", "complete"
    )

    message = reply.doc["error"]["message"]
    assert reply.doc["error"]["code"] == "request-not-pending"
    assert ("s1-a1-implement" in message, "s2-a1-implement" in message) == (True, True), message
    assert ("run status" in message, "remove request=" in message) == (False, True), message
    assert wip_text(root) == before


def test_an_unknown_request_while_several_are_outstanding_is_refused_naming_each_of_them(
    tmp_path,
):
    root = build(tmp_path, plan(1, 2), several("count=1 request=s2-a1-implement"))

    reply = withdraw(root, "s9-a1-implement")

    message = reply.doc["error"]["message"]
    named = re.findall(r"(?<![\w-])s\d+-a\d+-implement(?![\w-])", message)
    assert reply.doc["error"]["code"] == "request-not-pending"
    assert sorted(set(named)) == ["s1-a1-implement", "s2-a1-implement", "s9-a1-implement"], message


def test_the_withdrawn_envelope_prints_the_next_call_and_exits_zero():
    frame = cli.Frame(SLUG, cli.Iterations(0, 2), (), {"stop_reason": "not-started"})

    doc = cli.withdrawn_envelope(frame, "step_loop.py")

    assert (doc["then"], cli.exit_code(doc)) == (f"step_loop.py next {SLUG}", 0)
    assert json.loads(json.dumps(doc))["recorded"] == {"stop_reason": "not-started"}


def test_a_step_put_ahead_gets_its_checklist_line_in_front_of_the_next_one():
    steps = [PLAIN_STEP, SECOND]

    listed = with_checklist_line(WIP, PLAIN_STEP, steps)

    assert listed == f"# WIP\n\n## Progress\n\n- [ ] {STEP}1: Do it\n- [ ] {STEP}2: Do it\n"


@pytest.mark.parametrize(
    ("wip", "steps"),
    [
        pytest.param(f"# WIP\n\n- [ ] {STEP}1: Do it\n- [ ] {STEP}2: Do it\n", [PLAIN_STEP, SECOND], id="listed"),
        pytest.param(f"# WIP\n\n- [ ] {STEP}3: Other\n", [PLAIN_STEP, SECOND], id="no-later-line"),
    ],
)  # fmt: skip
def test_a_step_already_listed_or_with_no_later_line_leaves_the_text_as_it_was(wip, steps):
    assert with_checklist_line(wip, PLAIN_STEP, steps) == wip


def test_a_checklist_line_shown_inside_a_code_fence_lists_no_step():
    fenced = f"# WIP\n\n```\n- [ ] {STEP}1: Do it\n```\n\n- [ ] {STEP}2: Do it\n"

    listed = with_checklist_line(fenced, PLAIN_STEP, [PLAIN_STEP, SECOND])

    assert listed == fenced.replace(f"\n- [ ] {STEP}2", f"\n- [ ] {STEP}1: Do it\n- [ ] {STEP}2")
