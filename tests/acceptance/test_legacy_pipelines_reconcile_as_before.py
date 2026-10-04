"""Plans and progress files without the new fields reconcile exactly as they did before.

A pipeline whose plan declares no `Check:` and whose `WIP.md` records no attempt
count gets, from today's reconciler, the same steps, verdicts, recovery fields
and exit status the reconciler at the base commit gave it. Fields the change adds
to a verdict are allowed; no field the base reconciler emitted may change value.

The base reconciler is materialized from version control into a temporary
directory and run side by side with the working one over the same pipeline.
"""

from __future__ import annotations

import io
import subprocess
import tarfile
from pathlib import Path

import pytest

from tests.acceptance.drivers.step_checks import (
    REPO_ROOT,
    StepSetup,
    build_task,
    reconcile_raw,
)

BASE_COMMIT = "2d6ec71e"
SENSOR_REFUSAL = "Mutation: unavailable reason=run-failed (the sensor could not produce a reading)"

LEGACY_PIPELINES = {
    "otherwise-done": (StepSetup(number="1", title="Write the widget"),),
    "claimed-but-nothing-changed": (
        StepSetup(number="1", title="Write the widget", files_changed=False),
    ),
    "done-but-unclaimed": (StepSetup(number="1", title="Write the widget", claimed_done=False),),
    "claimed-with-a-red-run": (
        StepSetup(number="1", title="Write the widget", result="Result: pass=3 fail=1 skip=0"),
    ),
    "claimed-with-no-recorded-run": (StepSetup(number="1", title="Write the widget", result=None),),
    "green-with-acceptance-tests-pending": (
        StepSetup(
            number="1", title="Write the widget", result="Result: pass=4 fail=0 skip=0 pending=2"
        ),
    ),
    "mutation-tagged-without-a-reading": (
        StepSetup(
            number="1",
            title="Write the widget",
            tag="mutation: on",
            mutation_line=SENSOR_REFUSAL,
        ),
    ),
    "not-started": (
        StepSetup(
            number="1",
            title="Write the widget",
            files_changed=False,
            claimed_done=False,
            result=None,
        ),
    ),
    "one-done-one-not-started": (
        StepSetup(number="1", title="Write the widget"),
        StepSetup(
            number="2",
            title="Read the widget",
            files_changed=False,
            claimed_done=False,
            result=None,
        ),
    ),
}


def _base_commit_available() -> bool:
    probe = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "cat-file", "-e", f"{BASE_COMMIT}^{{commit}}"],
        capture_output=True,
        timeout=30,
    )
    return probe.returncode == 0


@pytest.fixture(scope="module")
def base_reconciler(tmp_path_factory) -> Path:
    if not _base_commit_available():
        pytest.skip(
            f"the base commit {BASE_COMMIT} is not in this clone's history (shallow clone); "
            "fetch full history to compare against the reconciler before the change"
        )
    archive = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "archive", "--format=tar", BASE_COMMIT, "scripts", "hooks"],
        capture_output=True,
        check=True,
        timeout=120,
    )
    target = tmp_path_factory.mktemp("base-reconciler")
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(target, filter="data")
    return target / "scripts" / "reconcile_pipeline_state.py"


def _changed_base_fields(before: list[dict], after: list[dict]) -> list[str]:
    changes = []
    for old, new in zip(before, after, strict=True):
        changes.extend(
            f"{old['step']}.{key}: {old[key]!r} -> {new.get(key, '<missing>')!r}"
            for key in old
            if new.get(key, object()) != old[key]
        )
    return changes


@pytest.mark.parametrize("pipeline", sorted(LEGACY_PIPELINES))
def test_legacy_pipeline_reconciles_to_the_same_verdicts_and_exit_status(
    tmp_path, base_reconciler, pipeline
):
    task = build_task(tmp_path, *LEGACY_PIPELINES[pipeline])
    base_exit, base_verdicts = reconcile_raw(task, base_reconciler)

    exit_code, verdicts = reconcile_raw(task)

    assert exit_code == base_exit
    assert [v["step"] for v in verdicts] == [v["step"] for v in base_verdicts]
    assert _changed_base_fields(base_verdicts, verdicts) == []
