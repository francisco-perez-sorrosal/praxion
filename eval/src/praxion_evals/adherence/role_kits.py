"""The kit declarations: what each role is asked, and in which repositories.

Declarations only. ``tasks`` builds the seeded task sets from them and re-exports
``RoleKit`` and ``ROLE_KITS``, so ``tasks.ROLE_KITS`` and every importer of it keep working.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class RoleKit:
    brief: str  # the input file the task prompt points the role at
    prompt: str  # the task prompt, with ``{slug}`` and ``{brief}`` slots
    fixtures: tuple[str, ...]  # repository ids under ``fixtures/repos``
    # Files every fixture contributes under ``<role>/inputs/<fixture>``: the planning
    # documents the role's own definition expects. Empty when the role needs none.
    fixture_inputs: tuple[str, ...] = ()
    # Project-level material the role expects beside the code, as directories under
    # ``fixtures/overlays`` copied over the repository root (a model, a ledger, a roadmap).
    overlays: tuple[str, ...] = ()


# Prompts name the role's mode only where its definition reads the mode from the spawn
# prompt, and never an arm: both arms receive the same words.
ROLE_KITS: Mapping[str, RoleKit] = {
    "researcher": RoleKit(
        brief="RESEARCH_BRIEF.md",
        prompt=(
            "Task slug: {slug}. Carry out the research described in "
            ".ai-work/{slug}/{brief}, working in the repository you are in."
        ),
        fixtures=("ledger-cli", "notes-service"),
    ),
    "verifier": RoleKit(
        brief="VERIFICATION_BRIEF.md",
        prompt=(
            "Task slug: {slug}. Verify the completed work. Your assignment is "
            ".ai-work/{slug}/{brief}; the planning documents are in the same directory "
            "and the implemented change is in the repository you are in."
        ),
        fixtures=("ledger-cli", "notes-service"),
        fixture_inputs=("SYSTEMS_PLAN.md", "IMPLEMENTATION_PLAN.md", "WIP.md"),
    ),
    "implementer": RoleKit(
        brief="WIP.md",
        prompt=(
            "Task slug: {slug}. Implement the current step in .ai-work/{slug}/{brief}; the "
            "plan and the learnings are in the same directory and the change goes in the "
            "repository you are in."
        ),
        fixtures=("ledger-cli", "notes-service"),
        fixture_inputs=("LEARNINGS.md",),
    ),
    "systems-architect": RoleKit(
        brief="TASK_BRIEF.md",
        prompt=(
            "Task slug: {slug}. Design the change described in .ai-work/{slug}/{brief}; the "
            "research findings are in the same directory and the repository you are in is "
            "the codebase."
        ),
        fixtures=("ledger-cli", "notes-service"),
        fixture_inputs=("RESEARCH_FINDINGS.md",),
    ),
    "implementation-planner": RoleKit(
        brief="SYSTEMS_PLAN.md",
        prompt=(
            "Task slug: {slug}. Plan the implementation of the design in "
            ".ai-work/{slug}/{brief}, working in the repository you are in."
        ),
        fixtures=("ledger-cli", "notes-service"),
    ),
    "test-engineer": RoleKit(
        brief="WIP.md",
        prompt=(
            "Task slug: {slug}. Write the tests for the step assigned in "
            ".ai-work/{slug}/{brief}; the plan, the systems plan and the learnings are in "
            "the same directory and the tests go in the repository you are in."
        ),
        fixtures=("ledger-cli", "notes-service"),
        fixture_inputs=("SYSTEMS_PLAN.md", "LEARNINGS.md"),
    ),
    "doc-engineer": RoleKit(
        brief="DOC_REQUEST.md",
        prompt=(
            "Task slug: {slug}. Carry out the documentation request in "
            ".ai-work/{slug}/{brief}, working in the repository you are in."
        ),
        fixtures=("ledger-cli", "notes-service"),
    ),
    "sentinel": RoleKit(
        brief="AUDIT_SCOPE.md",
        prompt=(
            "Task slug: {slug}. Run the audit scoped in .ai-work/{slug}/{brief} on the "
            "repository you are in."
        ),
        fixtures=("ledger-cli", "notes-service"),
        overlays=("ecosystem",),
    ),
    "architect-validator": RoleKit(
        brief="VALIDATION_SCOPE.md",
        prompt=(
            "Task slug: {slug}. Run --mode=on-demand for the repository you are in; what "
            "to look at is in .ai-work/{slug}/{brief}."
        ),
        fixtures=("ledger-cli", "notes-service"),
        overlays=("architecture",),
    ),
    "context-engineer": RoleKit(
        brief="TASK_BRIEF.md",
        prompt=(
            "Task slug: {slug}. Mode: shadowing. Review the context artifacts that the task "
            "in .ai-work/{slug}/{brief} touches, in the repository you are in."
        ),
        fixtures=("ledger-cli", "notes-service"),
        overlays=("ecosystem",),
    ),
    "cicd-engineer": RoleKit(
        brief="CI_REQUEST.md",
        prompt=(
            "Task slug: {slug}. Carry out the CI/CD request in .ai-work/{slug}/{brief}, "
            "working in the repository you are in."
        ),
        fixtures=("ledger-cli", "notes-service"),
        overlays=("ci",),
    ),
    "discipline-consultant": RoleKit(
        brief="TASK_BRIEF.md",
        prompt=(
            "Discipline: data-structure-specialist\nTask slug: {slug}\nConvened at: "
            "architecture. The task is in .ai-work/{slug}/{brief}; the draft you challenge "
            "is SYSTEMS_PLAN.md in the same directory."
        ),
        fixtures=("ledger-cli", "notes-service"),
        fixture_inputs=("RESEARCH_FINDINGS.md", "SYSTEMS_PLAN.md"),
    ),
    "interface-designer": RoleKit(
        brief="SYSTEMS_PLAN.md",
        prompt=(
            "Task slug: {slug}. Design the interface layer of the plan in "
            ".ai-work/{slug}/{brief}, working in the repository you are in."
        ),
        fixtures=("ledger-cli", "notes-service"),
    ),
    "agentic-transactions-architect": RoleKit(
        brief="SYSTEMS_PLAN.md",
        prompt=(
            "Task slug: {slug}. Design the transaction layer of the plan in "
            ".ai-work/{slug}/{brief}, working in the repository you are in."
        ),
        fixtures=("ledger-cli", "notes-service"),
    ),
    "promethean": RoleKit(
        brief="IDEATION_SEED.md",
        prompt=(
            "Task slug: {slug}. You are launched as a background agent and no user is "
            "available to answer, so run in non-interactive mode. The ideation seed is in "
            ".ai-work/{slug}/{brief}."
        ),
        fixtures=("ledger-cli", "notes-service"),
        overlays=("ecosystem", "sentinel-baseline"),
    ),
    "roadmap-cartographer": RoleKit(
        brief="ROADMAP_REQUEST.md",
        prompt=(
            "Task slug: {slug}. Mode: diff. No user is available to answer, so run in "
            "non-interactive mode. Re-audit the repository you are in against its existing "
            "ROADMAP.md; the request is in .ai-work/{slug}/{brief}."
        ),
        fixtures=("ledger-cli", "notes-service"),
        overlays=("ecosystem", "roadmap"),
    ),
    "skill-genesis": RoleKit(
        brief="LEARNINGS.md",
        prompt=(
            "Task slug: {slug}. This is a post-pipeline harvest: the finished pipeline's "
            "learnings are in .ai-work/{slug}/, starting with {brief}."
        ),
        fixtures=("ledger-cli", "notes-service"),
        fixture_inputs=("VERIFICATION_REPORT.md",),
        overlays=("ecosystem",),
    ),
}
