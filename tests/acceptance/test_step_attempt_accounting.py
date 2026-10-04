"""Each step's attempt count is on disk, and a step stops after two fresh attempts.

`WIP.md` records how many fresh attempts a step has used; the reconciler shows
that count beside the step's verdict, and shows none when `WIP.md` records none.
Once a step has used its two fresh attempts without verified completion, it is
marked `[BLOCKED]` with a replan request, and the reconciler routes it to a human
-- the exit status `/resume-pipeline` reserves for a human decision -- never to an
automatic resume.
"""

from __future__ import annotations

from tests.acceptance.drivers.step_checks import (
    AUTO_RESUME_VERDICTS,
    Check,
    StepSetup,
    build_task,
    reconcile,
)

COMMAND = "uv run pytest tests/test_widget.py -q --tb=short -rf"
UNMET_CHECK = Check(command=COMMAND, passed=6)  # the recorded run shows only 4 passing
NEEDS_A_HUMAN = 2
RECOVERY_NEEDED = 1
REPLAN_REQUEST = (
    "replan: the first attempt stopped at its turn cap with the reader half written; the "
    "second returned [COMPLETE] with two of six tests missing"
)


def _step(**overrides) -> StepSetup:
    return StepSetup(number="1", title="Write the widget", **overrides)


def test_reconciler_shows_the_attempt_count_wip_records_for_a_step(tmp_path):
    task = build_task(tmp_path, _step(attempt=2))

    judged = reconcile(task).step("1")

    assert judged.attempt == 2


def test_step_with_no_recorded_attempt_count_shows_none_rather_than_a_guess(tmp_path):
    task = build_task(tmp_path, _step())

    judged = reconcile(task).step("1")

    assert judged.attempt is None


def test_step_blocked_for_replan_after_two_attempts_goes_to_a_human_not_a_resume(tmp_path):
    task = build_task(
        tmp_path,
        _step(
            claimed_done=False,
            check=UNMET_CHECK,
            attempt=2,
            blocked_for_replan=REPLAN_REQUEST,
        ),
    )

    reconciliation = reconcile(task)
    judged = reconciliation.step("1")

    assert reconciliation.exit_code == NEEDS_A_HUMAN, judged.evidence
    assert judged.verdict not in AUTO_RESUME_VERDICTS | {"verified-complete"}, (
        f"a step past its attempt cap must not be offered for an automatic resume: "
        f"{judged.verdict!r}"
    )


def test_claimed_step_failing_its_check_on_the_second_attempt_goes_to_a_human(tmp_path):
    task = build_task(tmp_path, _step(claimed_done=True, check=UNMET_CHECK, attempt=2))

    reconciliation = reconcile(task)
    judged = reconciliation.step("1")

    assert judged.verdict != "verified-complete", judged.evidence
    assert reconciliation.exit_code == NEEDS_A_HUMAN, (
        f"the second fresh attempt is spent, so the step needs a human: {judged.evidence!r}"
    )


def test_claimed_step_failing_its_check_on_the_first_attempt_stays_resumable(tmp_path):
    task = build_task(tmp_path, _step(claimed_done=True, check=UNMET_CHECK, attempt=1))

    reconciliation = reconcile(task)
    judged = reconciliation.step("1")

    assert judged.verdict == "mismatch", judged.evidence
    assert reconciliation.exit_code == RECOVERY_NEEDED
