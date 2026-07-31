"""Structural tests for the main-agent rework-spawn contract.

Parses agents/verifier.md and asserts that the documented main-agent protocol
contains the correct orchestration behaviors for rework worktree spawning, td-NNN
lifecycle management, and user surfacing.

Phrasing flexibility assumption: tests use OR-matches for semantically equivalent
phrasing.  The canonical forms below describe the *intent*; the implementer
has latitude to use synonymous language.  Where a test accepts alternatives, the
docstring lists the canonical phrase and the accepted variants.

Section-anchor flexibility assumption: the new prose may live in a new
"### Rework Worktree Spawn Behavior" subsection, appended to the existing
"### With the Implementation Planner (Self-Healing Loop)" section, or in a
sibling subsection.  Tests locate prose by CONTENT, not by exact heading.

All tests are expected to FAIL until the implementer adds the spawn-behavior
prose to the verifier's Collaboration section.
"""

from __future__ import annotations

import re
from pathlib import Path

VERIFIER_FILE = Path(__file__).parents[2] / "agents" / "verifier.md"


def _collaboration_section() -> str:
    """Return the full text of agents/verifier.md from ## Collaboration onward.

    Defers file I/O so pytest collection succeeds even when the file is absent
    or the section does not exist yet.
    """
    text = VERIFIER_FILE.read_text(encoding="utf-8")
    # Locate ## Collaboration (or ## Collaboration Points)
    match = re.search(r"^## Collaboration", text, re.MULTILINE)
    if not match:
        raise AssertionError(
            "agents/verifier.md does not contain a '## Collaboration' section — "
            "the orchestration prose has not yet been added"
        )
    return text[match.start() :]


def test_collaboration_section_documents_rework_spawn() -> None:
    """A spawn-behavior subsection exists inside ## Collaboration.

    Canonical form: '### Rework Worktree Spawn Behavior'.
    Also accepted: any subsection heading mentioning 'rework' and ('spawn' or
    'worktree') within ## Collaboration.
    """
    body = _collaboration_section()
    assert re.search(
        r"###.{0,40}[Rr]ework.{0,60}(?:spawn|worktree)|"
        r"###.{0,40}(?:spawn|worktree).{0,60}[Rr]ework",
        body,
        re.IGNORECASE,
    ), (
        "agents/verifier.md ## Collaboration section must contain a subsection "
        "documenting the rework worktree spawn behavior (e.g., "
        "'### Rework Worktree Spawn Behavior').  The implementer adds this."
    )


def test_documents_one_worktree_per_row() -> None:
    """Spawn-behavior prose specifies one worktree per manifest row.

    Canonical form: 'one worktree per row'.
    Also accepted: 'one rework worktree per manifest row', 'per row, one
    worktree', 'one worktree per rework proposal', or any phrase combining
    'one' (or '1') with 'worktree' and 'row' (or 'manifest row' / 'proposal').
    """
    body = _collaboration_section()
    assert re.search(
        r"(?:one|1)\s+(?:rework\s+)?worktree\s+per\s+(?:manifest\s+)?row|"
        r"per\s+(?:manifest\s+)?row[,\s]+one\s+worktree|"
        r"per\s+(?:rework\s+)?proposal[,\s]+one\s+worktree",
        body,
        re.IGNORECASE,
    ), (
        "Spawn-behavior prose must specify 'one worktree per row' (or equivalent).  "
        "The main agent calls EnterWorktree once per REWORK_MANIFEST.md row."
    )


def test_documents_enter_worktree_call() -> None:
    """Spawn-behavior prose names EnterWorktree as the spawn mechanism.

    Case-insensitive match is acceptable; the exact API name must appear.
    """
    body = _collaboration_section()
    assert re.search(r"EnterWorktree", body, re.IGNORECASE), (
        "Spawn-behavior prose must name 'EnterWorktree' as the spawn mechanism.  "
        "The main agent uses EnterWorktree to create each rework worktree."
    )


def test_documents_findings_file_write() -> None:
    """Spawn-behavior prose specifies that the main agent writes VERIFIER_FINDINGS.md.

    The file must be mentioned in the context of the worktree creation sequence.
    """
    body = _collaboration_section()
    assert re.search(r"VERIFIER_FINDINGS\.md", body), (
        "Spawn-behavior prose must specify that the main agent writes "
        "'VERIFIER_FINDINGS.md' inside each rework worktree.  "
        "This is the primary handoff artifact for /resume-rework."
    )
    # Additionally confirm VERIFIER_FINDINGS.md is associated with the worktree write
    assert re.search(
        r"(?:write|writes|written|drop|drops|place|places).{0,80}VERIFIER_FINDINGS\.md|"
        r"VERIFIER_FINDINGS\.md.{0,80}(?:written|write|inside|in each|per worktree)",
        body,
        re.IGNORECASE | re.DOTALL,
    ), (
        "VERIFIER_FINDINGS.md must appear in a write-action context inside the "
        "spawn-behavior prose (e.g., 'writes VERIFIER_FINDINGS.md inside each worktree')."
    )


