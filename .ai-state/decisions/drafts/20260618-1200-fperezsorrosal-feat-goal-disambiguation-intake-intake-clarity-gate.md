---
id: dec-draft-7c4e9af2
title: Intake Clarity Gate + goal-disambiguation skill for task-intent disambiguation
status: proposed
category: architectural
date: 2026-06-18
summary: Add a clarity-axis intake gate (orthogonal to size-based tiering) that disambiguates user intent and captures measurable Key Signals into TASK_BRIEF.md before the pipeline commits.
tags: [intake, disambiguation, goal-elicitation, okr, acceptance-criteria, conversation-checkpoints, calibration]
made_by: agent
agent_type: main-orchestrator
branch: feat-goal-disambiguation-intake
pipeline_tier: standard
affected_files:
  - skills/goal-disambiguation/SKILL.md
  - skills/goal-disambiguation/references/worked-examples.md
  - rules/swe/swe-agent-coordination-protocol.md
  - skills/spec-driven-development/references/calibration-procedure.md
  - rules/swe/agent-intermediate-documents.md
  - agents/researcher.md
  - agents/systems-architect.md
  - agents/verifier.md
dissent: A disciplined orchestrator already practicing Surface Assumptions may treat the gate as redundant ceremony, and a poorly-calibrated gate risks re-introducing the interrogation the behavioral contract explicitly forbids.
---

## Context

Praxion's task front-end optimizes for task **size** (the 6-signal calibration → Direct/Lightweight/Standard/Full/Spike) and is silent on intent **clarity** and measurable success. Consequences: (1) the first formal goal statement lands at systems-architect Phase 1 — after research has already run — and is the architect's interpretation, never the user's verbatim success definition; (2) there is no measurable "definition of done" captured at intake; (3) the behavioral contract's `Surface Assumptions` is a judgment-based stance with no operational hook at the intake moment.

A three-lens research effort (internal audit + external elicitation literature + external outcome-signal literature; findings in `.ai-work/task-intake-disambiguation/`) found that three independent traditions — decision-theory/AI-agent research (expected regret), requirements engineering (Gause & Weinberg, ISO 29148), and OKR/BDD testability — converge on a single ask-vs-proceed rule. That cross-tradition convergence cleared the corroboration bar for treating the primitive as load-bearing.

## Decision

Add a **clarity axis** to intake, orthogonal to the size tier:

1. A new **`goal-disambiguation` skill** carrying the full procedure: the ask-vs-proceed decision rule (the 2×2 of intent-clarity × reversibility), a five-step protocol (smell scan → XY test → reversibility gate → assumption surfacing → Mom-Test phrasing, hard 3-question cap), and a measurable outcome-capture shape (Intent / Key Signals / Health Guards / Uncertainty Flag with mandatory `N/10`).
2. An **Intake Clarity Gate** — a ~5-line always-loaded Conversation Checkpoint (in `swe-agent-coordination-protocol.md`) that fires before tier-commit/first-spawn for all tiers above Direct, pointing into the skill for depth. It raises a *blocking* clarifying question only when intent is ambiguous AND a wrong guess is hard to reverse; otherwise it states assumptions univocally and proceeds.
3. A **`TASK_BRIEF.md`** ephemeral `.ai-work/<task-slug>/` artifact holding the captured signals, consumed first by researcher and systems-architect, and used by the verifier as a rubric grounding source.
4. A separate **goal-clarity read** in the calibration procedure that reports a `clear/ambiguous` + `reversible/hard-to-reverse` verdict feeding the Gate — explicitly NOT folded into the numeric size score.

User-ratified parameters: proceed-with-stated-assumptions in the ambiguous+reversible cell (assumptions revealed univocally so the user can halt); 3-question cap; Direct tier skips the brief; Uncertainty Flag is free-form with mandatory `N/10`; land the goal-clarity calibration signal alongside.

## Considered Options

### Option A — Thin skill + always-loaded gate clause + TASK_BRIEF artifact (chosen)
Mirrors the `multi-perspective-analysis` thin-composition-layer precedent: depth in a progressively-disclosed skill, a minimal always-loaded pointer, an ephemeral artifact following the established `.ai-work/` pattern.
- **Pros**: respects the 25k always-loaded token budget; reuses existing checkpoint/artifact vocabulary; serves all tiers; isolation-safe (shipped surfaces carry no concrete `.ai-state` entries).
- **Cons**: behavior is advisory (rule, not hook) — adherence is probabilistic.

### Option B — Embed the protocol per-agent
Each agent carries its own intake-clarity logic.
- **Cons**: duplicates the protocol, violates Simplicity First — the exact anti-pattern the multi-perspective-analysis decision rejected.

### Option C — New always-loaded rule with the full protocol
- **Cons**: blows the always-loaded budget for a behavior not used in 100% of sessions; defeats progressive disclosure.

### Option D — Slash command only (`/task-intake`)
- **Cons**: opt-in, so it never fires on ordinary natural-language tasks; the gate must live in the default orchestrator path.

## Consequences

**Positive**: intent disambiguation becomes systematic without becoming ceremony (throttled by the reversibility gate); the user's success definition is captured verbatim and flows downstream as the verifier's binary rubric; clarity and size become independently assessable; rework from misread intent drops.

**Negative**: one more always-loaded clause (~5 lines) against a tight budget; a risk of over-asking if the gate is miscalibrated; the gate is a PROMPT gate, so its bite is probabilistic, not enforced.

## Disconfirmation

- **Falsifier**: if calibration logs / sessions show the gate firing blocking questions on clearly-reversible or clearly-clear tasks (over-asking), or conversely missing genuinely ambiguous+irreversible tasks, the 2×2 rule is mis-specified.
- **Steelmanned runner-up**: Option D (command-only) is strongest if it turns out orchestrators reliably self-trigger disambiguation from the skill description alone without an always-loaded clause — that would save the budget line entirely. The clause exists precisely because model-invoked skills don't reliably fire at the pre-spawn moment.
- **Reversal trigger**: if the always-loaded budget crosses its guardrail and an audit attributes material pressure to this clause, or if usage shows the gate is dead weight (never changes orchestrator behavior), collapse it back to a skill-only, model-invoked mechanism.

## Golden bad-case (PROMPT gate liveness)

The gate must flag: *"Lock down the API so randoms can't hit it."* — ambiguous (vague actor + mechanism, no stated outcome) AND hard-to-reverse (auth/security). Correct behavior: ask ≤3 Mom-Test questions before committing. A gate that proceeds silently on this input is broken. (Worked in full as Cell 4 of `skills/goal-disambiguation/references/worked-examples.md`.)
