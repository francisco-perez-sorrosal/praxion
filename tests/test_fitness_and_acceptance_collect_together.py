"""A fitness test and an acceptance test collect in one session, in either order.

The acceptance tests import their drivers as `tests.acceptance.drivers...`. A
resolver-derived selection can name fitness tests before acceptance tests, so
nothing under `fitness/` may claim the top-level name `tests` ahead of the
repository's own `tests/` directory.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FITNESS_TEST = "fitness/tests/test_starter_rule.py"
ACCEPTANCE_TEST = "tests/acceptance/test_goal_loop_scaffold.py"


@pytest.mark.parametrize(
    "ordered_paths",
    [(FITNESS_TEST, ACCEPTANCE_TEST), (ACCEPTANCE_TEST, FITNESS_TEST)],
    ids=["fitness-first", "acceptance-first"],
)
def test_fitness_and_acceptance_tests_collect_without_errors_in_either_order(
    ordered_paths: tuple[str, ...],
) -> None:
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "--no-cov",
            "-n",
            "0",
            *ordered_paths,
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert run.returncode == 0, run.stdout[-1500:] + run.stderr[-500:]
