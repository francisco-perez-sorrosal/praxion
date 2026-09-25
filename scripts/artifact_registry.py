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
- ``floor`` — the per-tier artifact floor (see "Per-tier artifact floor"
  below): what a Standard/Full pipeline must produce, and how strictly.

Specialty artifacts (roadmap, ML, rework-worktree) are registered for
completeness with no consumer flags — documented, but not enforced into the
three core pipeline consumers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

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


# -- Per-tier artifact floor ---------------------------------------------------
# What a Standard/Full pipeline must produce, and how strictly -- the one
# registry-owned projection every reader derives from instead of duplicating
# the list. Replaces the correlated eval_tier/eval_required/eval_conditional
# trio (a Cartesian product whose combinations included impossible states,
# e.g. eval_required=True with eval_tier=None) with a single `floor` field
# naming a `Floor`, whose smart constructor makes "Full weaker than Standard"
# unrepresentable rather than merely undesirable.


class Tier(StrEnum):
    """Coordination-protocol tiers that carry a mechanical artifact floor."""

    STANDARD = "standard"
    FULL = "full"


class Signal(StrEnum):
    """A conditional floor entry's activation signal.

    ``PRODUCED`` is declarative, not file-decidable: "the producer agent was
    spawned" is not "the producer ran in its producing role" (a
    context-engineer invoked as plain executor writes no CONTEXT_REVIEW.md),
    so `signal_holds` never guesses at it -- it returns `None`.
    """

    TESTS_RAN = "tests-ran"
    SDD_ACTIVE = "sdd-active"
    PRODUCED = "produced"


# A floor entry's requirement: unconditional, or gated on a `Signal`.
Requirement = Literal["always"] | Signal

# The literal a planner writes into TEST_BASELINE.md when a project has no
# test target, so absence of a real baseline always reads as a defect rather
# than an unnoticed gap. Paired site: agents/implementation-planner.md.
NO_TEST_TARGET_MARKER = "no test target"

# A numbered requirement *heading* (the SDD behavioral-spec shape), not a bare
# mention of one in prose -- a config/infra plan that merely says a REQ block
# is unwarranted must not read as SDD-active.
_REQ_HEADING_RE = re.compile(r"(?m)^#{1,6}\s*REQ-\d")


def _requirement_strength(requirement: Requirement) -> int:
    """Total order enforcing Full >= Standard: always > decidable signal > produced."""
    if requirement == "always":
        return 2
    if requirement == Signal.PRODUCED:
        return 0
    return 1


@dataclass(frozen=True)
class Floor:
    """An artifact's per-tier obligation.

    `full` defaults to (never weaker than) `standard` -- the monotonicity
    invariant a Full pipeline can only add obligations, never drop them.
    """

    standard: Requirement
    full: Requirement | None = None

    def __post_init__(self) -> None:
        effective_full = self.standard if self.full is None else self.full
        if _requirement_strength(effective_full) < _requirement_strength(self.standard):
            raise ValueError(
                f"Full requirement {effective_full!r} is weaker than "
                f"Standard requirement {self.standard!r}"
            )
        if self.full is None:
            object.__setattr__(self, "full", effective_full)


@dataclass(frozen=True)
class FloorEntry:
    """One artifact's resolved requirement at a specific tier -- `floor()`'s projection."""

    name: str
    requirement: Requirement


def floor(tier: Tier | str) -> tuple[FloorEntry, ...]:
    """Every floor-bearing artifact's requirement at `tier`, in registry order."""
    resolved = Tier(tier)
    return tuple(
        FloorEntry(a.name, a.floor.full if resolved is Tier.FULL else a.floor.standard)
        for a in ARTIFACTS
        if a.floor is not None
    )


def signal_holds(signal: Signal, task_dir: Path) -> bool | None:
    """Whether `signal` holds for the pipeline in `task_dir`.

    `None` means undecidable from files (`Signal.PRODUCED`) -- the registry
    never guesses at a declarative signal.
    """
    if signal is Signal.TESTS_RAN:
        baseline = task_dir / "TEST_BASELINE.md"
        if not baseline.exists():
            return False
        try:
            text = baseline.read_text(encoding="utf-8")
        except OSError:
            return False
        return not text.startswith(NO_TEST_TARGET_MARKER)
    if signal is Signal.SDD_ACTIVE:
        plan = task_dir / "SYSTEMS_PLAN.md"
        if not plan.exists():
            return False
        try:
            return _REQ_HEADING_RE.search(plan.read_text(encoding="utf-8")) is not None
        except OSError:
            return False
    return None  # Signal.PRODUCED (and any future declarative signal)


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
    floor: Floor | None = None  # per-tier artifact floor; None = not floor-bearing
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
        floor=Floor(standard="always"),
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
        floor=Floor(standard=Signal.PRODUCED),
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
        floor=Floor(standard=Signal.PRODUCED),
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
        floor=Floor(standard=Signal.PRODUCED),
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
        floor=Floor(standard=Signal.PRODUCED),
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
        floor=Floor(standard="always"),
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
        floor=Floor(standard=Signal.PRODUCED),
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
        floor=Floor(standard="always"),
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
        floor=Floor(standard="always"),
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
        floor=Floor(standard="always"),
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
        floor=Floor(standard="always"),
        production_gate="producer:implementation-planner",
        cleanup_policy="delete",
        description="Pre-pipeline failing-test snapshot (verifier regression baseline).",
    ),
    Artifact(
        # Floor: gated on Signal.TESTS_RAN (TEST_BASELINE present without the
        # NO_TEST_TARGET_MARKER), so a no-test run is not penalised for its absence.
        "TEST_RESULTS.md",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        snapshot=True,
        floor=Floor(standard=Signal.TESTS_RAN),
        production_gate="producer:implementer",
        cleanup_policy="delete",
        description="Test-run evidence handoff to the verifier.",
    ),
    Artifact(
        # Floor: gated on Signal.SDD_ACTIVE (a requirement-id heading in
        # SYSTEMS_PLAN) at Standard; Full promotes it to an unconditional obligation.
        "traceability.yml",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=True,
        floor=Floor(standard=Signal.SDD_ACTIVE, full="always"),
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
        floor=Floor(standard="always"),
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
    Artifact(
        "HANDOFF.md",
        "ai-work",
        "ephemeral",
        "conditional",
        dashboard=False,
        snapshot=True,
        production_gate="script:compose_handoff.py",
        detection_gate="none",
        cleanup_policy="delete",
        description="Phase-boundary handoff document (Tier-3 orientation, never certification).",
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
