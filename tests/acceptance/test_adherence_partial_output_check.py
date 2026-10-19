"""C5: a forced early stop leaves the role's durable output in its own partial form.

The task variant stops the role after its definition requires the durable output
to exist and before it can finish. The researcher's definition states the form:
the title carries `[PARTIAL]` and a `**Completed phases**:` line follows it. A hard
stop leaves no return the agent authored, so C2 does not apply to that variant. The
check binds only on a session the record shows ran out of turns: each scenario's
spawn result carries the harness's turn-limit note ahead of the role's partial return.
"""

from __future__ import annotations

from tests.acceptance.drivers.adherence_eval import (
    SessionEvidence,
    grade,
    scratch_repo,
    session_envelope,
    session_places,
    write,
)
from tests.acceptance.drivers.adherence_scoring import TURN_LIMIT_NOTE

SKELETON_BODY = "\n## Summary\n[pending]\n\n## Sources\n[pending]\n"


def _stopped_researcher(tmp_path, findings: str, checks=("C5",)):
    repo = scratch_repo(tmp_path)
    places = session_places(tmp_path)
    path = repo.put(".ai-work/adherence-task/RESEARCH_FINDINGS.md", findings)
    envelope = session_envelope(
        role="researcher",
        cwd=repo.root,
        plugin_copy=places.plugin_copy,
        actions=[write(path, findings)],
        return_text="This is my last turn. I am writing the final report now.",
        spawn_result_note=TURN_LIMIT_NOTE,
    )
    evidence = SessionEvidence("researcher", repo, envelope, places, forced_stop=True)
    return grade(evidence, list(checks))


def test_a_stopped_role_whose_title_lacks_the_partial_marker_fails(tmp_path):
    findings = (
        "# Research Findings: idempotency keys\n\n**Completed phases**: 1, 2\n" + SKELETON_BODY
    )

    assert _stopped_researcher(tmp_path, findings).outcome("C5").kind == "failed"


def test_a_stopped_role_with_its_partial_title_and_progress_line_passes(tmp_path):
    findings = (
        "# Research Findings: idempotency keys [PARTIAL]\n\n**Completed phases**: 1, 2\n"
        + SKELETON_BODY
    )

    assert _stopped_researcher(tmp_path, findings).outcome("C5").kind == "passed"


def test_a_partial_title_without_the_progress_line_its_definition_states_fails(tmp_path):
    findings = "# Research Findings: idempotency keys [PARTIAL]\n" + SKELETON_BODY

    assert _stopped_researcher(tmp_path, findings).outcome("C5").kind == "failed"


def test_the_return_check_does_not_apply_to_a_forced_stop(tmp_path):
    findings = (
        "# Research Findings: idempotency keys [PARTIAL]\n\n**Completed phases**: 1\n"
        + SKELETON_BODY
    )

    graded = _stopped_researcher(tmp_path, findings, checks=("C2", "C5"))

    assert graded.outcome("C2").kind == "not applicable"
