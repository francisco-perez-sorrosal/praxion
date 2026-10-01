"""Structural invariants for the scheduled test-health workflow.

`.github/workflows/test-scheduled.yml` is the scheduled loop of the testing
doctrine: per pocket it runs the full suite with junit output, reruns only the
failures once to tell flaky from broken, runs the `large` tests the default run
deselects, and audits real failures against the derived selection. A step
silently dropped from that sequence leaves the loop running and green while it
no longer watches what it exists to watch, so the shape is pinned here.

Scope: parsed YAML and command text only. Whether the audit attributes a miss
correctly is covered by `scripts/test_audit_tests.py`; whether the workflow
runs on GitHub is proven only by a live dispatch.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_FILE = PROJECT_ROOT / ".github" / "workflows" / "test-scheduled.yml"
SHA_PIN = re.compile(r"@[0-9a-f]{40}\b")
PYTHON_POCKET_JOBS = ("health-root", "health-eval", "health-chronograph")
# task-chronograph-mcp's only `large` tests need a live Phoenix daemon the
# runner does not have (td-289), so that job carries no `-m large` step.
LARGE_STEP_JOBS = ("health-root", "health-eval")


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW_FILE.read_text(encoding="utf-8"))


def _run_text(job: dict) -> str:
    return "\n".join(step.get("run", "") for step in job["steps"])


def test_runs_weekly_and_on_demand() -> None:
    # PyYAML reads the bare `on:` key as boolean True.
    triggers = _workflow()[True]
    assert "schedule" in triggers
    assert "workflow_dispatch" in triggers


@pytest.mark.parametrize("job_id", PYTHON_POCKET_JOBS)
def test_python_pocket_runs_the_full_loop(job_id: str) -> None:
    text = _run_text(_workflow()["jobs"][job_id])
    assert "--junitxml=junit.xml" in text, "full run must emit junit for the audit"
    assert "--last-failed" in text, "failures must be rerun once to classify flakiness"
    assert "audit_tests.py" in text
    assert "--junit junit.xml" in text


@pytest.mark.parametrize("job_id", LARGE_STEP_JOBS)
def test_pocket_runs_the_deselected_large_tests(job_id: str) -> None:
    text = _run_text(_workflow()["jobs"][job_id])
    assert "-m large" in text, "the loop must run the tests the default run deselects"


@pytest.mark.parametrize("job_id", LARGE_STEP_JOBS)
def test_no_large_tests_counts_as_a_pass(job_id: str) -> None:
    text = _run_text(_workflow()["jobs"][job_id])
    assert '"$rc" -eq 5' in text, "pytest exit 5 (no tests collected) must not fail the job"


def test_dashboard_job_produces_junit_via_vitest_run() -> None:
    # `pnpm test -- <flags>` runs the `package.json` "test" script (`vitest run`)
    # with the flags appended as its OWN argv, not vitest's — vitest silently
    # ignores everything after its own `--` and writes no junit file, so the
    # audit step downstream fails closed on a missing file. `pnpm exec vitest
    # run <flags>` invokes the runner directly, so the flags land on vitest.
    text = _run_text(_workflow()["jobs"]["health-dashboard"])
    assert "pnpm exec vitest run" in text, "must invoke the runner directly"
    assert "pnpm test --" not in text, "pnpm test -- swallows its own flags"
    assert "--outputFile.junit=junit.xml" in text


def test_every_action_is_sha_pinned() -> None:
    for job in _workflow()["jobs"].values():
        for step in job["steps"]:
            uses = step.get("uses")
            if uses:
                assert SHA_PIN.search(uses), f"unpinned action: {uses}"


def test_workflow_is_read_only() -> None:
    permissions = _workflow()["permissions"]
    assert permissions.get("contents") == "read"
    assert not any(value == "write" for value in permissions.values())


# -- the gate-liveness jobs: read-only, secretless, bounded, and never one pytest over both trees --

LIVENESS_JOBS = ("gate-liveness", "gate-liveness-canaries")
LIVENESS_CLI = "scripts/check_gates_bite.py"
LIVENESS_STEP_LIMIT_MINUTES = 20  # the run's budget; the job limit adds setup around it
SESSION_OR_SECRET_TOKENS = ("secrets.", "github.token", "claude-code-action", "ANTHROPIC_")


def _runs(job: dict) -> list[str]:
    return [step["run"] for step in job["steps"] if "run" in step]


@pytest.mark.parametrize("job_id", LIVENESS_JOBS)
def test_liveness_job_holds_only_a_read_grant_of_its_own(job_id: str) -> None:
    job = _workflow()["jobs"][job_id]
    assert job["permissions"] == {"contents": "read"}


@pytest.mark.parametrize("job_id", LIVENESS_JOBS)
def test_liveness_job_reaches_no_secret_and_starts_no_assistant_session(job_id: str) -> None:
    job = _workflow()["jobs"][job_id]
    assert "env" not in job, "a job-level env is where a token would arrive"
    reached = [token for token in SESSION_OR_SECRET_TOKENS if token in yaml.safe_dump(job)]
    assert not reached, f"{job_id} reaches {reached}"


@pytest.mark.parametrize("job_id", LIVENESS_JOBS)
def test_liveness_job_has_a_time_limit_of_its_own(job_id: str) -> None:
    assert int(_workflow()["jobs"][job_id]["timeout-minutes"]) > 0


def test_liveness_cli_step_is_bounded_within_the_run_budget() -> None:
    job = _workflow()["jobs"]["gate-liveness"]
    steps = [step for step in job["steps"] if LIVENESS_CLI in step.get("run", "")]
    assert len(steps) == 1
    assert 0 < int(steps[0]["timeout-minutes"]) <= LIVENESS_STEP_LIMIT_MINUTES
    assert int(job["timeout-minutes"]) > int(steps[0]["timeout-minutes"])


def test_liveness_cli_runs_from_the_synced_environment_and_nowhere_else() -> None:
    jobs = _workflow()["jobs"]
    cli_jobs = [job_id for job_id, job in jobs.items() if LIVENESS_CLI in _run_text(job)]
    assert cli_jobs == ["gate-liveness"]
    assert ".venv/bin/python scripts/check_gates_bite.py" in _run_text(jobs["gate-liveness"])
    assert "uv sync --frozen" in _run_text(jobs["gate-liveness"])


def test_liveness_canaries_run_the_liveness_marker_over_the_e2e_directory() -> None:
    text = _run_text(_workflow()["jobs"]["gate-liveness-canaries"])
    assert "pytest -m liveness tests/e2e" in text
    assert "uv sync --frozen" in text


@pytest.mark.parametrize("job_id", LIVENESS_JOBS)
def test_no_liveness_pytest_run_mixes_the_root_and_fitness_trees(job_id: str) -> None:
    # td-302: tests/ and fitness/tests/ in one invocation collide on the `tests` package name.
    for run in _runs(_workflow()["jobs"][job_id]):
        assert "fitness" not in run, run
