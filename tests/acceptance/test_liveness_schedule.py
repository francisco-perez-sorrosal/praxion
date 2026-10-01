"""The liveness checks run weekly or by hand, bounded in time and read-only.

The job that starts the liveness run lives in the scheduled test-health workflow
or the scheduled audits workflow. It is triggered on a weekly schedule and by
hand, holds no secret and no write grant, starts no assistant session, and runs
under a time limit of its own of at most 20 minutes.
"""

from __future__ import annotations

import re

import yaml

from tests.acceptance.drivers.gate_liveness import REPO_ROOT, liveness_step_marker

CANDIDATE_WORKFLOWS = (
    ".github/workflows/test-scheduled.yml",
    ".github/workflows/audits.yml",
)
TIME_LIMIT_MINUTES = 20
_WEEKLY_CRON = re.compile(r"^\d{1,2} \d{1,2} \* \* [0-7A-Za-z]{1,3}$")


def _load(relpath: str) -> dict:
    return yaml.safe_load((REPO_ROOT / relpath).read_text(encoding="utf-8"))


def _triggers(workflow: dict) -> dict:
    # YAML 1.1 reads a bare `on:` key as the boolean True.
    triggers = workflow.get("on", workflow.get(True))
    return triggers if isinstance(triggers, dict) else dict.fromkeys(triggers or ())


def _liveness_steps(job: dict, marker: str) -> list[dict]:
    return [step for step in job.get("steps", []) if marker in str(step.get("run", ""))]


def _liveness_jobs() -> list[tuple[str, str, dict, dict]]:
    """(workflow path, job id, job, workflow) for every job with a step starting the run."""
    marker = liveness_step_marker()
    found = []
    for relpath in CANDIDATE_WORKFLOWS:
        workflow = _load(relpath)
        for job_id, job in workflow.get("jobs", {}).items():
            if _liveness_steps(job, marker):
                found.append((relpath, job_id, job, workflow))
    return found


def _require_liveness_jobs() -> list[tuple[str, str, dict, dict]]:
    jobs = _liveness_jobs()
    assert jobs, f"no job in {CANDIDATE_WORKFLOWS} starts the liveness run"
    return jobs


def _no_write_grant(permissions: object) -> bool:
    if isinstance(permissions, str):
        return permissions in ("read-all", "")
    return isinstance(permissions, dict) and all(
        v in ("read", "none") for v in permissions.values()
    )


def test_the_liveness_run_is_triggered_weekly_and_by_hand():
    liveness_jobs = _require_liveness_jobs()

    triggers_by_workflow = {
        relpath: _triggers(workflow) for relpath, _, _, workflow in liveness_jobs
    }

    weekly_and_manual = {
        relpath: (
            "workflow_dispatch" in triggers
            and any(
                _WEEKLY_CRON.match(entry.get("cron", "").strip())
                for entry in (triggers.get("schedule") or [])
            )
        )
        for relpath, triggers in triggers_by_workflow.items()
    }
    assert all(weekly_and_manual.values()), (
        f"each workflow running the liveness checks needs a weekly schedule and a manual "
        f"trigger: {triggers_by_workflow}"
    )


def test_the_liveness_job_holds_no_write_grant():
    liveness_jobs = _require_liveness_jobs()

    grants = {
        f"{relpath}::{job_id}": job.get("permissions", workflow.get("permissions"))
        for relpath, job_id, job, workflow in liveness_jobs
    }

    assert all(grant is not None and _no_write_grant(grant) for grant in grants.values()), (
        "each liveness job needs explicit permissions with no write grant "
        f"(an absent block falls back to the repository default): {grants}"
    )


def test_the_liveness_job_uses_no_secret_and_no_assistant_session():
    liveness_jobs = _require_liveness_jobs()

    job_texts = {
        f"{relpath}::{job_id}": yaml.safe_dump(job) for relpath, job_id, job, _ in liveness_jobs
    }

    offending = {
        name: [
            token
            for token in ("secrets.", "github.token", "claude-code-action", "ANTHROPIC_")
            if token in text
        ]
        for name, text in job_texts.items()
    }
    assert not any(offending.values()), f"the liveness job reaches a secret or session: {offending}"


def test_the_liveness_run_has_a_time_limit_of_at_most_twenty_minutes():
    liveness_jobs = _require_liveness_jobs()

    marker = liveness_step_marker()
    limits = {
        f"{relpath}::{job_id}": [
            step.get("timeout-minutes", job.get("timeout-minutes"))
            for step in _liveness_steps(job, marker)
        ]
        for relpath, job_id, job, _ in liveness_jobs
    }

    assert all(
        limit is not None and int(limit) <= TIME_LIMIT_MINUTES
        for step_limits in limits.values()
        for limit in step_limits
    ), f"each liveness step must stop within {TIME_LIMIT_MINUTES} minutes: {limits}"
