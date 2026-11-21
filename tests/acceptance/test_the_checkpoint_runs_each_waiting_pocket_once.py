"""Before `complete`, the loop runs each waiting pocket's whole suite once, and only then.

A pocket waits from the first committed step whose gate deferred it until a checkpoint run
of its whole suite is green; an attempt that is not committed adds nothing. With every step
done, `next` runs each waiting pocket's suite once, whatever the number of steps that
deferred it, and prints `complete` only when every run is green; with a step remaining it
starts no checkpoint run. A checkpoint run still inside its bound answers `gate-running`,
and the call made again never starts a second run of a pocket. Each run is recorded in a
block of its own that belongs to no step and leaves every step's verdict as it was. A
project with a single pocket gets the same treatment.
"""

from __future__ import annotations

import re

from tests.acceptance.drivers import deferred_pockets as dp
from tests.acceptance.drivers.deferred_pockets import BENCH, ROOT
from tests.acceptance.drivers.pocket_gate import cut_off, gate_block
from tests.acceptance.drivers.step_loop import Step, Work, attempt, next_action


def _deferring_plan(tmp_path, *step_ids, **build):
    task = dp.build_pocket_loop(tmp_path, *(dp.widening_step(i, BENCH) for i in step_ids), **build)
    for step_id in step_ids:
        recorded = attempt(task, dp.widening_work(step_id, BENCH))
        assert recorded.recorded["commit"] is not None, recorded.doc
    return task


# -- The checkpoint runs before complete ----------------------------------------------------------


def test_complete_is_printed_only_after_the_waiting_pocket_ran_whole(tmp_path):
    task = _deferring_plan(tmp_path, "41")
    assert dp.whole_suite_runs(task, BENCH) == 0, "the step's gate ran the widened suite"

    finished = dp.next_until_settled(task)

    assert finished.outcome == "complete", finished.doc
    assert dp.whole_suite_runs(task, BENCH) == 1


def test_a_pocket_two_steps_deferred_runs_once_at_the_checkpoint(tmp_path):
    task = _deferring_plan(tmp_path, "41", "42")
    assert dp.whole_suite_runs(task, BENCH) == 0, "a step's gate ran the widened suite"

    finished = dp.next_until_settled(task)

    assert finished.outcome == "complete", finished.doc
    assert dp.whole_suite_runs(task, BENCH) == 1


def test_a_pocket_whose_checkpoint_run_was_green_is_not_run_again(tmp_path):
    task = _deferring_plan(tmp_path, "41")
    assert dp.whole_suite_runs(task, BENCH) == 0, "the step's gate ran the widened suite"
    dp.next_until_settled(task)

    again = dp.next_until_settled(task)

    assert again.outcome == "complete", again.doc
    assert dp.whole_suite_runs(task, BENCH) == 1


def test_no_checkpoint_run_starts_while_a_step_remains(tmp_path):
    task = dp.build_pocket_loop(tmp_path, dp.widening_step("41", BENCH), Step("42"))
    attempt(task, dp.widening_work("41", BENCH))

    asked = next_action(task)

    assert asked.outcome == "spawn", asked.doc
    assert dp.whole_suite_runs(task, BENCH) == 0


# -- Only a committed deferral makes a pocket wait --------------------------------------------------


def test_a_red_attempt_that_widened_a_pocket_leaves_nothing_waiting(tmp_path):
    task = dp.build_pocket_loop(tmp_path, dp.widening_step("41", BENCH))
    attempt(task, dp.widening_work("41", BENCH, passes=False))
    put_back = Work(other_edits=((BENCH.config, BENCH.config_text),))
    committed = attempt(task, put_back)
    assert committed.recorded["commit"] is not None, committed.doc

    finished = dp.next_until_settled(task)

    assert finished.outcome == "complete", finished.doc
    assert dp.whole_suite_runs(task, BENCH) == 0


