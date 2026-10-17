"""A switched record's cited runs resolve to their results files, and the gate reads its parent ledger.

The commit gate resolves every run a switched record cites, `passing_run` included, to a
results file of that role, and refuses the commit, naming the role and the run, when a
cited run has no results file, measured another role, recorded other complete pairs,
disagrees with its pass flag, or, as the passing run, holds fewer than 20 complete pairs
or a verdict other than clear. A parent commit's ledger the gate cannot read refuses as
an input error; a parent commit with no ledger is still read as none.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from tests.acceptance.drivers import flip_gate, kernel_adoption, kernel_sandbox
from tests.acceptance.drivers.flip_gate import (
    CLEAR_24,
    NOT_CLEAR_24,
    UNDERPOWERED_13,
    cited_switch_record,
    passing_id,
    plant_results,
    switch_with_flag,
)
from tests.acceptance.drivers.kernel_adoption import AdherenceRun, AdoptionRecord
from tests.acceptance.drivers.kernel_sandbox import (
    ADOPTION_LEDGER,
    Sandbox,
    commit_gate,
    regenerate,
)

ROLE = "researcher"


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return kernel_sandbox.build_template(tmp_path_factory.mktemp("plugin") / "checkout")


@pytest.fixture
def sandbox(template: Path, tmp_path: Path) -> Sandbox:
    return kernel_sandbox.new_sandbox(template, tmp_path / "plugin")


def with_passing_run(record: AdoptionRecord, **changes: object) -> AdoptionRecord:
    *earlier, passing = record.runs
    return replace(record, runs=(*earlier, replace(passing, **changes)))


def gate_on_switch(sandbox: Sandbox, record: AdoptionRecord) -> kernel_sandbox.GateVerdict:
    switch_with_flag(sandbox, record)
    regenerate(sandbox.root)
    return commit_gate(sandbox.root)


def assert_refused_naming(verdict: kernel_sandbox.GateVerdict, run_id: str) -> None:
    assert verdict.refused, "the gate let the switched record through"
    assert ROLE in verdict.output, verdict.output
    assert run_id in verdict.output, f"the refusal does not name the run {run_id}"


def test_the_adoption_ledger_as_committed_passes_the_gate(sandbox: Sandbox) -> None:
    verdict = commit_gate(sandbox.root)

    assert not verdict.refused, verdict.output


def test_a_switched_record_whose_cited_runs_resolve_to_their_results_passes(
    sandbox: Sandbox,
) -> None:
    verdict = gate_on_switch(sandbox, cited_switch_record(sandbox.root, ROLE))

    assert not verdict.refused, verdict.output


def test_a_switched_record_citing_a_run_with_no_results_file_is_refused(sandbox: Sandbox) -> None:
    record = cited_switch_record(sandbox.root, ROLE)
    flip_gate.remove_results(sandbox.root, passing_id(ROLE))

    verdict = gate_on_switch(sandbox, record)

    assert_refused_naming(verdict, passing_id(ROLE))


def test_a_switched_record_citing_a_run_of_another_role_is_refused(sandbox: Sandbox) -> None:
    record = cited_switch_record(sandbox.root, ROLE)
    plant_results(sandbox.root, passing_id(ROLE), CLEAR_24, "verifier")

    verdict = gate_on_switch(sandbox, record)

    assert_refused_naming(verdict, passing_id(ROLE))


def test_a_switched_record_whose_complete_pairs_differ_from_its_results_is_refused(
    sandbox: Sandbox,
) -> None:
    record = with_passing_run(cited_switch_record(sandbox.root, ROLE), complete_pairs=23)

    verdict = gate_on_switch(sandbox, record)

    assert_refused_naming(verdict, passing_id(ROLE))


def test_a_cited_run_whose_pass_flag_disagrees_with_its_results_verdict_is_refused(
    sandbox: Sandbox,
) -> None:
    record = cited_switch_record(sandbox.root, ROLE)
    early, passing = record.runs
    flagged = replace(record, runs=(replace(early, passes_flip_rule=True), passing))

    verdict = gate_on_switch(sandbox, flagged)

    assert_refused_naming(verdict, early.run_id)


def test_a_passing_run_whose_results_hold_fewer_than_twenty_pairs_is_refused(
    sandbox: Sandbox,
) -> None:
    record = cited_switch_record(sandbox.root, ROLE)
    pairs = plant_results(sandbox.root, passing_id(ROLE), UNDERPOWERED_13, ROLE)

    verdict = gate_on_switch(sandbox, with_passing_run(record, complete_pairs=pairs))

    assert_refused_naming(verdict, passing_id(ROLE))


def test_a_passing_run_whose_results_verdict_is_not_clear_is_refused(sandbox: Sandbox) -> None:
    record = cited_switch_record(sandbox.root, ROLE)
    pairs = plant_results(sandbox.root, passing_id(ROLE), NOT_CLEAR_24, ROLE)

    verdict = gate_on_switch(sandbox, with_passing_run(record, complete_pairs=pairs))

    assert_refused_naming(verdict, passing_id(ROLE))


def test_an_unchanged_switched_record_citing_a_missing_results_file_is_refused(
    sandbox: Sandbox,
) -> None:
    run = AdherenceRun("20261014T152926Z-723e7a", 24, True)
    sandbox.delete(f"{flip_gate.RESULTS_SUBDIR}/{run.run_id}.json")

    verdict = commit_gate(sandbox.root)

    assert_refused_naming(verdict, run.run_id)


# -- The parent commit's ledger ------------------------------------------------------------


def test_a_parent_ledger_the_gate_cannot_read_is_refused_as_an_input_error(
    sandbox: Sandbox,
) -> None:
    ledger = flip_gate.commit_unreadable_parent_ledger(sandbox.root)

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, "the gate judged an unreadable parent ledger as no ledger"
    assert Path(ledger).name in verdict.output, verdict.output


def test_a_parent_commit_holding_no_ledger_is_still_read_as_none(sandbox: Sandbox) -> None:
    flip_gate.commit_without_ledger(sandbox)
    kernel_adoption.rewrite(sandbox.root, AdoptionRecord("verifier", "trial"))
    regenerate(sandbox.root)

    verdict = commit_gate(sandbox.root)

    assert (sandbox.root / ADOPTION_LEDGER).is_file()
    assert not verdict.refused, verdict.output
