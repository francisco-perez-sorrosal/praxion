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
