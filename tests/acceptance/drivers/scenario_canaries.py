"""Driver for canary scenarios planted in a scratch copy, to read what a scenarios job logs.

The canaries are three `liveness`-marked scenarios written into the copy's `tests/acceptance`:
one passes, one fails, and one runs until something cuts it, after writing a file that says it
has started. Each of the first two takes a little over a second, so a duration the job reports
for it is visibly not zero. They are selected by name through `PYTEST_ADDOPTS`, which pytest reads
on every invocation, so the job's own command line runs unchanged.
"""

from __future__ import annotations

from tests.acceptance.drivers.gate_liveness import RepoCopy

CANARY_FILE = "tests/acceptance/test_duration_canary_liveness.py"
PASSES = "test_duration_canary_that_passes"
FAILS = "test_duration_canary_that_fails"
CUT = "test_duration_canary_cut_by_a_time_limit"
ALL_CANARIES = (PASSES, FAILS, CUT)
STARTED_VARIABLE = "DURATION_CANARY_STARTED"

_SOURCE = f'''"""Canary scenarios planted by a liveness acceptance test; never committed."""

import os
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.liveness


def {PASSES}():
    time.sleep(1.2)


def {FAILS}():
    time.sleep(1.2)
    raise AssertionError("a canary that fails on purpose")


def {CUT}():
    Path(os.environ["{STARTED_VARIABLE}"]).write_text("started")
    time.sleep(600)
'''


def plant(copy: RepoCopy) -> None:
    copy.write(CANARY_FILE, _SOURCE)


def selecting(*names: str) -> str:
    """A `PYTEST_ADDOPTS` value that runs only the named canaries."""
    return "-k '" + " or ".join(names) + "'"


SELECTS_NOTHING = "-k 'no_scenario_carries_this_name'"
