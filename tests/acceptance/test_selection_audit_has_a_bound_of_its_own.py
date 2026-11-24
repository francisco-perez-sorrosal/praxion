"""The selection audit holds its traced run to a bound of its own, and says when it ran out.

The audit's bound is longer than the step loop's declared gate bound, which stays where it was.
When the traced suite outlasts the audit's bound, the audit's verdict fails stating the bound it
was held to and that the run was still going.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers.audit_bound import declare_audit_bound, declared_audit_bound_seconds
from tests.acceptance.drivers.gate_liveness import Gate, make_copy, run_liveness
from tests.acceptance.drivers.liveness_workflow import REPO_ROOT

STEP_LOOP_BOUND_SECONDS = 2500
SHORT_BOUND_SECONDS = 7
STILL_GOING = re.compile(
    r"still (?:going|running)|had not (?:yet )?finished|did not finish|unfinished|was running",
    re.IGNORECASE,
)


def test_the_audit_bound_is_longer_than_the_step_loops_gate_bound():
    bound = declared_audit_bound_seconds(REPO_ROOT)

    assert bound > STEP_LOOP_BOUND_SECONDS, (
        f"the audit's bound {bound} s is not past {STEP_LOOP_BOUND_SECONDS} s"
    )


@pytest.mark.liveness
def test_an_audit_that_outlasts_its_bound_fails_saying_the_bound_and_that_it_was_still_going(
    tmp_path,
):
    copy = make_copy(tmp_path)
    declare_audit_bound(copy, SHORT_BOUND_SECONDS)
    copy.commit("a selection audit bound too short for the traced suite")

    run = run_liveness(copy, [Gate.SELECTION_AUDIT], timeout=600)

    audit = run.verdict(Gate.SELECTION_AUDIT)
    assert not audit.passed, run.describe()
    assert re.search(rf"\b{SHORT_BOUND_SECONDS}\s?(?:s|sec|seconds)\b", audit.reason), (
        f"the verdict does not state the {SHORT_BOUND_SECONDS} s bound:\n{run.describe()}"
    )
    assert STILL_GOING.search(audit.reason), (
        f"the verdict does not say the run was still going:\n{run.describe()}"
    )
