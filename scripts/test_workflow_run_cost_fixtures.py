"""Golden-journal fixture guard for `workflow_run_cost.py` / `_workflow_run.py`
(td-232): anchors `read_journal` and `test_workflow_run_cost.py`'s own
`_write_journal` fixture helper to a real harness run, and guards the
committed fixture's own byte-identity.

Kept in its own file, separate from `test_workflow_run_cost_worldread.py`,
for a mechanical reason: these tests read
`scripts/test_fixtures/workflow_run/` from disk at runtime, and
`scripts/mutation_sensor.py`'s flat, `.py`-only sandbox (its own docstring:
"source_paths is the explicit list of the target directory's own top-level
`*.py` files") never copies that non-Python fixture directory into its
execution sandbox -- a file depending on it would refuse the mutation run
outright (`run-failed`) rather than merely fail to attribute. This file is
therefore deliberately excluded from `mutation_sensor.py --tests`;
`test_workflow_run_cost_worldread.py` (fixtures built entirely in
`tmp_path`) is the one passed instead.

Reuses `test_workflow_run_cost.py`'s own fixture builders directly via a
plain module import (DAMP favors composing the existing builders over
re-deriving the run-directory layout a second time).

Import strategy: same `importlib.import_module` RED/GREEN-deferred-import
convention as the sibling files in this directory.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))


def _load():
    return importlib.import_module("workflow_run_cost")


wfc = _load()

import test_workflow_run_cost as base  # noqa: E402 -- after sys.path insertion

_FIXTURES_DIR = Path(__file__).resolve().parent / "test_fixtures" / "workflow_run"
_GOLDEN_JOURNAL = _FIXTURES_DIR / "journal_golden.jsonl"
_PROVENANCE = _FIXTURES_DIR / "PROVENANCE.md"


def _per_type_key_sets(records: list[dict]) -> dict[str, set]:
    grouped: dict[str, set] = {}
    for record in records:
        grouped.setdefault(record["type"], set()).update(record.keys())
    return grouped


# --------------------------------------------------------------------------- #
# golden-fixture integrity + read_journal / _write_journal shape-compat
# --------------------------------------------------------------------------- #
def test_golden_journal_fixture_sha256_matches_its_recorded_provenance():
    """A pre-commit whitespace/EOF fixer, or an editor re-save, would
    silently break byte-identity with the source harness run this fixture
    was copied from -- this test is the tripwire."""
    provenance_text = _PROVENANCE.read_text(encoding="utf-8")
    match = re.search(r"sha256\*\*:\s*`([0-9a-f]{64})`", provenance_text)
    assert match, "PROVENANCE.md must record a sha256 hash"

    actual = hashlib.sha256(_GOLDEN_JOURNAL.read_bytes()).hexdigest()

    assert actual == match.group(1)


def test_read_journal_parses_the_golden_harness_fixture_to_the_expected_roster(tmp_path):
    """`journal.jsonl`, byte-identical to a real Workflow run (see
    `PROVENANCE.md`), parses to the two-agent roster with both results
    present -- the golden fixture is the sole source of truth; nothing here
    is hand-transcribed a second time."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "journal.jsonl").write_bytes(_GOLDEN_JOURNAL.read_bytes())

    roster = wfc.wr.read_journal(run_dir)

    assert roster == {
        "a7065c7bcb9c98b45": {
            "label": "probe:hooks",
            "phase": "Probe",
            "journal_result": "present",
        },
        "a7be5ed2ac3f45a30": {
            "label": "probe:scripts",
            "phase": "Probe",
            "journal_result": "present",
        },
    }


def test_write_journal_emits_records_whose_per_type_key_set_matches_the_golden_harness_journal(
    tmp_path,
):
    """`test_workflow_run_cost.py`'s own fixture writer must not drift from
    the harness's real journal shape; the golden fixture is parsed directly
    for the comparison, never hand-transcribed a second time."""
    golden_records = [
        json.loads(line) for line in _GOLDEN_JOURNAL.read_text(encoding="utf-8").splitlines()
    ]
    expected = _per_type_key_sets(golden_records)

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    base._write_journal(run_dir, [dict(a) for a in base._DEFAULT_AGENTS])
    written_records = [
        json.loads(line)
        for line in (run_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert _per_type_key_sets(written_records) == expected
