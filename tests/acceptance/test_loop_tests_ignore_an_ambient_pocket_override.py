"""Three standing tests pass whatever pocket-timeout override the environment carries.

A step gate may run the suite with `PRAXION_STEP_LOOP_POCKET_TIMEOUTS` set for its own
pockets. The adherence-eval tripwire, the compaction-orientation scenarios and the
abandoned-gate-run scenario must not read that ambient value as their own: each passes with
an override naming the eval pocket, whatever its value, or only the root pocket.

The value matters: a short bound (`eval=1`) happens to agree with the bounds the
abandoned-gate-run scenario sets for itself, while a long one (`eval=3600`) is read in
place of its own declaration. The scenarios therefore run both.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.acceptance.drivers.loop_repairs import env_without

REPO_ROOT = Path(__file__).resolve().parents[2]
VARIABLE = "PRAXION_STEP_LOOP_POCKET_TIMEOUTS"

ADHERENCE_TRIPWIRE = (
    "tests/acceptance/test_adherence_eval_tests_start_no_claude.py::"
    "test_the_eval_suite_passes_without_ever_starting_claude"
)
COMPACTION = "tests/acceptance/test_compaction_orientation_follows_the_driver.py"
ABANDONED_GATE = "tests/acceptance/test_abandoned_gate_run_is_stopped.py"

EVAL_OVERRIDES = {"eval-short": "eval=1", "eval-long": "eval=3600"}
ROOT_OVERRIDES = {"root-short": ".=1", "root-long": ".=3600"}


def _run(target: str, override: str) -> subprocess.CompletedProcess[str]:
    env = env_without(("PYTEST_ADDOPTS",))
    env[VARIABLE] = override
    return subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "--tb=short", "-p", "no:cacheprovider"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=1500,
        env=env,
    )


def _said(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout[-3000:] + result.stderr[-1000:]


@pytest.mark.parametrize(
    "override",
    list({**EVAL_OVERRIDES, **ROOT_OVERRIDES}.values()),
    ids=list({**EVAL_OVERRIDES, **ROOT_OVERRIDES}),
)
def test_the_abandoned_gate_run_scenario_passes_whatever_pocket_override_is_ambient(override):
    result = _run(ABANDONED_GATE, override)

    assert result.returncode == 0, _said(result)


@pytest.mark.parametrize("override", list(EVAL_OVERRIDES.values()), ids=list(EVAL_OVERRIDES))
def test_the_compaction_orientation_scenarios_pass_with_an_eval_override(override):
    result = _run(COMPACTION, override)

    assert result.returncode == 0, _said(result)


# The tripwire re-run costs about 500 s and repeats a node the default suite already runs, so
# it sits with the gate-liveness runs, outside the default selection (`-m liveness`).
@pytest.mark.liveness
@pytest.mark.parametrize("override", list(EVAL_OVERRIDES.values()), ids=list(EVAL_OVERRIDES))
def test_the_adherence_eval_tripwire_passes_with_an_eval_override(override):
    result = _run(ADHERENCE_TRIPWIRE, override)

    assert result.returncode == 0, _said(result)
