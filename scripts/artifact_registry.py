#!/usr/bin/env python3
"""Canonical registry of Praxion pipeline artifacts — the single source of truth.

Three hard-coded `.ai-work/<slug>/` artifact lists historically drifted apart:
the dashboard's workshop discovery (`dashboard_app/src/server/artifacts/files.ts`),
the eval task manifest (`eval/src/praxion_evals/harness/task_manifest.py`), and the
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

- ``dashboard`` — listed by the dashboard's `CANONICAL_WORKSHOP_ARTIFACTS`
  in `files.ts` (the renderable/discoverable set).
- ``snapshot`` — captured by the precompact hook's `PIPELINE_DOCS` (the
  post-compaction orientation set).
- ``eval_tier`` / ``eval_required`` — the eval task manifest's expected
  deliverable for a coordination tier.

Specialty artifacts (roadmap, ML, rework-worktree) are registered for
completeness with no consumer flags — documented, but not enforced into the
three core pipeline consumers.
"""

from __future__ import annotations

from dataclasses import dataclass

# -- Declarative-spine vocabularies -------------------------------------------
# Each artifact names the gate that makes it exist (`production_gate`) and the
# policy that governs its removal (`cleanup_policy`). The fields are *populated*
# here and *checked* by scripts/test_artifact_registry.py — they are not read by
# the projection helpers, so adding them is back-compatible by construction.

# production_gate kinds — the gate that MAKES the artifact exist. Format is
# "<kind>:<ref>" for ref-bearing kinds; the ref-free kinds carry no ":<ref>":
#   script:<script-name> — a script produces or enforces the artifact
#   hook:<hook-name>     — a git/session hook produces it
#   producer:<agent>     — a pipeline agent produces it as a deliverable
#   none                 — no gate (the obligation is unenforced)
#   deferred             — gate is realized later in the same wave (bare, no ref)
_GATE_KINDS: frozenset[str] = frozenset({"script", "hook", "producer", "none", "deferred"})

# detection_gate kinds — the gate that DETECTS the artifact's absence or quality,
# distinct from production: a detector flags a missing/hollow artifact, it does
# not create one. Separated from production_gate per the Wave-1–3 audit (EA-02),
# which found `sentinel:Pxx` mislabelled as production when it is presence-detection.
#   sentinel:<check-id>  — a sentinel catalog check flags absence/quality
#   none                 — no detection backstop
_DETECTION_GATE_KINDS: frozenset[str] = frozenset({"sentinel", "none"})

# cleanup_policy values mirror clean_work_safety.py's deletion classes:
#   delete           — SAFE: deletable once the pipeline ends
#   archive          — preserve into a permanent location before removal
#   block-if-active  — BLOCK: never delete while the pipeline is in flight
#   consume-marker   — WARN: deletable only after its handoff marker is consumed
_CLEANUP_POLICIES: frozenset[str] = frozenset(
    {"delete", "archive", "block-if-active", "consume-marker"}
)


# -- Model --------------------------------------------------------------------


