"""A writer role's paired run, planned and then reported, says which modes its claim rests on.

The operator plans the test-engineer's or the systems-architect's run with the dry run, the run
leaves its results file, and the report renders it: beside the role's flip claim it names each
mode the run covered with that mode's count of complete pairs, and lists every other mode of the
role's definition as unmeasured.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers.writer_kits import COVERED_MODES, UNMEASURED_MODES, WRITER_ROLES
from tests.e2e.drivers.writer_report_journey import RecordedRun, report_of_a_recorded_run

COVERED = [(role, mode) for role in WRITER_ROLES for mode in COVERED_MODES[role]]
UNMEASURED = [(role, mode) for role in WRITER_ROLES for mode in UNMEASURED_MODES[role]]


@pytest.fixture(scope="module")
def runs(tmp_path_factory) -> dict[str, RecordedRun]:
    return {
        role: report_of_a_recorded_run(tmp_path_factory.mktemp(f"{role}-journey"), role)
        for role in WRITER_ROLES
    }


def lines_naming(report: str, mode: str) -> list[str]:
    return [line for line in report.splitlines() if re.search(rf"\b{re.escape(mode)}\b", line)]


@pytest.mark.parametrize(("role", "mode"), COVERED)
def test_the_report_names_a_covered_mode_with_its_count_of_complete_pairs(runs, role, mode):
    run = runs[role]
    count = run.complete_pairs[mode]

    counted = [line for line in lines_naming(run.report, mode) if re.search(rf"\b{count}\b", line)]

    assert counted, f"no line names {mode} with {count} complete pairs:\n{run.report[-3000:]}"


@pytest.mark.parametrize(("role", "mode"), UNMEASURED)
def test_the_report_lists_another_mode_of_the_role_as_unmeasured(runs, role, mode):
    report = runs[role].report

    unmeasured = [line for line in lines_naming(report, mode) if "unmeasured" in line.lower()]

    assert unmeasured, f"the {role}'s report does not list {mode} as unmeasured:\n{report[-3000:]}"
