"""Behavioral tests for the /skill-genesis and /skill-genesis-review command files.

These are static-analysis tests: YAML frontmatter parsing and grep-based body
inspection of the two new command files, plus fixture-based simulation of the
disposition discovery logic. No runtime Claude Code session is involved.

RED state on first run: commands/skill-genesis.md and commands/skill-genesis-review.md
do not exist yet — all tests that read those files produce FileNotFoundError-equivalent
failures via Path.exists() assertions. They go GREEN once the two command files exist.

Test strategy: static analysis (YAML frontmatter parse + grep + fixture-based logic).
Rationale is documented in ADR dec-187.
"""

from __future__ import annotations

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
REVIEW_COMMAND = REPO_ROOT / "commands" / "skill-genesis-review.md"
GENESIS_COMMAND = REPO_ROOT / "commands" / "skill-genesis.md"
FIXTURE_REPORT = REPO_ROOT / "tests" / "fixtures" / "skill_genesis_report_sample.md"


# ---------------------------------------------------------------------------
# Helpers (mirrored from test_skill_genesis_agent.py for DAMP readability)
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


def _command_body(text: str) -> str:
    """Return the body text after the closing frontmatter delimiter."""
    end = text.index("---", 3)
    return text[end + 3 :]


def _allowed_tools_list(fm: dict[str, object]) -> list[str]:
    """Normalize the allowed-tools value to a flat list of strings."""
    raw = fm.get("allowed-tools", [])
    if isinstance(raw, list):
        return [str(t) for t in raw]
    # May be a string like "Read, Glob, Grep"
    return [t.strip() for t in str(raw).split(",")]


def _pending_proposals_from_report(report_text: str) -> list[str]:
    """Extract proposal names where Disposition is 'pending' or 'pending refinement'.

    Simulates the discovery logic the review command applies when it opens a
    report file and scans for proposals that still need user disposition.
    Returns a list of proposal header strings.
    """
    pending: list[str] = []
    # Split into proposal sections (each starts with "### Proposal N:")
    proposal_sections = re.split(r"(?=^### Proposal \d+:)", report_text, flags=re.MULTILINE)
    for section in proposal_sections:
        if not re.match(r"^### Proposal \d+:", section):
            continue
        # A proposal is pending if its Disposition line is pending or pending refinement
        disp_match = re.search(
            r"^\s*-\s+\*\*Disposition\*\*:\s*(pending(?: refinement)?)",
            section,
            re.MULTILINE,
        )
        if disp_match:
            header_match = re.match(r"(### Proposal \d+:.*)", section)
            if header_match:
                pending.append(header_match.group(1).strip())
    return pending


# ---------------------------------------------------------------------------
# Group 1: /skill-genesis-review command file existence and frontmatter
# ---------------------------------------------------------------------------


def test_review_command_file_exists() -> None:
    """commands/skill-genesis-review.md must exist.

    This is the disposition command the user runs to batch-present pending
    proposals. Its absence means the review flow is entirely broken.
    """
    assert REVIEW_COMMAND.exists(), (
        f"commands/skill-genesis-review.md not found at {REVIEW_COMMAND}. "
        "This command file must exist before tests can pass."
    )


def test_review_command_frontmatter_parseable() -> None:
    """commands/skill-genesis-review.md frontmatter must parse as valid YAML.

    All Praxion command files use YAML frontmatter with required keys.
    A parse failure here means the command is not registered by Claude Code.
    """
    text = REVIEW_COMMAND.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    required_keys = ["description", "argument-hint", "allowed-tools"]
    for key in required_keys:
        assert key in fm, (
            f"Required frontmatter key '{key!r}' missing from commands/skill-genesis-review.md. "
            f"Present keys: {list(fm.keys())}"
        )


