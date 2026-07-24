"""Behavioral tests for the mechanical §5.2 template validator and dedup-
signature builder that gates the fixer agent (SYSTEMS_PLAN.md § Architecture
› Components, workflow step 6: "Mechanical template-validate + dedup").

`parse_sections` / `missing_required_sections` / `extract_fingerprint` /
`dedup_signature` all run on the already-sanitized issue body -- deterministic
and judgment-free, entirely before any agent spend. The workflow step this
module backs is a cheap rejection filter in front of the LLM: a malformed or
duplicate issue must never reach the fixer.

The single highest-risk behavior this module backs: the two machine-only
§5.2 sections (`Fingerprint`, `Capture Provenance`) are populated by the
automated reporter CLI, never by a human filing manually in the browser --
the shipped issue template explicitly tells a manual filer to leave them
blank (see `.github/ISSUE_TEMPLATE/ecosystem-defect.md`). Treating either as
required would false-reject every legitimate human-filed defect report.
Every other §5.2 heading is human-authored and required.
"""

from __future__ import annotations

from scripts.praxion_feedback.issue_triage import (
    dedup_signature,
    extract_fingerprint,
    missing_required_sections,
    parse_sections,
)
from scripts.praxion_feedback.render import SECTION_HEADINGS

# Distinct, non-blank filler content for every §5.2 heading -- keyed by the
# exact heading text so `_full_valid_sections` can derive both the section
# *set* and *order* from `SECTION_HEADINGS` itself, rather than hardcoding a
# second, independently-ordered list that could drift from render.py's.
_SECTION_CONTENT = {
    "Fingerprint": "9f8c7d6e5b4a3210",
    "Plugin / Component": (
        "- Category: scripts\n- Artifact: scripts/praxion_feedback/issue_triage.py"
    ),
    "Capture Provenance": (
        "- Detected by: sentinel\n- Detection point: post-implementation audit\n- Confidence: high"
    ),
    "Expected vs Observed": (
        "- Expected: parses every §5.2 heading\n- Observed: raises AttributeError"
    ),
    "Reproduction Command": (
        "python3 -m pytest scripts/praxion_feedback/tests/test_issue_triage.py"
    ),
    "Evidence Excerpt (sanitized)": (
        "```\nAttributeError: 'NoneType' object has no attribute 'foo'\n```"
    ),
    "Environment": "macOS, Python 3.11",
    "Regression Status": "new",
}


def _full_valid_sections(overrides: dict[str, str] | None = None) -> dict[str, str]:
    """All eight §5.2 sections, in `SECTION_HEADINGS` order, each populated
    with distinct, non-blank content. Pass `overrides` to replace one or more
    sections' content by heading name; the caller deletes keys from the
    returned dict to simulate a heading that is entirely absent from a body."""
    sections = {heading: _SECTION_CONTENT[heading] for heading in SECTION_HEADINGS}
    if overrides:
        sections.update(overrides)
    return sections


def _body(sections: dict[str, str]) -> str:
    """Render `sections` into a §5.2 markdown body, `## <heading>\n\n<content>\n`
    per entry, in the given (insertion) order. A heading absent from
    `sections` is entirely absent from the body -- simulating a human filer
    who deleted the heading rather than leaving the template's placeholder
    HTML comment behind."""
    return "\n".join(f"## {heading}\n\n{content}\n" for heading, content in sections.items())


class TestParseSectionsExtractsOnlyHeadingsPresentInTheBody:
    def test_every_populated_heading_maps_to_its_content(self) -> None:
        body = _body(_full_valid_sections())
        parsed = parse_sections(body)

        assert parsed["Environment"].strip() == "macOS, Python 3.11"
        # Last heading in SECTION_HEADINGS order -- no trailing "## " boundary
        # to terminate the section, so this also proves EOF-terminated parsing.
        assert parsed["Regression Status"].strip() == "new"

    def test_a_heading_absent_from_the_body_is_absent_from_the_result(self) -> None:
        sections = _full_valid_sections()
        del sections["Fingerprint"]

        assert "Fingerprint" not in parse_sections(_body(sections))


class TestMissingRequiredSectionsAcceptsAFullyPopulatedFiling:
    def test_a_body_with_every_section_populated_has_no_missing_sections(self) -> None:
        body = _body(_full_valid_sections())
        assert missing_required_sections(body) == ()


