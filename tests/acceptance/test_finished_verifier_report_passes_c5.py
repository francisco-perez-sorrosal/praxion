"""C5 credits a capped verifier for a report it finished, never for a stripped marker.

A verifier stopped at its turn cap whose report title carries no `[PARTIAL]` passes C5
only when no section still reads `[pending]` (a section closed as `[not reached]` counts)
and `## Verdict` names `PASS`, `PASS WITH FINDINGS` or `FAIL`; otherwise C5 fails and names
what is unfinished. The marked partial form passes for every role, as before; a role other
than the verifier fails on an unmarked title, as before, even when its report looks done.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.capped_reports import (
    FINISHED,
    SKELETON,
    VERDICTS,
    Report,
    body,
    c5,
    title,
)

# The progress lines each definition states for its partial form, beyond `**Completed phases**`.
PROGRESS_LINES = {
    "verifier": "",
    "researcher": "",
    "sentinel": "\n**Stopped at**: Phase 3 -- the turn cap",
}


def verifier_ending(text_body: str) -> Report:
    return Report("verifier", final_text=title("verifier", marked=False) + text_body)


@pytest.mark.parametrize("verdict", VERDICTS)
def test_a_capped_verifier_report_finished_and_unmarked_passes(verdict):
    assert c5(verifier_ending(body(verdict=verdict))).kind == "passed"


def test_a_section_closed_as_not_reached_counts_as_finished():
    closed = body(sections={"Summary": "Two criteria met.", "Findings": "[not reached]"})

    assert c5(verifier_ending(closed)).kind == "passed"


def test_an_unmarked_report_with_a_section_still_pending_fails_naming_that_section():
    unfinished = body(sections={"Summary": "Two criteria met.", "Coverage Gaps": "[pending]"})

    outcome = c5(verifier_ending(unfinished))

    assert outcome.kind == "failed"
    assert "Coverage Gaps" in (outcome.reason or ""), outcome


def test_an_unmarked_report_without_a_verdict_section_fails_naming_the_missing_verdict():
    outcome = c5(verifier_ending(body(verdict=None)))

    assert outcome.kind == "failed"
    assert "verdict" in (outcome.reason or "").lower(), outcome


@pytest.mark.parametrize("verdict", ["[pending]", "WARN", ""])
def test_an_unmarked_report_whose_verdict_names_no_outcome_fails(verdict):
    assert c5(verifier_ending(body(verdict=verdict))).kind == "failed"


def test_an_unmarked_skeleton_stripped_of_its_marker_fails():
    assert c5(verifier_ending(SKELETON)).kind == "failed"


@pytest.mark.parametrize("role", ["verifier", "sentinel", "researcher"])
def test_a_capped_report_carrying_partial_and_its_progress_line_passes(role):
    marked = Report(role, final_text=title(role, marked=True) + PROGRESS_LINES[role] + SKELETON)

    assert c5(marked).kind == "passed"


@pytest.mark.parametrize("role", ["sentinel", "researcher"])
def test_a_capped_report_of_another_role_fails_unmarked_even_when_finished(role):
    unmarked = Report(role, final_text=title(role, marked=False) + FINISHED)

    assert c5(unmarked).kind == "failed"
