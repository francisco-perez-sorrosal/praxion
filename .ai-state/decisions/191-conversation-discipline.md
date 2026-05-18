---
id: dec-191
title: Operationalize the Conversation C as a human↔agent inspect discipline
status: accepted
category: behavioral
date: 2026-05-17
summary: Embed the 3Cs "Conversation" rhythm as a tier-independent human↔agent discipline (intake / phase-transition / pre-verification surfacing) threaded through Understand-Plan-Verify, not as a fourth step.
tags: [process, behavioral-contract, pipeline, conversation, assumptions, methodology]
made_by: user
agent_type: claude
branch: worktree-3cs-loop-audit
pipeline_tier: spike
affected_files:
  - rules/swe/agent-behavioral-contract.md
  - skills/software-planning/references/behavioral-contract.md
  - rules/swe/swe-agent-coordination-protocol.md
  - skills/software-planning/SKILL.md
  - skills/software-planning/references/document-templates.md
  - claude/config/CLAUDE.md
  - claude/config/CLAUDE.md.tmpl
---

# Operationalize the Conversation C as a human↔agent inspect discipline

## Context

A 3Cs-loop audit (Contract / Conversation / Checks) evaluated Praxion's process
surface — the always-loaded `CLAUDE.md` files, the process rules, the 17 agent
definitions, the planning/SDD skills, and the pipeline commands. Two independent
surveys converged on the same finding.

- **Contract** is strongly embedded (SPEC/REQ-IDs, BDD, AaC, tier calibration,
  delegation checklists, `Surface Assumptions`, the three-document model).
- **Checks** is strongly embedded (the `verifier`, including its
  `[UNSURFACED-ASSUMPTION]` Phase-5.5 scan).
- **Conversation** — the `ask-inspect-adjust` rhythm — is the weak C. The
  `inspect` discipline (interrogating a *received* output for what it reveals:
  wrong assumptions, sideways drift, an adjacent-question answer) exists nowhere
  in the corpus.

The structural cause: Praxion's methodology is **Understand → Plan → Verify**.
Mapped onto the 3Cs, *Understand ≈ Contract* and *Verify ≈ Checks*, but the
middle is **"Plan"** — Praxion converted the conversational middle into static
planning artifacts. This was a deliberate and largely correct trade: it buys an
autonomous, thrash-free, forward-only pipeline. But the trade removed the
human-reader from the middle of the loop and **assigned the `inspect` function
to no one**. Each downstream agent consumes its upstream artifact as
authoritative-by-construction. The behavioral contract's `Surface Assumptions`
is *producer-side, forward, self-directed*; its *consumer-side, backward* mirror
— inspect what you just received before trusting it — is missing.

The highest-value place to restore that mirror is the very first handoff: the
user's prompt → the agent. The full audit, gap list, and lessons live in
`.ai-work/3cs-loop-audit/` (`SYNTHESIS.md` + two `RESEARCH_FINDINGS_*.md`).

## Decision

