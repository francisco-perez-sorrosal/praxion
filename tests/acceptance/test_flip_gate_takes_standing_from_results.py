"""The flip gate judges a cited run by what its results files record, not by the index.

A switched record's passing run must have scored the role's convention check. Each cited
run's lineage, complete pairs and flip standing are derived from the results files; an
index or a record that claims otherwise is refused, naming the role and the run (and both
figures for a count), even when every digest in the index is intact. Each refusal sits
beside its known-good counterpart.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from tests.acceptance.drivers import flip_evidence, kernel_sandbox
from tests.acceptance.drivers.flip_gate import (
    NOT_CLEAR_24,
    UNDERPOWERED_13,
    cited_switch_record,
    earlier_id,
    passing_id,
    plant_results,
    switch_with_flag,
)
from tests.acceptance.drivers.kernel_adoption import AdoptionRecord
from tests.acceptance.drivers.kernel_sandbox import Sandbox, commit_gate, regenerate

ROLE = "researcher"
PASSING = passing_id(ROLE)


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return kernel_sandbox.build_template(tmp_path_factory.mktemp("plugin") / "checkout")


@pytest.fixture
def sandbox(template: Path, tmp_path: Path) -> Sandbox:
    return kernel_sandbox.new_sandbox(template, tmp_path / "plugin")


def with_passing_run(record: AdoptionRecord, **changes: object) -> AdoptionRecord:
    *earlier, passing = record.runs
    return replace(record, runs=(*earlier, replace(passing, **changes)))


def judge(sandbox: Sandbox, record: AdoptionRecord, *index_edits) -> kernel_sandbox.GateVerdict:
    """Write the switch (the index rebuilt from the results), apply hand edits, run the gate."""
    switch_with_flag(sandbox, record)
    for edit in index_edits:
        edit(sandbox.root)
    regenerate(sandbox.root)
    return commit_gate(sandbox.root)


def assert_refused_naming(verdict, run_id: str, *figures: int) -> None:
    assert verdict.refused, "the gate let the switched record through"
    assert ROLE in verdict.output, verdict.output
    assert run_id in verdict.output, f"the refusal does not name the run {run_id}"
    for figure in figures:
        assert str(figure) in verdict.output, f"the refusal does not state {figure}"


# -- The passing run scored the convention check ------------------------------------------


def test_a_passing_run_that_scored_the_convention_check_passes(sandbox):
    verdict = judge(sandbox, cited_switch_record(sandbox.root, ROLE))

    assert not verdict.refused, verdict.output


def test_a_passing_run_that_left_the_convention_check_uncovered_is_refused(sandbox):
    record = cited_switch_record(sandbox.root, ROLE)
    flip_evidence.leave_convention_uncovered(sandbox.root, PASSING, ROLE)

    verdict = judge(sandbox, record)

    assert_refused_naming(verdict, PASSING)


def test_a_passing_run_whose_verdict_records_no_scored_checks_is_refused(sandbox):
    record = cited_switch_record(sandbox.root, ROLE)
    flip_evidence.drop_check_verdicts(sandbox.root, PASSING, ROLE)

    verdict = judge(sandbox, record)

    assert_refused_naming(verdict, PASSING)


# -- Complete pairs and lineage come from the results files ---------------------------------


def test_an_index_and_record_raising_a_runs_pairs_are_refused_naming_both_figures(sandbox):
    record = with_passing_run(cited_switch_record(sandbox.root, ROLE), complete_pairs=30)

    verdict = judge(
        sandbox,
        record,
        lambda root: flip_evidence.hand_edit_index(root, PASSING, ROLE, complete_pairs=30),
    )

    assert_refused_naming(verdict, PASSING, 30, 24)


def test_an_underpowered_run_dressed_as_clear_in_the_index_is_refused(sandbox):
    record = cited_switch_record(sandbox.root, ROLE)
    plant_results(sandbox.root, PASSING, UNDERPOWERED_13, ROLE)

    verdict = judge(
        sandbox,
        with_passing_run(record, complete_pairs=24),
        lambda root: flip_evidence.hand_edit_index(
            root, PASSING, ROLE, complete_pairs=24, flip="clear"
        ),
    )

    assert_refused_naming(verdict, PASSING, 24, 13)


def test_an_index_regrouping_two_runs_into_one_lineage_is_refused(sandbox):
    record = cited_switch_record(sandbox.root, ROLE)

    verdict = judge(
        sandbox,
        record,
        lambda root: flip_evidence.hand_edit_index(root, PASSING, lineage_root=earlier_id(ROLE)),
    )

    assert_refused_naming(verdict, PASSING)


def test_a_results_file_recording_more_pairs_than_its_sessions_give_is_refused(sandbox):
    record = with_passing_run(cited_switch_record(sandbox.root, ROLE), complete_pairs=30)
    flip_evidence.record_complete_pairs(sandbox.root, PASSING, ROLE, 30)

    verdict = judge(sandbox, record)

    assert_refused_naming(verdict, PASSING, 30, 24)


def test_a_task_whose_latest_lean_session_errored_is_not_a_complete_pair(sandbox):
    record = cited_switch_record(sandbox.root, ROLE)
    flip_evidence.add_later_errored_lean_session(sandbox.root, PASSING, ROLE)

    verdict = judge(sandbox, record)

    assert_refused_naming(verdict, PASSING, 24, 23)


def test_a_task_whose_lean_error_came_before_its_measured_session_stays_complete(sandbox):
    record = cited_switch_record(sandbox.root, ROLE)
    flip_evidence.add_earlier_errored_lean_session(sandbox.root, PASSING, ROLE)

    verdict = judge(sandbox, record)

    assert not verdict.refused, verdict.output


# -- Flip standing comes from the results files ------------------------------------------------


def test_a_not_clear_run_labelled_clear_in_the_index_is_refused(sandbox):
    record = cited_switch_record(sandbox.root, ROLE)
    plant_results(sandbox.root, PASSING, NOT_CLEAR_24, ROLE)

    verdict = judge(
        sandbox,
        record,
        lambda root: flip_evidence.hand_edit_index(root, PASSING, ROLE, flip="clear"),
    )

    assert_refused_naming(verdict, PASSING)


def test_an_earlier_run_labelled_clear_in_the_index_and_the_record_is_refused(sandbox):
    record = cited_switch_record(sandbox.root, ROLE)
    early, passing = record.runs
    flagged = replace(record, runs=(replace(early, passes_flip_rule=True), passing))

    verdict = judge(
        sandbox,
        flagged,
        lambda root: flip_evidence.hand_edit_index(root, early.run_id, ROLE, flip="clear"),
    )

    assert_refused_naming(verdict, early.run_id)
