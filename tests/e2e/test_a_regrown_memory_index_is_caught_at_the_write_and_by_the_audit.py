"""A memory index that regrows past its budget is caught twice: at the write and by the audit.

A session's Write grows the index past 5,000 bytes. The guard lets it land and tells
the session; the harness writes it; the audit run afterwards reports the same index
with one size warning and exits 0. Two boundaries: the PreToolUse hook payload and
the audit's command line.
"""

from __future__ import annotations

from pathlib import Path

from tests.acceptance.drivers.memory_index import (
    audit,
    guard_write,
    index_lines,
    land_write,
    lengthened,
    names_number,
    size_findings,
    sized_index,
)


def test_a_write_past_the_budget_lands_with_a_warning_and_the_audit_then_reports_it(
    tmp_path: Path,
) -> None:
    home = sized_index(tmp_path, lines=39, total_bytes=4_990)
    grown = lengthened(index_lines(39, 4_990), 0, 20)

    guarded = guard_write(home, grown)
    land_write(home, grown)
    audited = audit(tmp_path, "--all", "--json")

    assert guarded.lets_the_write_land, guarded.stdout
    assert guarded.session_reads is not None, guarded.stdout
    assert home.size() == (5_010, 39)
    sized = size_findings(audited.findings_for(home.index))
    assert audited.exit_code == 0
    assert [f["severity"] for f in sized] == ["warn"], sized
    assert names_number(str(sized[0]), 5_010), sized[0]
