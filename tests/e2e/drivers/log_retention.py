"""Drivers for the observation log's end-to-end scenarios.

* Concurrent hook deliveries: several sessions start at the same moment, each
  in its own thread running the registered hooks as separate processes.
* The project-metrics cost report, run as `python -m scripts.project_metrics
  --mechanical-only` from a scratch checkout; its JSON report is read back.
  It resolves external tools on first run, hence the `large` marker.
* The sentinel's family runner and the log owner's three gates, run inside a
  scratch copy of this repository (`gate_liveness.make_copy`).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tests.acceptance.drivers.gate_liveness import RepoCopy, isolated_env, make_copy
from tests.acceptance.drivers.observation_harness import HookHarness, Session

REPO_ROOT = Path(__file__).resolve().parents[3]
OWNER_GATES = (
    "hooks/test_observation_log_registry.py",  # consumer contract
    "hooks/test_observation_log_writer_truth.py",
    "hooks/test_observation_log_private_reader.py",
)

__all__ = ["RepoCopy", "make_copy"]


def start_sessions_concurrently(harness: HookHarness, cwd: Path, session_ids: list[str]) -> None:
    sessions = [Session(harness, sid, cwd) for sid in session_ids]
    with ThreadPoolExecutor(max_workers=len(sessions)) as pool:
        list(pool.map(lambda s: s.session_start(), sessions))


def run_alongside(action, harness: HookHarness, cwd: Path, session_ids: list[str]):
    """Run `action()` while the sessions start; returns its result, re-raising its error."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(action)
        start_sessions_concurrently(harness, cwd, session_ids)
        return pending.result()


def cost_report(checkout: Path) -> dict:
    """The whole metrics report the cost collector contributes to, as JSON."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("CLAUDE", "PRAXION_", "GIT_", "ANTHROPIC_"))
    }
    env["PYTHONPATH"] = str(REPO_ROOT)
    result = subprocess.run(
        [sys.executable, "-m", "scripts.project_metrics", "--mechanical-only"],
        cwd=checkout,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, f"project-metrics failed: {result.stderr[-2000:]}"
    reports = sorted((checkout / ".ai-state" / "metrics_reports").glob("METRICS_REPORT_*.json"))
    return json.loads(reports[-1].read_text(encoding="utf-8"))


def attributed_rows(report: dict) -> int:
    cost = report.get("cost", {})
    cost = cost.get("data", cost)
    assert "coverage" in cost, f"the cost report did not run: {json.dumps(cost)[:500]}"
    return cost["coverage"]["attributed_rows"]


def run_family_runner(copy: RepoCopy, *, table: bool = False) -> str:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_check_families.py",
            "--repo-root",
            str(copy.root),
            "--table" if table else "--json",
        ],
        cwd=copy.root,
        env=isolated_env(),
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert result.stdout.strip(), f"the family runner printed nothing: {result.stderr[-2000:]}"
    return result.stdout


def run_owner_gates(copy: RepoCopy) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--no-cov",
            "-n",
            "0",
            *OWNER_GATES,
        ],
        cwd=copy.root,
        env=isolated_env(),
        capture_output=True,
        text=True,
        timeout=900,
    )
