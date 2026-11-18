"""A paired run's files go to a results directory of their own, and the ones committed keep reading.

Started without `--output`, a run of the paired axis writes its results file and its run index in
the paired directory, and adds nothing to the directory the adoption gate reads; a reindex of the
paired axis rebuilds the paired directory's index. The three paired runs already committed stay
where they are: a reindex of their directory reproduces the index it holds, and each renders a
report. The adoption gate's parity test passes and the adoption gate stays clean.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.acceptance.drivers import adherence_eval, adherence_runs
from tests.acceptance.drivers import paired_move_runs as paired

ROLE = "implementer"
REPO_ROOT = adherence_eval.REPO_ROOT
COMMITTED_PAIRED = REPO_ROOT / ".ai-state" / "eval_ledger" / "adherence" / paired.AXIS


def _top_level_files(checkout: Path) -> set[str]:
    directory = adherence_runs.results_dir(checkout)
    return {p.name for p in directory.glob("*") if p.is_file()} if directory.is_dir() else set()


def _console(workspace: Path, checkout: Path, *args: str) -> subprocess.CompletedProcess[str]:
    tripwire = adherence_eval.install_tripwire(adherence_runs._fresh_directory(workspace, "cli"))
    return adherence_runs._console(checkout, tripwire.bin_dir, [str(checkout), *args])


def _index(directory: Path) -> dict:
    return json.loads((directory / "index.json").read_text(encoding="utf-8"))


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    return paired.new_checkout(tmp_path)


@pytest.fixture
def committed_copy(checkout: Path) -> Path:
    """The committed paired runs, placed in the checkout as they sit in this repository."""
    target = paired.paired_results_dir(checkout)
    shutil.copytree(COMMITTED_PAIRED, target)
    return target


def test_a_paired_run_without_output_writes_its_results_and_index_in_the_paired_directory(
    tmp_path, checkout
):
    before = _top_level_files(checkout)

    run = paired.stopped_paired_run(tmp_path, checkout, ROLE)

    paired.assert_stopped(run)
    assert run.results_path.parent == paired.paired_results_dir(checkout), run.results_path
    assert run.results_path.stem in _index(paired.paired_results_dir(checkout))["runs"]
    assert _top_level_files(checkout) == before, "the paired run wrote where the gate reads"


def test_a_reindex_of_the_paired_axis_rebuilds_the_paired_directory_index(tmp_path, checkout):
    run = paired.stopped_paired_run(tmp_path, checkout, ROLE)
    (paired.paired_results_dir(checkout) / "index.json").unlink()
    before = _top_level_files(checkout)

    done = _console(tmp_path, checkout, "--axis", paired.AXIS, "--reindex")

    assert done.returncode == 0, done.stderr[-2000:]
    assert run.results_path.stem in _index(paired.paired_results_dir(checkout))["runs"]
    assert _top_level_files(checkout) == before, "the reindex wrote where the gate reads"


def test_a_reindex_of_the_committed_paired_runs_reproduces_the_index_they_hold(
    tmp_path, checkout, committed_copy
):
    held = _index(committed_copy)
    (committed_copy / "index.json").unlink()

    done = _console(tmp_path, checkout, "--axis", paired.AXIS, "--reindex")

    assert done.returncode == 0, done.stderr[-2000:]
    assert _index(committed_copy) == held


@pytest.mark.parametrize(
    "results", sorted(p.name for p in COMMITTED_PAIRED.glob("*.json") if p.name != "index.json")
)
def test_each_committed_paired_run_still_renders_its_report(tmp_path, results):
    rendering = paired.report(tmp_path, COMMITTED_PAIRED / results)

    assert rendering.exit_code == 0, rendering.stderr[-2000:]
    assert rendering.text.strip(), f"{results} rendered an empty report"


def test_the_adoption_gate_parity_test_passes_and_the_gate_stays_clean():
    parity = subprocess.run(
        [sys.executable, "-m", "pytest", "scripts/test_kernel_run_evidence_parity.py", "-q"]
        + ["-n", "0", "--no-cov", "-p", "no:cacheprovider"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    gate = subprocess.run(
        [sys.executable, "scripts/check_kernel_manifest.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )

    assert parity.returncode == 0, parity.stdout[-3000:]
    assert gate.returncode == 0, gate.stdout[-2000:] + gate.stderr[-1000:]
