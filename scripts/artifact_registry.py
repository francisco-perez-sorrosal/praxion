#!/usr/bin/env python3
"""Canonical registry of Praxion pipeline artifacts — the single source of truth.

Four hard-coded `.ai-work/<slug>/` artifact lists historically drifted apart:
the documentation manifest (`scripts/build_doc_manifest.py`), the dashboard's
workshop discovery (`dashboard_app/src/server/artifacts/files.ts`), the eval
task manifest (`eval/src/praxion_evals/harness/task_manifest.py`), and the
compaction snapshot hook (`hooks/precompact_state.py`). Each lists a *different*
subset for a *different* purpose, so they cannot share one structure — but they
must agree on the underlying artifact set.

This registry is the authority. `scripts/test_artifact_registry.py` asserts
every consumer's list matches this registry's projection for that consumer (the
drift gate, per the gate-liveness rule: it ships canaries proving it bites when a
consumer adds an unknown artifact or drops a required one). Consumers are
*checked* against the registry today; wiring them to *read* from it (so a new
artifact is a one-line change) is a clean future step.

Per-consumer membership is expressed as flags on each `Artifact`:

- ``dashboard`` — listed by `build_doc_manifest._AI_WORK_FILES` AND the
  dashboard's `CANONICAL_WORKSHOP_ARTIFACTS` (the renderable/discoverable set).
- ``snapshot`` — captured by the precompact hook's `PIPELINE_DOCS` (the
  post-compaction orientation set).
- ``eval_tier`` / ``eval_required`` — the eval task manifest's expected
  deliverable for a coordination tier.

Specialty artifacts (roadmap, ML, rework-worktree) are registered for
completeness with no consumer flags — documented, but not enforced into the
four core pipeline consumers.
"""

from __future__ import annotations

from dataclasses import dataclass

# -- Model --------------------------------------------------------------------


@dataclass(frozen=True)
class Artifact:
    """One pipeline artifact and the consumers that must list it."""

    name: str  # filename
    location: str  # ai-work | ai-work-root | ai-state | docs
    lifecycle: str  # ephemeral | session-persistent | permanent
    activation: str  # always | conditional | specialist | roadmap | ml | rework
    dashboard: bool = False  # build_doc_manifest._AI_WORK_FILES + files.ts
    snapshot: bool = False  # precompact PIPELINE_DOCS
    eval_tier: str | None = None  # standard | full
    eval_required: bool = False  # required deliverable at eval_tier
    description: str = ""


# -- Canonical `.ai-work/<slug>/` set -----------------------------------------
# Grounded in rules/swe/agent-intermediate-documents.md (the .ai-work tree) plus
# the artifact-lifecycle audit's F-04 (manifest coverage) and F-10 (eval scope).

