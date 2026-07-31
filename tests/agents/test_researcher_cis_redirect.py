"""Behavioral tests for the CIS disposition-vocabulary redirect in agent files.

The implementer will replace the inline three-bullet definition block
for switch-now / defer-with-rationale / dismiss-with-rationale in both
agents/researcher.md and agents/systems-architect.md with a one-line pointer
to skills/software-planning/references/disposition-vocabulary.md.

These tests are expected to FAIL until the CIS redirect lands:
  - researcher.md still has the inline definitions (no pointer yet)
  - systems-architect.md still has the inline definitions (no pointer yet)

Tests use plain pathlib reads + re.search; no fixtures or mocks needed
because the contract is purely structural (file content assertions).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RESEARCHER = REPO_ROOT / "agents/researcher.md"
ARCHITECT = REPO_ROOT / "agents/systems-architect.md"
SHARED_REF = "skills/software-planning/references/disposition-vocabulary.md"

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

_INLINE_DEFINITION_RE = re.compile(
    r"""
    (?:                                    # match any of:
      \*\*switch-now\*\*.*\n              #  bolded switch-now line
    | \*\*defer-with-rationale\*\*.*\n   #  bolded defer line
    | \*\*dismiss-with-rationale\*\*.*\n #  bolded dismiss line
    )
    """,
    re.VERBOSE,
)

_CIS_SECTION_RE = re.compile(r"##\s+Continuous\s+Improvement\s+Signals", re.IGNORECASE)
_POINTER_RE = re.compile(re.escape(SHARED_REF))

# Fields that currently exist in each file's frontmatter and must survive the CIS redirect.
# permissionMode was removed fleet-wide (td-072: Claude Code ignores it for
# plugin-distributed agents), so it is no longer part of this contract.
_RESEARCHER_FM_FIELDS = (
    "name:",
    "description:",
    "tools:",
    "skills:",
)
_ARCHITECT_FM_FIELDS = (
    "name:",
    "description:",
    "tools:",
    "model:",
    "skills:",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _cis_block(text: str) -> str:
    """Return the text from the CIS heading to the next ## heading (exclusive)."""
    m = _CIS_SECTION_RE.search(text)
    if not m:
        return ""
    start = m.start()
    rest = text[start:]
    # Find the next top-level heading after the section opener
    next_h = re.search(r"\n##\s+", rest[3:])  # skip the opening ##
    if next_h:
        return rest[: next_h.start() + 3]
    return rest


# -----------------------------------------------------------------------
# researcher.md
# -----------------------------------------------------------------------


def test_researcher_cis_points_to_shared_reference():
    """The CIS section in researcher.md must contain a markdown link to the shared vocab file."""
    text = _read(RESEARCHER)
    block = _cis_block(text)
    assert block, "No '## Continuous Improvement Signals' section found in researcher.md"
    assert _POINTER_RE.search(block), (
        f"researcher.md CIS section does not contain a link to '{SHARED_REF}'; "
        "CIS redirect has not landed yet"
    )


def test_no_inline_vocabulary_duplication_in_researcher():
    """The inline three-bullet definition block must be gone from researcher.md.

    The terms switch-now / defer-with-rationale / dismiss-with-rationale may
    still appear in prose, but the bolded definition lines (the *definition
    block* that the CIS redirect replaces) must not be present.
    """
    text = _read(RESEARCHER)
    block = _cis_block(text)
    assert block, "No CIS section found in researcher.md — cannot check for inline defs"

    # The definition block is three consecutive bolded terms on their own lines.
    # We look for any two of the three bolded inline definitions coexisting.
    bolded = re.findall(
        r"\*\*(switch-now|defer-with-rationale|dismiss-with-rationale)\*\*",
        block,
    )
    assert len(bolded) < 2, (
        f"researcher.md still contains {len(bolded)} inline bolded definition(s) "
        f"for the disposition terms: {bolded!r}. "
        "The CIS redirect should have replaced the definition block with a pointer."
    )


def test_frontmatter_preserved_in_researcher():
    """YAML frontmatter in researcher.md must remain intact after CIS redirect edits."""
    text = _read(RESEARCHER)
    for field in _RESEARCHER_FM_FIELDS:
        assert field in text, (
            f"researcher.md frontmatter field '{field}' is missing; "
            "CIS redirect must not alter frontmatter"
        )


# -----------------------------------------------------------------------
# systems-architect.md
# -----------------------------------------------------------------------


def test_architect_cis_points_to_shared_reference():
    """The CIS obligation block in systems-architect.md must link to the shared vocab file."""
    text = _read(ARCHITECT)
    # The architect's CIS block is part of Phase 7 prose, not a dedicated ## section.
    # We search the full file for the pointer.
    assert _POINTER_RE.search(text), (
        f"systems-architect.md does not contain a link to '{SHARED_REF}'; "
        "CIS redirect has not landed yet"
    )


def test_no_inline_vocabulary_duplication_in_architect():
    """The inline bolded definition list in systems-architect.md must be replaced.

    The CIS redirect replaces the three-bullet definition block (~lines
    186-188) with a one-line pointer. After the redirect, the architect file
    must not contain all three inline bolded definitions for the disposition
    terms.
    """
    text = _read(ARCHITECT)
    bolded = re.findall(
        r"\*\*(switch-now|defer-with-rationale|dismiss-with-rationale)\*\*",
        text,
    )
    assert len(bolded) < 2, (
        f"systems-architect.md still contains {len(bolded)} inline bolded definition(s) "
        f"for the disposition terms: {bolded!r}. "
        "The CIS redirect should have replaced the definition block with a pointer."
    )


def test_frontmatter_preserved_in_architect():
    """YAML frontmatter in systems-architect.md must remain intact after CIS redirect edits."""
    text = _read(ARCHITECT)
    for field in _ARCHITECT_FM_FIELDS:
        assert field in text, (
            f"systems-architect.md frontmatter field '{field}' is missing; "
            "CIS redirect must not alter frontmatter"
        )