def test_review_command_description_is_non_empty() -> None:
    """commands/skill-genesis-review.md must have a non-empty description field.

    The description appears in Claude Code's /command tab and is the user's
    primary discovery mechanism for what the command does.
    """
    text = REVIEW_COMMAND.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    desc = fm.get("description", "")
    assert isinstance(desc, str), (
        "The 'description' field in commands/skill-genesis-review.md must be a non-empty string. "
        f"Got: {desc!r}"
    )
    assert desc.strip(), (
        "The 'description' field in commands/skill-genesis-review.md must be a non-empty string. "
        f"Got: {desc!r}"
    )


def test_review_allowed_tools_include_askuserquestion() -> None:
    """commands/skill-genesis-review.md must list AskUserQuestion in allowed-tools.

    The batch multi-select disposition flow requires AskUserQuestion to
    present pending proposals to the user and collect their choices.
    Without it, no interactive disposition is possible.
    """
    text = REVIEW_COMMAND.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    tools = _allowed_tools_list(fm)
    assert any("AskUserQuestion" in t for t in tools), (
        "AskUserQuestion must be in 'allowed-tools' for commands/skill-genesis-review.md. "
        f"Current allowed-tools: {tools!r}. "
        "The review command uses AskUserQuestion for the batch multi-select disposition pass."
    )


def test_review_allowed_tools_include_edit() -> None:
    """commands/skill-genesis-review.md must list Edit in allowed-tools.

    The review command appends rows to ## Disposition Log and updates the
    report's frontmatter fields (review_status, disposition_count) in place.
    Edit permission is required for this in-place mutation.
    """
    text = REVIEW_COMMAND.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    tools = _allowed_tools_list(fm)
    assert any("Edit" in t for t in tools), (
        "Edit must be in 'allowed-tools' for commands/skill-genesis-review.md. "
        f"Current allowed-tools: {tools!r}. "
        "The review command uses Edit to append rows to ## Disposition Log and "
        "update review_status in the report frontmatter."
    )


def test_review_argument_hint_present() -> None:
    """commands/skill-genesis-review.md must have an argument-hint field.

    The argument-hint documents the command's optional flags in the Claude
    Code command tab. At minimum the hint must be a non-empty string.
    """
    text = REVIEW_COMMAND.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    hint = fm.get("argument-hint", "")
    assert isinstance(hint, str), (
        "'argument-hint' in commands/skill-genesis-review.md must be a non-empty string. "
        f"Got: {hint!r}"
    )
    assert hint.strip(), (
        "'argument-hint' in commands/skill-genesis-review.md must be a non-empty string. "
        f"Got: {hint!r}"
    )


# ---------------------------------------------------------------------------
# Group 2: /skill-genesis-review command body — behavioral contracts
# ---------------------------------------------------------------------------


def test_review_body_references_skill_genesis_reports_path() -> None:
    """The review command body must reference .ai-state/skill_genesis_reports/.

    The command's report-discovery logic scans this directory for pending
    reports. If the path is not referenced, the discovery logic is absent
    or points at the wrong location.
    """
    text = REVIEW_COMMAND.read_text(encoding="utf-8")
    body = _command_body(text)
    assert ".ai-state/skill_genesis_reports/" in body, (
        "commands/skill-genesis-review.md body must reference '.ai-state/skill_genesis_reports/'. "
        "The report-discovery logic (step 1 of the command's 9 responsibilities) scans "
        "this path for the most recent unreviewed report."
    )


def test_review_body_states_disposition_log_append_contract() -> None:
    """The review command body must describe appending to ## Disposition Log.

    The contract is: existing disposition rows must never be rewritten,
    only new rows appended. This makes re-runs idempotent and preserves
    the audit trail.
    """
    text = REVIEW_COMMAND.read_text(encoding="utf-8")
    body = _command_body(text)
    # Check that both "Disposition Log" and append semantics are present
    assert "Disposition Log" in body, (
        "commands/skill-genesis-review.md body must mention 'Disposition Log' — "
        "the section the command appends rows to after each disposition pass."
    )
    # The body must state the append-only / never-rewrite constraint
    has_append = any(kw in body.lower() for kw in ("append", "never rewrite", "never rewrites"))
    assert has_append, (
        "commands/skill-genesis-review.md body must state the append-only contract for "
        "the ## Disposition Log (e.g., 'append rows', 'never rewrite existing rows'). "
        "This is what makes re-running /skill-genesis-review idempotent."
    )


