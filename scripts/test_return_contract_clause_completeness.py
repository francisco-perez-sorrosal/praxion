"""Canary for the Return-contract row's clause completeness.

The coordination rule's `Return contract` table row is the single source of
truth for the pointer-not-a-payload convention every subagent's final message
must honor. A future edit to that row (line wrap, terminology drift, an
accidental deletion while editing an adjacent cell) could silently drop one of
its four load-bearing clauses without any other test noticing, since nothing
else in the corpus restates them.

The row is read from the live rule file at test time, never transcribed here
-- a copy would pass because someone typed it correctly once and then drift
silently the moment the live row changes.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RULE_FILE = REPO_ROOT / "rules" / "swe" / "swe-agent-coordination-protocol.md"


def _return_contract_row() -> str:
    """Return the live `Return contract` table row from the coordination rule."""
    text = RULE_FILE.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("| Return contract |"):
            return line
    raise AssertionError(f"no 'Return contract' row found in {RULE_FILE}")


def test_names_the_pointer_not_a_payload_shape() -> None:
    row = _return_contract_row()
    assert "pointer, not a payload" in row, row


def test_bounds_the_summary_to_a_terse_line_count() -> None:
    row = _return_contract_row()
    assert "terse summary" in row, row
    assert "15 lines" in row, row


def test_forbids_the_artifact_body_in_the_returned_message() -> None:
    row = _return_contract_row()
    assert "never the artifact body" in row, row


def test_forbids_the_orchestrator_from_soliciting_the_artifact_body() -> None:
    # The orchestrator-facing clause that replaced the deleted CLAUDE.md.tmpl
    # sentence; it must be bound on its own, not as one branch of a disjunction.
    row = _return_contract_row()
    assert "never solicits the artifact body inline" in row, row


def test_states_the_artifact_is_read_only_when_the_detail_is_needed() -> None:
    row = _return_contract_row()
    assert "reads an artifact only when it needs the detail" in row, row
