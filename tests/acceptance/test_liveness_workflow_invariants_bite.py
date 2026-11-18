"""Each property of the liveness workflow is held by a test that fails when it is broken.

In a scratch copy, one property of the liveness workflow file is broken at a time (a write grant,
a secret, a job without its own limit, the command through another interpreter, the scenarios
without the marker, the two trees in one run, an action unpinned, the audit beside the fast
probes, the triggers changed). The tests outside the outer loop that read that workflow then fail,
naming what broke. The scheduled workflow's own invariant test asks nothing of liveness jobs: it
passes on a scheduled workflow that holds none.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.gate_liveness import make_copy
from tests.acceptance.drivers.liveness_workflow import (
    MUTATIONS,
    PROPERTY_WORDS,
    SCHEDULED,
    invariant_tests_of,
    liveness_workflow,
    run_tests,
    without_liveness_jobs,
)

SCHEDULED_INVARIANTS = "tests/test_test_scheduled_workflow_invariants.py"


def test_the_liveness_workflow_has_an_invariant_test_of_its_own():
    workflow = liveness_workflow()

    tests = invariant_tests_of(workflow)

    assert tests, f"no test outside the outer loop reads {workflow.basename}"


@pytest.mark.parametrize("broken", sorted(MUTATIONS))
def test_breaking_one_property_of_the_liveness_workflow_fails_a_test_that_names_it(
    tmp_path, broken
):
    workflow = liveness_workflow()
    tests = invariant_tests_of(workflow)
    copy = make_copy(tmp_path)
    mutated = MUTATIONS[broken](workflow.text)
    assert mutated != workflow.text, f"the workflow holds nothing to break for {broken}"
    copy.write(workflow.relpath, mutated)

    run = run_tests(copy, tests)

    assert run.exit_code != 0, f"{tests} still pass with {broken}:\n{run.output[-3000:]}"
    assert any(word in run.output.lower() for word in PROPERTY_WORDS[broken]), (
        f"the failure does not name {broken} (any of {PROPERTY_WORDS[broken]}):\n"
        f"{run.output[-3000:]}"
    )


def test_the_scheduled_invariant_test_passes_on_a_scheduled_workflow_with_no_liveness_job(
    tmp_path,
):
    copy = make_copy(tmp_path)
    copy.write(SCHEDULED, without_liveness_jobs(copy.read(SCHEDULED)))

    run = run_tests(copy, [SCHEDULED_INVARIANTS])

    assert run.exit_code == 0, (
        f"{SCHEDULED_INVARIANTS} still asks for liveness jobs:\n{run.output[-3000:]}"
    )
