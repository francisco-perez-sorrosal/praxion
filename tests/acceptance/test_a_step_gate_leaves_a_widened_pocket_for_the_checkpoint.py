"""A step with a check pays for its check and the tests its change reaches, not for a widened suite.

When the test scope of a driven step's change marks a pocket `widened`, the step's gate runs
the step's `Check:` and every `narrow` pocket and starts no run of the widened pocket's
suite; the check and the narrow runs decide the verdict, the commit and the record. The
block names each pocket it left on a `Deferred:` line of its own, before the deciding
`Result:` line, and writes no `Scope:` line for it. The reconciler reads that block as it
reads the same block without the `Deferred:` lines. A step with only narrow pockets or
nothing to run, and a step with no check, gate, record and decide exactly as before.
"""

from __future__ import annotations

from tests.acceptance.drivers import deferred_pockets as dp
from tests.acceptance.drivers.deferred_pockets import BENCH, ROOT
from tests.acceptance.drivers.pocket_gate import gate_block
from tests.acceptance.drivers.step_loop import (
    Step,
    Work,
    attempt,
    build_loop,
    head,
    reconciler_verdict,
)

SHARED = "src/shared.py"
SHARED_TEST = "tests/test_shared.py"
SHARED_FILES = {
    SHARED: "def shared():\n    return 1\n",
    SHARED_TEST: "from src.shared import shared\n\n\ndef test_shared_is_one():\n"
    "    assert shared() == 1\n",
}


def _own_files_already_there(step):
    """The step's source and unit test as the base commit already holds them, passing."""
    return {
        step.source: f"def value():\n    return {step.id!r}\n",
        step.unit_test: f"from src.{step.module} import value\n\n\n"
        f"def test_value_is_the_step_id():\n    assert value() == {step.id!r}\n",
    }


def _gate(task, work):
    recorded = attempt(task, work)
    assert recorded.recorded is not None, recorded.doc
    return recorded, gate_block(task, recorded.recorded["request"])


# -- A widened pocket is left for the checkpoint ------------------------------------------------


def test_a_checked_step_starts_no_run_of_the_pocket_its_change_widens(tmp_path):
    task = dp.build_pocket_loop(tmp_path, dp.widening_step("1", BENCH))

    recorded, _ = _gate(task, dp.widening_work("1", BENCH))

    assert dp.whole_suite_runs(task, BENCH) == 0, "the gate ran the widened pocket's suite"
    assert recorded.recorded["gate"]["verdict"] == "verified-complete", recorded.doc
    assert recorded.recorded["commit"] is not None, recorded.doc


def test_a_checked_step_is_decided_by_its_check_whatever_its_widened_pocket_holds(tmp_path):
    task = dp.build_pocket_loop(
        tmp_path, dp.widening_step("1", BENCH), outcomes={BENCH.label: "fails"}
    )

    recorded, _ = _gate(task, dp.widening_work("1", BENCH))

    assert recorded.recorded["gate"]["verdict"] == "verified-complete", recorded.doc
    assert recorded.recorded["gate"]["decided_by"] == "check", recorded.doc
    assert recorded.recorded["commit"] is not None, recorded.doc


def test_a_narrow_pocket_still_fails_a_step_that_also_widens_another(tmp_path):
    step = Step("1", more_files=(BENCH.config, SHARED))
    task = dp.build_pocket_loop(tmp_path, step, base_files=SHARED_FILES)
    head_before = head(task)
    breaks_shared = dp.widening_work("1", BENCH)
    work = Work(other_edits=(*breaks_shared.other_edits, (SHARED, "def shared():\n    return 2\n")))

    recorded, _ = _gate(task, work)

    assert recorded.recorded["gate"]["verdict"] != "verified-complete", recorded.doc
    assert recorded.recorded["commit"] is None, recorded.doc
    assert head(task) == head_before


# -- Steps the change does not concern gate as before --------------------------------------------


def test_a_step_with_only_narrow_pockets_runs_records_and_commits_as_before(tmp_path):
    task = dp.build_pocket_loop(tmp_path, Step("1"))

    recorded, block = _gate(task, Work())

    assert dp.deferred_lines(block) == [], block
    assert dp.lines_naming(block, "Scope:", ROOT) != [], block
    assert dp.last_line(block).startswith("Result:"), block
    assert (dp.whole_suite_runs(task, ROOT), dp.whole_suite_runs(task, BENCH)) == (0, 0)
    assert recorded.recorded["gate"]["verdict"] == "verified-complete", recorded.doc
    assert recorded.recorded["commit"] is not None, recorded.doc


