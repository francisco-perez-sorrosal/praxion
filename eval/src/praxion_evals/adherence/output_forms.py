"""Where each role's definition puts its output, and the partial form it states for a forced stop.

Two tables read off the agent definitions, one row per role: C1 holds a session to
:data:`DURABLE_OUTPUTS` and C5 to :data:`PARTIAL_FORMS`. A role absent from either has had its
definition unread, which the check reports as withheld.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

DRAFT_ADRS = ".ai-state/decisions/drafts"  # where a decision-making role leaves its ADR fragments


@dataclass(frozen=True)
class DurableOutput:
    """Where a role's own definition puts its output.

    ``document`` is a file in the task's slug directory, or a path under ``.ai-state/``,
    either of which may hold ``*`` for a name the definition leaves open (see
    :func:`document_path`); ``also_accepted`` are the files that stand in for it (a
    parallel-mode fragment); ``other_locations`` are the repo-relative files or
    directories it may also write. ``anywhere`` is a role whose work is the
    change to the repository itself: its document must exist, and no write is stray.
    No ``document`` means the definition names none (the role's edits are the output).
    """

    document: str | None
    other_locations: tuple[str, ...] = ()
    also_accepted: tuple[str, ...] = ()
    anywhere: bool = False

    def __post_init__(self) -> None:
        if self.anywhere and self.other_locations:
            raise ValueError("a role that may write anywhere has no other locations to list")

    def documents(self) -> tuple[str, ...]:
        return (self.document, *self.also_accepted) if self.document else ()


RESEARCH_FINDINGS = "RESEARCH_FINDINGS.md"
SENTINEL_REPORTS = ".ai-state/sentinel_reports"
SKILL_GENESIS_REPORTS = ".ai-state/skill_genesis_reports"

# Rows are read off each role's agent definition, one per role the eval covers so far.
DURABLE_OUTPUTS: Mapping[str, DurableOutput] = {
    "researcher": DurableOutput(RESEARCH_FINDINGS),
    "verifier": DurableOutput("VERIFICATION_REPORT.md", (".ai-state/TECH_DEBT_LEDGER.md",)),
    "systems-architect": DurableOutput(
        "SYSTEMS_PLAN.md",
        (
            DRAFT_ADRS,
            ".ai-state/DESIGN.md",
            ".ai-state/SYSTEM_DEPLOYMENT.md",
            "docs/architecture.md",
            "docs/diagrams",
        ),
    ),
    "implementation-planner": DurableOutput("IMPLEMENTATION_PLAN.md", (DRAFT_ADRS,)),
    "implementer": DurableOutput("WIP.md", also_accepted=("WIP_implementer.md",), anywhere=True),
    "test-engineer": DurableOutput(
        "TEST_RESULTS.md",
        also_accepted=("TEST_RESULTS_test-engineer.md", "ACCEPTANCE_TESTS.md"),
        anywhere=True,
    ),
    "doc-engineer": DurableOutput(None, anywhere=True),
    "interface-designer": DurableOutput("INTERFACE_DESIGN.md", (DRAFT_ADRS,)),
    "agentic-transactions-architect": DurableOutput("TRANSACTIONS_DESIGN.md", (DRAFT_ADRS,)),
    "sentinel": DurableOutput(
        f"{SENTINEL_REPORTS}/SENTINEL_REPORT_*.md",
        (SENTINEL_REPORTS, ".ai-state/TECH_DEBT_LEDGER.md"),
    ),
    "architect-validator": DurableOutput(
        "ARCHITECTURE_VALIDATION.md", (".ai-state/TECH_DEBT_LEDGER.md",)
    ),
    "context-engineer": DurableOutput("CONTEXT_REVIEW.md", anywhere=True),
    "cicd-engineer": DurableOutput(None, anywhere=True),
    "discipline-consultant": DurableOutput("CONSULT_*.md"),
    "promethean": DurableOutput("IDEA_PROPOSAL.md", (".ai-state/idea_ledgers", "CLAUDE.md")),
    "roadmap-cartographer": DurableOutput("ROADMAP_DRAFT.md", ("ROADMAP.md",)),
    "skill-genesis": DurableOutput(
        f"{SKILL_GENESIS_REPORTS}/SKILL_GENESIS_REPORT_*.md", (SKILL_GENESIS_REPORTS,)
    ),
}


PARTIAL_MARKER = "[PARTIAL]"
COMPLETED_PHASES = "**Completed phases**:"
STOPPED_AT = "**Stopped at**:"
FAILED_AT = "**Failed at**:"


@dataclass(frozen=True)
class PartialForm:
    """The partial form a role's definition states: ``[PARTIAL]`` in the title, then these lines."""

    progress_lines: tuple[str, ...]


# A role absent from the table has had its definition unread (withheld); a role mapped
# to None was read and states no partial form (not applicable).
PARTIAL_FORMS: Mapping[str, PartialForm | None] = {
    "researcher": PartialForm((COMPLETED_PHASES,)),
    "verifier": PartialForm((COMPLETED_PHASES,)),
    "systems-architect": PartialForm((COMPLETED_PHASES,)),
    "implementation-planner": PartialForm((COMPLETED_PHASES,)),
    "implementer": PartialForm((COMPLETED_PHASES, STOPPED_AT)),
    "test-engineer": PartialForm((COMPLETED_PHASES, FAILED_AT)),
    "doc-engineer": PartialForm((COMPLETED_PHASES, FAILED_AT)),
    "interface-designer": PartialForm((COMPLETED_PHASES, FAILED_AT)),
    "agentic-transactions-architect": PartialForm((COMPLETED_PHASES, FAILED_AT)),
    "sentinel": PartialForm((COMPLETED_PHASES, STOPPED_AT)),
    "architect-validator": None,
    "context-engineer": PartialForm((COMPLETED_PHASES, FAILED_AT)),
    "cicd-engineer": PartialForm((COMPLETED_PHASES, FAILED_AT)),
    "discipline-consultant": None,
    "promethean": PartialForm((COMPLETED_PHASES, STOPPED_AT)),
    "roadmap-cartographer": PartialForm((COMPLETED_PHASES, STOPPED_AT)),
    "skill-genesis": PartialForm((COMPLETED_PHASES, FAILED_AT)),
}
