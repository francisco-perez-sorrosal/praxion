---
id: dec-draft-f6986093
title: Test-topology growth-trigger thresholds — two-factor gate with calibratable values
status: proposed
category: configuration
date: 2026-05-19
summary: The advisory growth trigger fires on a two-factor gate — primary signal is full-suite wall-clock runtime, co-factor is structural feasibility (Built-component count plus a test-count floor). Starting values are 90 s runtime, 4 Built components, 200 tests, all recorded as explicitly calibratable guesses.
tags: [test-topology, growth-trigger, thresholds, calibration, sentinel, configuration]
made_by: agent
agent_type: systems-architect
branch: worktree-test-topology-activation
pipeline_tier: full
affected_files:
  - agents/sentinel.md
  - agents/systems-architect.md
  - skills/testing-strategy/references/test-topology.md
affected_reqs: [REQ-01, REQ-02, REQ-04, REQ-18]
---

## Context

The M2 growth trigger (sentinel TT06 and the systems-architect Phase 2 readiness check) proposes adopting a test topology when a topology-less project has grown enough that scoped test execution would pay off. It needs a concrete firing condition. The condition must distinguish a project where a topology *helps* from one where it would be an anti-pattern.

`dec-087` rejected a Praxion pilot specifically because Praxion's full test fleet runs in ~35 s — scoped invocation saves nothing at that scale — and because the topology groups would have recapitulated the whole repo rather than mapping to real subsystems. Both halves of that reasoning are signals: runtime (does scoping save anything?) and structural feasibility (do groups map to real subsystems?).

This decision does not contradict `dec-draft-19082bdc` (the M2 activation decision); it *refines* it by fixing the specific threshold values that decision left to "the architect finalizes." It is filed as a separate ADR because the threshold values are independently calibratable and will likely be tuned on their own cadence, separate from the structural M2 decision.

## Decision

The growth trigger fires on a **two-factor gate** — all conditions must hold:

1. **Primary signal — full-suite wall-clock runtime ≥ 90 seconds.** This is the signal scoped invocation actually saves. 90 s is ~2.5× Praxion's ~35 s fleet — a deliberate margin clearly past the point at which `dec-087` judged scoping not worth it.
2. **Structural co-factor A — ≥ 4 Built components in `.ai-state/DESIGN.md` §3.** Below this, topology groups would recapitulate the whole project rather than map to distinct subsystems (the rejected anti-pattern). Four is the minimum at which a meaningful group partition (more than two non-trivial groups plus their boundaries) is possible.
3. **Structural co-factor B — ≥ 200 total project tests.** A test-count floor: a suite small enough to fall below this is not worth partitioning even if it is slow, and per-group counts would be too thin for the closure semantics to matter.

All three values are **explicitly calibratable starting guesses.** This is recorded inline in the trunk policy section (`skills/testing-strategy/references/test-topology.md` §"Growth-Trigger Policy") and in the sentinel TT06 rule text, using the same honest framing the regeneration-cadence decision used for its "3+ rows is a guess" threshold. The first consumer projects to cross the gate provide the calibration evidence.

`/refresh-topology --init` applies the structural co-factors as a gate of its own: it declines to scaffold a topology when `DESIGN.md` is absent or §3 has fewer than 4 Built components, explaining that groups would recapitulate the whole project.

## Considered Options

### Option 1 — Single signal: runtime only

Fire when full-suite runtime exceeds a threshold.

- Pro: simplest; runtime is the signal scoping saves.
- Con: a slow but architecturally thin project (few components, monolithic) would be told to adopt a topology whose groups cannot map to real subsystems — the exact anti-pattern `dec-087` rejected. Rejected.

### Option 2 — Two-factor gate: runtime AND structural feasibility (chosen)

Runtime AND Built-component count AND test count.

- Pro: catches the project where a topology genuinely helps; rejects the slow-but-thin project where it would be an anti-pattern; rejects the small-suite project where partitioning is pointless.
- Con: a three-way AND will miss edge cases (slow, well-componentized, but only 150 tests → not proposed). Acceptable — the trigger is advisory and a user can always invoke `/refresh-topology --init` directly.

### Option 3 — Subsystem-count signal instead of test count

Use the number of declared subsystems rather than a raw test count as the co-factor.

- Pro: arguably more directly tied to "can groups map to subsystems."
- Con: a project that has not yet adopted the topology has no declared subsystems to count — the signal is unavailable precisely when the trigger needs it. Built-component count from `DESIGN.md` §3 is the available proxy; test count is the orthogonal "is the suite big enough" floor. Rejected.

## Consequences

**Positive:**
- The gate encodes both halves of the `dec-087` rejection reasoning, so a project that crosses it is one where a topology genuinely pays off.
- Advisory-only: a miscalibrated threshold costs at most an ignorable INFO note, never a blocked pipeline.
- Values are calibratable and the calibratable framing is explicit, so the first tuning pass has no decision to relitigate — only numbers to adjust.

**Negative:**
- The numbers are guesses with no field data behind them yet. The three-way AND may be too conservative (misses real candidates) or the runtime floor too low (proposes too eagerly). First-consumer-project evidence will tell.

**Neutral:**
- Praxion itself never crosses the gate (~35 s fleet), so this decision has no effect on Praxion's own pipeline — consistent with the pilot deferral.

## Relationship to the M2 Activation Decision

This ADR refines `dec-draft-19082bdc` (test-topology M2 activation), which established the two-factor-gate *shape* and named the growth-trigger homes but explicitly left the threshold *values* for the architect to finalize. This ADR fixes those values. No supersession relationship is recorded: the M2 decision's structural content (agent wiring, growth-trigger homes, re-affirmations) remains fully authoritative; this ADR only makes its "thresholds TBD" placeholder concrete. The two are co-authored in the same pipeline and stand together — the values here are expected to be re-tuned independently of the structural decision, which is why they live in a separate `configuration`-category ADR.
