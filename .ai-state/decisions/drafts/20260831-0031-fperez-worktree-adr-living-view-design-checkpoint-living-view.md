---
id: dec-draft-c5d81484
title: The architecture living view is DESIGN.md plus an authored checkpoint and a derived validator, never a generated digest
status: proposed
category: architectural
date: 2026-08-31
summary: '.ai-state/DESIGN.md carries a `Current as of dec-NNN` high-water mark; scripts/check_design_checkpoint.py derives the un-folded architecture-bearing suffix of the decision log; no digest artifact is generated and no LLM synthesis step exists.'
tags: [adr, architecture-doc, checkpoint, living-view, read-path, context-cost, design-md]
made_by: agent
agent_type: systems-architect
branch: worktree-adr-living-view
pipeline_tier: standard
dissent: "A generated digest could be sized for the job the authored document cannot do — DESIGN.md is ~37K tokens, so this decision makes the living view trustworthy without making it cheap, and an agent that trusts it still pays 37K tokens to read it."
affected_files:
  - .ai-state/DESIGN.md
  - scripts/check_design_checkpoint.py
  - skills/software-planning/assets/ARCHITECTURE_TEMPLATE.md
  - skills/software-planning/references/architecture-documentation.md
  - agents/systems-architect.md
  - agents/sentinel.md
  - agents/architect-validator.md
---

## Context

The adr-compaction spike established that the ADR cost is the read path, not the corpus, and that the tier-1 sources (Nygard, arc42, Structurizr, AWS) all separate an append-only decision log from a living current-state view. Praxion already instantiates that split: `.ai-state/decisions/` is the log, `.ai-state/DESIGN.md` and `docs/architecture.md` are the views.

The spike left one question open — whether `DESIGN.md` could *be* the digest, collapsing "build an artifact" to "add a checkpoint plus a trigger". Reading the artifact against the log answers it. The living view is not missing; it is **unprovable**. Nothing on disk states how much of the log it accounts for, so an agent needing certainty falls back to the log — which is the measured cost.

The still-current audit added the shape of the exclusion problem: the read-path weight is *correct-but-inert* records (one-off consumed task decisions, permanently accurate and permanently useless for "what is the architecture now"), invisible to any `status` filter. Measured on this corpus: 347 finalized records, 328 in the current streamline, 231 `architectural`, 225 `architectural` with at least one live `affected_files` path, 133 of those not cited anywhere in `DESIGN.md`.

## Decision

`.ai-state/DESIGN.md` §1 carries an authored `Current as of` row naming a `dec-NNN` high-water mark and the date it was asserted. `scripts/check_design_checkpoint.py` — read-only, stdlib-capable, `--json` — computes the **un-folded suffix**: ADRs after the checkpoint satisfying the **architecture-bearing predicate**

    status ∈ {accepted, re-affirmation} ∧ category == architectural ∧ ≥1 live affected_files entry

Three consumers surface it: sentinel (new AC-family auto check, advisory), the systems-architect's Phase 5 (the write path — fold in, then advance the mark), and the architect-validator (per-PR, the ADR leg of its code↔DSL↔ADR triangle). Deliberately **not** a git hook: the disposition needs judgment, and a hook that auto-advances the mark mechanizes a lie.

**No file is generated and no LLM synthesizes anything.** The only derived artifact is the validator's stdout.

Advancing the checkpoint **is** the disposition — for "folded in" and for "considered, not applicable" alike. There is no separate waiver field.

The initial checkpoint is set to the corpus tip at landing. The 133 historical architecture-bearing records not cited in `DESIGN.md` are **explicitly not debt**, the same posture `adr-conventions.md § Migration — historical ADRs` already takes; the validator never emits pre-checkpoint ids, so the backlog cannot be mistaken for a work queue.

The inert-record problem is solved by the predicate, not by curation: `dec-318` defines `architectural` as *"changes what exists or what connects"*, which is exactly what `DESIGN.md` §3 describes, so `implementation`/`behavioral`/`configuration` records — the audit's inert population — drop out by construction. Recency is expressed as the checkpoint delta rather than as a filter window, because the audit found age to be a weak predictor of relevance (old records are disproportionately principled and rot-proof).

## Considered Options

### A — Authored checkpoint + derived validator, no generated artifact (chosen)

Pros: LLM-synthesis lossiness is eliminated **structurally** — a summary cannot drop a constraint if no summary is written; the "deletable and rebuildable from `decisions/` alone" test passes trivially because nothing is written; the artifact slot is already occupied by `DESIGN.md`, matching the tier-1 evidence; the change is one table row plus one small script. Cons: the mark is authored, so it can be advanced without the work being done — mitigated by `cited_in_*` proxies, not solved.

### B — Generated `ARCHITECTURE_DIGEST.md` synthesized from accepted ADRs

Pros: could be sized deliberately for cheap orientation, which the 37K-token `DESIGN.md` is not. Cons: becomes a second source of truth the first time anyone edits it; its synthesis is the one irreversible lossy step in the whole design space, and a digest that silently drops a constraint is worse than none because agents will trust it; the research found **no** practitioner precedent for scheduled ADR→current-state distillation (novel-for-domain, low-med certainty) — a poor place to spend novelty budget on an artifact whose slot is filled.

### C — Checkpoint row alone, no validator

Pros: near-zero cost. Cons: a marker nobody checks decays into a lie within one pipeline; the whole value is staleness being *detectable*.

### D — Post-merge git hook advancing the checkpoint mechanically

Pros: no agent compliance required. Cons: converts an honest gap into a machine-certified falsehood — the mark asserts human consideration, and a machine cannot make that assertion truthfully.

## Consequences

**Positive.** "What is the architecture now" has a sanctioned answer whose currency is checkable in one command. The un-folded suffix of the log is visible rather than silent. The inert-record exclusion is a derivable predicate with no curated list anywhere. Zero always-loaded token cost — the convention documents in the skill reference and the agent files. Exactly one component enters the inventory.

**Negative.** A new script to maintain and ship. The checkpoint's honesty depends on the architect, and the `cited_in_*` signal is a proxy (an architectural decision can be reflected in `DESIGN.md`'s substance with no inline `dec-NNN`) — reported as a ranking hint, never as pass/fail. `category` is author-assigned, so an over-broad `architectural` inflates the obligation set with noise; sentinel DH05 already measures that discrimination.

**Unresolved and named.** This makes `DESIGN.md` trustworthy, not cheap. §3a/§3b is the seam a future cost-reduction pass would use; that pass is out of scope here.

## Disconfirmation

- **Falsifier**: sentinel or metrics runs showing the checkpoint being advanced in lockstep with the corpus tip while `cited_in_design` stays false for most un-folded records — i.e. the mark is being advanced as a formality — would prove the authored-signature model insufficient and the whole mechanism decorative.
- **Steelmanned runner-up**: Option B is right if the real requirement is *cheap* orientation rather than *trustworthy* orientation. A 2K-token generated digest answers "what is the architecture now" at 5% of `DESIGN.md`'s cost, and its lossiness is bounded if every claim carries a validator-checked `dec-NNN` citation — turning the digest into an index of pointers (the llms.txt shape) rather than a synthesis. If agents keep paying 37K tokens to orient, B is the correct escalation, and this decision's checkpoint infrastructure is exactly the substrate it would need.
- **Reversal trigger**: observation data showing agents reading `DESIGN.md` whole for orientation ≥ 4 weeks after landing, or the un-folded count exceeding ~15 sustained across two pipelines → revisit B in its citation-checked form.