def test_review_body_states_idempotency_contract() -> None:
    """The review command body must describe the no-op behavior for fully-dispositioned reports.

    When all proposals have been dispositioned (none remain with Disposition: pending),
    re-running the command must exit cleanly rather than presenting an empty selection.
    """
    text = REVIEW_COMMAND.read_text(encoding="utf-8")
    body = _command_body(text)
    # Looking for language about pending filter, no-op, or idempotent re-run
    keywords = (
        "no-op",
        "no pending",
        "fully",
        "already reviewed",
        "none remain",
        "pending",
    )
    has_idempotency = any(kw in body.lower() for kw in keywords)
    assert has_idempotency, (
        "commands/skill-genesis-review.md body must describe the idempotency behavior: "
        "when no pending proposals remain, the command exits with a no-op or summary message "
        "rather than presenting an empty multi-select. "
        f"Searched for keywords {keywords!r} in body — none found."
    )


def test_review_body_references_pending_filter() -> None:
    """The review command body must describe filtering proposals by pending status.

    The command shows only proposals with Disposition: pending or
    Disposition: pending refinement. Without this filter, re-runs would
    re-present already-dispositioned proposals.
    """
    text = REVIEW_COMMAND.read_text(encoding="utf-8")
    body = _command_body(text)
    assert "pending" in body.lower(), (
        "commands/skill-genesis-review.md body must reference 'pending' proposals — "
        "the filter that determines which proposals to show in the multi-select. "
        "Without this filter, re-running the command presents already-dispositioned proposals."
    )


def test_review_body_lists_four_disposition_values() -> None:
    """The review command body must name all four disposition values.

    The four values — approve, reject, refine, defer — form the disposition
    vocabulary. The body must document them so the user understands the
    options available in the AskUserQuestion multi-select.
    """
    text = REVIEW_COMMAND.read_text(encoding="utf-8")
    body = _command_body(text)
    for value in ("approve", "reject", "refine", "defer"):
        assert value in body.lower(), (
            f"Disposition value '{value}' not found in commands/skill-genesis-review.md body. "
            f"All four disposition values (approve, reject, refine, defer) must be named "
            f"so the user understands the options in the batch multi-select."
        )


def test_review_body_describes_refine_as_pending_refinement() -> None:
    """The review command body must describe 'refine' as producing pending refinement status.

    When the user selects 'refine' for a proposal, it must be recorded as
    'pending refinement' rather than approved or rejected — it remains
    actionable in future review passes.
    """
    text = REVIEW_COMMAND.read_text(encoding="utf-8")
    body = _command_body(text)
    # Check that refine semantics (pending refinement / re-run later) are documented
    has_refinement_semantics = (
        "pending refinement" in body.lower()
        or ("refine" in body.lower() and "re-run" in body.lower())
        or ("refine" in body.lower() and "later" in body.lower())
    )
    assert has_refinement_semantics, (
        "commands/skill-genesis-review.md body must describe the 'refine' disposition as "
        "producing a 'pending refinement' state that the user can revisit in a future pass. "
        "This ensures refine does not force an immediate approve/reject decision."
    )


