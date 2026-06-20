"""Documentation-verification tests for the Checkpoint Digest ### Spec Drift subsection.

The orchestrator (LLM) is the renderer — there is no Python rendering function.
These tests verify that coordination-details.md contains the documented contract
for the Spec Drift subsection so the orchestrator can follow it correctly.

All assertions match on stable tokens and substrings rather than full-line
equality to stay robust to minor prose edits.
"""

from __future__ import annotations

from pathlib import Path

_COORDINATION_DETAILS = (
    Path(__file__).parent.parent
    / "skills"
    / "software-planning"
    / "references"
    / "coordination-details.md"
)


def _doc() -> str:
    return _COORDINATION_DETAILS.read_text(encoding="utf-8")


def _spec_drift_section() -> str:
    """Extract the text of the ### Spec Drift subsection from coordination-details.md.

    The subsection starts at the '### Spec Drift' heading and ends just before the
    next heading of equal-or-higher level (## or ###).  Assertions scoped to this
    slice will FAIL if the Spec Drift prose is deleted, even if the same tokens
    appear elsewhere in the document.
    """
    text = _doc()
    start = text.find("### Spec Drift")
    if start == -1:
        return ""
    # Find the next heading of equal-or-higher level after the start
    import re

    next_heading = re.search(r"\n(?:#{1,3}) ", text[start + 1 :])
    if next_heading:
        end = start + 1 + next_heading.start()
        return text[start:end]
    return text[start:]


def test_checkpoint_digest_documents_spec_drift_subsection() -> None:
    """The pre-verification checkpoint digest section contains a ### Spec Drift heading."""
    text = _doc()
    assert "### Spec Drift" in text, (
        "coordination-details.md must contain a '### Spec Drift' heading inside "
        "the Checkpoint Digest section so the orchestrator knows the subsection exists."
    )


def test_checkpoint_digest_documents_conditional_omission() -> None:
    """The prose instructs that the subsection is omitted when there are no findings."""
    section = _spec_drift_section()
    # Look for the conditional-omission instruction — stable tokens are "omit" and
    # "findings" appearing in the Spec Drift section.  Accept either "omit" or
    # "omitted" to tolerate minor wording variation.
    has_omit = "omit" in section.lower()
    has_findings_context = "findings" in section
    assert has_omit and has_findings_context, (
        "The ### Spec Drift subsection of coordination-details.md must document "
        "that the subsection is omitted when detect_drift returns no findings. "
        f"'omit' found={has_omit}, 'findings' found={has_findings_context}."
    )


def test_checkpoint_digest_documents_advisory_only() -> None:
    """The prose states the Spec Drift subsection is advisory and never blocks."""
    section = _spec_drift_section()
    # Accept "advisory" or "never blocks" (both are present in the written prose)
    has_advisory = "advisory" in section.lower()
    has_never_block = "never block" in section.lower()
    assert has_advisory or has_never_block, (
        "The ### Spec Drift subsection of coordination-details.md must document "
        "that the subsection is advisory only and never blocks the pipeline. "
        f"'advisory' found={has_advisory}, 'never block' found={has_never_block}."
    )


def test_checkpoint_digest_documents_bullet_format() -> None:
    """The documented bullet format includes [<severity>] and the 'pointer:' token."""
    text = _doc()
    # The format line is: [<severity>] <req>: <rationale> — pointer: <pointer>
    # Match on stable tokens: severity placeholder marker and the literal "pointer:"
    has_severity_bracket = "[<severity>]" in text
    has_pointer_token = "pointer:" in text
    assert has_severity_bracket and has_pointer_token, (
        "coordination-details.md must document the bullet format containing "
        "'[<severity>]' and 'pointer:'. "
        f"'[<severity>]' found={has_severity_bracket}, 'pointer:' found={has_pointer_token}."
    )
