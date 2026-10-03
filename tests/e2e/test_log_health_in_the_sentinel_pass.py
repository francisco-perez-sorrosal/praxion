"""The log-health family runs in the sentinel's automatic pass; the owner's gates still bite.

Inside a scratch copy of this repository: the family runner reports every
log-health check id (JSON and the Markdown table the sentinel reads), with a
warning for a session recorded under an invalid mode setting; the log owner's
consumer-contract, writer-truth and private-reader gates pass on this change's
state, and the private-reader gate still fails when a module outside the owner
reads an archive by name. Each copies the repository, hence the `large` marker.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.acceptance.drivers.log_health import Check, check_ids
from tests.acceptance.drivers.log_rows import session_start
from tests.e2e.drivers.log_retention import make_copy, run_family_runner, run_owner_gates

pytestmark = pytest.mark.large

TYPO_SESSION = "typo-session-0001"


def _copy_with_a_mistyped_mode_session(tmp_path: Path):
    copy = make_copy(tmp_path)
    copy.seed_project_log(
        [
            json.dumps(
                session_start(
                    TYPO_SESSION,
                    at="2026-09-20T10:00:00+00:00",
                    project="praxion",
                    source="invalid-setting",
                )
            )
        ]
    )
    return copy


def test_the_family_runner_reports_every_log_health_check(tmp_path: Path) -> None:
    ids = check_ids()
    copy = _copy_with_a_mistyped_mode_session(tmp_path)

    digest = json.loads(run_family_runner(copy))

    assert set(ids.values()) <= set(digest["checks"]), sorted(digest["checks"])
    assert digest["checks"][ids[Check.MODE_SOURCE]]["warn"] >= 1, digest["checks"][
        ids[Check.MODE_SOURCE]
    ]


def test_the_sentinel_table_lists_every_log_health_check(tmp_path: Path) -> None:
    ids = check_ids()
    copy = _copy_with_a_mistyped_mode_session(tmp_path)

    table = run_family_runner(copy, table=True)

    assert [check_id for check_id in sorted(ids.values()) if check_id not in table] == []


def test_the_log_owners_three_gates_pass_on_this_change(tmp_path: Path) -> None:
    copy = make_copy(tmp_path)

    result = run_owner_gates(copy)

    assert result.returncode == 0, result.stdout[-3000:]


def test_the_private_reader_gate_fails_on_a_module_that_reads_an_archive_by_name(
    tmp_path: Path,
) -> None:
    copy = make_copy(tmp_path)
    copy.write(
        "scripts/rogue_archive_reader.py", 'ROWS = open(".ai-state/observations.jsonl.1").read()\n'
    )
    copy.commit("a reader outside the owner")

    result = run_owner_gates(copy)

    assert result.returncode != 0, "the private-reader gate passed a direct archive reader"
    assert "rogue_archive_reader" in result.stdout, result.stdout[-3000:]