ARTIFACTS: tuple[Artifact, ...] = (
    Artifact(
        "TASK_BRIEF.md",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        snapshot=True,
        description="Intake intent / key signals / health guards / uncertainty.",
    ),
    Artifact(
        "IDEA_PROPOSAL.md",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        snapshot=True,
        description="Promethean's validated idea feeding research/design.",
    ),
    Artifact(
        "RESEARCH_FINDINGS.md",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        snapshot=True,
        description="Researcher's evidence base.",
    ),
    Artifact(
        "CONTEXT_REVIEW.md",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        description="Context-engineer's cumulative artifact-health review.",
    ),
    Artifact(
        "INTERFACE_DESIGN.md",
        "ai-work",
        "ephemeral",
        "specialist",
        dashboard=True,
        snapshot=True,
        description="Interface-designer's boundary decisions + challenge loop.",
    ),
    Artifact(
        "TRANSACTIONS_DESIGN.md",
        "ai-work",
        "ephemeral",
        "specialist",
        dashboard=True,
        snapshot=True,
        description="Transactions-architect's mandate/settlement/HITL decisions.",
    ),
    Artifact(
        "SYSTEMS_PLAN.md",
        "ai-work",
        "ephemeral",
        "always",
        dashboard=True,
        snapshot=True,
        eval_tier="standard",
        eval_required=True,
        description="Architect's system plan with acceptance criteria.",
    ),
    Artifact(
        "PRE_REFACTOR_PLAN.md",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        snapshot=True,
        description="Pre-feature refactor mini-pipeline activation artifact.",
    ),
    Artifact(
        "SPEC_DELTA.md",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        description="Brownfield behavioral delta from archived specs.",
    ),
    Artifact(
        "IMPLEMENTATION_PLAN.md",
        "ai-work",
        "session-persistent",
        "always",
        dashboard=True,
        snapshot=True,
        eval_tier="standard",
        eval_required=True,
        description="Planner's approved step decomposition.",
    ),
    Artifact(
        "WIP.md",
        "ai-work",
        "session-persistent",
        "always",
        dashboard=True,
        snapshot=True,
        eval_tier="standard",
        eval_required=True,
        description="Live execution position.",
    ),
    Artifact(
        "LEARNINGS.md",
        "ai-work",
        "session-persistent",
        "always",
        dashboard=True,
        snapshot=True,
        eval_tier="standard",
        eval_required=True,
        description="In-flight learning capture; the bridge to durable intelligence.",
    ),
    Artifact(
        "TEST_BASELINE.md",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        description="Pre-pipeline failing-test snapshot (verifier regression baseline).",
    ),
    Artifact(
        # eval: conditionally produced (only when tests run), so NOT marked
        # eval_required — the flat manifest model can't express "required when
        # tests ran". Expanding to conditional eval specs is a follow-up.
        "TEST_RESULTS.md",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        snapshot=True,
        description="Test-run evidence handoff to the verifier.",
    ),
    Artifact(
        "traceability.yml",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        description="In-flight REQ -> tests -> implementation mapping.",
    ),
    Artifact(
        "VERIFICATION_REPORT.md",
        "ai-work",
        "ephemeral",
        "always",
        dashboard=True,
        snapshot=True,
        eval_tier="standard",
        eval_required=True,
        description="Verifier's quality-gate report.",
    ),
    Artifact(
        "REWORK_MANIFEST.md",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        snapshot=True,
        description="Clustered remediation worktree manifest.",
    ),
    Artifact(
        "PROGRESS.md",
        "ai-work",
        "ephemeral",
        "always",
        dashboard=True,
        snapshot=True,
        description="Append-only phase-transition log.",
    ),
    Artifact(
        "RECOVERY_LOG.md",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        snapshot=True,
        description="Audit trail for truncation auto-recovery actions.",
    ),
    # --- ai-work root (not slug-scoped) ---
    Artifact(
        "PIPELINE_STATE.md",
        "ai-work-root",
        "ephemeral",
        "always",
        description="PreCompact consolidated snapshot (output, not an input doc).",
    ),
    # --- specialty: rework worktree, roadmap, ML (registered, not enforced) ---
    Artifact(
        "VERIFIER_FINDINGS.md",
        "ai-work",
        "ephemeral",
        "rework",
        description="Rework-intake artifact derived from one manifest row (rework worktree).",
    ),
    Artifact(
        "ROADMAP_DRAFT.md",
        "ai-work",
        "ephemeral",
        "roadmap",
        description="Cartographer's intermediate roadmap draft.",
    ),
    Artifact(
        "CONTRADICTION_MAP.md",
        "ai-work",
        "ephemeral",
        "roadmap",
        description="Cartographer's cross-lens conflict list.",
    ),
    Artifact(
        "TRAINING_RESULTS.md",
        "ai-work",
        "ephemeral",
        "ml",
        description="ML run metrics + budget/eval evidence.",
    ),
)


# -- Projections (the per-consumer expected sets the drift test enforces) ------


def dashboard_artifacts() -> set[str]:
    """Filenames the doc manifest + dashboard workshop discovery must list."""
    return {a.name for a in ARTIFACTS if a.dashboard}


def snapshot_artifacts() -> set[str]:
    """Filenames the precompact hook's PIPELINE_DOCS must snapshot."""
    return {a.name for a in ARTIFACTS if a.snapshot}


def eval_required(tier: str) -> set[str]:
    """Filenames the eval task manifest must require for the given tier."""
    return {a.name for a in ARTIFACTS if a.eval_required and a.eval_tier == tier}


def all_names() -> set[str]:
    """Every registered artifact filename."""
    return {a.name for a in ARTIFACTS}


def by_name(name: str) -> Artifact | None:
    for a in ARTIFACTS:
        if a.name == name:
            return a
    return None
