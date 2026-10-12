"""C3 is judged; when judging is unavailable or not requested it is withheld with that reason."""

from __future__ import annotations

from tests.acceptance.drivers.adherence_eval import (
    SessionEvidence,
    grade,
    scratch_repo,
    session_envelope,
    session_places,
)


def test_without_judging_the_assumption_and_objection_check_is_withheld_with_its_reason(tmp_path):
    repo = scratch_repo(tmp_path)
    places = session_places(tmp_path)
    envelope = session_envelope(
        role="researcher",
        cwd=repo.root,
        plugin_copy=places.plugin_copy,
        return_text="Assumption: 'cache' means the HTTP cache.\n[COMPLETE]",
    )

    outcome = grade(
        SessionEvidence("researcher", repo, envelope, places, judging=False), ["C3"]
    ).outcome("C3")

    assert outcome.kind == "withheld"
    assert (outcome.reason or "").strip(), "a withheld check carries its reason"
