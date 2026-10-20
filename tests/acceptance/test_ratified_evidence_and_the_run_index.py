"""The evidence already in the results directory stays valid, and the index lists what each run scored.

Rebuilt by `--reindex`, the index carries for every entry and role the checks the run
scored beside its complete pairs and flip label, and the results files written before
this change keep every byte. Over that index the stricter gate reports nothing new: the
committed adoption ledger passes, and for every committed results file the lineage,
complete pairs and flip standing the gate derives equal what the eval derived.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from tests.acceptance.drivers import flip_evidence, kernel_adoption, kernel_sandbox
from tests.acceptance.drivers.flip_gate import (
    CLEAR_24,
    RESULTS_SUBDIR,
    passing_id,
    plant_results,
    reindex,
    switch_with_flag,
)
from tests.acceptance.drivers.kernel_adoption import AdherenceRun, AdoptionRecord
from tests.acceptance.drivers.kernel_sandbox import REPO_ROOT, Sandbox, commit_gate, regenerate

ROLE = "researcher"
# The results files at the base commit: the evidence every switched and held record rests on.
BASE_RUNS = (
    "20261014T023850Z-809185",
    "20261014T031818Z-d71d91",
    "20261014T033052Z-4f6604",
    "20261014T045733Z-7050ca",
    "20261014T152926Z-723e7a",
    "20261015T035717Z-03a785",
    "20261015T082642Z-672192",
    "20261016T024750Z-62073e",
)


def _committed(run_id: str) -> Path:
    return REPO_ROOT / RESULTS_SUBDIR / f"{run_id}.json"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def reindexed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A copy of the committed results directory, its index rebuilt by `--reindex`."""
    root = tmp_path_factory.mktemp("results")
    shutil.copytree(REPO_ROOT / RESULTS_SUBDIR, root / RESULTS_SUBDIR)
    reindex(root)
    return root


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return kernel_sandbox.build_template(tmp_path_factory.mktemp("plugin") / "checkout")


@pytest.fixture
def sandbox(template: Path, tmp_path: Path) -> Sandbox:
    return kernel_sandbox.new_sandbox(template, tmp_path / "plugin")


# -- The index lists what each run scored ---------------------------------------------------


@pytest.mark.parametrize("run_id", BASE_RUNS)
def test_reindexing_keeps_every_earlier_results_file_byte_for_byte(reindexed, run_id):
    rebuilt = reindexed / RESULTS_SUBDIR / f"{run_id}.json"

    assert _digest(rebuilt) == _digest(_committed(run_id))


@pytest.mark.parametrize("run_id", BASE_RUNS)
def test_the_index_lists_the_checks_each_earlier_run_scored_per_role(reindexed, run_id):
    verdicts = json.loads(_committed(run_id).read_text(encoding="utf-8"))["verdicts"]
    index = flip_evidence.read_index(reindexed)

    listed = {
        role: sorted(flip_evidence.index_scored_checks(reindexed, run_id, role))
        for role in index["runs"][run_id]["roles"]
    }

    assert listed == {role: flip_evidence.scored_in_verdict(v) for role, v in verdicts.items()}


# -- The ratified evidence still passes ------------------------------------------------------


def test_the_committed_ledger_over_a_reindexed_results_directory_passes(sandbox):
    reindex(sandbox.root)
    regenerate(sandbox.root)

    verdict = commit_gate(sandbox.root)

    assert not verdict.refused, verdict.output


@pytest.mark.parametrize("run_id", BASE_RUNS)
def test_the_gate_derives_each_committed_runs_standing_as_the_eval_does(sandbox, run_id):
    """A copy of the run, cited at the figures the eval's index gives it, passes the gate."""
    source_role = next(iter(json.loads(_committed(run_id).read_text())["verdicts"]))
    copy_id = f"20261103T000000Z-{run_id[-6:]}"
    plant_results(sandbox.root, copy_id, (run_id, source_role, 0), ROLE)
    plant_results(sandbox.root, passing_id(ROLE), CLEAR_24, ROLE)
    reindex(sandbox.root)
    eval_says = flip_evidence.read_index(sandbox.root)["runs"][copy_id]["roles"][ROLE]
    full = kernel_adoption.full_switch_record(ROLE)
    record = AdoptionRecord(
        ROLE,
        "switched",
        runs=(
            AdherenceRun(copy_id, eval_says["complete_pairs"], eval_says["flip"] == "clear"),
            AdherenceRun(passing_id(ROLE), CLEAR_24[2], True),
        ),
        probe_before_tokens=full.probe_before_tokens,
        probe_after_tokens=full.probe_after_tokens,
        flip_rule_ratified=True,
        flip_ratified=True,
    )
    switch_with_flag(sandbox, record)
    regenerate(sandbox.root)

    verdict = commit_gate(sandbox.root)

    assert not verdict.refused, verdict.output
