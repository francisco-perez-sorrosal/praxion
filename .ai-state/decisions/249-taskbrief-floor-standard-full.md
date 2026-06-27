---
id: dec-249
title: Raise the TASK_BRIEF floor — mandatory at Standard/Full, decoupled from the blocking-question gate, with a mechanical absence backstop
status: accepted
category: behavioral
date: 2026-06-26
summary: Make TASK_BRIEF.md unconditional at Standard/Full tier in the always-loaded Intake Clarity Gate and the goal-disambiguation skill (the subjective "non-obvious success" gate no longer suppresses it), keep Direct/Lightweight unchanged, and add a sentinel auto-check (primary) plus a verifier WARN (secondary) that flag a Standard/Full run producing no brief.
tags: [pipeline, intake, task-brief, criteria-thread, verifier, sentinel, gate-liveness]
made_by: agent
agent_type: systems-architect
branch: wave2-criticals
pipeline_tier: standard
affected_files:
  - rules/swe/swe-agent-coordination-protocol.md
  - skills/goal-disambiguation/SKILL.md
  - agents/verifier.md
  - agents/sentinel.md
---

## Context

`TASK_BRIEF.md` had **zero** live instances across 15+ task slugs on Praxion's own repo. The artifact carries the user's success definition verbatim and seeds the criteria → acceptance-criteria → verifier-rubric thread — but its production gate ("Where success is non-obvious") is a subjective orchestrator judgment that, in practice, never resolved to *yes*. Consequence: the verifier's primary rubric check (`verifier.md:48` — "flag any Key Signal not carried into `SYSTEMS_PLAN.md`") had nothing to compare against, and the architect derived acceptance criteria with no provenance anchor to user intent. A signature idea of the pipeline was paper-only on its own repo: an obligation in prose with no mechanical floor and no detection backstop.

## Decision

Raise the floor and add a backstop, keeping the lower tiers untouched:

1. **Unconditional at Standard/Full.** In the always-loaded Intake Clarity Gate (`rules/swe/swe-agent-coordination-protocol.md`), replace "Where success is non-obvious, capture … `TASK_BRIEF.md`" with: **always** capture the brief at Standard/Full; capture it at Lightweight when success is non-obvious; Direct skips it. Mirror the same floor in `skills/goal-disambiguation/SKILL.md` ("When this fires" + the capture-calibration table).
2. **Decouple the floor from the blocking-question gate.** The 2×2 (intent-clarity × reversibility) still governs *whether to ask a clarifying question*; the floor governs only *whether to write the brief*. A clear, reversible Standard/Full task writes the brief from stated assumptions **without** a blocking question — so the floor adds no interrogation overhead.
3. **Mechanical absence backstop (two layers).** Primary: a new sentinel auto-check (`P06`) — for each `.ai-work/<slug>/` containing a `SYSTEMS_PLAN.md` (the architect's Standard/Full output) but no `TASK_BRIEF.md`, WARN. Grep-amenable, no LLM, ships a gate-liveness canary fixture. Secondary: extend the verifier's Phase-1 logic to WARN when a feature-scope `SYSTEMS_PLAN.md` exists with no brief.

## Considered Options

### Option A — Raise the floor at the always-loaded gate + dual backstop (CHOSEN)

- **Pros:** the criteria thread always exists where architectural decisions are made; the verifier carry-forward check gets a real brief; provenance to user intent is guaranteed at the tiers that matter; the backstop is mechanical and gate-liveness-canaried, matching the enforcement style the analysis recommends. Direct/Lightweight unchanged.
- **Cons:** a small always-loaded token cost (≈ +60 chars / ~20 tok, within the ~3.7K-tok headroom) and a mandatory artifact at Standard/Full. Both accepted; the floor's decoupling from the question gate keeps overhead near-zero.

### Option B — Drop the verifier's dependence on the brief (rely on SYSTEMS_PLAN acceptance criteria alone)

- **Pros:** no new artifact obligation; the verifier already reads `SYSTEMS_PLAN.md` acceptance criteria.
- **Cons (why it loses):** the brief is the **only** surface carrying the user's success definition *verbatim*, distinct from the architect's synthesis (provenance hygiene). Dropping it erases the criteria thread's anchor exactly where blast radius is highest, and leaves `verifier.md:48` permanently inert. Rejected against the criteria-first design intent.

### Option C — Floor only in the (non-always-loaded) skill

- **Pros:** zero always-loaded budget cost.
- **Cons:** the orchestrator reads the always-loaded Intake Clarity Gate first; if that still says "where success is non-obvious," the stricter Standard/Full rule in the skill may never be consulted — the floor would not reliably fire. Rejected: the always-loaded edit is load-bearing.

## Consequences

**Positive:**
- The criteria → acceptance → verifier-rubric thread is guaranteed at Standard/Full.
- The verifier carry-forward check and the sentinel backstop both have substance to act on (gate-liveness: a consumer with a guaranteed producer; a check proven to bite via its canary).
- The mechanical backstop catches drift even when no verifier runs.

**Negative / costs:**
- A small always-loaded token cost (measured, within headroom) and a mandatory artifact at Standard/Full.
- One new sentinel row + canary fixture to maintain.

## Disconfirmation

- **Falsifier:** if, after the floor lands, Standard/Full runs still ship without a brief *despite* the P06 WARN and verifier WARN (i.e., the WARNs are ignored at the same rate the subjective gate was), the floor is as aspirational as what it replaced and the obligation would need a hard gate (block the architect spawn until the brief exists) rather than a detection WARN.
- **Steelmanned runner-up (Option B):** the leanest design adds no artifact at all and trusts `SYSTEMS_PLAN.md` acceptance criteria — the architect is competent to derive testable criteria, and a verbatim user-intent capture may be ceremony for a team whose intake conversation is already captured elsewhere. If provenance-to-verbatim-intent proved low-value in practice, dropping the dependence would be simpler than enforcing a floor.
- **Reversal trigger:** if the P06/verifier WARNs are routinely ignored (floor not honored) or if briefs are produced but add no signal the architect's criteria lacked, revisit — either harden to a blocking gate or retire the dependence per Option B.
