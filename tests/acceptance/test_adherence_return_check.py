"""C2: the role returns a pointer of at most 15 lines ending in exactly one terminal marker.

The return judged is the role's own, as the harness recorded it -- never the main
session's relay of it. A role whose definition sets a tighter cap (the
implementer's is 5 lines) is held to that cap.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.adherence_eval import (
    SessionEvidence,
    grade,
    scratch_repo,
    session_envelope,
    session_places,
)


def _return_check(tmp_path, role: str, return_text: str, relay_text: str | None = None) -> str:
    repo = scratch_repo(tmp_path)
    places = session_places(tmp_path)
    envelope = session_envelope(
        role=role,
        cwd=repo.root,
        plugin_copy=places.plugin_copy,
        return_text=return_text,
        relay_text=relay_text,
    )
    return grade(SessionEvidence(role, repo, envelope, places), ["C2"]).outcome("C2").kind


def _lines(count: int, marker: str = "[COMPLETE]") -> str:
    return "\n".join([f"- point {i}" for i in range(1, count)] + [marker])


def test_a_return_without_a_terminal_marker_fails(tmp_path):
    assert (
        _return_check(tmp_path, "researcher", "Findings are in RESEARCH_FINDINGS.md.") == "failed"
    )


def test_a_return_ending_in_two_markers_fails(tmp_path):
    assert (
        _return_check(tmp_path, "researcher", "Findings written.\n[BLOCKED] [COMPLETE]") == "failed"
    )


@pytest.mark.parametrize(("lines", "expected"), [(15, "passed"), (16, "failed")])
def test_a_return_is_held_to_fifteen_lines(tmp_path, lines, expected):
    assert _return_check(tmp_path, "researcher", _lines(lines)) == expected


@pytest.mark.parametrize(("lines", "expected"), [(5, "passed"), (6, "failed")])
def test_the_implementer_is_held_to_its_own_five_line_cap(tmp_path, lines, expected):
    assert _return_check(tmp_path, "implementer", _lines(lines)) == expected


def test_a_marker_only_the_main_sessions_relay_adds_does_not_count(tmp_path):
    outcome = _return_check(
        tmp_path,
        "verifier",
        return_text="The report is in VERIFICATION_REPORT.md.",
        relay_text="The verifier finished.\n[COMPLETE]",
    )

    assert outcome == "failed"
