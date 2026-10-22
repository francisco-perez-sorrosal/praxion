"""The two pockets of this checkout declare a gate bound that fits their whole suites.

The step-loop gate widens a runner-config change to a pocket's whole suite, which outlasts the
540 second default; a pocket that declares nothing would see its gate cut off and read red. The
driver's own reader is the judge, so a declaration it cannot read fails here, not at a gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _step_loop_pocket_runs import pocket_bound  # noqa: E402

REPO = SCRIPT_DIR.parent
WHOLE_SUITE_FLOOR_SECONDS = 1000.0


@pytest.mark.parametrize("pocket", [".", "eval"])
def test_each_pocket_declares_a_bound_that_fits_its_whole_suite(pocket):
    reading = pocket_bound(REPO, pocket, environ={})

    assert reading.bound.source == "declared"
    assert reading.bound.seconds >= WHOLE_SUITE_FLOOR_SECONDS
    assert reading.warnings == ()
