"""The iteration ledger: one append-only record per implementer return, read through one shape.

When an implementer spawn returns or stops, one record -- the step, the attempt,
the agent's id, the reconciler verdict with the criterion that decided it, the
step's test result line, the commit holding the work or an explicit none, and why
the agent stopped -- can be appended to a pipeline artifact in the task's working
directory. Earlier records never change, a record that breaks the shape is
reported with its position rather than skipped or guessed, an absent or empty
ledger reads as no history, and the ledger is a registered pipeline artifact with
its writer, readers and shape documented.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace

import pytest

from tests.acceptance.drivers.iteration_ledger import (
    IterationRecord,
    StopReason,
    append_malformed_record,
    append_record,
    create_empty_ledger,
    ledger_artifact_name,
    read_ledger,
    task_dir,
)
from tests.acceptance.drivers.step_checks import REPO_ROOT, Criterion

INVENTORY = REPO_ROOT / "skills" / "software-planning" / "references" / "artifact-inventory.md"

FIRST_RETURN = IterationRecord(
    step="1",
    attempt=1,
    agent_id="a3f9c2e17b",
    verdict="mismatch",
    criterion=Criterion.CHECK,
    test_result="Result: pass=4 fail=0 skip=0 pending=2",
    commit=None,
    stop_reason=StopReason.TURN_CAP,
)
SECOND_RETURN = IterationRecord(
    step="1",
    attempt=2,
    agent_id="b81d04a6c3",
    verdict="verified-complete",
    criterion=Criterion.CHECK,
    test_result="Result: pass=6 fail=0 skip=0 pending=0",
    commit="04569546",
    stop_reason=StopReason.COMPLETED,
)


def _load_registry():
    spec = importlib.util.spec_from_file_location(
        "artifact_registry", REPO_ROOT / "scripts" / "artifact_registry.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("stop_reason", list(StopReason), ids=lambda r: r.name.lower())
def test_appended_record_reads_back_with_every_field_for_each_stop_reason(tmp_path, stop_reason):
    directory = task_dir(tmp_path)
    record = replace(SECOND_RETURN, stop_reason=stop_reason)

    append_record(directory, record)

    assert read_ledger(directory).records == (record,)


def test_record_with_no_commit_reads_back_stating_that_none_holds_the_work(tmp_path):
    directory = task_dir(tmp_path)

    append_record(directory, FIRST_RETURN)

    assert read_ledger(directory).records[0].commit is None


def test_appending_a_record_leaves_every_earlier_record_unchanged(tmp_path):
    directory = task_dir(tmp_path)
    append_record(directory, FIRST_RETURN)

    append_record(directory, SECOND_RETURN)

    assert read_ledger(directory).records == (FIRST_RETURN, SECOND_RETURN)


def test_record_that_breaks_the_shape_is_reported_with_its_position_never_guessed(tmp_path):
    directory = task_dir(tmp_path)
    append_record(directory, FIRST_RETURN)
    append_malformed_record(directory)
    append_record(directory, SECOND_RETURN)

    reading = read_ledger(directory)

    assert [f.record_position for f in reading.findings] == [2], reading.findings
    assert reading.records == (FIRST_RETURN, SECOND_RETURN), (
        "the malformed record must be reported, not returned with guessed fields"
    )


def test_absent_ledger_reads_as_no_history(tmp_path):
    directory = task_dir(tmp_path)

    reading = read_ledger(directory)

    assert reading.records == ()
    assert reading.findings == ()


def test_empty_ledger_reads_as_no_history(tmp_path):
    directory = task_dir(tmp_path)
    create_empty_ledger(directory)

    reading = read_ledger(directory)

    assert reading.records == ()
    assert reading.findings == ()


def test_artifact_registry_lists_the_ledger_as_a_task_scoped_pipeline_artifact():
    registry = _load_registry()

    artifact = registry.by_name(ledger_artifact_name())

    assert artifact is not None, "the iteration ledger is missing from the artifact registry"
    assert artifact.location == "ai-work"


def _inventory_entries_naming(name: str) -> str:
    lines = INVENTORY.read_text(encoding="utf-8").splitlines()
    return " ".join(line for line in lines if name in line).lower()


def test_artifact_inventory_documents_the_ledgers_writer_readers_and_shape():
    name = ledger_artifact_name()

    documented = _inventory_entries_naming(name)

    assert "writer" in documented, documented
    assert "orchestrator" in documented, documented
    assert "reader" in documented, documented
    assert "shape" in documented, documented
