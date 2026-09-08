"""Structural tests for the parent-pipeline cleanup gating contract.

Parses agents/verifier.md and asserts that the documented cleanup contract
specifies: (a) cleanup is gated on open-rework completion, (b) the main agent
surfaces open-rework count before cleanup, (c) finalize_tech_debt_ledger.py
is the mechanism that resolves in-flight td-NNN rows on merge.

Phrasing flexibility assumption: tests use OR-matches for synonyms.  Canonical
forms are stated in each docstring alongside accepted alternatives.

Section-anchor flexibility assumption: the prose may appear in the spawn-behavior
subsection, in the Collaboration section's cleanup sub-block, or in a sibling
subsection.  Tests locate prose by content, not by heading path.

All tests are expected to FAIL until the implementer adds the cleanup-contract
prose to the verifier's Collaboration section.
"""

from __future__ import annotations

import re
from pathlib import Path

VERIFIER_FILE = Path(__file__).parents[2] / "agents" / "verifier.md"
# The rework-spawn / cleanup procedure prose moved out of the verifier body into this
# reference (process-economy P1.9); the verifier keeps the trigger + a pointer to it.
REWORK_REFERENCE = (
    Path(__file__).parents[2] / "skills" / "software-planning" / "references" / "rework-manifest.md"
)


def _collaboration_section() -> str:
    """Return agents/verifier.md from ## Collaboration onward plus the rework-manifest reference it points to."""
    text = VERIFIER_FILE.read_text(encoding="utf-8")
    match = re.search(r"^## Collaboration", text, re.MULTILINE)
    if not match:
        raise AssertionError(
            "agents/verifier.md does not contain a '## Collaboration' section — "
            "the orchestration prose has not yet been added"
        )
    reference = REWORK_REFERENCE.read_text(encoding="utf-8") if REWORK_REFERENCE.is_file() else ""
    return text[match.start() :] + "\n" + reference


def test_documents_cleanup_gated_on_open_reworks() -> None:
    """Cleanup-contract prose specifies that parent .ai-work/ deletion is gated.

    Canonical form: 'parent .ai-work/<parent-slug>/ cleanup is gated on rework
    completion' or similar.  Also accepted: any phrase combining 'cleanup' (or
    'delete' / 'deletion') with a gating condition tied to open reworks (e.g.,
    'not deleted until', 'gated on', 'requires completion of').
    """
    body = _collaboration_section()
    assert re.search(
        r"(?:cleanup|delete|deletion|clean up).{0,160}(?:gated|open.rework|rework.complet)|"
        r"(?:gated|not deleted|requires.{0,20}complet).{0,160}(?:rework|worktree)",
        body,
        re.IGNORECASE | re.DOTALL,
    ), (
        "Cleanup-contract prose must specify that parent .ai-work/<parent-slug>/ "
        "cleanup is gated on open-rework completion.  The parent pipeline directory "
        "must not be deleted while any rework worktree listed in REWORK_MANIFEST.md "
        "is still open."
    )


def test_documents_open_rework_count_surfacing() -> None:
    """Cleanup-contract prose specifies the main agent surfaces open-rework count.

    Canonical form: 'main agent surfaces the count of open reworks'.
    Also accepted: 'lists open rework worktrees', 'surfaces N open reworks',
    'reports open-rework count', or any phrase combining 'open' with 'rework'
    and a surfacing/listing/counting action directed at the user.
    """
    body = _collaboration_section()
    assert re.search(
        r"(?:surface[sd]?|list[sd]?|report[sd]?|count|show[sd]?).{0,120}open.{0,40}rework|"
        r"open.{0,40}rework.{0,120}(?:surface[sd]?|list[sd]?|count|before.{0,30}clean)",
        body,
        re.IGNORECASE | re.DOTALL,
    ), (
        "Cleanup-contract prose must specify that the main agent surfaces the count "
        "of open rework worktrees to the user before / at cleanup time."
    )


def test_documents_finalize_tech_debt_ledger_path() -> None:
    """Cleanup-contract prose mentions finalize_tech_debt_ledger.py for resolved status.

    Canonical form: 'finalize_tech_debt_ledger.py'.
    Also accepted: 'finalize_tech_debt_ledger' (without .py extension), or any
    description of the finalize script as the mechanism that transitions td-NNN
    rows from in-flight to resolved when reworks merge.
    """
    body = _collaboration_section()
    assert re.search(
        r"finalize_tech_debt_ledger(?:\.py)?",
        body,
        re.IGNORECASE,
    ), (
        "Cleanup-contract prose must mention 'finalize_tech_debt_ledger.py' (or the "
        "script without extension) as the mechanism that flips td-NNN rows from "
        "'in-flight' to 'resolved' when rework worktrees merge to main."
    )
