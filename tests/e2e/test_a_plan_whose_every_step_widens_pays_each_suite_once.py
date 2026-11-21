"""A plan whose every step widens every pocket pays each whole suite once, at the checkpoint.

Relayed through `next`, the Agent tool's double and `record`, a three-step plan in a
project whose test scope widens every pocket at every step commits each step on its check
alone, runs no whole suite at any step's gate, and before `complete` runs each pocket's
whole suite exactly once. The pocket is treated by what the test scope says of it whatever
its directory is called, including the names of Praxion's own pockets.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import deferred_pockets as dp
from tests.acceptance.drivers.deferred_pockets import ROOT, Pocket
from tests.acceptance.drivers.step_loop import commits_after
from tests.e2e.drivers.step_loop_journey import relay_until_stopped

STEP_IDS = ("1", "2", "3")


@pytest.mark.parametrize(
    "pocket",
    [
        pytest.param(Pocket("bench", "bench"), id="a-pocket-of-its-own"),
        pytest.param(Pocket("eval", "evaluation"), id="named-like-praxions-eval"),
        pytest.param(Pocket("task-chronograph-mcp", "chronograph"), id="named-like-praxions-mcp"),
    ],
)
def test_every_widened_pocket_runs_whole_once_at_the_checkpoint_and_never_at_a_gate(
    tmp_path, pocket
):
    task = dp.build_pocket_loop(
        tmp_path, *(dp.everywhere_step(i) for i in STEP_IDS), pockets=(ROOT, pocket)
    )

    relay_until_stopped(task, {i: [dp.everywhere_work(i)] for i in STEP_IDS})
    finished = dp.next_until_settled(task)

    assert len(commits_after(task, task.base)) == len(STEP_IDS)
    assert finished.outcome == "complete", finished.doc
    assert (dp.whole_suite_runs(task, ROOT), dp.whole_suite_runs(task, pocket)) == (1, 1)
