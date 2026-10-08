"""Tests for the verdict policy's reading of a goal step (``scripts/_step_verdict.py``).

A goal step carries its ``Iterations:`` budget in its evidence. It is `attempts-exhausted`
exactly when its ``Attempts:`` line carries the replan request the step-loop driver writes when
the loop stalls, never by its count; an ordinary step (no budget) keeps the count rule and its
evidence text byte for byte; an unreadable budget is surfaced to a person as `unknown`.
Every case passes evidence in and reads a verdict dict out: nothing is read or run.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_verdict as verdicts  # noqa: E402
from _loop_fields import Attempt, OutstandingAttempt, UnreadableIterations  # noqa: E402

STEP_LABEL = "Step "
STEP = f"{STEP_LABEL}1"
BUDGET = 5
CAP = 2
REPLAN = "attempt 1: completed; no commit | attempt 2: completed; no commit"
REQUEST = "s1-a3-implement"
FILE = "src/a.py"
EXHAUSTED = "attempts-exhausted"
STOPPED_MID_WORK = f"partial@{FILE}"


def evidence(**overrides: Any) -> verdicts.StepEvidence:
    """A goal step whose file changed, tests red, its agent stopped: partial before the cap."""
    fields: dict[str, Any] = {
        "step_id": STEP,
        "claim": "PENDING",
        "files": [FILE],
        "changed": [FILE],
        "unchanged": [],
        "test_status": "red",
        "tier2": {"agent_stop_seen": True, "last_write": FILE},
        "iterations": BUDGET,
    }
    return verdicts.StepEvidence(**{**fields, **overrides})


def done(**overrides: Any) -> verdicts.StepEvidence:
    """The same step with its work verified by its files and green tests."""
    return evidence(test_status="green", claim="COMPLETE", **overrides)


@pytest.mark.parametrize("count", [1, CAP, CAP + 1, BUDGET])
def test_a_goal_step_without_a_replan_is_never_exhausted_by_its_count(count):
    verdict = verdicts.classify_step(evidence(), None, Attempt(count))

    assert (verdict["verdict"], verdict["attempt"]) == (STOPPED_MID_WORK, count)


@pytest.mark.parametrize("count", [CAP, CAP + 1])
def test_a_goal_step_whose_attempts_line_carries_the_replan_is_exhausted(count):
    verdict = verdicts.classify_step(evidence(), None, Attempt(count, REPLAN))

    assert verdict["verdict"] == EXHAUSTED
    assert verdict["evidence"] == (
        f"{count} of {BUDGET} iteration(s) used and the loop stalled without verified "
        f"completion; replan requested: {REPLAN}; underlying verdict {STOPPED_MID_WORK}: "
        f"1 file(s) changed; agent stopped after {FILE}; remainder: none"
    )


def test_a_verified_goal_step_outranks_its_replan():
    verdict = verdicts.classify_step(done(), None, Attempt(CAP, REPLAN))

    assert verdict["verdict"] == "verified-complete"


def test_an_outstanding_goal_iteration_reads_in_flight_whatever_its_count():
    verdict = verdicts.classify_step(evidence(), None, OutstandingAttempt(BUDGET, REQUEST))

    assert (verdict["verdict"], verdict["attempt"]) == ("in-flight", BUDGET)


def test_an_ordinary_step_at_the_cap_reads_exhausted_with_its_text_unchanged():
    verdict = verdicts.classify_step(evidence(iterations=None), None, Attempt(CAP, REPLAN))

    assert verdict["evidence"] == (
        f"{CAP} fresh attempt(s) used (cap {CAP}) without verified completion; "
        f"replan requested: {REPLAN}; underlying verdict {STOPPED_MID_WORK}: "
        f"1 file(s) changed; agent stopped after {FILE}; remainder: none"
    )


def test_an_ordinary_step_under_the_cap_is_not_exhausted_by_a_replan_alone():
    verdict = verdicts.classify_step(evidence(iterations=None), None, Attempt(1, REPLAN))

    assert verdict["verdict"] == STOPPED_MID_WORK


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(evidence, id="work-in-progress"),
        pytest.param(done, id="work-that-files-and-tests-would-verify"),
    ],
)
def test_an_unreadable_iterations_value_reads_unknown_whatever_the_evidence(build):
    verdict = verdicts.classify_step(build(iterations=UnreadableIterations("many")), None, None)

    assert verdict["verdict"] == "unknown"
    assert "Iterations: value cannot be read ('many'" in verdict["evidence"]


def test_an_unreadable_iterations_value_is_never_hidden_behind_an_exhausted_count():
    unreadable = evidence(iterations=UnreadableIterations("0"))

    verdict = verdicts.classify_step(unreadable, None, Attempt(CAP, REPLAN))

    assert verdict["verdict"] == "unknown"