def test_a_step_whose_scope_has_nothing_to_run_is_decided_by_its_check_as_before(tmp_path):
    step = Step("1", more_files=("README.md",))
    task = build_loop(tmp_path, step, base_files=_own_files_already_there(step))

    recorded, block = _gate(
        task, Work(touches_files=False, other_edits=(("README.md", "# loop widget, settled\n"),))
    )

    assert dp.deferred_lines(block) == [], block
    assert recorded.recorded["gate"]["verdict"] == "verified-complete", recorded.doc
    assert recorded.recorded["gate"]["decided_by"] == "check", recorded.doc


# -- The block records each deferral ---------------------------------------------------------------


def test_each_deferred_pocket_has_a_line_of_its_own_before_the_deciding_result(tmp_path):
    task = dp.build_pocket_loop(tmp_path, dp.everywhere_step("1"))

    _, block = _gate(task, dp.everywhere_work("1"))

    deferred = dp.deferred_lines(block)
    assert len(deferred) == 2, block
    assert dp.lines_naming(block, "Deferred:", BENCH) != [], block
    assert dp.lines_naming(block, "Deferred:", ROOT) != [], block
    assert dp.lines_after_the_first_result(block, "Deferred:") == [], block
    assert dp.last_line(block).startswith("Result:"), block


def test_a_deferred_line_says_its_pocket_waits_for_the_checkpoint_and_no_scope_line_names_it(
    tmp_path,
):
    task = dp.build_pocket_loop(tmp_path, dp.widening_step("1", BENCH))

    _, block = _gate(task, dp.widening_work("1", BENCH))

    naming_bench = dp.lines_naming(block, "Deferred:", BENCH)
    assert len(naming_bench) == 1, block
    assert "checkpoint" in naming_bench[0].lower(), naming_bench
    assert dp.lines_naming(block, "Scope:", BENCH) == [], block
    assert dp.lines_naming(block, "Scope:", ROOT) != [], block


# -- The reconciler reads a deferral as no evidence either way ------------------------------------


def test_the_reconciler_gives_a_deferring_step_the_verdict_its_check_decides(tmp_path):
    task = dp.build_pocket_loop(
        tmp_path, dp.widening_step("1", BENCH), outcomes={BENCH.label: "fails"}
    )
    recorded, _ = _gate(task, dp.widening_work("1", BENCH))

    verdict = reconciler_verdict(task, "1")

    assert verdict["verdict"] == "verified-complete", verdict
    assert verdict["decided_by"] == "check", verdict
    assert verdict["verdict"] == recorded.recorded["gate"]["verdict"], recorded.doc


def test_the_reconciler_reads_a_deferring_block_as_the_same_block_without_its_deferred_lines(
    tmp_path,
):
    task = dp.build_pocket_loop(tmp_path, dp.widening_step("1", BENCH))
    _, block = _gate(task, dp.widening_work("1", BENCH))
    assert dp.deferred_lines(block) != [], block
    with_deferral = reconciler_verdict(task, "1")
    results = task.task_dir / "TEST_RESULTS.md"

    results.write_text(dp.without_deferred_lines(dp.results_text(task)), encoding="utf-8")

    assert reconciler_verdict(task, "1") == with_deferral


# -- A step with no check gates as today ----------------------------------------------------------


def test_a_step_with_no_check_runs_its_widened_pocket_whole_beside_its_narrow_one(tmp_path):
    task = dp.build_pocket_loop(tmp_path, dp.widening_step("1", BENCH, declares_check=False))

    recorded, block = _gate(task, dp.widening_work("1", BENCH))

    assert dp.whole_suite_runs(task, BENCH) == 1, block
    assert dp.deferred_lines(block) == [], block
    assert recorded.recorded["gate"]["verdict"] == "verified-complete", recorded.doc
    assert reconciler_verdict(task, "1")["verdict"] == "verified-complete"


def test_a_step_with_no_check_whose_change_only_widens_runs_it_whole_and_reads_unverified(
    tmp_path,
):
    step = dp.widening_step("1", BENCH, declares_check=False)
    task = dp.build_pocket_loop(tmp_path, step, base_files=_own_files_already_there(step))

    recorded, block = _gate(task, dp.widening_work("1", BENCH, touches_files=False))

    assert dp.whole_suite_runs(task, BENCH) == 1, block
    assert dp.deferred_lines(block) == [], block
    assert recorded.recorded["gate"]["verdict"] != "verified-complete", recorded.doc
    assert recorded.recorded["commit"] is None, recorded.doc
    assert reconciler_verdict(task, "1")["verdict"] != "verified-complete"


def test_a_committed_step_with_no_check_leaves_nothing_for_the_checkpoint(tmp_path):
    task = dp.build_pocket_loop(tmp_path, dp.widening_step("1", BENCH, declares_check=False))
    recorded, _ = _gate(task, dp.widening_work("1", BENCH))
    assert recorded.recorded["commit"] is not None, recorded.doc

    finished = dp.next_until_settled(task)

    assert finished.outcome == "complete", finished.doc
    assert dp.whole_suite_runs(task, BENCH) == 1