Operationalize the Conversation C as a **tier-independent human↔agent
discipline**, embedded as **connective tissue threaded through
Understand/Plan/Verify** — not as a fourth methodology step, and not as new
always-loaded vocabulary. The bar is senior-engineer judgment ("when a principal
engineer would genuinely raise a concern"), not a mechanical checkbox.

The discipline has three checkpoints:

1. **Intake surfacing** (user → agent, every task, every tier). On receiving a
   task the agent restates its interpretation, **unconditionally enumerates** the
   assumptions it makes to fill gaps (including small ones — a plausible
   assumption does not *feel* like ambiguity, so a perception-gated trigger
   misses it), **self-challenges** the load-bearing ones, defaults to the happy
   path on unspecified constraints (no constraint-dimension checklist — raise a
   *targeted* question only on a genuine smell), and **pauses before starting**
   only when an unsurfaced assumption is *both load-bearing and hard to
   reverse*.

2. **Phase-transition surfacing** (Standard/Full pipelines). Pause + digest at
   phase boundaries (`research→architecture`, `architecture→planning`,
   `planning→implementation`) and at genuinely load-bearing steps — **not** at
   intra-phase agent handoffs (`implementer ∥ test-engineer` is a tight loop
   working as designed). Per-step assumptions are logged quietly; the loud pause
   is rare, so it stays meaningful.

3. **Pre-verification checkpoint** (the Conversation→Checks seam). Before the
   `verifier` runs, the orchestrator presents a **curated executive digest** of
   everything done (critical assumptions, load-bearing constraints, decisions,
   deviations — not a raw dump) plus a multi-select acknowledgement over the
   *load-bearing residue*. The user proceeds, or rolls back to a specific
   upstream agent. This catches what the verifier structurally cannot: the
   verifier checks the build against the *plan's* acceptance criteria; if the
   plan drifted from intent, the verifier passes the drift.

Supporting decisions:

- **Producer side.** Agents capture load-bearing assumptions *as they are taken*
  (not batched at end-of-task) in a new `### Assumptions & Constraints Taken`
  section of `LEARNINGS.md`; the orchestrator harvests it to compose digests.
- **Two rollback mechanisms bracket the verifier**, by design: (1) user-driven
  at the pre-verification checkpoint (orchestrator re-invokes an upstream agent,
  pipeline still in flight — *not* the rework loop, *not* a rework worktree);
  (2) verifier-driven afterward (`REWORK_MANIFEST.md` → rework worktrees) as the
  automated backstop for whatever the user did not catch.
- **Checkpoints are orchestrator-owned.** They run at the seams between subagent
  spawns, where the orchestrator (interactive) is driving — so background
  subagents being non-interactive does not block the design.
- **Automated mode.** Interactive (pauses on) is the default. When the user
  *explicitly* requests an automated run, pauses are suppressed but capture and
  digest-writing are retained: the digest becomes a post-hoc record for review.
  The loop degrades gracefully to a record; it is not deleted. Automated is an
  execution *mode* orthogonal to the Direct/Lightweight/Standard/Full tier.
- **Implementation is text-sharpening, not new machinery.** Sharpen
  `Surface Assumptions` (minimal always-loaded edit), put the operational "how"
  in the progressive-disclosure `behavioral-contract.md` reference, add the
  checkpoints to the coordination protocol, and thread the methodology's three
  existing scattered fragments into one coherent conversational beat.

## Considered Options

### A fifth behavioral-contract behavior ("Inspect Inputs") — rejected

Perfectly symmetric with `Surface Assumptions` and universal across tiers, but a
large blast radius: always-loaded token cost, re-paste into the ~11 agents that
carry the contract block, and mutation of a carefully-tuned four-behavior
contract and the global philosophy doc. The same effect is achieved by
*sharpening* the existing `Surface Assumptions` (its consumer-side reading was
always latent) plus a pipeline gate — far cheaper.

### General agent↔agent inspect loops — rejected

Generalizing the `interface-designer ↔ systems-architect` challenge loop to all
agent pairs would reintroduce exactly the thrash, non-determinism, and cost
blow-up the forward-only model was designed to eliminate. The one pair that
genuinely benefits already has its bounded loop. All other seam inspection
routes through the human (`agent → human → agent`), which needs no new
machinery.

### A constraint-dimension checklist at intake — rejected

Interrogating the user across a fixed list of constraint dimensions
(scale / auth / performance / …) is the wrong shape — it is ceremony, not
judgment. The senior-engineer move is: default to the happy path, raise a
*targeted* question only when something genuinely smells.

### Naming the "3Cs" as vocabulary in always-loaded surfaces — rejected

The *spirit* of the 3Cs should live in Praxion; the literal labels need not.
Naming for its own sake costs always-loaded tokens for little behavior change.
"Conversation" is embedded as operational mechanics threaded through the
existing methodology, not as a new named element.

### Do nothing — rely on the verifier's Phase-5.5 assumption scan — rejected

`verifier` Phase 5.5 is the right *mechanism* (inspect a prior agent's output
for unsurfaced assumptions) at the wrong *time* — post-implementation, at Checks
time, when the cost of the missed conversation is already sunk. The discipline
relocates that catch to Conversation time.

## Consequences

**Positive.**
- The `inspect` half of the loop gains an owner; misunderstandings are caught at
  the seam where rollback is still cheap, not a full pipeline pass late.
- Symmetric completion of the behavioral contract — producer-side
  `Surface Assumptions` now has a consumer-side counterpart.
- Communication quality and project health improve: assumptions (even small
  ones) become visible to the user as a matter of course.
- `background:`-mode loop-deletion is converted into a designed graceful
  degradation.
- Minimal new surface — text-sharpening of existing artifacts; no fifth
  behavior, no loops, no new artifacts beyond one `LEARNINGS.md` section.

**Negative / costs.**
- A modest always-loaded token increase in the behavioral-contract rule and the
  methodology — measure with `wc -c` against the 25k budget before committing.
- `Surface Assumptions` text may live in a shipped canonical `CLAUDE.md` block;
  if so the change must propagate through `sync_canonical_blocks.py` and the
  `onboard-project` / `new-project` / `new_project.sh` mirror, and the ~11
  pasted agent copies must be checked for drift.
- New pause points add interaction friction in interactive mode — mitigated by
  the phase-boundary (not per-step) granularity and the curated-digest rule.
- Implementation touches ~6–8 surfaces across rules, skills, and the philosophy
  doc — a Standard-tier change; see the companion `IMPLEMENTATION_PLAN.md`.
