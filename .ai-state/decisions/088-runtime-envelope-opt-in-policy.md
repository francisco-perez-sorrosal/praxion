---
id: dec-088
title: expected_runtime_envelope is opt-in at M1 and M2; required from M3 (sentinel TT04 activation)
status: proposed
category: behavioral
date: 2026-04-28
summary: The per-group expected_runtime_envelope (p50/p95 wall-clock seconds) is optional at M1 and M2; sentinel TT04 (runtime drift) self-deactivates when fewer than 7 metrics reports with per-group data exist; the field becomes required at M3 when TT04 is the load-bearing refactor trigger.
tags: [test-topology, schema, runtime-envelope, sentinel, tt04, milestones]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_reqs: []
affected_files:
  - skills/testing-strategy/references/test-topology.md
  - agents/sentinel.md
---

## Context

Open Question 1 from `RESEARCH_FINDINGS.md` §E.4. The schema in §C.1.2 declares `expected_runtime_envelope` (p50, p95 wall-clock seconds per group) as a required field. But at M1 the project has no measurements — forcing the field would invent fictional baselines that the team would then have to calibrate against. The researcher's default suggestion: opt-in at M1, required by M3. The architect was asked to confirm or override.

The downstream consumer of this field is sentinel TT04: it compares actual P95 over 7 sentinel runs against the declared envelope and files a `topology-drift` ledger row when the actual exceeds 1.5× the declared. Without the field populated, TT04 cannot fire — but the rest of the protocol (TT01–TT03, TT05; step/phase/pipeline tier selection; integration_boundaries closure) functions independently of the envelope.

## Decision

**`expected_runtime_envelope` is OPTIONAL at M1 and M2; REQUIRED from M3.**

Implementation specifics:

- Trunk schema marks the field as `optional at M1; required from M3 (sentinel TT04 activation milestone)`.
- Sentinel TT04 has a conditional activation clause: skip the entire check when fewer than 7 `metrics_reports/METRICS_REPORT_*.json` files contain per-group runtime data. This handles the cold-start case generically (a project just adopting the protocol may have no metrics history at all).
- A separate (independent) clause in TT04: skip per-group when that group's `expected_runtime_envelope` field is absent. This handles the "envelope opt-in" case at the per-group granularity.
- M3 is defined (in `RESEARCH_FINDINGS.md` §E.2) as the milestone where the refactor trigger goes live. At that point the field becomes required for any group whose runtime is being tracked. Non-tracked groups (e.g., Lightweight-tier-only) remain optional indefinitely.

## Considered Options

### Option A — Required from M1

Force every group at creation time to declare a `p50` and `p95`.

**Pros:**
- Schema completeness from day one.
- Forces calibration discipline.

**Cons (decisive):**
- M1 has no measurements. Calibration before measurement produces fiction. The project then either (a) lives with fiction in the ledger forever, or (b) rewrites every group's envelope at M2. Either is worse than declaring optional and letting the field fill in lazily.
- TT04 cannot meaningfully fire on fictional baselines anyway; the check would be either always-passing or always-noisy.
- New group authors face an unnecessary friction barrier.

### Option B — Opt-in at M1, required from M3 (chosen)

The recommended path from the researcher.

**Pros:**
- Schema is honest about what data exists.
- TT04 self-deactivates cleanly when data is missing.
- M3 defines the activation moment, giving the project time to accumulate baseline data through normal pipeline runs.
- Migration path is gentle: groups can opt in incrementally as their runtime stabilizes.

**Cons:**
- The schema is in two states (M1–M2 vs M3+), which requires the trunk reference to document both. Mitigation: a one-line "optional until M3" annotation handles this with no real cost.
- A group that is created in M2 with no envelope, then lives through M3 transition without anyone backfilling the envelope, will silently stop being TT04-tracked. Mitigation: TT05's marker-vs-id check is unaffected; TT04 emits a per-pocket "envelope absent" WARN at M3 to surface the gap.

### Option C — Permanently optional

Never require the field; treat TT04 as opt-in indefinitely.

**Rejected.** The sentinel dimension family is the load-bearing answer to the maintenance-burden risk (researcher §D.2). If the field is never required, TT04 becomes an opt-in feature that most projects will not opt into, and the maintenance signal degrades to nothing. The protocol's value depends on TT04 firing reliably at scale.

## Consequences

### Positive

- M1 is honest: the schema reflects what the project knows, not what it might know.
- TT04's self-deactivation clause is a generic mechanism that handles cold-start, partial adoption, and missing-metrics cases uniformly.
- M3 has a clean activation moment that the planner can decompose into concrete steps (backfill envelopes, validate across 7 sentinel runs, flip the requirement flag).

### Negative

- Two-state schema (optional pre-M3, required from M3) requires documentation in the trunk reference. Acknowledged; the documentation cost is one short paragraph.
- A group created without an envelope and never updated will accumulate technical debt of the "envelope absent" form at M3. The fix is a planner-driven backfill pass that consumes the metrics data accumulated since M1.

### Reversibility

Easily reversible. If M3 reveals the requirement is too aggressive (e.g., too many groups remain transient and an envelope is meaningless for them), a follow-up ADR can keep the field optional with a `tracked_for_drift: true|false` flag governing whether TT04 applies. This is an additive change that does not break the M1–M2 semantics.

## Prior Decision

None.
