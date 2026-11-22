"""The deferral touches only the gates it concerns; everything else reads as it did.

A goal step's iteration still runs every widened pocket whole at its gate and defers
nothing. Task directories the base commit's driver wrote over a step whose change widened a
pocket read back with the same `status` and `next` and are left as they were, so no pocket
waits. The three fast gate probes still pass.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.acceptance.drivers import base_written_records as base_records
from tests.acceptance.drivers import deferred_pockets as dp
from tests.acceptance.drivers import goal_loop
from tests.acceptance.drivers.deferred_pockets import BENCH
from tests.acceptance.drivers.pocket_gate import gate_block

REPO_ROOT = Path(__file__).resolve().parents[2]
FAST_PROBES = ("mutation-sensor", "observation-hooks", "spawn-count")


# -- A goal step's gate is unchanged ----------------------------------------------------------------


def test_a_goal_iteration_runs_its_widened_pocket_whole_and_defers_nothing(tmp_path):
    suite = dp.whole_suite_test(BENCH, dp.run_log_path(tmp_path), outcome="passes", hold=None)
    task = goal_loop.build_goal(
        tmp_path,
        base_files={BENCH.config: BENCH.config_text, BENCH.suite_test: suite},
        paths=(goal_loop.WIDGET, BENCH.config),
    )
    iteration = goal_loop.Iteration(
        implemented=("one",), other_edits=(dp.config_edit(BENCH, "settled by the goal"),)
    )

    relayed = goal_loop.iterate_by_relay(task, iteration)

    block = gate_block(task, relayed.request["id"])
    assert dp.whole_suite_runs(task, BENCH) == 1, block
    assert dp.deferred_lines(block) == [], block


# -- Records the base commit's driver wrote read as before --------------------------------------------


@pytest.mark.parametrize("case", base_records.CASES)
def test_records_the_base_driver_wrote_over_a_widened_step_read_as_they_did(tmp_path, case):
    base_records.restore(tmp_path, case)

    state, envelope = base_records.read_back(tmp_path, case)

    assert state == base_records.frozen(case, "status"), json.dumps(state, indent=1)
    assert envelope == base_records.frozen(case, "next"), json.dumps(envelope, indent=1)


@pytest.mark.parametrize("case", base_records.CASES)
def test_reading_the_base_drivers_records_runs_no_checkpoint_and_rewrites_none(tmp_path, case):
    base_records.restore(tmp_path, case)
    before = base_records.task_records(tmp_path)

    base_records.read_back(tmp_path, case)

    assert base_records.task_records(tmp_path) == before


# -- The fast gate probes still bite ------------------------------------------------------------------


def test_the_three_fast_gate_probes_pass():
    gates = [arg for probe in FAST_PROBES for arg in ("--gate", probe)]

    done = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_gates_bite.py"), *gates, "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )

    assert done.returncode == 0, done.stdout + done.stderr
    assert [v["gate"] for v in json.loads(done.stdout)["verdicts"] if v["passed"]] == list(
        FAST_PROBES
    )
