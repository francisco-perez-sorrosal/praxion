"""Behavioral tests for the §5.2 markdown body renderer.

`render_candidate` projects a stored candidate dict into the fixed eight-
heading markdown structure that both the machine reporter and a human filing
manually in the browser share (SYSTEMS_PLAN.md § Interfaces -- "one artifact,
both entry paths"). `SECTION_HEADINGS`'s exact text/order is also what a
sibling template-drift guard (outside this module's scope) checks against
the shipped issue template, so it is load-bearing beyond this file.

Label application (`bug`, `auto-filed`, `category:<slug>`, `from-managed-
project`, never `ecosystem-feedback`) is a `gh issue create --label` /
issue-template-frontmatter concern, not part of the rendered markdown body --
render.py has no labels field to test.
"""

from __future__ import annotations

from scripts.praxion_feedback.render import (
    RESERVED_MAINTAINER_LABEL,
    SECTION_HEADINGS,
    build_issue_labels,
    render_candidate,
)


def _rendered_fields(**overrides: object) -> dict:
    fields: dict[str, object] = {
        "fingerprint": "abc123def456",
        "category": "scripts",
        "artifact_path": "scripts/praxion_feedback/fingerprint.py",
        "detected_by": "sentinel",
        "detection_point": "post-implementation audit",
        "confidence": "high",
        "expected": "normalize_error strips volatile tokens",
        "observed": "raises AttributeError on a None error string",
        "reproduction_command": (
            "python3 -m pytest scripts/praxion_feedback/tests/test_fingerprint.py"
        ),
        "evidence_excerpt": "AttributeError: 'NoneType' object has no attribute 'foo'",
        "environment": "macOS, Python 3.11",
        "regression_status": "new",
    }
    fields.update(overrides)
    return fields


class TestSectionHeadingsAreFixedAndOrdered:
    def test_declares_exactly_the_eight_schema_headings_in_order(self) -> None:
        assert SECTION_HEADINGS == (
            "Fingerprint",
            "Plugin / Component",
            "Capture Provenance",
            "Expected vs Observed",
            "Reproduction Command",
            "Evidence Excerpt (sanitized)",
            "Environment",
            "Regression Status",
        )


class TestRenderCandidateProducesAllHeadingsInOrder:
    def test_body_contains_every_heading_in_the_declared_order(self) -> None:
        body = render_candidate(_rendered_fields())

        positions = [body.index(f"## {heading}") for heading in SECTION_HEADINGS]
        assert positions == sorted(positions)

    def test_body_uses_exactly_the_declared_headings_no_more_no_fewer(self) -> None:
        body = render_candidate(_rendered_fields())

        heading_lines = [line for line in body.splitlines() if line.startswith("## ")]
        assert heading_lines == [f"## {heading}" for heading in SECTION_HEADINGS]


class TestRenderCandidateMapsFieldsUnderTheCorrectHeading:
    def test_fingerprint_field_lands_under_the_fingerprint_heading(self) -> None:
        body = render_candidate(_rendered_fields(fingerprint="fp-marker-99"))
        fingerprint_section = body.split("## Fingerprint", 1)[1].split("## ", 1)[0]
        assert "fp-marker-99" in fingerprint_section

    def test_reproduction_command_lands_under_the_reproduction_command_heading(self) -> None:
        body = render_candidate(_rendered_fields(reproduction_command="repro-marker-99"))
        repro_section = body.split("## Reproduction Command", 1)[1].split("## ", 1)[0]
        assert "repro-marker-99" in repro_section

    def test_evidence_excerpt_lands_under_the_evidence_excerpt_heading(self) -> None:
        body = render_candidate(_rendered_fields(evidence_excerpt="evidence-marker-99"))
        evidence_section = body.split("## Evidence Excerpt (sanitized)", 1)[1].split("## ", 1)[0]
        assert "evidence-marker-99" in evidence_section

    def test_regression_status_lands_under_the_regression_status_heading(self) -> None:
        body = render_candidate(_rendered_fields(regression_status="status-marker-99"))
        # Regression Status is the last declared heading -- no trailing
        # "## " boundary to split on.
        regression_section = body.split("## Regression Status", 1)[1]
        assert "status-marker-99" in regression_section


class TestRenderCandidateHandlesMissingOptionalFields:
    def test_missing_confidence_field_does_not_raise(self) -> None:
        fields = _rendered_fields()
        del fields["confidence"]

        body = render_candidate(fields)  # must not raise KeyError

        assert "## Capture Provenance" in body

    def test_missing_optional_field_renders_a_placeholder_not_the_string_none(self) -> None:
        fields = _rendered_fields()
        del fields["confidence"]

        body = render_candidate(fields)

        # A deleted optional field must render a placeholder, not the literal
        # ``str(None)``. A blanket ``"None" not in body`` would wrongly trip on
        # legitimate content like ``NoneType`` in evidence excerpts -- the
        # reporter's own domain -- so target the rendered field form instead.
        assert ": None" not in body


class TestBuildIssueLabelsEnforcesTheReporterLabelInvariant:
    """The managed-project reporter must never emit the maintainer arming label."""

    def test_applies_exactly_the_four_reporter_labels_for_a_category(self) -> None:
        assert build_issue_labels("scripts") == (
            "bug",
            "auto-filed",
            "from-managed-project",
            "category:scripts",
        )

    def test_never_emits_the_reserved_maintainer_label(self) -> None:
        assert RESERVED_MAINTAINER_LABEL not in build_issue_labels("hooks")
