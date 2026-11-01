"""The write-early check binds on a capped session's opening, never on its closing title.

The verifier and the sentinel write their report early, its title marked `[PARTIAL]`, and
take the marker off last. A late, unmarked or edited opening fails the check however the
session ended. A session the harness stopped at its turn cap is not judged on the title the
report ends with; one whose ending cannot be told is withheld unless its opening already
fails. A session that ended on its own, or ran with no lowered cap, still fails when its
title keeps `[PARTIAL]` or its report is gone.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.capped_reports import (
    FINISHED,
    SKELETON,
    WRITE_WINDOW,
    Report,
    title,
    write_early,
)

ROLES = ("verifier", "sentinel")
EVERY_ENDING = ("stopped at cap", "ended on its own", "unknown", "no lowered cap")


def still_partial(role: str) -> Report:
    return Report(role, final_text=title(role, marked=True) + SKELETON)


def finished_unmarked(role: str) -> Report:
    return Report(role, final_text=title(role, marked=False) + FINISHED)


# -- The opening binds on every session --------------------------------------------------------


@pytest.mark.parametrize("ending", EVERY_ENDING)
def test_a_verifier_report_first_written_after_its_third_call_fails_however_the_session_ended(
    ending,
):
    late = Report("verifier", opened_at_call=WRITE_WINDOW + 1)

    assert write_early(late, ending).kind == "failed"


@pytest.mark.parametrize("ending", EVERY_ENDING)
@pytest.mark.parametrize("role", ROLES)
def test_a_report_opened_without_the_partial_marker_fails_however_the_session_ended(role, ending):
    unmarked = Report(role, opened_marked=False)

    assert write_early(unmarked, ending).kind == "failed"


@pytest.mark.parametrize("ending", EVERY_ENDING)
@pytest.mark.parametrize("role", ROLES)
def test_a_report_first_recorded_as_an_edit_fails_however_the_session_ended(role, ending):
    edited = Report(role, opened_with="Edit")

    assert write_early(edited, ending).kind == "failed"


# -- A capped session is not judged on its closing title ---------------------------------------


@pytest.mark.parametrize("role", ROLES)
def test_a_capped_session_that_opened_in_time_passes_with_partial_still_in_its_title(role):
    assert write_early(still_partial(role), "stopped at cap").kind == "passed"


@pytest.mark.parametrize("role", ROLES)
def test_a_capped_session_that_opened_in_time_passes_with_its_title_unmarked(role):
    assert write_early(finished_unmarked(role), "stopped at cap").kind == "passed"


@pytest.mark.parametrize("role", ROLES)
def test_a_session_whose_ending_cannot_be_told_is_withheld_with_its_reason(role):
    outcome = write_early(still_partial(role), "unknown")

    assert outcome.kind == "withheld"
    assert outcome.reason, "the write-early check was withheld without a reason"


# -- A session that ended on its own must close its title --------------------------------------


@pytest.mark.parametrize("ending", ["ended on its own", "no lowered cap"])
@pytest.mark.parametrize("role", ROLES)
def test_a_session_with_the_turns_to_finish_fails_when_its_title_keeps_partial(role, ending):
    assert write_early(still_partial(role), ending).kind == "failed"


@pytest.mark.parametrize("ending", ["ended on its own", "no lowered cap"])
@pytest.mark.parametrize("role", ROLES)
def test_a_session_with_the_turns_to_finish_fails_when_its_report_ends_empty(role, ending):
    emptied = Report(role, final_text="")

    assert write_early(emptied, ending).kind == "failed"


@pytest.mark.parametrize("ending", ["ended on its own", "no lowered cap"])
@pytest.mark.parametrize("role", ROLES)
def test_a_session_with_the_turns_to_finish_passes_when_it_opened_in_time_and_closed(role, ending):
    assert write_early(finished_unmarked(role), ending).kind == "passed"
