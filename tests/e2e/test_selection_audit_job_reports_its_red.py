"""The selection audit's job, run as the liveness workflow runs it, shows its red in its log.

In a scratch copy that holds two test files reading files no test route points at, the audit's
job is run from its own steps. The job fails, and its log carries the verdict's expected and
observed text and both unselected reads, so the week's red names what it found.

The job runs the traced default suite, so this scenario carries the `liveness` marker and runs
with the whole-suite scenarios.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.liveness_workflow import audit_job, liveness_workflow, run_job_locally
from tests.e2e.drivers.selection_audit import (
    add_tests_reading_unrouted_files,
    make_copy,
    whole_suite_timeout,
)

pytestmark = pytest.mark.liveness


def test_a_failing_audit_job_logs_what_it_expected_what_it_observed_and_each_unselected_read(
    tmp_path,
):
    workflow = liveness_workflow()
    copy = make_copy(tmp_path)
    reads = add_tests_reading_unrouted_files(copy)

    job = run_job_locally(
        copy, workflow, audit_job(workflow), extra_env={}, timeout=whole_suite_timeout()
    )

    missing = [
        part
        for part in ("expected", "observed", *reads.direct, *reads.via_child_process)
        if part not in job.text
    ]
    assert job.failed, f"the audit job concluded success on unselected reads:\n{job.text[-3000:]}"
    assert missing == [], f"the audit job's log lacks {missing}:\n{job.text[-4000:]}"
