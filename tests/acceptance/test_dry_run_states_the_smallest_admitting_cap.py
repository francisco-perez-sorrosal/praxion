"""A dry run states the smallest run cap under which every planned session launches.

Beside the per-role task counts, a dry run on either axis states the number of sessions the run
would launch, the session budget, and their product: the smallest cap that admits every session
launched once, whatever each costs up to its budget. It says that a launch tried again reserves
its budget again. Given a cap below that, it says later launches may be refused and names the cap
that admits them all. Each planned session's line on standard output stays as it was.
"""

from __future__ import annotations

import json
import re

import pytest

from tests.acceptance.drivers import adherence_eval
from tests.acceptance.drivers.run_cap import BASE_SESSION_FIELDS, dry_run, smallest_cap_stated

AXES = ("ordinary", "paired")
BUDGET = 1.25
TOO_SMALL_CAP = 1.0
AMPLE_CAP = 10_000.0
RETRY_WORDS = re.compile(r"\bagain\b|\bretr(?:y|ied|ies)\b", re.IGNORECASE)
REFUSAL_WORDS = re.compile(r"\brefus", re.IGNORECASE)


@pytest.mark.parametrize("axis", AXES)
def test_a_dry_run_states_the_session_count_the_budget_and_their_product(tmp_path, axis):
    run = dry_run(tmp_path, axis, budget=BUDGET)

    assert run.exit_code == 0, run.stderr[-2000:]
    assert run.launched == (), "the dry run started claude"
    assert smallest_cap_stated(run, BUDGET) is not None, (
        f"no session count and its product with {BUDGET} are stated:\n{run.stderr[-2000:]}"
    )


@pytest.mark.parametrize("axis", AXES)
def test_a_dry_run_says_a_launch_tried_again_reserves_its_budget_again(tmp_path, axis):
    run = dry_run(tmp_path, axis, budget=BUDGET)

    assert RETRY_WORDS.search(run.stderr), f"nothing about a retried launch:\n{run.stderr[-2000:]}"


@pytest.mark.parametrize("axis", AXES)
def test_a_cap_below_the_smallest_says_later_launches_may_be_refused_and_names_the_cap(
    tmp_path, axis
):
    run = dry_run(tmp_path, axis, budget=BUDGET, cap=TOO_SMALL_CAP)

    assert REFUSAL_WORDS.search(run.stderr), f"no warning of refusals:\n{run.stderr[-2000:]}"
    assert smallest_cap_stated(run, BUDGET) is not None, (
        f"the cap that admits every session is not named:\n{run.stderr[-2000:]}"
    )


@pytest.mark.parametrize("axis", AXES)
def test_a_cap_that_admits_every_session_draws_no_refusal_warning(tmp_path, axis):
    run = dry_run(tmp_path, axis, budget=BUDGET, cap=AMPLE_CAP)

    assert run.exit_code == 0, run.stderr[-2000:]
    assert not REFUSAL_WORDS.search(run.stderr), f"a needless warning:\n{run.stderr[-2000:]}"


@pytest.mark.parametrize("axis", AXES)
def test_each_planned_sessions_line_keeps_its_shape(tmp_path, axis):
    run = dry_run(tmp_path, axis, budget=BUDGET)

    lines = run.planned_lines()
    sessions = adherence_eval.planned_sessions(run.stdout)
    shapes = {frozenset(json.loads(line)) >= BASE_SESSION_FIELDS for line in lines}

    assert len(sessions) == len(lines) > 0, f"stdout is not one session per line:\n{run.stdout}"
    assert shapes == {True}, f"a session line lost a field of {sorted(BASE_SESSION_FIELDS)}"