def test_review_body_describes_delegation_handoff() -> None:
    """The review command body must describe surfacing delegation handoffs after approval.

    After dispositioning, the command surfaces which approved proposals
    should be delegated to context-engineer (skill/rule creation) vs
    executed directly (memory proposals via remember). This is the
    recommended-delegation surface step.
    """
    text = REVIEW_COMMAND.read_text(encoding="utf-8")
    body = _command_body(text)
    has_delegation = any(
        kw in body.lower() for kw in ("delegation", "context-engineer", "handoff", "delegate")
    )
    assert has_delegation, (
        "commands/skill-genesis-review.md body must describe surfacing delegation handoffs "
        "for approved proposals (context-engineer for skills/rules, remember for memory). "
        "Searched for 'delegation', 'context-engineer', 'handoff', 'delegate' — none found."
    )


# ---------------------------------------------------------------------------
# Group 3: /skill-genesis invocation command
# ---------------------------------------------------------------------------


def test_genesis_command_file_exists() -> None:
    """commands/skill-genesis.md must exist.

    This is the on-demand invocation wrapper that spawns the skill-genesis
    agent in the background. Without it, users have no way to trigger a
    harvest pass via /skill-genesis.
    """
    assert GENESIS_COMMAND.exists(), (
        f"commands/skill-genesis.md not found at {GENESIS_COMMAND}. "
        "This command file must exist before tests can pass."
    )


def test_genesis_command_frontmatter_parseable() -> None:
    """commands/skill-genesis.md frontmatter must parse as valid YAML.

    A parse failure means the command is not registered by Claude Code.
    """
    text = GENESIS_COMMAND.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    required_keys = ["description", "argument-hint", "allowed-tools"]
    for key in required_keys:
        assert key in fm, (
            f"Required frontmatter key '{key!r}' missing from commands/skill-genesis.md. "
            f"Present keys: {list(fm.keys())}"
        )


def test_genesis_argument_hint_contains_since_flag() -> None:
    """commands/skill-genesis.md argument-hint must document the --since flag.

    --since <commit> scopes the harvest to learning sources newer than a
    given commit. It must be discoverable from the argument-hint.
    """
    text = GENESIS_COMMAND.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    hint = str(fm.get("argument-hint", ""))
    assert "--since" in hint, (
        f"'--since' flag not found in argument-hint for commands/skill-genesis.md. "
        f"Current argument-hint: {hint!r}. "
        "The --since <commit> flag scopes the harvest to recent learning sources."
    )


def test_genesis_argument_hint_contains_scope_flag() -> None:
    """commands/skill-genesis.md argument-hint must document the --scope flag.

    --scope <area> narrows the harvest to a specific area of the codebase.
    It must be discoverable from the argument-hint.
    """
    text = GENESIS_COMMAND.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    hint = str(fm.get("argument-hint", ""))
    assert "--scope" in hint, (
        f"'--scope' flag not found in argument-hint for commands/skill-genesis.md. "
        f"Current argument-hint: {hint!r}. "
        "The --scope <area> flag narrows the harvest to a specific codebase area."
    )


def test_genesis_argument_hint_contains_dry_run_flag() -> None:
    """commands/skill-genesis.md argument-hint must document the --dry-run flag.

    --dry-run lets the user preview what sources would be harvested without
    actually spawning the agent. It must be discoverable from the argument-hint.
    """
    text = GENESIS_COMMAND.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    hint = str(fm.get("argument-hint", ""))
    assert "--dry-run" in hint, (
        f"'--dry-run' flag not found in argument-hint for commands/skill-genesis.md. "
        f"Current argument-hint: {hint!r}. "
        "The --dry-run flag previews harvest without spawning the agent."
    )


def test_genesis_body_references_skill_genesis_agent() -> None:
    """commands/skill-genesis.md body must reference the skill-genesis agent via Task.

    The command is a thin wrapper: it spawns the skill-genesis agent in
    background mode. Without a Task delegation the agent is never invoked.
    """
    text = GENESIS_COMMAND.read_text(encoding="utf-8")
    body = _command_body(text)
    has_agent_ref = "skill-genesis" in body and ("Task" in body or "background" in body.lower())
    assert has_agent_ref, (
        "commands/skill-genesis.md body must reference the skill-genesis agent (via Task) "
        "and spawn it in background mode. "
        "The command is a thin wrapper: parse flags → Task(skill-genesis, bg=True) → surface path."
    )


