---
id: dec-240
title: Intra-step pair-review reuses the verifier in a scoped light-review mode rather than a new agent
status: accepted
category: architectural
date: 2026-06-19
summary: The intra-step risky-step reviewer is the existing verifier invoked in a scoped light-review mode (sonnet), not a 17th agent — independence comes from the spawn, not the agent type.
tags: [pipeline, verifier, code-review, model-routing, reliability-gate, simplicity-first]
made_by: agent
agent_type: systems-architect
branch: feat-intra-step-review
pipeline_tier: standard
affected_files:
  - agents/verifier.md
  - skills/code-review/SKILL.md
  - rules/swe/swe-agent-coordination-protocol.md
  - rules/swe/agent-model-routing.md
  - skills/software-planning/references/intra-step-review.md
dissent: A dedicated step-reviewer agent would keep the verifier single-responsibility and avoid mode-branching that could blur full-pipeline vs step-scoped assessment.
---

## Context

Praxion is adding a lightweight, independent reviewer pass at the step boundary (after the implementer reports `[COMPLETE]`, before the planner advances) for RISKY steps — a cheaper, earlier reliability gate than the end-of-pipeline verifier. Two decisions are already user-ratified: the reviewer is a dedicated independent SPAWN (not enhanced implementer self-review — independence is the value), and the trigger is BOTH auto-signals (TASK_BRIEF Uncertainty Flag < 7, one-way-door, planner `tier: H`) AND an explicit planner override.

The remaining load-bearing fork: is the reviewer a brand-new agent type, or the existing review capability invoked in a scoped "light mode"? The decision lens is quality/reliability per unit effort — smart, lean, cost-conscious. Adding a 17th agent carries standing cost (a model-routing row, a catalog entry, an agent-crafting maintenance surface, `description`-disambiguation pressure against the existing verifier).

## Decision

The intra-step reviewer is the **existing `verifier` agent invoked in a scoped `Mode: light-review`** (paired with a third Report Mode in the `code-review` skill), routed down to `sonnet` via a per-spawn override of the verifier's `opus` capability floor. It is NOT a new agent type. The independence the user ratified is delivered by the separate spawn with its own context window — not by the agent being a distinct type. Iteration is bounded to one revise loop; a second `revise` escalates to the user and records residue for the end-of-pipeline verifier.

## Considered Options

### Option 1 — New lightweight `step-reviewer` agent (17th agent)
- **Pros:** keeps the verifier single-responsibility; a purpose-built prompt with no mode-branching; clearest separation of "step gate" vs "final gate".
- **Cons:** duplicates ~90% of existing `code-review` + verifier logic (PASS/FAIL/WARN classification, changed-lines scoping, acceptance-criteria review); adds a model-routing row, a `plugin.json`/`README.md` catalog entry, an agent-crafting maintenance surface, and `description`-disambiguation pressure against the verifier (delegation ambiguity). Standing cost the lens forbids for a capability that already exists.

### Option 2 — Reuse the verifier in a scoped light-review mode (CHOSEN)
- **Pros:** near-zero new infrastructure (one agent mode + one report mode + a procedural reference); independence delivered by the spawn; same finding-classification vocabulary flows from step-boundary into the final verifier (one taxonomy); follows the proven architect three-mode precedent.
- **Cons:** the verifier gains a second responsibility (mode-branching); light-review and full-verify must be kept distinct in the prompt to prevent assessment bleed.

### Option 3 — Enhanced implementer self-review
- **Pros:** zero new spawn cost.
- **Cons:** excluded by ratified decision 1 — no independence (same agent, same context), which is the explicit value of the feature.

## Consequences

**Positive:** lean, lens-aligned path; reuses confirmed-present machinery; coherent finding vocabulary across both gates; deterministic cost ceiling (`sonnet` + ≤1 revise loop); non-RISKY steps cost zero.

**Negative:** the verifier agent must carry a clean mode split (mitigated by explicit per-mode anti-instructions, mirroring `agents/CLAUDE.md` § Architect Invocation Modes); a future divergence of light-review behavior from full-verify could justify a later split.

## Disconfirmation

- **Falsifier:** a measurable rise in mis-routed or mis-scoped verifier spawns after the light-review mode lands (the model bleeding full-pipeline assessment into a step-scoped pass, or the delegator confusing the two modes) would show the mode-branching was the wrong call.
- **Steelmanned runner-up (Option 1):** a dedicated `step-reviewer` keeps the verifier single-responsibility, gives the step gate a prompt tuned purely for fast diff-vs-acceptance judgment with no risk of full-pipeline assessment leaking in, and removes any delegation ambiguity — the standing cost of one more agent is a one-time price for permanent clarity, and Praxion already maintains 16 agents so the marginal maintenance is small.
- **Reversal trigger:** if light-review's prompt-branching makes the verifier error-prone, OR light-review accrues step-scoped behavior that genuinely diverges (different output-schema consumers, different tool needs), split it into a dedicated agent at that point.
