---
id: dec-076
title: Routing dimensionality — 1D now, defer 2D (model × effort)
status: accepted
category: architectural
date: 2026-04-25
summary: Routing policy picks only a tier (model alias) per agent; `effort` as a second axis is deferred pending telemetry and uniform cross-tier support
tags: [model-routing, dimensionality, effort-parameter, opus, sonnet, deferred]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
re_affirmed_by:
  - dec-301
affected_files:
  - rules/swe/agent-model-routing.md
affected_reqs:
  - AC2
  - AC10
---

## Context

Opus 4.6 / 4.7 and Sonnet 4.6 support an `effort` parameter (`low`/`medium`/`high`/`xhigh`), which shifts the cost-quality curve orthogonally to the model tier. A 2D routing matrix (model × effort) could theoretically capture additional savings — notably on Opus-tier agents (systems-architect, verifier, promethean) when the task at hand is small. However, `effort` is **not uniformly supported**: `xhigh` is Opus 4.7 only, `low/medium/high` is Opus 4.5/4.6, and Haiku 4.5 does not expose it. A 2D policy today forces per-model branching in the rule and per-spawn prompt logic.

## Decision

Ship the policy as **1D** — tier-alias only — for v1. Defer 2D (model × effort) to a follow-up ADR that must be triggered by either:

- Telemetry showing a specific agent spending >30% of its tokens on a consistently easy-case workload pattern, or
- Anthropic extending `effort` support uniformly across current tiers (including Haiku).

## Considered Options

### Option 1 — 1D (selected)

- Pros: Single mental model; one alias per agent; the rule table fits on a screen; cognitive overhead for authors is minimal.
- Cons: Leaves potential ~20–40% additional savings on Opus-tier agents during light workloads.

### Option 2 — 2D (model × effort)

- Pros: Captures the second cost-quality lever; better fit for quality-load-bearing but often-small workloads (e.g., verifier on a clean pipeline).
- Cons: Asymmetric support across tiers forces branching logic. Two columns in the rule table. Operators must reason about two axes. Premature optimization at current scale.

## Consequences

**Positive:**

- Policy ships days, not weeks.
- The rule stays within ~800 tokens (dec-079 token budget).
- Clear re-open trigger preserves optionality.

**Negative:**

- Real savings left on the table for Opus-tier agents in routine use.

**Risks accepted:**

- 2D becomes material after 1D ships — the re-open trigger is the safety net. Telemetry stance (dec-080) provides the signal.