def test_genesis_body_surfaces_report_path_or_review_reminder() -> None:
    """commands/skill-genesis.md body must surface the expected report path or /skill-genesis-review.

    After spawning the agent, the command must tell the user where the report
    will land and remind them to run /skill-genesis-review once it completes.
    """
    text = GENESIS_COMMAND.read_text(encoding="utf-8")
    body = _command_body(text)
    has_next_step = "skill-genesis-review" in body or "skill_genesis_reports" in body
    assert has_next_step, (
        "commands/skill-genesis.md body must reference either 'skill-genesis-review' or "
        "'.ai-state/skill_genesis_reports/' so the user knows where the report lands and "
        "what to run next to disposition it."
    )


# ---------------------------------------------------------------------------
# Group 4: Fixture-based disposition logic simulation
# ---------------------------------------------------------------------------


def test_fixture_has_pending_proposals_extractable_by_regex() -> None:
    """The fixture report must contain proposals parseable as 'pending' by regex.

    Simulates the review command's first step: scanning the report for
    proposals whose Disposition field is 'pending'. If no pending proposals
    are found, the review command would exit with a no-op — an incorrect
    behavior on a freshly-written report.
    """
    text = FIXTURE_REPORT.read_text(encoding="utf-8")
    pending = _pending_proposals_from_report(text)
    assert len(pending) >= 1, (
        "The fixture report must contain at least one proposal with 'Disposition: pending'. "
        f"Found pending proposals: {pending!r}. "
        "A freshly-written report must have pending proposals for the review command to present."
    )


def test_fixture_disposition_log_section_is_append_ready() -> None:
    """The fixture report's ## Disposition Log section must exist with table header.

    The review command appends rows to this section using Edit. If the
    section is absent on report creation, the append operation would need
    to first create the section — a more fragile operation. The section
    (with its table header) must exist from the start.
    """
    text = FIXTURE_REPORT.read_text(encoding="utf-8")
    assert "## Disposition Log" in text, (
        "Fixture report must contain '## Disposition Log' section. "
        "This section must be present (empty) at report creation so /skill-genesis-review "
        "can append rows without first creating the section."
    )
    # The disposition log table header must be present
    assert "| Timestamp |" in text or "Timestamp" in text, (
        "The ## Disposition Log section in the fixture must contain a table header row. "
        "The review command appends below this header; without it the table has no structure."
    )


def test_fully_dispositioned_report_has_no_pending_proposals() -> None:
    """A report where all proposals are approved/rejected must yield zero pending proposals.

    Simulates the idempotency check: re-running /skill-genesis-review on a
    fully-dispositioned report must find 0 pending proposals and exit with
    a no-op message rather than presenting an empty multi-select.
    """
    # Build a synthetic report where all proposals have Disposition: approved
    original_text = FIXTURE_REPORT.read_text(encoding="utf-8")
    # Replace all "Disposition**: pending" with "Disposition**: approved"
    fully_dispositioned = re.sub(
        r"(\*\*Disposition\*\*:\s*)pending(?: refinement)?",
        r"\1approved",
        original_text,
    )
    pending = _pending_proposals_from_report(fully_dispositioned)
    assert len(pending) == 0, (
        "After replacing all 'Disposition: pending' entries with 'Disposition: approved', "
        "the pending-proposal scanner must return 0 proposals. "
        f"Found {len(pending)} pending proposals in the fully-dispositioned report: {pending!r}. "
        "This failure means the pending-detection regex is too broad."
    )