@dataclass(frozen=True)
class Artifact:
    """One pipeline artifact and the consumers that must list it."""

    name: str  # filename
    location: str  # ai-work | ai-work-root | ai-state | docs
    lifecycle: str  # ephemeral | session-persistent | permanent
    activation: str  # always | conditional | specialist | roadmap | ml | rework
    dashboard: bool = False  # dashboard CANONICAL_WORKSHOP_ARTIFACTS (files.ts)
    snapshot: bool = False  # precompact PIPELINE_DOCS
    eval_tier: str | None = None  # standard | full
    eval_required: bool = False  # always-required deliverable at eval_tier
    eval_conditional: bool = False  # required at eval_tier only when its producer ran
    production_gate: str = "none"  # "<kind>:<ref>" | "none" | "deferred"; kind ∈ _GATE_KINDS
    detection_gate: str = "none"  # "sentinel:<id>" | "none"; kind ∈ _DETECTION_GATE_KINDS
    cleanup_policy: str = "delete"  # ∈ _CLEANUP_POLICIES
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
        production_gate="producer:orchestrator",
        detection_gate="sentinel:P06",
        cleanup_policy="delete",
        description="Intake intent / key signals / health guards / uncertainty.",
    ),
    Artifact(
        "IDEA_PROPOSAL.md",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        snapshot=True,
        production_gate="producer:promethean",
        cleanup_policy="delete",
        description="Promethean's validated idea feeding research/design.",
    ),
    Artifact(
        "RESEARCH_FINDINGS.md",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        snapshot=True,
        production_gate="producer:researcher",
        cleanup_policy="delete",
        description="Researcher's evidence base.",
    ),
    Artifact(
        "CONTEXT_REVIEW.md",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        production_gate="producer:context-engineer",
        cleanup_policy="delete",
        description="Context-engineer's cumulative artifact-health review.",
    ),
    Artifact(
        "INTERFACE_DESIGN.md",
        "ai-work",
        "ephemeral",
        "specialist",
        dashboard=True,
        snapshot=True,
        production_gate="producer:interface-designer",
        detection_gate="sentinel:P07",  # challenge-disposition detection
        cleanup_policy="delete",
        description="Interface-designer's boundary decisions + challenge loop.",
    ),
    Artifact(
        "TRANSACTIONS_DESIGN.md",
        "ai-work",
        "ephemeral",
        "specialist",
        dashboard=True,
        snapshot=True,
        production_gate="producer:agentic-transactions-architect",
        detection_gate="sentinel:P07",  # challenge-disposition detection
        cleanup_policy="delete",
        description="Transactions-architect's mandate/settlement/HITL decisions.",
    ),
    # The only variable-named artifact in the set: one fragment per convened
    # discipline, so a slug can hold several. `dashboard` and `snapshot` are
    # false because both consumers match exact filenames (a TS string list and
    # `task_dir / doc_name`), not because the fragment is uninteresting to
    # either -- wiring it in needs glob support on the consumer side, which is
    # a change to them and not to this registry.
    Artifact(
        "CONSULT_<discipline>.md",
        "ai-work",
        "ephemeral",
        "specialist",
        production_gate="producer:discipline-consultant",
        detection_gate="sentinel:P07",  # undispositioned-challenge detection
        cleanup_policy="delete",
        description=(
            "Discipline consultant's per-challenge falsifiable objections; the convener "
            "adjudicates each in place and mirrors it to CONSULT_LEDGER.md. Cleanup is "
            "`delete` because that is what clean_work_safety.py actually classifies it as "
            "-- the ledger is the durable half of the pair."
        ),
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
        production_gate="producer:systems-architect",
        cleanup_policy="consume-marker",  # REQ-bearing plan WARNs until its spec is archived
        description="Architect's system plan with acceptance criteria.",
    ),
    Artifact(
        "PRE_REFACTOR_PLAN.md",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        snapshot=True,
        production_gate="producer:systems-architect",
        cleanup_policy="consume-marker",  # WARNs until a [CONSUMED] marker is present
        description="Pre-feature refactor mini-pipeline activation artifact.",
    ),
    Artifact(
        "SPEC_DELTA.md",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        production_gate="producer:systems-architect",
        cleanup_policy="delete",
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
        production_gate="producer:implementation-planner",
        cleanup_policy="delete",
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
        production_gate="producer:implementation-planner",
        cleanup_policy="block-if-active",  # BLOCK while any step box is unchecked
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
        production_gate="producer:implementation-planner",
        cleanup_policy="consume-marker",  # WARNs until merged to .ai-state/ (verifier harvest)
        description="In-flight learning capture; the bridge to durable intelligence.",
    ),
    Artifact(
        "TEST_BASELINE.md",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        production_gate="producer:test-engineer",
        cleanup_policy="delete",
        description="Pre-pipeline failing-test snapshot (verifier regression baseline).",
    ),
    Artifact(
        # eval: conditionally required — `eval_conditional` at standard, gated by the
        # task_manifest activation predicate `_tests_ran` (TEST_BASELINE present), so a
        # no-test run is not penalised for its absence.
        "TEST_RESULTS.md",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        snapshot=True,
        eval_tier="standard",
        eval_conditional=True,
        production_gate="producer:implementer",
        cleanup_policy="delete",
        description="Test-run evidence handoff to the verifier.",
    ),
    Artifact(
        # eval: conditionally required — gated by `_sdd_active` (a requirement-id
        # heading in SYSTEMS_PLAN), so a config/infra pipeline with no requirements
        # block is not penalised.
        "traceability.yml",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        eval_tier="standard",
        eval_conditional=True,
        production_gate="producer:implementer",
        cleanup_policy="consume-marker",  # WARNs until rendered into the archived spec matrix
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
        production_gate="producer:verifier",
        cleanup_policy="consume-marker",  # WARNs until its patterns are folded into LEARNINGS.md
        description="Verifier's quality-gate report.",
    ),
    Artifact(
        "REWORK_MANIFEST.md",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        snapshot=True,
        production_gate="script:rework_manifest.py",
        cleanup_policy="block-if-active",  # BLOCK: an open manifest means rework may be live
        description="Clustered remediation worktree manifest.",
    ),
    Artifact(
        "PROGRESS.md",
        "ai-work",
        "ephemeral",
        "always",
        dashboard=True,
        snapshot=True,
        production_gate="producer:orchestrator",
        cleanup_policy="delete",
        description="Append-only phase-transition log.",
    ),
    Artifact(
        "RECOVERY_LOG.md",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        snapshot=True,
        production_gate="producer:orchestrator",
        cleanup_policy="consume-marker",  # WARNs: it is the auto-recovery audit trail
        description="Audit trail for truncation auto-recovery actions.",
    ),
    # --- ai-work root (not slug-scoped) ---
    Artifact(
        "PIPELINE_STATE.md",
        "ai-work-root",
        "ephemeral",
        "always",
        production_gate="hook:precompact_state.py",
        cleanup_policy="delete",
        description="PreCompact consolidated snapshot (output, not an input doc).",
    ),
    # --- specialty: rework worktree, roadmap, ML (registered, not enforced) ---
    Artifact(
        "VERIFIER_FINDINGS.md",
        "ai-work",
        "ephemeral",
        "rework",
        production_gate="producer:orchestrator",
        cleanup_policy="delete",
        description="Rework-intake artifact derived from one manifest row (rework worktree).",
    ),
    Artifact(
        "ROADMAP_DRAFT.md",
        "ai-work",
        "ephemeral",
        "roadmap",
        production_gate="producer:roadmap-cartographer",
        cleanup_policy="delete",
        description="Cartographer's intermediate roadmap draft.",
    ),
    Artifact(
        "CONTRADICTION_MAP.md",
        "ai-work",
        "ephemeral",
        "roadmap",
        production_gate="producer:roadmap-cartographer",
        cleanup_policy="delete",
        description="Cartographer's cross-lens conflict list.",
    ),
    Artifact(
        "TRAINING_RESULTS.md",
        "ai-work",
        "ephemeral",
        "ml",
        production_gate="producer:ml-training-run",
        cleanup_policy="delete",
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
    """Filenames the eval task manifest must *always* require for the given tier."""
    return {a.name for a in ARTIFACTS if a.eval_required and a.eval_tier == tier}


def eval_conditional(tier: str) -> set[str]:
    """Filenames the eval task manifest requires *conditionally* (activation-gated) for the tier."""
    return {a.name for a in ARTIFACTS if a.eval_conditional and a.eval_tier == tier}


def all_names() -> set[str]:
    """Every registered artifact filename."""
    return {a.name for a in ARTIFACTS}


def by_name(name: str) -> Artifact | None:
    for a in ARTIFACTS:
        if a.name == name:
            return a
    return None


def cleanup_policy_for(name: str) -> str | None:
    """The artifact's cleanup_policy, or None if unregistered (read-only projection)."""
    a = by_name(name)
    return a.cleanup_policy if a is not None else None
