"""A plan step's declared completion check decides its verdict before any other evidence.

A step may declare a `Check:` -- a command, the counts its recorded `Result:`
line must show and, where acceptance tests fall due, the expected `pending=`
count. The reconciler judges such a step by its check first: a met check
completes it unless an existing blocker applies; a check that is not met, or
whose outcome cannot be established from a result recorded for that step,
keeps it from `verified-complete`, whatever `WIP.md` claims. A step without a
check keeps the existing evidence (declared files changed plus green tests).
Every verdict names the criterion that decided it, and reconciling stays a
read-only question that is safe to repeat.

Unless a scenario says otherwise, each step's files changed after the base
commit, `WIP.md` ticks it done, and its recorded run reads green.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.acceptance.drivers.step_checks import (
    UNREADABLE_CHECK,
    Check,
    Criterion,
    OutcomeSource,
    StepSetup,
    build_task,
    readable_report,
    reconcile,
    snapshot_working_tree,
)

COMMAND = "uv run pytest tests/test_widget.py -q --tb=short -rf"
CHECK_FOUR_GREEN = Check(command=COMMAND, passed=4)
CHECK_FOUR_GREEN_NOTHING_PENDING = Check(command=COMMAND, passed=4, pending=0)
SENSOR_MISSING_TAG = "mutation: on"


def _step(**overrides) -> StepSetup:
    return StepSetup(number="1", title="Write the widget", **overrides)


# -- A met check completes the step ------------------------------------------------


def test_step_whose_declared_check_is_met_is_verified_complete_by_its_check(tmp_path):
    task = build_task(
        tmp_path, _step(check=CHECK_FOUR_GREEN, result="Result: pass=4 fail=0 skip=0")
    )

    judged = reconcile(task).step("1")

    assert judged.verdict == "verified-complete", judged.evidence
    assert judged.criterion is Criterion.CHECK


def test_met_check_read_from_the_recorded_result_says_so(tmp_path):
    task = build_task(tmp_path, _step(check=CHECK_FOUR_GREEN))

    judged = reconcile(task).step("1")

    assert judged.outcome_source is OutcomeSource.RECORDED, (
        "a reconcile not asked to run commands can only have read the recorded result"
    )


def test_met_check_does_not_lift_an_existing_completion_blocker(tmp_path):
    task = build_task(tmp_path, _step(check=CHECK_FOUR_GREEN, tag=SENSOR_MISSING_TAG))

    judged = reconcile(task).step("1")

    assert judged.verdict != "verified-complete", (
        "a step tagged for mutation testing with no mutation reading stays blocked even when "
        f"its check is met: {judged.evidence!r}"
    )


# -- An unmet check never yields to the agent's own claim --------------------------


_RESULT_KEY = re.compile(r"\b(?:pass|fail|skip|pending)=")
_WINDOW = 60


def _counts_named_after(evidence: str, key: str) -> set[str]:
    """Every count written after an occurrence of `key`, up to the next `Result:` key."""
    counts: set[str] = set()
    for match in re.finditer(re.escape(key), evidence):
        window = evidence[match.end() : match.end() + _WINDOW]
        next_key = _RESULT_KEY.search(window)
        counts |= set(re.findall(r"\d+", window[: next_key.start()] if next_key else window))
    return counts


def _unnamed(evidence: str, unmet: tuple[tuple[str, int, int], ...]) -> list[str]:
    """The unmet expectations the evidence does not name by key, expected and observed count."""
    return [
        f"{key} expected {expected} observed {observed}"
        for key, expected, observed in unmet
        if not {str(expected), str(observed)} <= _counts_named_after(evidence, key)
    ]


@pytest.mark.parametrize(
    ("check", "recorded", "unmet"),
    [
        (
            CHECK_FOUR_GREEN_NOTHING_PENDING,
            "Result: pass=4 fail=0 skip=0 pending=3",
            (("pending=", 0, 3),),
        ),
        (
            Check(command=COMMAND, passed=6),
            "Result: pass=4 fail=0 skip=0",
            (("pass=", 6, 4),),
        ),
        (CHECK_FOUR_GREEN, "Result: pass=4 fail=2 skip=0", (("fail=", 0, 2),)),
        (CHECK_FOUR_GREEN, "Result: pass=4 fail=0 skip=1", (("skip=", 0, 1),)),
        (
            Check(command=COMMAND, passed=6, pending=0),
            "Result: pass=4 fail=0 skip=0 pending=3",
            (("pass=", 6, 4), ("pending=", 0, 3)),
        ),
    ],
    ids=[
        "acceptance-tests-still-pending",
        "fewer-passing-tests",
        "failing-tests",
        "a-skipped-test",
        "two-expectations-unmet",
    ],
)
def test_claimed_step_whose_check_is_not_met_is_a_mismatch_naming_each_unmet_count(
    tmp_path, check, recorded, unmet
):
    task = build_task(tmp_path, _step(check=check, result=recorded, claimed_done=True))

    judged = reconcile(task).step("1")

    assert judged.verdict == "mismatch", judged.evidence
    assert _unnamed(judged.evidence, unmet) == [], (
        "the mismatch should name each unmet expectation by its Result: key with the expected "
        f"and observed counts: {judged.evidence!r}"
    )


def test_check_with_no_result_recorded_for_its_step_is_never_verified_complete(tmp_path):
    task = build_task(tmp_path, _step(check=CHECK_FOUR_GREEN, result=None))

    judged = reconcile(task).step("1")

    assert judged.verdict != "verified-complete", judged.evidence


def test_check_is_never_met_by_a_result_recorded_for_another_step(tmp_path):
    earlier = StepSetup(number="1", title="Write the widget")
    checked = StepSetup(number="2", title="Read the widget", check=CHECK_FOUR_GREEN, result=None)
    task = build_task(tmp_path, earlier, checked)

    judged = reconcile(task).step("2")

    assert judged.verdict != "verified-complete", (
        "the only recorded run belongs to the earlier step and must not establish the later "
        f"step's check: {judged.evidence!r}"
    )


def test_unreadable_check_degrades_the_step_to_unknown_naming_the_check(tmp_path):
    task = build_task(tmp_path, _step(check=UNREADABLE_CHECK))

    reconciliation = reconcile(task)
    judged = reconciliation.step("1")

    assert judged.verdict == "unknown", judged.evidence
    assert reconciliation.exit_code == 2, "an unknown step is surfaced to a human"
    assert "check" in judged.evidence.lower(), (
        f"the finding should name the step's unreadable check: {judged.evidence!r}"
    )


# -- Steps without a check keep the existing evidence ------------------------------


def test_step_without_a_check_beside_a_checked_step_is_decided_by_the_existing_evidence(
    tmp_path,
):
    unchecked = StepSetup(number="1", title="Write the widget")
    checked = StepSetup(number="2", title="Read the widget", check=CHECK_FOUR_GREEN)
    task = build_task(tmp_path, unchecked, checked)

    reconciliation = reconcile(task)

    assert reconciliation.step("1").verdict == "verified-complete"
    assert reconciliation.step("1").criterion is Criterion.FALLBACK
    assert reconciliation.step("2").criterion is Criterion.CHECK


def test_not_started_step_without_a_check_names_no_deciding_evidence(tmp_path):
    task = build_task(tmp_path, _step(files_changed=False, claimed_done=False, result=None))

    judged = reconcile(task).step("1")

    assert judged.criterion is Criterion.NONE


def test_readable_output_names_the_criterion_that_decided_each_step(tmp_path):
    unchecked = StepSetup(number="1", title="Write the widget")
    checked = StepSetup(number="2", title="Read the widget", check=CHECK_FOUR_GREEN)
    task = build_task(tmp_path, unchecked, checked)
    reconciliation = reconcile(task)

    report = readable_report(task)

    assert reconciliation.step("1").criterion_label in report, report
    assert reconciliation.step("2").criterion_label in report, report


# -- Reconciling stays a read-only question ------------------------------------------


def _marker_check(marker: Path) -> Check:
    return Check(command=f"touch {marker}", passed=4)


@pytest.mark.parametrize("declares_check", [True, False], ids=["with-check", "without-check"])
def test_reconciling_twice_gives_the_same_verdicts_and_changes_no_file(tmp_path, declares_check):
    marker = tmp_path / "declared-command-ran.marker"
    check = _marker_check(marker) if declares_check else None
    task = build_task(tmp_path, _step(check=check))
    before = snapshot_working_tree(task.root)

    first = reconcile(task)
    second = reconcile(task)

    assert first == second
    assert snapshot_working_tree(task.root) == before


def test_reconciling_without_being_asked_to_run_commands_runs_no_declared_command(tmp_path):
    marker = tmp_path / "declared-command-ran.marker"
    task = build_task(tmp_path, _step(check=_marker_check(marker)))

    reconcile(task)
    readable_report(task)

    assert not marker.exists(), "the reconciler ran a step's declared command unasked"