def test_a_step_that_deferred_a_pocket_on_two_attempts_is_one_waiting_step(tmp_path):
    task = dp.build_pocket_loop(tmp_path, dp.widening_step("41", BENCH))
    attempt(task, dp.widening_work("41", BENCH, passes=False))
    committed = attempt(task, dp.widening_work("41", BENCH))
    assert committed.recorded["commit"] is not None, committed.doc

    assert dp.waiting_in_status(task) == {BENCH.root: ["41"]}


# -- A checkpoint longer than one call resumes -------------------------------------------------------


def test_a_checkpoint_run_inside_its_bound_answers_gate_running_and_prints_no_complete(tmp_path):
    hold = tmp_path / "hold-the-suite"
    task = _deferring_plan(tmp_path, "41", holds={BENCH.label: hold})
    dp.limit_call_wait(task, 1)
    hold.touch()

    held = next_action(task)
    hold.unlink()
    finished = dp.next_until_settled(task)

    assert dp.is_gate_running(held), held.doc
    assert held.exit_code == 4
    assert finished.outcome == "complete", finished.doc
    assert dp.whole_suite_runs(task, BENCH) == 1


def test_a_checkpoint_call_cut_off_and_made_again_never_starts_a_second_run(tmp_path):
    hold = tmp_path / "hold-the-suite"
    task = _deferring_plan(tmp_path, "41", holds={BENCH.label: hold})
    assert dp.whole_suite_runs(task, BENCH) == 0, "the step's gate ran the widened suite"
    hold.touch()
    call = dp.start_next(task)
    dp.wait_for_whole_suite_run(task, BENCH, deadline_seconds=300)
    cut_off(call)
    hold.unlink()

    finished = dp.next_until_settled(task)

    assert finished.outcome == "complete", finished.doc
    assert dp.whole_suite_runs(task, BENCH) == 1


# -- The checkpoint's evidence is recorded apart ------------------------------------------------------


def test_the_checkpoint_records_a_block_of_its_own_naming_the_pocket_its_counts_and_steps(tmp_path):
    task = _deferring_plan(tmp_path, "41", "42")
    before = dp.results_text(task)

    dp.next_until_settled(task)

    added = dp.blocks_added(before, dp.results_text(task))
    naming_the_pocket = dp.blocks_naming(added, BENCH)
    assert len(naming_the_pocket) == 1, f"blocks added by the checkpoint:\n{added}"
    (block,) = naming_the_pocket
    assert re.match(r"## Step \S+", block) is None, block
    assert re.search(r"\bpass=1\b", block), block
    assert re.search(r"\b41\b", block), block
    assert re.search(r"\b42\b", block), block


def test_recording_the_checkpoint_leaves_every_steps_verdict_as_the_reconciler_read_it(tmp_path):
    task = _deferring_plan(tmp_path, "41", "42")
    before = dp.results_text(task)
    verdicts_before = dp.verdicts(task)

    dp.next_until_settled(task)

    assert dp.blocks_added(before, dp.results_text(task)) != [], "the checkpoint left no block"
    assert dp.verdicts(task) == verdicts_before


# -- A project with one pocket ------------------------------------------------------------------------


def test_a_single_pocket_project_runs_only_the_check_at_the_gate_and_its_suite_at_the_checkpoint(
    tmp_path,
):
    task = dp.build_pocket_loop(tmp_path, dp.widening_step("41", ROOT), pockets=(ROOT,))
    recorded = attempt(task, dp.widening_work("41", ROOT))
    block = gate_block(task, recorded.recorded["request"])
    gate_runs = dp.whole_suite_runs(task, ROOT)

    finished = dp.next_until_settled(task)

    assert gate_runs == 0, block
    assert len(dp.deferred_lines(block)) == 1, block
    assert recorded.recorded["gate"]["verdict"] == "verified-complete", recorded.doc
    assert finished.outcome == "complete", finished.doc
    assert dp.whole_suite_runs(task, ROOT) == 1
