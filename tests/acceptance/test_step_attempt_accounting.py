"""Each step's attempt count is on disk, and a step stops after two fresh attempts.

`WIP.md` records how many fresh attempts a step has used; the reconciler shows
that count beside the step's verdict, and shows none when `WIP.md` records none.
Once a step has used its two fresh attempts without verified completion, the
reconciler gives it a verdict of its own, distinct from `mismatch` and `blocked`,
and routes it to a human -- the exit status `/resume-pipeline` reserves for a human
decision -- never to an automatic resume, whether or not `WIP.md` ticks it or
already marks it `[BLOCKED]` with a replan request. Below the cap, a claimed step
failing its check stays a resumable `mismatch`.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.step_checks import (
    AUTO_RESUME_VERDICTS,
    Check,
    StepSetup,
    build_task,
    cap_exhausted_verdict,
    reconcile,
)

COMMAND = "uv run pytest tests/test_widget.py -q --tb=short -rf"
UNMET_CHECK = Check(command=COMMAND, passed=6)  # the recorded run shows only 4 passing
NEEDS_A_HUMAN = 2
RECOVERY_NEEDED = 1
NOT_THE_CAP_VERDICT = AUTO_RESUME_VERDICTS | {"mismatch", "blocked", "verified-complete"}
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


@pytest.mark.parametrize(
    ("claimed_done", "blocked_for_replan"),
    [
        (True, None),
        (False, None),
        (False, REPLAN_REQUEST),
        (True, REPLAN_REQUEST),
    ],
    ids=["ticked-not-yet-marked", "unticked-not-yet-marked", "marked-blocked", "ticked-and-marked"],
)
def test_step_past_its_two_fresh_attempts_gets_the_cap_verdict_and_goes_to_a_human(
    tmp_path, claimed_done, blocked_for_replan
):
    task = build_task(
        tmp_path,
        _step(
            claimed_done=claimed_done,
            check=UNMET_CHECK,
            attempt=2,
            blocked_for_replan=blocked_for_replan,
        ),
    )

    reconciliation = reconcile(task)
    judged = reconciliation.step("1")

    assert judged.verdict == cap_exhausted_verdict(), judged.evidence
    assert judged.verdict not in NOT_THE_CAP_VERDICT, (
        f"the cap verdict must differ from mismatch, blocked and every auto-resume verdict: "
        f"{judged.verdict!r}"
    )
    assert reconciliation.exit_code == NEEDS_A_HUMAN, judged.evidence


def test_claimed_step_failing_its_check_on_the_first_attempt_stays_resumable(tmp_path):
    task = build_task(tmp_path, _step(claimed_done=True, check=UNMET_CHECK, attempt=1))

    reconciliation = reconcile(task)
    judged = reconciliation.step("1")

    assert judged.verdict == "mismatch", judged.evidence
    assert reconciliation.exit_code == RECOVERY_NEEDED
