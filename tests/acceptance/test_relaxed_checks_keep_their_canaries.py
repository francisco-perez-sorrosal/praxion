"""Each relaxed reading keeps a canary its check still fails.

The catalog pairs every check with violation evidence the check must fail. The write-early
check keeps one of a session that ended on its own with `[PARTIAL]` still in its title, and
one of a capped session whose report opened late or unmarked; C5 keeps one of a capped
verifier report with an unmarked title and a section still `[pending]`, and one with an
unmarked title and no verdict.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.capped_reports import Canary, canaries, write_early_check


def outcomes_of(found: list[Canary]) -> set[str]:
    assert found, "the catalog pairs no canary of this case with the check"
    return {canary.outcome for canary in found}


@pytest.mark.parametrize("role", ["verifier", "sentinel"])
def test_the_write_early_check_fails_its_canary_of_a_session_that_ended_with_partial_kept(role):
    found = [
        c
        for c in canaries(role, write_early_check(role))
        if c.ending == "ended on its own" and c.final_title_marked
    ]

    assert outcomes_of(found) == {"failed"}


@pytest.mark.parametrize("role", ["verifier", "sentinel"])
def test_the_write_early_check_fails_its_canary_of_a_capped_session_that_opened_badly(role):
    found = [
        c
        for c in canaries(role, write_early_check(role))
        if c.ending == "stopped at cap" and c.opening in {"late", "unmarked"}
    ]

    assert outcomes_of(found) == {"failed"}


def test_c5_fails_its_canary_of_an_unmarked_capped_verifier_report_with_a_pending_section():
    found = [
        c
        for c in canaries("verifier", "C5")
        if c.ending == "stopped at cap" and c.final_title_marked is False and c.pending_sections
    ]

    assert outcomes_of(found) == {"failed"}


def test_c5_fails_its_canary_of_an_unmarked_capped_verifier_report_with_no_verdict():
    found = [
        c
        for c in canaries("verifier", "C5")
        if c.ending == "stopped at cap" and c.final_title_marked is False and c.verdict is None
    ]

    assert outcomes_of(found) == {"failed"}
