"""A continued run is one declared run, from its stop through its report to a flip record citing it.

The journey crosses the adherence eval's console entry and the commit gate: a run stops on
a repeated infrastructure failure in both arms, is continued, and then reads as one run
everywhere: its verdict equals the verdict over the same counted pairs taken as one run,
its report names every part of its lineage with its stop, a later run lists it once, and a
switched record citing any part of it is judged as one citing the whole lineage.
"""

from __future__ import annotations

from pathlib import Path

from tests.acceptance.drivers import adherence_runs as runs
from tests.acceptance.drivers import adherence_scoring as scoring
from tests.acceptance.drivers import flip_gate, kernel_sandbox
from tests.acceptance.drivers.adherence_runs import Plan, Script, credit_exhausted, graded_failure
from tests.acceptance.drivers.kernel_adoption import AdherenceRun, AdoptionRecord

PLAN = Plan(max_tasks=6)
STOP_AT = 3  # the planned task at which the credit runs out in both arms
OUTCOMES = Script(by_task={(1, "full"): graded_failure(), (4, "lean"): graded_failure()})
STOPPING = Script(
    by_task={
        **OUTCOMES.by_task,
        **{(p, arm): credit_exhausted(p) for p in range(STOP_AT, 6) for arm in ("full", "lean")},
    }
)


def stopped_then_continued(
    tmp_path: Path, checkout: Path
) -> tuple[runs.StandInRun, runs.StandInRun]:
    stopped = runs.run_with_stand_in(tmp_path / "first", checkout, PLAN, STOPPING)
    continued = runs.continue_run(
        tmp_path / "second", checkout, stopped.results_path, PLAN, OUTCOMES
    )
    return stopped, continued


def test_a_continued_runs_verdict_equals_the_verdict_over_the_same_pairs_as_one_run(
    tmp_path: Path,
) -> None:
    whole = runs.run_with_stand_in(
        tmp_path / "whole", runs.new_checkout(tmp_path / "a"), PLAN, OUTCOMES
    )
    _, continued = stopped_then_continued(tmp_path, runs.new_checkout(tmp_path / "b"))

    verdicts = [
        scoring.flip_verdict_class(runs.run_report(tmp_path, r.results_path), PLAN.role)
        for r in (whole, continued)
    ]

    assert verdicts[0] == verdicts[1]


def test_a_continued_runs_report_names_every_part_of_its_lineage_with_its_stop(
    tmp_path: Path,
) -> None:
    stopped, continued = stopped_then_continued(tmp_path, runs.new_checkout(tmp_path))

    report = runs.run_report(tmp_path, continued.results_path)
    parts = runs.lineage(continued.results_path)

    assert [p.run_id for p in parts] == [stopped.results_path.stem, continued.results_path.stem]
    assert parts[0].stop
    assert parts[-1].stop is None
    assert all(p.run_id in report for p in parts), "the report does not name every part"
    assert "continued" in report.lower()


def test_a_later_run_lists_a_continued_lineage_once(tmp_path: Path) -> None:
    checkout = runs.new_checkout(tmp_path)
    stopped, continued = stopped_then_continued(tmp_path, checkout)

    later = runs.run_with_stand_in(tmp_path / "later", checkout, PLAN, OUTCOMES)
    listed = runs.earlier_runs(later.results_path, PLAN.role)

    assert [d.run_ids for d in listed.draws] == [
        (stopped.results_path.stem, continued.results_path.stem)
    ]


CLEAR_PLAN = Plan(max_tasks=24)
CLEAR_STOPPING = Script(
    by_task={(p, arm): credit_exhausted(p) for p in range(12, 15) for arm in ("full", "lean")}
)


def clear_lineage(tmp_path: Path) -> tuple[list[Path], int, bool]:
    """A stand-in lineage of identical outcomes in both arms: its parts, pairs and verdict."""
    checkout = runs.new_checkout(tmp_path / "lineage")
    stopped = runs.run_with_stand_in(tmp_path / "first", checkout, CLEAR_PLAN, CLEAR_STOPPING)
    continued = runs.continue_run(tmp_path / "second", checkout, stopped.results_path, CLEAR_PLAN)
    report = runs.run_report(tmp_path, continued.results_path)
    pairs = runs.lineage_complete_pairs(continued.results_path, CLEAR_PLAN.role)
    clear = scoring.flip_verdict_class(report, CLEAR_PLAN.role) == "clear"
    return [stopped.results_path, continued.results_path], pairs, clear


def gate_on_citing(
    template: Path, dest: Path, parts: list[Path], cited: list[Path], pairs: int, clear: bool
) -> bool:
    """Whether the commit gate refuses a switch of the role whose runs cite `cited`."""
    sandbox = kernel_sandbox.new_sandbox(template, dest)
    for part in parts:
        sandbox.write(f"{flip_gate.RESULTS_SUBDIR}/{part.name}", part.read_text(encoding="utf-8"))
    full = flip_gate.cited_switch_record(sandbox.root, CLEAR_PLAN.role)
    record = AdoptionRecord(
        CLEAR_PLAN.role,
        "switched",
        runs=tuple(AdherenceRun(path.stem, pairs, clear) for path in cited),
        probe_before_tokens=full.probe_before_tokens,
        probe_after_tokens=full.probe_after_tokens,
        flip_rule_ratified=True,
        flip_ratified=True,
    )
    flip_gate.switch_with_flag(sandbox, record)
    kernel_sandbox.regenerate(sandbox.root)
    return kernel_sandbox.commit_gate(sandbox.root).refused


def test_a_switched_record_is_judged_the_same_whichever_part_of_a_lineage_it_cites(
    tmp_path: Path,
) -> None:
    parts, pairs, clear = clear_lineage(tmp_path)
    template = kernel_sandbox.build_template(tmp_path / "template")

    first = gate_on_citing(template, tmp_path / "first-cited", parts, parts[:1], pairs, clear)
    later = gate_on_citing(template, tmp_path / "later-cited", parts, parts[1:], pairs, clear)

    assert pairs >= 20, f"the stand-in lineage holds {pairs} complete pairs"
    assert first == later


def test_a_record_citing_two_parts_of_one_lineage_counts_one_run(tmp_path: Path) -> None:
    parts, pairs, clear = clear_lineage(tmp_path)
    template = kernel_sandbox.build_template(tmp_path / "template")

    one = gate_on_citing(template, tmp_path / "one-part", parts, parts[1:], pairs, clear)
    both = gate_on_citing(template, tmp_path / "both-parts", parts, parts, pairs, clear)

    assert one == both
