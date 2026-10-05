"""The step loop drives a whole plan, end to end, with a substitute for the Agent tool.

Relaying only `next`, the substitute's work, and `record`, the orchestrator sees a
dependent two-step plan through to completion: one commit per verified step holding
only that step's files, one ledger record per return, and a reconciler that agrees.
A failed attempt is retried and leaves a ledger record with no commit; an exhausted
step pauses the loop with verified work kept, and a plan revision resumes it.
"""

from __future__ import annotations

from pathlib import Path

from tests.acceptance.drivers.step_loop import (
    Step,
    Work,
    build_loop,
    commits_after,
    files_in_commit,
    head,
    ledger_records,
    reconciler_verdict,
    revise_step,
    step_id_of,
)
from tests.e2e.drivers.step_loop_journey import relay_until_stopped

PASSES = Work()
FAILS = Work(passes=False, final_marker="complete")


def test_a_dependent_two_step_plan_runs_to_completion_through_the_relay(tmp_path):
    task = build_loop(tmp_path, Step("1"), Step("2", depends_on=("1",)))
    base_head = head(task)

    journey = relay_until_stopped(task, {"1": [PASSES], "2": [PASSES]})

    assert journey.final.exit_code == 0
    assert journey.final.outcome == "complete"
    commits = list(reversed(commits_after(task, base_head)))
    assert [files_in_commit(task, sha) for sha in commits] == [
        set(task.step("1").files),
        set(task.step("2").files),
    ]
    assert reconciler_verdict(task, "1")["verdict"] == "verified-complete"
    assert reconciler_verdict(task, "2")["verdict"] == "verified-complete"


def test_the_ledger_holds_one_record_per_return_with_each_verified_commit(tmp_path):
    task = build_loop(tmp_path, Step("1"), Step("2", depends_on=("1",)))

    journey = relay_until_stopped(task, {"1": [FAILS, PASSES], "2": [PASSES]})

    records, findings = ledger_records(task)
    assert findings == []
    assert [step_id_of(r["step"]) for r in records] == ["1", "1", "2"]
    assert [r["attempt"] for r in records] == [1, 2, 1]
    assert records[0]["commit"] is None
    assert [r["commit"][:7] for r in records[1:]] == [
        e.recorded["commit"][:7] for e in journey.returns[1:]
    ]


def test_an_exhausted_step_pauses_the_loop_keeping_verified_work_and_a_revision_resumes_it(
    tmp_path,
):
    task = build_loop(tmp_path, Step("1"), Step("2", depends_on=("1",)))
    base_head = head(task)
    paused = relay_until_stopped(task, {"1": [PASSES], "2": [FAILS, FAILS]})
    revise_step(task, "2", "Write `src/step_2.py` returning the step id, in smaller pieces.")

    resumed = relay_until_stopped(task, {"2": [PASSES]})

    assert paused.final.exit_code == 2
    assert step_id_of(paused.final.stop["step"]) == "2"
    assert Path(paused.final.stop["handoff"]).is_file()
    assert resumed.final.outcome == "complete"
    assert len(commits_after(task, base_head)) == 2
