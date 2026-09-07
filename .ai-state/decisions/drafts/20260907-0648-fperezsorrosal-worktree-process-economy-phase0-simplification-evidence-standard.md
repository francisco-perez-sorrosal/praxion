---
id: dec-draft-a4b27081
title: Simplification requires a measured cost and an executable guard
status: proposed
category: behavioral
date: 2026-09-07
summary: A simplification of process or context artifacts requires a measured cost and an executable guard (check, test, eval scenario, or read/fire telemetry); self-graded logs are not guards until they show variance.
tags: [process-economy, evidence-standard, calibration, consult-ledger, quality-guard]
made_by: agent
agent_type: implementation-planner
branch: worktree-process-economy-phase0
pipeline_tier: standard
affected_files:
  - docs/independent-analysis/process-economy-roadmap.md
---

## Context

The process-economy roadmap (`docs/independent-analysis/process-economy-roadmap.md`) found
two of Praxion's own instruments used to justify process weight are zero-variance and
self-graded: the calibration log's retrospective enum has recorded `over-calibrated` or
`under-calibrated` **zero times in 85 rows over five months**, and the discipline-consultant
ledger has recorded **zero dismissals in 77 dispositioned challenges**. Both are Type-I-blind
by construction — written by the same agent, in the same session, with full knowledge of the
outcome it is grading. A roadmap that proposes removing ceremony on the strength of "quality
preserved, verified by the calibration log" or "verified by the consult ledger" would be
citing an instrument that cannot record the exact failure it exists to detect. This is
directionally consistent with `dec-040`'s existing out-of-band-eval stance (evals run only
via explicit invocation, never as an implicit hook-driven gate) — that decision is not
touched here, only extended to a broader evidentiary standard.

## Decision

A simplification of process or context artifacts (removing a rule, shortening an agent
prompt, retiring a check, reducing an artifact's mandate, etc.) requires **both**: (1) a
measured cost it removes (a number produced by a script, tool, or telemetry reading — not a
reasoned estimate), and (2) an executable guard that would catch a regression in the
behavior the removed content bought — a check script, a test, an eval scenario, or
read/fire telemetry. Self-graded logs (the calibration retrospective, the consult ledger)
are explicitly **not** guards until they demonstrate variance (the roadmap's P0.6 and P2.8
items give them a path to earn that status).

## Considered Options

| Option | Pros | Cons |
|---|---|---|
| **Measured cost + executable guard mandatory (chosen)** | Closes the exact gap the roadmap's evidence lens found; forces every future simplification to name a concrete regression detector | Some judgment-based simplifications (roadmap `Conf: L` items) cannot proceed until new instrumentation exists, slowing them relative to today's norm |
| Status quo — a named rationale suffices | No new friction; matches current implicit practice | This is precisely the norm that let a wrong budget-hook figure sit uncorrected in the WAL for 23 sessions across 5 weeks, unnoticed |
| Require a controlled A/B for every simplification | Would answer the causal question directly | Prohibitively expensive and confounded by task selection; the evidence lens's own gap analysis (G8) recommends against attempting this, in favor of the affordable substitute this decision codifies |

## Consequences

**Positive**: no future simplification can cite a zero-variance self-graded log as its
quality guard; the burden of proof for removing ceremony now sits explicitly on the
ceremony, matching the roadmap's guiding principle 4 ("a quality guard is executable or it
is not a guard"). **Negative**: a handful of currently-`Conf: L` roadmap items (no existing
guard) cannot proceed as simplifications until an instrument is built for them — this is a
deliberate slowdown of unguarded cuts, not an oversight.
