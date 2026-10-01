"""The whole liveness run, selection audit included, end to end in a scratch copy.

The selection audit runs the project's default suite while observing every
tracked file each test file reads, its child processes included, and asks the
test-scope resolver whether a change to that file alone selects the test. Its
oracle is the reads it observed, not a list of known cases: a read nobody listed
fails it, and two runs over the same commit give the same verdict and the same
unselected pairs. Run against this change's own state, every check passes.

Each of these runs the whole default suite at least once (about two minutes), so
they carry the `large` marker: deselected from the default run, which they would
otherwise slow down and which they cannot sit inside without running the suite
from within itself; run them with `-m large`.
"""

from __future__ import annotations

import pytest

from tests.e2e.drivers.selection_audit import (
    ALL_GATES,
    PROJECT_LOG,
    RESOLVER,
    WHOLE_SUITE_TIMEOUT,
    Gate,
    add_tests_reading_unrouted_files,
    make_copy,
    mutation_sensor_parallel_inheritance_failure,
    resolver_selects_nothing,
    run_liveness,
)

pytestmark = pytest.mark.large


def test_every_liveness_check_passes_on_this_change_and_leaves_no_trace(tmp_path):
    copy = make_copy(tmp_path)

    run = run_liveness(copy, ALL_GATES, timeout=WHOLE_SUITE_TIMEOUT)

    assert run.exit_code == 0, run.describe()
    assert all(run.verdict(gate).passed for gate in ALL_GATES), run.describe()
    assert copy.status() == "", f"the run changed the repository:\n{copy.status()}"
    assert not copy.path(PROJECT_LOG).exists(), "the run wrote the project's own log"


def test_audit_fails_on_unanticipated_reads_and_repeats_its_findings_exactly(tmp_path):
    copy = make_copy(tmp_path)
    reads = add_tests_reading_unrouted_files(copy)

    first = run_liveness(copy, [Gate.SELECTION_AUDIT], timeout=WHOLE_SUITE_TIMEOUT)
    second = run_liveness(copy, [Gate.SELECTION_AUDIT], timeout=WHOLE_SUITE_TIMEOUT)

    first_audit = first.verdict(Gate.SELECTION_AUDIT)
    second_audit = second.verdict(Gate.SELECTION_AUDIT)
    assert not first_audit.passed, first.describe()
    assert first.exit_code != 0, first.describe()
    assert {reads.direct, reads.via_child_process} <= set(first_audit.unselected), (
        f"the audit should list both unselected reads {reads}\n{first.describe()}"
    )
    assert (second_audit.passed, sorted(second_audit.unselected)) == (
        first_audit.passed,
        sorted(first_audit.unselected),
    ), f"two runs over one commit disagree:\n{first.describe()}\n---\n{second.describe()}"


def test_resolver_that_selects_nothing_fails_the_audit(tmp_path):
    copy = make_copy(tmp_path)
    resolver_selects_nothing(copy)
    copy.commit("dead test-scope resolver")

    run = run_liveness(copy, [Gate.SELECTION_AUDIT], timeout=WHOLE_SUITE_TIMEOUT)

    audit = run.verdict(Gate.SELECTION_AUDIT)
    assert not audit.passed, run.describe()
    assert audit.unselected, f"the audit should list the unselected reads\n{run.describe()}"


def test_missing_resolver_fails_the_audit_and_says_why(tmp_path):
    copy = make_copy(tmp_path)
    copy.remove(RESOLVER)
    copy.commit("missing test-scope resolver")

    run = run_liveness(copy, [Gate.SELECTION_AUDIT], timeout=WHOLE_SUITE_TIMEOUT)

    audit = run.verdict(Gate.SELECTION_AUDIT)
    assert not audit.passed, run.describe()
    assert run.exit_code != 0, run.describe()
    assert audit.reason.strip(), f"a failure with no reason\n{run.describe()}"


def test_a_dead_gate_fails_its_own_check_while_the_other_three_still_run_and_pass(tmp_path):
    copy = make_copy(tmp_path)
    mutation_sensor_parallel_inheritance_failure(copy)
    copy.commit("dead mutation sensor")

    run = run_liveness(copy, ALL_GATES, timeout=WHOLE_SUITE_TIMEOUT)

    assert run.exit_code != 0, run.describe()
    assert not run.verdict(Gate.MUTATION_SENSOR).passed, run.describe()
    assert all(
        run.verdict(gate).passed for gate in ALL_GATES if gate is not Gate.MUTATION_SENSOR
    ), run.describe()
