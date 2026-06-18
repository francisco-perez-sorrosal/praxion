---
id: dec-233
title: Extend the Context Engineering principle rather than create a new principle for multi-perspective deliberation
status: accepted
category: architectural
date: 2026-06-18
summary: Add one clause about structurally-independent vantage points to the existing Context Engineering principle (cross-ref Balanced Coupling); do not create an "Epistemic Diversity" principle.
tags: [philosophy, context-engineering, multi-perspective, storm-integration, always-loaded]
made_by: agent
agent_type: systems-architect
branch: worktree-storm-integration
pipeline_tier: full
affected_files:
  - claude/config/CLAUDE.md
affected_reqs: [REQ-08, REQ-09]
dissent: "A reader who values rhetorical salience may argue a one-clause extension under-signals the importance of structural-independence vs. a named heading. Held minority view: revisit if usage telemetry shows the clause is ignored where a heading would not be."
---

## Context

The storm-integration work introduces multi-perspective deliberation primitives (lens fan-out, contradiction mapping, isolate-collect/reconcile-synthesis). The question: does this warrant a NEW always-loaded philosophy principle ("Epistemic Diversity" / "Perspective Coverage"), or an extension of an existing one?

Two hard constraints: (1) the always-loaded budget is a 25k-token guardrail and Praxion's surface is already ~36k tokens (over budget); (2) no reputable source in the research base names epistemic/perspective diversity as a first-class principle.

## Decision

Extend the existing **Context Engineering** principle in `claude/config/CLAUDE.md` with exactly one clause: gathering the right context includes gathering from structurally independent vantage points when task uncertainty warrants it — isolate during collection, reconcile at synthesis, gate by cost. Cross-reference **Balanced Coupling** (decoupled collection / coupled synthesis). Do not add a new principle. Net always-loaded add ≤ ~350 chars.

## Considered Options

### Option 1 — New principle ("Epistemic Diversity" / "Perspective Coverage")
- Pro: rhetorical prominence; a named heading signals importance.
- Con: Praxion-proprietary framing with no external backing; Anthropic's own engineering writing places multi-agent context isolation *inside* context engineering, and LangChain's taxonomy makes "isolate" one of four context-engineering verbs. Duplicates the existing "gather" clause and Balanced Coupling's "separate/integrate" clause; fragments a coherent concept; adds always-loaded tokens to an already-over-budget surface.

### Option 2 — Extend Context Engineering + cross-ref Balanced Coupling (CHOSEN)
- Pro: matches the most reputable in-domain framing (Anthropic); minimal token cost; coherent; the multi-perspective fan-out is literally "gather what you need" applied with deliberate structural diversity, and the isolate/reconcile structure is Balanced Coupling at the pipeline level.
- Con: a clause is less salient than a heading.

## Consequences

- Positive: minimal always-loaded growth; externally grounded; the `multi-perspective-analysis` skill operationalizes the clause so the always-loaded prose can stay terse.
- Negative: relies on the skill + the cross-reference to carry operational weight; a future reader must follow the pointer to see the mechanism.

## Disconfirmation (Tier A)

- **Falsifier**: This decision is wrong if the one-clause extension proves too weak to change behavior — i.e., agents continue to fan out without isolation discipline despite the clause existing.
- **Steelmanned runner-up (Option 1)**: A named principle would make structural-independence a first-class checkable value ("From Craft to Constitution" argues techniques graduate to principles when they recur cross-domain, have measurable violation consequences, and can be stated as falsifiable constraints — multi-agent isolation passes the first two). The strongest case for Option 1 is that a heading is more enforceable than a buried clause.
- **Reversal trigger**: Revisit and promote to a full principle if (a) a future eval shows the clause is systematically ignored, OR (b) the always-loaded budget is brought back under guardrail and a heading's token cost becomes affordable, OR (c) the technique is restated as a falsifiable always-loaded constraint with a mechanical check.

**Activation:** fired — signals: criticality (always-loaded philosophy change) + novelty; lens set = Simplicity + Balanced-Coupling; convergence = stable (researcher MULTIAGENT_CONTEXT Topic 5 and the architect independently reached extend-not-create).
