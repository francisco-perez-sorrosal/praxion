"""C1: the role's durable output is where its definition puts it, and nothing is written elsewhere.

The evidence is the session's recorded tool calls and the scratch repository's
changes against its fixture commit -- never what the agent says it did.
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

FINDINGS = (
    "# Research Findings: idempotency keys\n\n"
    "**Completed phases**: 1, 2, 3, 4, 5\n\n"
    "## Summary\nKeys expire after 24 hours [1].\n\n"
    "## Sources\n[1] https://docs.example.com/api/idempotency\n"
)
RETURN = "Findings: .ai-work/adherence-task/RESEARCH_FINDINGS.md\n- keys expire after 24 hours\n[COMPLETE]"


def test_findings_in_the_slug_directory_and_no_other_write_pass(tmp_path):
    repo = scratch_repo(tmp_path)
    places = session_places(tmp_path)
    findings = repo.put(".ai-work/adherence-task/RESEARCH_FINDINGS.md", FINDINGS)
    envelope = session_envelope(
        role="researcher",
        cwd=repo.root,
        plugin_copy=places.plugin_copy,
        actions=[write(findings, FINDINGS)],
        return_text=RETURN,
    )

    graded = grade(SessionEvidence("researcher", repo, envelope, places), ["C1"])

    assert graded.outcome("C1").kind == "passed"


def test_a_write_outside_the_slug_directory_fails(tmp_path):
    repo = scratch_repo(tmp_path)
    places = session_places(tmp_path)
    findings = repo.put(".ai-work/adherence-task/RESEARCH_FINDINGS.md", FINDINGS)
    stray = repo.put("notes/scratch.md", "working notes\n")
    envelope = session_envelope(
        role="researcher",
        cwd=repo.root,
        plugin_copy=places.plugin_copy,
        actions=[write(findings, FINDINGS), write(stray, "working notes\n")],
        return_text=RETURN,
    )

    graded = grade(SessionEvidence("researcher", repo, envelope, places), ["C1"])

    assert graded.outcome("C1").kind == "failed"


def test_a_durable_output_the_agent_only_claims_to_have_written_fails(tmp_path):
    repo = scratch_repo(tmp_path)
    places = session_places(tmp_path)
    envelope = session_envelope(
        role="researcher",
        cwd=repo.root,
        plugin_copy=places.plugin_copy,
        actions=[],
        return_text=RETURN,
    )

    graded = grade(SessionEvidence("researcher", repo, envelope, places), ["C1"])

    assert graded.outcome("C1").kind == "failed"
