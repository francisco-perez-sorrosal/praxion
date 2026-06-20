---
id: dec-draft-04237662
title: Memory direction — sandbook subsumes beads-class capability; defer-by-dependency, not by-priority
status: proposed
category: architectural
date: 2026-06-19
summary: Ratify that sandbook (five-tier, vector+graph, consolidation, eval suite) strictly subsumes Gastown beads-class capability; agent memory is Praxion's #1 gap by importance but is deferred only because sandbook is pre-1.0 — land it behind a pinned ref when the API settles.
tags: [memory, sandbook, beads, competitive, deferral, architecture]
made_by: agent
agent_type: systems-architect
branch: main
pipeline_tier: standard
re_affirms: dec-225
affected_files:
  - hooks/inject_decisions.py
  - .ai-state/observations.jsonl
dissent: "If sandbook stalls at alpha indefinitely, the #1 gap stays open and a lighter interim memory shim (even file-backed) might beat waiting."
---

## Context

The competitive evaluation (`.ai-work/praxion-competitive-eval/COMPARATIVE_REPORT.md`)
ranks durable, queryable agent memory as Praxion's clearest external-evidenced gap
(dec-225 removed the in-house subsystem), and forwards Continuous Improvement Signal A:
adopt a Gastown-beads-style git+versioned-SQL (Dolt) structured work-state store as the
memory substrate. Open Question 1 asks whether `sandbook` is meant to reach beads-class
capability or stay lighter.

## Decision

Ratify that **`sandbook` already exceeds beads-class capability** and is the committed
memory direction — no new design decision is needed. Per dec-225, sandbook is a
purpose-built engine offering five-tier memory, **vector + graph retrieval**, background
consolidation, and a deterministic eval suite — strictly more capable than beads (a
git+Dolt issue/work-state store). Agent memory remains Praxion's **#1 gap by importance**
but is **deferred by dependency, not by priority**: sandbook is alpha, pre-1.0, not yet on
PyPI. The action *now* is **zero-code** — add a tracking trigger so that when sandbook
reaches a pinnable, stable git ref, the integration ADR + pipeline fires (wiring
`remember`/`recall`/`search` consumption surfaces and integrating with `observations.jsonl`
+ ADR injection at the seam dec-225 already left clean).

## Considered Options

### Adopt Gastown beads (git+Dolt) as the memory substrate now
Rejected. It introduces a new heavy dependency (Dolt) to deliver a *subset* of what
sandbook already promises. Two memory directions is strictly worse (the same logic
dec-225 used to remove the in-house engine).

### Build a lighter interim memory now against sandbook's alpha API
Rejected for now (this is the dissent). Building against a pre-1.0 API invites churn —
the opposite of lean. Reconsider only if sandbook stalls at alpha for an extended period.

### Defer-by-dependency: pin and land sandbook when stable (chosen)
Matches dec-225's "remove now, behind a pinned sandbook reference" stance. Keeps Praxion
clean, avoids alpha-API rework, and treats the #1 gap as a *scheduled* landing gated on
dependency maturity rather than an open design question.

## Consequences

**Positive.** No premature dependency; the seam stays clean; the #1 gap has a concrete,
gated landing path instead of speculative design work; sandbook's superior capability is
not diluted by an interim shim.

**Negative / accepted.** The persistent half of the Learning Loop stays dormant until
sandbook stabilizes — `LEARNINGS.md` (ephemeral) and `observations.jsonl` carry the gap.
If sandbook's timeline slips, the gap persists.

## Disconfirmation

- **Falsifier:** sandbook proves *less* capable than beads in practice (e.g. no working
  queryable/versioned store), making the "subsumes" claim false.
- **Steelmanned runner-up:** a file-backed interim memory (cheap, no external dep) landed
  now would close *some* of the gap immediately and de-risk the Learning Loop, rather than
  waiting on an alpha package of uncertain timeline.
- **Reversal trigger:** sandbook remains un-pinnable/alpha past a reasonable horizon, or a
  managed project hits a concrete cross-session-memory need that ephemeral artifacts can't
  serve — then land an interim shim.

## Prior Decision

Re-affirms **dec-225** (remove in-house memory; offload to sandbook). dec-225 settled the
*removal + offload* direction; this ADR settles the *competitive-parity* question
(beads vs sandbook) and the *sequencing* question (defer-by-dependency) without superseding
it. A future ADR will record the actual sandbook integration.
