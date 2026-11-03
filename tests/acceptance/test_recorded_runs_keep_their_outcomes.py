"""Runs recorded before the checks changed keep their outcomes and stay apart from later runs.

Nothing in the eval ledger is rewritten: every file there keeps its bytes, and each kernel
trial's results file renders the verdicts it showed. A stopped run recorded before the
change is refused continuation under the changed checks, before anything launches.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from tests.acceptance.drivers import adherence_runs as runs
from tests.acceptance.drivers import adherence_scoring as scoring
from tests.acceptance.drivers.adherence_eval import REPO_ROOT

FIXTURES = Path(__file__).resolve().parent / "fixtures"
LEDGER = REPO_ROOT / ".ai-state" / "eval_ledger"
LEDGER_BEFORE = json.loads((FIXTURES / "eval_ledger_before.json").read_text(encoding="utf-8"))
TRIALS_BEFORE = {
    run_id: roles
    for run_id, roles in json.loads(
        (FIXTURES / "kernel_trial_verdicts_before.json").read_text(encoding="utf-8")
    ).items()
    if not run_id.startswith("_")
}
# The measured identity a results file carried before the checks changed: these keys, and per
# role its definition and kernel. Read off the results files committed at the base commit.
IDENTITY_BEFORE = ("tree", "model", "roles")
ROLE_IDENTITY_BEFORE = ("definition_sha", "kernel")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


# A directory's run index is derived from its results files and gains an entry whenever a later
# run is recorded, so its bytes are not frozen; what it held is (every run it named stays named).
RUN_INDEX = "index.json"
RECORDS_BEFORE = sorted(p for p in LEDGER_BEFORE["files"] if Path(p).name != RUN_INDEX)
INDEXED_BEFORE = {Path(p).parent for p in LEDGER_BEFORE["files"] if Path(p).name == RUN_INDEX}
RESULTS_BEFORE = [p for p in RECORDS_BEFORE if Path(p).parent in INDEXED_BEFORE]


@pytest.mark.parametrize("relpath", RECORDS_BEFORE)
def test_every_file_the_eval_ledger_held_keeps_its_bytes(relpath):
    path = LEDGER / relpath

    assert path.is_file(), f"{relpath} is gone from the eval ledger"
    assert digest(path) == LEDGER_BEFORE["files"][relpath], f"{relpath} was rewritten"


@pytest.mark.parametrize("relpath", RESULTS_BEFORE)
def test_every_run_the_eval_ledger_held_is_still_named_by_its_run_index(relpath):
    index = json.loads((LEDGER / Path(relpath).parent / RUN_INDEX).read_text(encoding="utf-8"))

    assert Path(relpath).stem in index["runs"], f"{relpath} was dropped from its run index"


@pytest.mark.parametrize("run_id", sorted(TRIALS_BEFORE))
def test_a_kernel_trial_renders_the_verdicts_it_showed(run_id):
    ((role, shown),) = TRIALS_BEFORE[run_id].items()

    with tempfile.TemporaryDirectory(prefix="trial-report-") as workspace:
        rendering = scoring.render(scoring.recorded_results_file(run_id), Path(workspace))
    checks = {
        name: next(
            (
                line.strip()
                for line in scoring.check_block(rendering.text, role, name).splitlines()
                if line.strip().startswith("verdict:")
            ),
            None,
        )
        for name in shown["checks"]
    }

    assert rendering.exit_code == 0, rendering.stderr[-2000:]
    assert scoring.flip_verdict_class(rendering.text, role) == shown["flip"]
    assert checks == shown["checks"]


def as_recorded_before_change(path: Path) -> None:
    """Give a planted results file the measured identity a run recorded before the change."""
    document = json.loads(path.read_text(encoding="utf-8"))
    identity = document["run"]["identity"]
    reduced = {key: identity[key] for key in IDENTITY_BEFORE if key in identity}
    reduced["roles"] = {
        role: {key: value[key] for key in ROLE_IDENTITY_BEFORE if key in value}
        for role, value in identity.get("roles", {}).items()
    }
    document["run"]["identity"] = reduced
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def test_a_stopped_run_recorded_before_the_change_is_refused_continuation(tmp_path):
    checkout = runs.new_checkout(tmp_path)
    plan = runs.Plan(role="verifier", max_tasks=len(runs.EIGHT_SHAPES))
    stopped = runs.plant_stopped_run(tmp_path, checkout, plan)
    as_recorded_before_change(stopped.path)
    recorded = stopped.path.read_bytes()

    result = runs.continue_run(tmp_path, checkout, stopped.path, plan)

    assert result.exit_code != 0, "the continuation was accepted"
    assert result.launches == (), f"the refused continuation launched {result.launches}"
    assert stopped.path.read_bytes() == recorded, "the refused run's results file was rewritten"
