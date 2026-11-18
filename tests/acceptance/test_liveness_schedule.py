"""The liveness checks run weekly or by hand, bounded in time and read-only.

The jobs that start the liveness checks live in a workflow of their own, apart from the scheduled
test-health workflow. It is triggered on a weekly schedule and by hand, holds no secret and no
write grant, starts no assistant session, and gives every job a time limit of its own: none past
the runner's six-hour job maximum, and the fast-probe job's at most 20 minutes.
"""

from __future__ import annotations

import yaml

from tests.acceptance.drivers.liveness_workflow import (
    FAST_JOB_MAXIMUM_MINUTES,
    REACHING_TOKENS,
    RUNNER_JOB_MAXIMUM_MINUTES,
    SESSION_TOKENS,
    Workflow,
    fast_probe_job,
    job_level_limit,
    liveness_workflow,
    runs_a_liveness_check,
)


def _liveness_jobs() -> tuple[Workflow, dict[str, dict]]:
    workflow = liveness_workflow()
    jobs = {job_id: job for job_id, job in workflow.jobs.items() if runs_a_liveness_check(job)}
    assert jobs, f"{workflow.relpath} has no job that starts a liveness check"
    return workflow, jobs


def _no_write_grant(permissions: object) -> bool:
    if isinstance(permissions, str):
        return permissions in ("read-all", "")
    return isinstance(permissions, dict) and all(
        v in ("read", "none") for v in permissions.values()
    )


def test_the_liveness_run_is_triggered_weekly_and_by_hand():
    workflow, _ = _liveness_jobs()

    assert workflow.is_weekly_and_by_hand(), (
        f"{workflow.relpath} needs a weekly schedule and a manual trigger: {workflow.triggers}"
    )


def test_the_liveness_job_holds_no_write_grant():
    workflow, jobs = _liveness_jobs()

    grants = {job_id: workflow.permissions_of(job_id) for job_id in jobs}

    assert all(grant is not None and _no_write_grant(grant) for grant in grants.values()), (
        "each liveness job needs explicit permissions with no write grant "
        f"(an absent block falls back to the repository default): {grants}"
    )


def test_the_liveness_job_uses_no_secret_and_no_assistant_session():
    _, jobs = _liveness_jobs()

    job_texts = {job_id: yaml.safe_dump(job) for job_id, job in jobs.items()}

    offending = {
        job_id: [token for token in (*REACHING_TOKENS, *SESSION_TOKENS) if token in text]
        for job_id, text in job_texts.items()
    }
    assert not any(offending.values()), f"a liveness job reaches a secret or session: {offending}"


def test_every_liveness_job_has_a_time_limit_of_its_own_within_the_runner_maximum():
    workflow, jobs = _liveness_jobs()

    limits = {job_id: job_level_limit(workflow, job_id) for job_id in jobs}

    assert all(
        limit is not None and 0 < limit <= RUNNER_JOB_MAXIMUM_MINUTES for limit in limits.values()
    ), (
        f"each liveness job needs its own time limit of at most "
        f"{RUNNER_JOB_MAXIMUM_MINUTES} minutes: {limits}"
    )


def test_the_fast_probe_job_stops_within_twenty_minutes():
    workflow, _ = _liveness_jobs()
    fast = fast_probe_job(workflow)

    limit = job_level_limit(workflow, fast)

    assert 0 < (limit or 0) <= FAST_JOB_MAXIMUM_MINUTES, (
        f"the fast-probe job {fast} must stop within {FAST_JOB_MAXIMUM_MINUTES} minutes: {limit}"
    )