def test_partially_dispositioned_report_shows_only_remaining_pending() -> None:
    """A partially-reviewed report must yield only the still-pending proposals.

    Simulates a partial re-run: the user dispositioned some proposals in a
    prior pass; on the next pass, only the unreviewed ones should appear.
    """
    original_text = FIXTURE_REPORT.read_text(encoding="utf-8")
    # Approve only the first proposal (replace first occurrence of "pending" in a proposal)
    first_proposal_pattern = re.compile(
        r"(### Proposal 1:.*?)(- \*\*Disposition\*\*:\s*)pending",
        re.DOTALL,
    )
    partial_text = first_proposal_pattern.sub(r"\1\2approved", original_text, count=1)
    pending = _pending_proposals_from_report(partial_text)
    # There should be fewer pending proposals than in the original
    original_pending = _pending_proposals_from_report(original_text)
    assert len(pending) < len(original_pending), (
        "After approving Proposal 1, the pending-proposal scanner must return fewer results "
        f"than the original report. Original pending: {len(original_pending)}, "
        f"After partial disposition: {len(pending)}. "
        "The review command must only show truly-pending proposals in each pass."
    )


def test_refined_proposal_still_appears_as_pending() -> None:
    """A proposal with 'pending refinement' disposition must still be returned by the pending scanner.

    The 'refine' disposition records the proposal as 'pending refinement' —
    it is NOT approved or rejected. A subsequent /skill-genesis-review pass
    must still present it so the user can finalize it.
    """
    # Build a report variant where the first proposal has "pending refinement"
    original_text = FIXTURE_REPORT.read_text(encoding="utf-8")
    first_proposal_pattern = re.compile(
        r"(### Proposal 1:.*?)(- \*\*Disposition\*\*:\s*)pending(?! refinement)",
        re.DOTALL,
    )
    refined_text = first_proposal_pattern.sub(r"\1\2pending refinement", original_text, count=1)
    pending = _pending_proposals_from_report(refined_text)
    assert len(pending) >= 1, (
        "A proposal with 'Disposition: pending refinement' must be returned by the "
        "pending-proposal scanner. Got 0 pending proposals from a report where Proposal 1 "
        "has 'Disposition: pending refinement'. "
        "The review command must include pending-refinement proposals in its next pass."
    )


# ---------------------------------------------------------------------------
# Group 5: Per-proposal type coverage — review command references all types
# ---------------------------------------------------------------------------


def test_review_body_references_skill_proposal_type() -> None:
    """The review command body must reference the 'skill' proposal type.

    Skill proposals are delegated to context-engineer. The body must
    acknowledge this type so the delegation surface step handles it.
    """
    text = REVIEW_COMMAND.read_text(encoding="utf-8")
    body = _command_body(text)
    assert "skill" in body.lower(), (
        "commands/skill-genesis-review.md body must reference 'skill' proposals. "
        "Skill proposals are the most common type and route to context-engineer delegation."
    )


def test_review_body_references_rule_proposal_type() -> None:
    """The review command body must reference the 'rule' proposal type.

    Rule proposals are also delegated to context-engineer. The body must
    distinguish them from skill proposals so the delegation surface is accurate.
    """
    text = REVIEW_COMMAND.read_text(encoding="utf-8")
    body = _command_body(text)
    assert "rule" in body.lower(), (
        "commands/skill-genesis-review.md body must reference 'rule' proposals. "
        "Rule proposals are delegated to context-engineer alongside skill proposals."
    )


# ---------------------------------------------------------------------------
# Bonus: argument-hint completeness for review command
# ---------------------------------------------------------------------------


def test_review_argument_hint_documents_report_flag() -> None:
    """commands/skill-genesis-review.md argument-hint must document --report flag.

    --report <path> lets the user override auto-discovery and specify a
    particular report file. Without documenting it, users must rely on
    auto-discovery even when they want to review a specific older report.
    """
    text = REVIEW_COMMAND.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    hint = str(fm.get("argument-hint", ""))
    assert "--report" in hint, (
        f"'--report' flag not found in argument-hint for commands/skill-genesis-review.md. "
        f"Current argument-hint: {hint!r}. "
        "The --report <path> flag lets the user target a specific report for disposition."
    )