def test_documents_verification_report_snapshot() -> None:
    """Spawn-behavior prose describes what happens to VERIFICATION_REPORT.md in
    the context of rework worktree creation.

    The parent's report must be mentioned in a worktree/rework context:
    snapshotted into the rework worktree, or its path carried in.
    Canonical form: 'snapshot' or 'snapshotted'.
    Also accepted: 'copy', 'copied', 'path' (near 'rework' or 'worktree').

    NOTE: 'reference' is intentionally excluded because it appears in existing
    Interface Designer prose ('record findings in VERIFICATION_REPORT.md') and
    in file-path components ('references/'), both of which are false positives.
    """
    body = _collaboration_section()
    assert re.search(
        r"VERIFICATION_REPORT\.md.{0,120}(?:snapshot|copy|copie)|"
        r"(?:snapshot|snapshots|copy|copies|copie).{0,120}VERIFICATION_REPORT\.md|"
        r"VERIFICATION_REPORT\.md.{0,80}(?:rework|worktree).{0,80}(?:path|snapshot|copy)|"
        r"(?:path.{0,40}VERIFICATION_REPORT\.md.{0,60}worktree|"
        r"worktree.{0,80}VERIFICATION_REPORT\.md)",
        body,
        re.IGNORECASE | re.DOTALL,
    ), (
        "Spawn-behavior prose must cover what happens to the parent's "
        "VERIFICATION_REPORT.md in the rework worktree creation context "
        "(e.g., snapshotted into each rework worktree, or path carried in). "
        "This prose does not yet exist — the implementer adds it."
    )


def test_documents_td_nnn_flip() -> None:
    """Spawn-behavior prose specifies the main agent flips td-NNN rows open→in-flight.

    Canonical form: 'open → in-flight' (or 'open to in-flight') with the
    notes suffix '// in-flight via rework worktree <name>'.
    Also accepted: any phrase combining 'td' or 'TECH_DEBT' with 'in-flight'
    and either 'open' or 'flip' or 'status'.
    """
    body = _collaboration_section()
    assert re.search(
        r"(?:td-?\w+|TECH_DEBT).{0,120}in.flight|"
        r"in.flight.{0,120}(?:td-?\w+|TECH_DEBT)|"
        r"(?:flip|flips|status).{0,80}in.flight",
        body,
        re.IGNORECASE | re.DOTALL,
    ), (
        "Spawn-behavior prose must specify the main agent flips linked td-NNN rows "
        "from 'open' to 'in-flight'.  This is the ledger-linkage contract for "
        "the rework loop."
    )
    # Confirm the notes-suffix pattern is documented (per dec-181)
    assert re.search(
        r"in.flight via rework worktree|notes.{0,60}suffix|// in.flight",
        body,
        re.IGNORECASE | re.DOTALL,
    ), (
        "Spawn-behavior prose must document the notes-field suffix pattern "
        "'// in-flight via rework worktree <name>' (per the td-linkage ADR)."
    )


def test_documents_one_liner_user_surface() -> None:
    """Spawn-behavior prose describes the one-liner the main agent surfaces to the user.

    Canonical form: a sentence of the form '[N] rework worktrees created. Run
    /resume-rework in each.'  Also accepted: any phrase describing a user-facing
    one-liner, status message, or summary combining worktree-count information
    with /resume-rework.
    """
    body = _collaboration_section()
    assert re.search(
        r"/resume.rework",
        body,
        re.IGNORECASE,
    ), (
        "Spawn-behavior prose must reference '/resume-rework' as the command the "
        "main agent tells the user to run."
    )
    assert re.search(
        r"(?:one.liner|surface[sd]?|message|tells the user|user.facing).{0,120}/resume.rework|"
        r"/resume.rework.{0,120}(?:each|every|worktree|session)",
        body,
        re.IGNORECASE | re.DOTALL,
    ), (
        "Spawn-behavior prose must describe the one-liner the main agent surfaces to "
        "the user after creating rework worktrees — pointing them to /resume-rework."
    )
