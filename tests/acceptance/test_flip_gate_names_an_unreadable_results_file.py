"""A cited run whose results file cannot be read is refused naming that file and why.

When a switched record cites a run whose lineage holds a results file that cannot be read
or parsed, the commit gate refuses the record with a finding that names the file and why it
could not be read, never as a disagreement about the run's lineage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import kernel_sandbox
from tests.acceptance.drivers.flip_evidence import results_path
from tests.acceptance.drivers.flip_gate import (
    cited_switch_record,
    earlier_id,
    passing_id,
    switch_with_flag,
)
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
