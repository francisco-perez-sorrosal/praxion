"""A run that finalizes or is closed records, per role, what its lineage stands on.

Journey through the adherence eval's console entry with every session a stand-in: a run
finalizes (or a stopped run is closed), its results file records for each role the
lineage's complete pairs, flip label and the checks it scored (those its verdict gives a
per-check verdict and does not leave uncovered), and the run index rebuilt by
`--reindex` carries the same list beside the pairs and the label, while the results files
already in the directory keep every byte.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tests.acceptance.drivers import adherence_runs, flip_evidence
from tests.acceptance.drivers.adherence_runs import Plan, Script
from tests.acceptance.drivers.flip_gate import reindex

ROLE = adherence_runs.ROLE
SMALL_PLAN = Plan(max_tasks=3)
REQUIRED_PAIRS = ("--required-pairs", "2")  # a verdict over three tasks, so checks are scored


def _bytes_of_results(checkout: Path) -> dict[str, str]:
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in adherence_runs.results_dir(checkout).glob("2*.json")
    }


def test_a_finalized_run_records_and_indexes_the_checks_it_scored(tmp_path):
    checkout = adherence_runs.new_checkout(tmp_path)
    earlier = _bytes_of_results(checkout)

    run = adherence_runs._run_console(tmp_path, checkout, SMALL_PLAN, Script(), REQUIRED_PAIRS)
    reindex(checkout)

    assert run.results_path.is_file(), run.stderr[-2000:]
    verdict = json.loads(run.results_path.read_text())["verdicts"][ROLE]
    standing = flip_evidence.recorded_standing(run.results_path, ROLE)
    assert standing.complete_pairs == verdict["complete_pairs"]
    assert standing.flip == verdict.get("flip")
    assert sorted(standing.scored_checks) == flip_evidence.scored_in_verdict(verdict)
    assert standing.scored_checks, "a verdict over complete pairs scored no check"
    indexed = flip_evidence.index_scored_checks(checkout, run.results_path.stem, ROLE)
    assert sorted(indexed) == sorted(standing.scored_checks)
    entry = flip_evidence.read_index(checkout)["runs"][run.results_path.stem]["roles"][ROLE]
    assert (entry["complete_pairs"], entry["flip"]) == (standing.complete_pairs, standing.flip)
    assert {k: v for k, v in _bytes_of_results(checkout).items() if k in earlier} == earlier


def test_a_closed_run_records_its_lineage_standing_and_the_index_carries_it(tmp_path):
    checkout = adherence_runs.new_checkout(tmp_path)
    shapes = adherence_runs.EIGHT_SHAPES
    stopped = adherence_runs.plant_stopped_run(
        tmp_path, checkout, Plan(max_tasks=len(shapes)), shapes
    )
    before = _bytes_of_results(checkout)

    closed = adherence_runs.close_run(tmp_path, checkout, stopped.path, "operator closed it")
    reindex(checkout)

    written = sorted(
        name for name, digest in _bytes_of_results(checkout).items() if before.get(name) != digest
    )
    assert written, f"closing wrote no results file: {closed.stderr[-2000:]}"
    path = adherence_runs.results_dir(checkout) / written[-1]
    standing = flip_evidence.recorded_standing(path, ROLE)
    assert standing.complete_pairs == adherence_runs.lineage_complete_pairs(path, ROLE)
    indexed = flip_evidence.index_scored_checks(checkout, path.stem, ROLE)
    assert sorted(indexed) == sorted(standing.scored_checks)
