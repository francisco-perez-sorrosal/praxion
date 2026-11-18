"""Each liveness job, run the way the workflow runs it, logs what the next re-sizing needs.

The fast-probe job ends with one verdict for each of the three fast probes. A scenarios job logs
the duration of every scenario it ran, whether the scenario passed, failed or was cut by a time
limit, and logs the free disk space before the first scenario and after the last.

Each job runs from its own steps, locally, in a scratch copy (`run_job_locally`); the canaries
are planted scenarios selected by name, so no real scenario runs here.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers import scenario_canaries as canaries
from tests.acceptance.drivers.gate_liveness import make_copy
from tests.acceptance.drivers.liveness_workflow import (
    AUDIT_PROBE,
    QUICK_PROBES,
    QUICK_SCENARIO_FILES,
    disk_reading_positions,
    fast_probe_job,
    jobs_collecting,
    liveness_workflow,
    run_job_locally,
    scenario_jobs,
)

pytestmark = pytest.mark.liveness

DURATION = re.compile(r"\b\d+(?:\.\d+)?\s?(?:s|sec|seconds)\b")


def _verdict_named(log: str, probe: str) -> bool:
    line_verdict = rf"(?m)^.*\b(?:PASS|FAIL)\b.*\b{re.escape(probe)}\b.*$"
    reversed_verdict = rf"(?m)^.*\b{re.escape(probe)}\b.*\b(?:PASS|FAIL)\b.*$"
    json_verdict = rf'"gate":\s*"{re.escape(probe)}"'
    return any(re.search(p, log) for p in (line_verdict, reversed_verdict, json_verdict))


def _quick_scenarios_job() -> str:
    workflow = liveness_workflow()
    jobs = sorted(jobs_collecting(workflow, QUICK_SCENARIO_FILES))
    assert jobs, "no liveness job runs the quick scenarios"
    return jobs[0]


def _durations_reported(log: str, name: str) -> bool:
    return any(name in line and DURATION.search(line) for line in log.splitlines())


def test_the_fast_probe_job_ends_with_one_verdict_for_each_fast_probe(tmp_path):
    workflow = liveness_workflow()
    copy = make_copy(tmp_path / "copy")

    log = run_job_locally(copy, workflow, fast_probe_job(workflow), extra_env={}).text

    unreported = [probe for probe in QUICK_PROBES if not _verdict_named(log, probe)]
    assert unreported == [], f"the fast-probe job gave no verdict for {unreported}:\n{log[-3000:]}"
    assert not _verdict_named(log, AUDIT_PROBE), f"the fast-probe job ran the audit:\n{log[-3000:]}"


def test_a_scenarios_job_logs_each_scenarios_duration_whether_it_passed_failed_or_was_cut(
    tmp_path,
):
    workflow = liveness_workflow()
    copy = make_copy(tmp_path / "copy")
    canaries.plant(copy)
    started = tmp_path / "cut-canary-started"
    env = {
        "PYTEST_ADDOPTS": canaries.selecting(*canaries.ALL_CANARIES),
        canaries.STARTED_VARIABLE: str(started),
    }

    job = run_job_locally(copy, workflow, _quick_scenarios_job(), extra_env=env, cut_when=started)

    unreported = [name for name in canaries.ALL_CANARIES if not _durations_reported(job.text, name)]
    assert started.exists(), f"the cut canary never started:\n{job.text[-3000:]}"
    assert unreported == [], f"no duration logged for {unreported}:\n{job.text[-4000:]}"


def test_a_scenarios_job_logs_free_disk_space_before_the_first_scenario_and_after_the_last(
    tmp_path,
):
    workflow = liveness_workflow()
    copy = make_copy(tmp_path / "copy")
    canaries.plant(copy)
    env = {"PYTEST_ADDOPTS": canaries.selecting(canaries.PASSES)}

    log = run_job_locally(copy, workflow, _quick_scenarios_job(), extra_env=env).text

    ran_at = log.find(canaries.PASSES)
    readings = disk_reading_positions(log)
    assert ran_at >= 0, f"the canary scenario did not run:\n{log[-3000:]}"
    assert any(at < ran_at for at in readings), f"no free-space reading before:\n{log[:3000]}"
    assert any(at > ran_at for at in readings), f"no free-space reading after:\n{log[-3000:]}"


def test_every_scenarios_job_logs_free_disk_space_twice_even_when_it_runs_nothing(tmp_path):
    workflow = liveness_workflow()
    copy = make_copy(tmp_path / "copy")
    env = {"PYTEST_ADDOPTS": canaries.SELECTS_NOTHING}

    readings = {
        job: len(disk_reading_positions(run_job_locally(copy, workflow, job, extra_env=env).text))
        for job in scenario_jobs(workflow)
    }

    assert readings, f"{workflow.relpath} runs no liveness-marked scenarios"
    assert all(count >= 2 for count in readings.values()), (
        f"free-space readings per job: {readings}"
    )