class TestMissingRequiredSectionsRejectsAnAbsentHumanAuthoredSection:
    def test_a_body_missing_the_environment_section_names_it_as_missing(self) -> None:
        sections = _full_valid_sections()
        del sections["Environment"]

        assert "Environment" in missing_required_sections(_body(sections))

    def test_a_body_missing_the_reproduction_command_section_names_it_as_missing(self) -> None:
        sections = _full_valid_sections()
        del sections["Reproduction Command"]

        assert "Reproduction Command" in missing_required_sections(_body(sections))

    def test_two_missing_required_sections_are_both_named(self) -> None:
        sections = _full_valid_sections()
        del sections["Environment"]
        del sections["Regression Status"]

        missing = missing_required_sections(_body(sections))

        assert "Environment" in missing
        assert "Regression Status" in missing


class TestMissingRequiredSectionsTreatsAWhitespaceOnlySectionAsMissing:
    def test_a_whitespace_only_required_section_is_named_as_missing(self) -> None:
        body = _body(_full_valid_sections({"Environment": "   \n  "}))
        assert "Environment" in missing_required_sections(body)


class TestMissingRequiredSectionsToleratesAbsentMachineOnlySections:
    """Critical case: the two machine-only §5.2 sections are absent from
    every human filing by design -- the shipped issue template tells a
    manual filer to leave them blank. Requiring either would false-reject
    legitimate defect reports filed by hand."""

    def test_a_body_missing_fingerprint_and_capture_provenance_is_still_valid(self) -> None:
        sections = _full_valid_sections()
        del sections["Fingerprint"]
        del sections["Capture Provenance"]

        assert missing_required_sections(_body(sections)) == ()


class TestExtractFingerprintReturnsThePresentValue:
    def test_extracts_the_fingerprint_section_content_when_present(self) -> None:
        body = _body(_full_valid_sections({"Fingerprint": "fp-marker-99"}))
        assert extract_fingerprint(body) == "fp-marker-99"


class TestExtractFingerprintReturnsNoneForAHumanFiling:
    def test_returns_none_when_the_fingerprint_heading_is_entirely_absent(self) -> None:
        sections = _full_valid_sections()
        del sections["Fingerprint"]

        assert extract_fingerprint(_body(sections)) is None

    def test_returns_none_when_the_fingerprint_section_is_blank(self) -> None:
        body = _body(_full_valid_sections({"Fingerprint": "   "}))
        assert extract_fingerprint(body) is None


class TestDedupSignatureUsesTheParsedFingerprintWhenPresent:
    def test_returns_the_fingerprint_value_verbatim(self) -> None:
        body = _body(_full_valid_sections({"Fingerprint": "fp-marker-77"}))
        assert dedup_signature(body) == "fp-marker-77"


class TestDedupSignatureFallsBackForAHumanFilingWithNoFingerprint:
    def test_a_body_without_a_fingerprint_still_produces_a_non_empty_signature(self) -> None:
        sections = _full_valid_sections()
        del sections["Fingerprint"]
        del sections["Capture Provenance"]

        signature = dedup_signature(_body(sections))

        assert isinstance(signature, str)
        assert signature != ""


class TestDedupSignatureIsStableAndDiscriminating:
    def test_the_same_body_produces_the_same_signature_across_calls(self) -> None:
        sections = _full_valid_sections()
        del sections["Fingerprint"]
        del sections["Capture Provenance"]
        body = _body(sections)

        assert dedup_signature(body) == dedup_signature(body)

    def test_two_bodies_describing_different_defects_produce_different_signatures(self) -> None:
        # Non-vacuity guard: a constant-returning `dedup_signature` would pass
        # every test above but must fail here. Vary artifact, expectation, and
        # evidence together so the assertion holds regardless of which of
        # those fields a fallback signature formula actually keys on.
        sections = _full_valid_sections()
        del sections["Fingerprint"]
        del sections["Capture Provenance"]
        first = _body(sections)

        different_sections = _full_valid_sections(
            {
                "Plugin / Component": (
                    "- Category: hooks\n- Artifact: hooks/completely_different_artifact.py"
                ),
                "Expected vs Observed": (
                    "- Expected: something else entirely\n- Observed: a different failure"
                ),
                "Evidence Excerpt (sanitized)": "```\nKeyError: 'totally-different-defect'\n```",
            }
        )
        del different_sections["Fingerprint"]
        del different_sections["Capture Provenance"]
        second = _body(different_sections)

        assert dedup_signature(first) != dedup_signature(second)
