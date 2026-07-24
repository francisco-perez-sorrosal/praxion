"""Behavioral test guarding the ecosystem-defect.md issue template stays in
sync with `render.py`'s §5.2 heading schema.

`.github/ISSUE_TEMPLATE/ecosystem-defect.md` (the human-facing GitHub issue
template) and `render.py`'s `SECTION_HEADINGS` (the machine-rendered body)
are two independently-authored files. SYSTEMS_PLAN.md's "one artifact, both
entry paths" claim only holds if they cannot silently drift apart -- this
test parses the `##` headings out of the shipped template and asserts the
sequence equals `SECTION_HEADINGS` exactly, text and order both.

Naming note: this file guards the same contract the plan's Group F step
describes as `scripts/praxion_feedback/tests/test_template_sync.py`; it is
written here under a different basename per an explicit instruction from
the orchestrating agent for this pass. Flagged in LEARNINGS.md so the
integration checkpoint runs the right file and the plan's `Files` field gets
reconciled, not silently diverged from.
"""

from __future__ import annotations

import re
from pathlib import Path

# tests/ -> praxion_feedback/ -> scripts/ -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_PATH = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "ecosystem-defect.md"

_HEADING_RE = re.compile(r"^## (.+)$", re.MULTILINE)
_MANUAL_FILING_NOTE = "<!-- leave blank if filing manually -->"


def _parse_headings(text: str) -> list[str]:
    return [heading.strip() for heading in _HEADING_RE.findall(text)]


class TestTemplateExists:
    def test_the_ecosystem_defect_template_file_exists(self) -> None:
        assert (
            TEMPLATE_PATH.exists()
        ), f"expected the issue template at {TEMPLATE_PATH}, but it has not been created yet"


class TestTemplateHeadingsMatchTheRendererExactly:
    def test_headings_and_order_are_identical_to_section_headings(self) -> None:
        from scripts.praxion_feedback.render import SECTION_HEADINGS

        text = TEMPLATE_PATH.read_text()
        headings = _parse_headings(text)

        assert tuple(headings) == SECTION_HEADINGS, (
            "the template's ## headings must exactly match render.py's "
            f"SECTION_HEADINGS in the same order; got {headings!r} vs "
            f"{SECTION_HEADINGS!r}"
        )


class TestTemplateAnnotatesMachineOnlyFields:
    """Fingerprint and Capture Provenance are populated by the reporter CLI,
    never expected from a human filing manually in the browser."""

    def test_fingerprint_heading_carries_the_manual_filing_note(self) -> None:
        text = TEMPLATE_PATH.read_text()
        fingerprint_section = text.split("## Fingerprint", 1)[1].split("## ", 1)[0]
        assert _MANUAL_FILING_NOTE in fingerprint_section

    def test_capture_provenance_heading_carries_the_manual_filing_note(self) -> None:
        text = TEMPLATE_PATH.read_text()
        provenance_section = text.split("## Capture Provenance", 1)[1].split("## ", 1)[0]
        assert _MANUAL_FILING_NOTE in provenance_section


class TestTemplateNeverAdvertisesTheReservedMaintainerLabel:
    """`ecosystem-feedback` is P5's independent maintainer arming gate -- the
    template's own frontmatter labels must never pre-apply it."""

    def test_frontmatter_labels_do_not_include_ecosystem_feedback(self) -> None:
        text = TEMPLATE_PATH.read_text()
        # Frontmatter is delimited by the first two `---` lines.
        parts = text.split("---")
        assert len(parts) >= 3, f"expected `---`-delimited frontmatter; got {text[:200]!r}"
        frontmatter = parts[1]
        assert "ecosystem-feedback" not in frontmatter
