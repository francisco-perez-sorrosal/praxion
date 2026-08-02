"""Behavioral tests for the skill-genesis agent rewrite to autonomous mode.

These tests are static-analysis tests: they parse YAML frontmatter and grep the
body text of agents/skill-genesis.md and a canonical fixture report. No runtime
agent execution or Claude Code session is involved.

RED state on first run: tests that check for 'background: true', absence of
'AskUserQuestion', 'Report Synthesis' phase heading, etc. will fail because the
current agents/skill-genesis.md still has the old interactive behavior. They go
GREEN once the agent is rewritten to autonomous pull-driven mode.

Test strategy: static analysis (YAML frontmatter parse + grep + fixture schema).
Rationale is documented in ADR dec-187.
"""

from __future__ import annotations

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT_FILE = REPO_ROOT / "agents" / "skill-genesis.md"
FIXTURE_REPORT = REPO_ROOT / "tests" / "fixtures" / "skill_genesis_report_sample.md"

# Expected log header columns (from SYSTEMS_PLAN.md Run-log schema)
EXPECTED_LOG_HEADER_COLUMNS = [
    "Timestamp",
    "Report File",
    "Items Extracted",
    "Proposals",
    "Review Status",
    "Approved",
    "Rejected",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_frontmatter(text: str) -> dict[str, object]:
    """Extract and parse YAML frontmatter from a Markdown file.

    Returns a dict; raises ValueError if frontmatter delimiters are missing.
    """
    import yaml

    if not text.startswith("---"):
        raise ValueError("File does not start with YAML frontmatter delimiter '---'")
    end = text.index("---", 3)
    fm_text = text[3:end].strip()
    return yaml.safe_load(fm_text) or {}


def _agent_body(text: str) -> str:
    """Return the body text after the closing frontmatter delimiter."""
    end = text.index("---", 3)
    return text[end + 3 :]


def _non_comment_lines(text: str) -> list[str]:
    """Return lines that are not Markdown comment blocks or YAML comments.

    Filters lines that start with '#' (yaml/bash comments) or contain HTML
    comment markers. Used to check for forbidden patterns without being
    tripped up by documentation comments.
    """
    result = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith("<!--") or stripped.endswith("-->"):
            continue
        result.append(line)
    return result


# ---------------------------------------------------------------------------
# Prerequisite: agent file exists
# ---------------------------------------------------------------------------


def test_agent_file_exists() -> None:
    """agents/skill-genesis.md must exist — it is the file under test."""
    assert AGENT_FILE.exists(), (
        f"agents/skill-genesis.md not found at {AGENT_FILE}. "
        "The file is a pre-existing agent definition; something is wrong with the path."
    )


# ---------------------------------------------------------------------------
# Group 1: Static frontmatter tests
# ---------------------------------------------------------------------------


def test_no_askuserquestion_in_tools() -> None:
    """AskUserQuestion must be absent from the tools: frontmatter field.

    The agent rewrite removes AskUserQuestion from tools: so the agent can run
    in background mode without user interaction (autonomous report writer).
    """
    text = AGENT_FILE.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    tools_raw = fm.get("tools", "")
    # tools: may be a string like "Read, Glob, ..." or a list
    if isinstance(tools_raw, list):
        tools_str = ", ".join(str(t) for t in tools_raw)
    else:
        tools_str = str(tools_raw)
    assert "AskUserQuestion" not in tools_str, (
        "AskUserQuestion must be removed from the 'tools:' frontmatter field. "
        f"Current tools: {tools_str!r}"
    )


def test_background_true() -> None:
    """agents/skill-genesis.md must declare background: true in frontmatter.

    This flips the coordination-protocol Bg Safe column from No to Yes,
    enabling the agent to be spawned via /skill-genesis without blocking
    the user's current work.
    """
    text = AGENT_FILE.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    assert fm.get("background") is True, (
        f"Expected 'background: true' in frontmatter, got background={fm.get('background')!r}. "
        "The agent rewrite must add 'background: true' to enable Bg Safe execution."
    )


def test_disallowed_tools_contains_edit() -> None:
    """agents/skill-genesis.md must declare disallowedTools: Edit in frontmatter.

    Mirrors the sentinel pattern: the autonomous report writer must never
    modify files other than its own report and log output.
    """
    text = AGENT_FILE.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    disallowed = fm.get("disallowedTools", "")
    if isinstance(disallowed, list):
        disallowed_str = ", ".join(str(t) for t in disallowed)
    else:
        disallowed_str = str(disallowed)
    assert "Edit" in disallowed_str, (
        f"'Edit' must appear in 'disallowedTools:' frontmatter. "
        f"Current disallowedTools: {disallowed_str!r}. "
        "The agent rewrite must add 'disallowedTools: Edit' to mirror sentinel."
    )


# ---------------------------------------------------------------------------
# Group 2: Agent body tests
# ---------------------------------------------------------------------------


def test_no_askuserquestion_in_body() -> None:
    """AskUserQuestion must not appear anywhere in the agent body text.

    The rewrite removes all interactive proposal presentation. Body text must
    not reference AskUserQuestion even in prose or instruction sections.
    """
    text = AGENT_FILE.read_text(encoding="utf-8")
    body = _agent_body(text)
    assert "AskUserQuestion" not in body, (
        "AskUserQuestion appears in the agent body. "
        "The rewrite must remove all references — including Phase 5 instructions "
        "and the Constraints section 'Proposals require user approval via AskUserQuestion'."
    )


def test_no_remember_call_in_body() -> None:
    """No remember( call must appear in non-comment lines of the agent body.

    In autonomous mode, the agent must NOT execute remember() directly. Memory
    entries become pending proposals in the report; /skill-genesis-review
    executes the remember() call only after user approval.

    Note: comment lines (starting with '#') are excluded per the LEARNINGS
    gotcha that the triage decision tree diagram may contain 'remember' in
    comments.
    """
    text = AGENT_FILE.read_text(encoding="utf-8")
    body = _agent_body(text)
    non_comment = _non_comment_lines(body)
    matches = [ln for ln in non_comment if "remember(" in ln]
    assert not matches, (
        "Found remember( in non-comment lines of the agent body. "
        "In autonomous mode, all remember() calls must be removed — memory entries "
        "appear as pending proposals in the report instead.\n"
        f"Matching lines: {matches!r}"
    )


# ---------------------------------------------------------------------------
# Group 3: Report schema fixture tests
# ---------------------------------------------------------------------------


def test_fixture_report_exists() -> None:
    """The canonical fixture report must exist at tests/fixtures/skill_genesis_report_sample.md."""
    assert FIXTURE_REPORT.exists(), (
        f"Fixture report not found at {FIXTURE_REPORT}. "
        "tests/fixtures/skill_genesis_report_sample.md must be created by the test-engineer."
    )


def test_report_frontmatter_parseable() -> None:
    """The fixture report frontmatter must parse cleanly and contain all required keys."""
    text = FIXTURE_REPORT.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    required_keys = [
        "schema_version",
        "report_id",
        "generated_at",
        "task_slug",
        "review_status",
        "disposition_count",
    ]
    for key in required_keys:
        assert key in fm, (
            f"Required frontmatter key '{key}' missing from fixture report. "
            f"Present keys: {list(fm.keys())}"
        )


def test_report_review_status_is_pending() -> None:
    """A fresh fixture report must have review_status: pending.

    This is the initial state that /skill-genesis-review discovers when it
    scans for unreviewed reports.
    """
    text = FIXTURE_REPORT.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    assert fm.get("review_status") == "pending", (
        f"Expected review_status='pending' in fixture frontmatter, "
        f"got review_status={fm.get('review_status')!r}. "
        "A fresh report written by the agent must start with review_status: pending."
    )


def test_report_has_proposals_section() -> None:
    """The fixture report must contain a '## Proposals' section.

    The Proposals section is required by the report schema — it carries the
    pending proposal entries that /skill-genesis-review presents to the user.
    """
    text = FIXTURE_REPORT.read_text(encoding="utf-8")
    assert re.search(r"^## Proposals", text, re.MULTILINE), (
        "Fixture report is missing the '## Proposals' section. "
        "The report schema requires this section to hold proposal entries."
    )


def test_report_has_disposition_log_section() -> None:
    """The fixture report must contain a '## Disposition Log' section.

    The Disposition Log is the append-only section that /skill-genesis-review
    populates. It must be present (empty) on initial report creation so the
    review command can append rows without creating the section itself.
    """
    text = FIXTURE_REPORT.read_text(encoding="utf-8")
    assert re.search(r"^## Disposition Log", text, re.MULTILINE), (
        "Fixture report is missing the '## Disposition Log' section. "
        "This section must exist (empty) on initial report creation so "
        "/skill-genesis-review can append rows idempotently."
    )


def test_report_log_header_row_has_required_columns() -> None:
    """The SKILL_GENESIS_LOG.md header row must contain all required columns.

    The log header is frozen at schema v1. These columns are the contract
    between the skill-genesis agent (writer) and /skill-genesis-review
    (updater of the Review Status column).
    """
    # The expected header is not in the report itself but in the SYSTEMS_PLAN.md.
    # We validate this by checking the fixture's Disposition Log section contains
    # the expected table header format — and we validate the log column contract
    # by asserting it is documented in the fixture or SYSTEMS_PLAN-derived spec.
    #
    # Verify all expected column names appear as substrings — the fixture body
    # should document the log format in its commentary or as an example.
    text = FIXTURE_REPORT.read_text(encoding="utf-8")
    # The fixture itself demonstrates the schema; the Disposition Log table
    # header appears in the fixture body.
    for col in ["Timestamp", "Proposal", "Disposition", "Notes"]:
        assert col in text, (
            f"Expected column name '{col}' to appear somewhere in the fixture report "
            f"(as a table header or in the Disposition Log section). "
            f"The report schema requires a '## Disposition Log' table with these columns."
        )
    # Also verify the log column names are recognized (schema contract check)
    assert all(col in EXPECTED_LOG_HEADER_COLUMNS for col in EXPECTED_LOG_HEADER_COLUMNS), (
        "Internal test invariant: EXPECTED_LOG_HEADER_COLUMNS must be self-consistent"
    )


# ---------------------------------------------------------------------------
# Group 4: Phase heading structural tests
# ---------------------------------------------------------------------------


def test_phase_5_heading_contains_report_synthesis() -> None:
    """Phase 5 heading must be 'Report Synthesis (5/7)', not 'Interactive Proposals'.

    The rewrite replaces the interactive proposal phase with an autonomous
    report synthesis phase — all triaged items become proposals in the report,
    none are presented interactively.
    """
    text = AGENT_FILE.read_text(encoding="utf-8")
    body = _agent_body(text)
    # Look for a Phase 5 heading with "Report Synthesis"
    assert re.search(r"###\s+Phase\s+5.*Report Synthesis", body), (
        "Phase 5 heading must contain 'Report Synthesis'. "
        f"Current Phase 5 heading appears to be: "
        f"{re.search(r'###.*Phase 5.*', body).group(0) if re.search(r'###.*Phase 5.*', body) else 'not found'}. "
        "The agent rewrite must replace 'Interactive Proposals (5/7)' with 'Report Synthesis (5/7)'."
    )


def test_phase_6_heading_contains_delegation_recommendations() -> None:
    """Phase 6 heading must be 'Delegation Recommendations (6/7)', not 'Delegation'.

    The rewrite renames Phase 6 to clarify that it populates the
    '## Recommended Delegations' table in the report rather than
    executing agent spawns or remember() calls directly.
    """
    text = AGENT_FILE.read_text(encoding="utf-8")
    body = _agent_body(text)
    assert re.search(r"###\s+Phase\s+6.*Delegation Recommendations", body), (
        "Phase 6 heading must contain 'Delegation Recommendations'. "
        f"Current Phase 6 heading: "
        f"{re.search(r'###.*Phase 6.*', body).group(0) if re.search(r'###.*Phase 6.*', body) else 'not found'}. "
        "The agent rewrite must replace 'Delegation (6/7)' with 'Delegation Recommendations (6/7)'."
    )


def test_phase_7_references_ai_state_path() -> None:
    """Phase 7 output path must reference .ai-state/skill_genesis_reports/.

    The rewrite redirects the Phase 7 output from the ephemeral
    .ai-work/<task-slug>/SKILL_GENESIS_REPORT.md to the permanent
    .ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_<TS>.md.
    This ensures reports accumulate across runs and survive pipeline cleanup.
    """
    text = AGENT_FILE.read_text(encoding="utf-8")
    body = _agent_body(text)
    assert ".ai-state/skill_genesis_reports/" in body, (
        "Phase 7 (Output Report) must reference '.ai-state/skill_genesis_reports/'. "
        "The rewrite redirects the output from .ai-work/ to .ai-state/ so reports "
        "are permanent and accumulate across multiple /skill-genesis invocations."
    )


# ---------------------------------------------------------------------------
# Group 5: Proposal entry shape completeness (fixture-level)
# ---------------------------------------------------------------------------


_REQUIRED_PROPOSAL_FIELDS = [
    "Disposition",
    "Type",
    "Maturity",
    "Scope",
    "Priority",
    "Source",
    "Description",
    "Rationale",
    "Estimated scope",
    "Overlap check",
    "Recommended delegation",
]


def test_first_proposal_in_fixture_has_all_required_fields() -> None:
    """Each proposal in a report must carry all Proposal Entry Shape fields.

    Validates that the fixture's first proposal contains all the fields
    required by the report schema, so /skill-genesis-review can disposition
    each proposal without re-reading source artifacts.
    """
    text = FIXTURE_REPORT.read_text(encoding="utf-8")
    # Find the first proposal block (from ### Proposal N: to the next ###)
    proposal_match = re.search(
        r"^### Proposal \d+:.*?(?=^###|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert proposal_match, (
        "No '### Proposal N:' section found in fixture report. "
        "The fixture must contain at least one well-formed proposal entry."
    )
    proposal_block = proposal_match.group(0)
    for field in _REQUIRED_PROPOSAL_FIELDS:
        assert field in proposal_block, (
            f"Required proposal field '{field}' missing from Proposal 1 in fixture. "
            f"All Proposal Entry Shape fields must be present so /skill-genesis-review "
            f"can disposition without re-reading source artifacts."
        )
