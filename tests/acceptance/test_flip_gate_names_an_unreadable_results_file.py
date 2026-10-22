"""A cited run whose results file cannot be read is refused naming that file and why.

When a switched record cites a run whose lineage holds a results file that cannot be read
or parsed, the commit gate refuses the record with a finding that names the file and why it
could not be read, never as a disagreement about the run's lineage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.acceptance.drivers import adherence_runs as runs
from tests.acceptance.drivers import adherence_scoring as scoring
from tests.acceptance.drivers import kernel_sandbox
from tests.acceptance.drivers.flip_evidence import results_path
from tests.acceptance.drivers.flip_gate import (
    RESULTS_SUBDIR,
    cited_switch_record,
    earlier_id,
    passing_id,
    switch_with_flag,
)
from tests.acceptance.drivers.kernel_adoption import AdherenceRun, AdoptionRecord
from tests.acceptance.drivers.kernel_sandbox import Sandbox, commit_gate, regenerate

ROLE = "researcher"
LINEAGE_DISAGREEMENTS = ("I9-run-pairs-differ", "I9-run-flag-disagrees")
SPOILED = {
    "not JSON": b'{"run": {"id": "cut off mid-wr',
    "not UTF-8 text": b"\xff\xfe\x00\x9c" * 64,
}


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return kernel_sandbox.build_template(tmp_path_factory.mktemp("plugin") / "checkout")


@pytest.fixture
def sandbox(template: Path, tmp_path: Path) -> Sandbox:
    return kernel_sandbox.new_sandbox(template, tmp_path / "plugin")


@pytest.mark.parametrize("run", ["earlier", "passing"])
@pytest.mark.parametrize("spoiled", sorted(SPOILED))
def test_a_cited_run_with_an_unreadable_results_file_is_refused_naming_the_file(
    sandbox: Sandbox, run: str, spoiled: str
) -> None:
    record = cited_switch_record(sandbox.root, ROLE)
    switch_with_flag(sandbox, record)
    regenerate(sandbox.root)
    run_id = earlier_id(ROLE) if run == "earlier" else passing_id(ROLE)
    results_path(sandbox.root, run_id).write_bytes(SPOILED[spoiled])

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, "the gate let a record citing an unreadable results file through"
    assert f"{run_id}.json" in verdict.output, verdict.output
    lineage_findings = [kind for kind in LINEAGE_DISAGREEMENTS if kind in verdict.output]
    assert lineage_findings == [], verdict.output


# -- A continued run whose uncited earlier part cannot be read ----------------------------------

# A stand-in run of identical outcomes in both arms whose credit runs out mid-way, then is
# continued: two parts of one lineage, clear, with at least twenty complete pairs.
CLEAR_PLAN = runs.Plan(max_tasks=24)
CLEAR_STOPPING = runs.Script(
    by_task={(p, arm): runs.credit_exhausted(p) for p in range(12, 15) for arm in ("full", "lean")}
)


# The spoiled file's bytes no longer match the run index, which the gate reports on its own;
# the scenarios judge the findings beside that one.
STALE_INDEX = "I9-run-index-stale"
UNREADABLE_WHY = re.compile(r"json|utf-?8|decod|pars|not text|cannot be read|unreadable", re.I)
MISSING_PART = re.compile(r"no results file holds|no one lineage", re.I)


def _findings_beside_the_stale_index(output: str) -> list[str]:
    return [
        line.strip()
        for line in output.splitlines()
        if line.strip().startswith("I") and not line.strip().startswith(STALE_INDEX)
    ]


@dataclass(frozen=True)
class Lineage:
    earlier: Path  # the stopped part, which the record does not cite
    continued: Path  # the continuation, which the record cites
    pairs: int
    clear: bool


@pytest.fixture(scope="module")
def lineage(tmp_path_factory: pytest.TempPathFactory) -> Lineage:
    workspace = tmp_path_factory.mktemp("lineage")
    checkout = runs.new_checkout(workspace / "checkout")
    stopped = runs.run_with_stand_in(workspace / "first", checkout, CLEAR_PLAN, CLEAR_STOPPING)
    continued = runs.continue_run(workspace / "second", checkout, stopped.results_path, CLEAR_PLAN)
    report = runs.run_report(workspace, continued.results_path)
    return Lineage(
        earlier=stopped.results_path,
        continued=continued.results_path,
        pairs=runs.lineage_complete_pairs(continued.results_path, CLEAR_PLAN.role),
        clear=scoring.flip_verdict_class(report, CLEAR_PLAN.role) == "clear",
    )


def _switch_citing_only_the_continuation(sandbox: Sandbox, lineage: Lineage) -> None:
    for part in (lineage.earlier, lineage.continued):
        sandbox.write(f"{RESULTS_SUBDIR}/{part.name}", part.read_text(encoding="utf-8"))
    full = cited_switch_record(sandbox.root, CLEAR_PLAN.role)
    record = AdoptionRecord(
        CLEAR_PLAN.role,
        "switched",
        runs=(AdherenceRun(lineage.continued.stem, lineage.pairs, lineage.clear),),
        probe_before_tokens=full.probe_before_tokens,
        probe_after_tokens=full.probe_after_tokens,
        flip_rule_ratified=True,
        flip_ratified=True,
    )
    switch_with_flag(sandbox, record)
    regenerate(sandbox.root)


def test_a_record_citing_a_continued_run_whose_earlier_part_reads_cleanly_passes(
    sandbox: Sandbox, lineage: Lineage
) -> None:
    assert (lineage.pairs >= 20, lineage.clear) == (True, True), lineage
    _switch_citing_only_the_continuation(sandbox, lineage)

    verdict = commit_gate(sandbox.root)

    assert not verdict.refused, verdict.output


@pytest.mark.parametrize("spoiled", sorted(SPOILED))
def test_an_unreadable_uncited_earlier_part_is_refused_naming_its_file_not_a_lineage_disagreement(
    sandbox: Sandbox, lineage: Lineage, spoiled: str
) -> None:
    _switch_citing_only_the_continuation(sandbox, lineage)
    (sandbox.root / RESULTS_SUBDIR / lineage.earlier.name).write_bytes(SPOILED[spoiled])

    verdict = commit_gate(sandbox.root)

    findings = _findings_beside_the_stale_index(verdict.output)
    assert verdict.refused, "the gate let a lineage with an unreadable part through"
    naming_why = [f for f in findings if lineage.earlier.name in f and UNREADABLE_WHY.search(f)]
    assert naming_why, f"no finding names {lineage.earlier.name} and why:\n{verdict.output}"
    misread = [f for f in findings if MISSING_PART.search(f) or f.startswith(LINEAGE_DISAGREEMENTS)]
    assert misread == [], verdict.output
