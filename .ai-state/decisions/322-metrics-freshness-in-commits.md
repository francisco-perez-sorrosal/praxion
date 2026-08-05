---
id: dec-322
title: A metrics report records what it describes, and freshness is measured in commits
status: accepted
category: architectural
date: 2026-08-05
summary: 'Metrics reports gain run provenance (generated_at / commit / dirty) and a new TD06 check measures staleness as per-hotspot commit distance rather than report age, because a hotspot is invalidated by a commit and a 6-day-old report can sit behind ~180 of them.'
tags: [metrics, provenance, staleness, sentinel, tech-debt-ledger, gate-liveness, false-positive, hotspots]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: standard
dissent: 'Report age is a cheaper proxy that needs no provenance plumbing, no new script, and no schema change — and on a slow-moving repository it would rarely disagree with commit distance.'
affected_files:
  - scripts/project_metrics/schema.py
  - scripts/project_metrics/cli.py
  - scripts/project_metrics/report.py
  - scripts/check_metrics_freshness.py
  - scripts/test_check_metrics_freshness.py
  - agents/sentinel.md
---

## Context

A sentinel audit reported that the metrics substrate was **frozen**: `hotspots.top_n` was
byte-identical across three consecutive reports, and "a sliding 90-day window advanced 13
days cannot leave every entry unchanged." The prescribed remedy was to fix the
recomputation.

**The premise is false and the recomputation is correct.** `churn_90d` changes only when
commits *enter* or *leave* the window. A file written in a burst and then left alone has a
genuinely constant value until new commits touch it or the burst ages out. Verified by
recomputing every entry from git at each report's own timestamp: **10 of 10 churn values
reproduce exactly**, and `dashboard_app/src/components/metrics-dashboard.tsx` is legitimately
1823 on 2026-06-20, 2026-07-16 and 2026-07-29 — and 2191 today, because a commit on
2026-07-30 moved it. The window slides; the value changes when reality changes.

But the *harm* the audit observed was real. The sentinel came within one judgement call of
filing a `td-NNN` row against that file — for debt that commit `56d5e50` had already paid by
decomposing it from ~700 lines to 133. The audit caught it only by checking `git log` by
hand.

So a correct computation still produced a near-false filing, and the cause lies between the
producer and the consumer:

1. **A report does not record what it is a report of.** `RunMetadata` carries `window_days`,
   `top_n`, `wall_clock_seconds` — how the run was *configured* — but no timestamp and no
   commit. Only the filename encodes a date; nothing encodes the analysed state.
2. **The consuming staleness policy is denominated in days.** `agents/sentinel.md` warned
   when the latest report was older than 14 days. The report in question was **6 days old**
   — comfortably fresh — while roughly **180 commits** had landed, one of which resolved the
   finding.

TD01–TD04 are among only four sanctioned writers to `TECH_DEBT_LEDGER.md`, which five agents
consume. That authority was resting on an input whose currency no one could mechanically
establish.

## Decision

**Report provenance.** `RunMetadata` gains three additive, optional fields — `generated_at`
(ISO 8601 UTC), `commit` (analysed `HEAD`), and `dirty` (tree had uncommitted changes at
capture). `SCHEMA_VERSION` takes a **patch** bump (1.2.0 → 1.2.1), deliberately: trend
computation compares only major.minor, so a minor bump would mark every prior report
`schema_mismatch` and sever trend continuity for a change that breaks no reader.

**Freshness measured in commits, gated per path.** A new `scripts/check_metrics_freshness.py`
answers whether the newest report still describes current `HEAD`. Its gate is **not** a
commit threshold — inventing one would reproduce the original defect in a new unit. The gate
is the only question admitting an exact answer:

> has *this* ranked hotspot's file been touched since the report was taken?

`commits_since` and `age_days` are reported as context, never as the verdict. Distance alone
is explicitly not staleness: a hundred commits elsewhere leave a ranking valid.

**Withholding over guessing.** A report predating provenance has an *unrecoverable* commit
distance — no filename or log records the analysed SHA. The checker returns a distinct
`withheld` status with a named reason rather than a silent `fresh`, because collapsing
"unanswerable" into "clean" is precisely how the original gap stayed invisible.

**Consumer wiring.** A new sentinel check **TD06** runs the script before TD01 and bars every
`hotspots_touched` path from filing until re-verified against current source. On `withheld`,
TD01 must hand-verify and say so. TD06 writes no ledger row — it gates TD01 rather than
filing.

## Considered Options

### A. Fix the recomputation, as the audit prescribed

Rejected on evidence. There is nothing to fix; 10 of 10 values reproduce from git. Changing
correct code to satisfy a false finding would have made the complaint stop while leaving the
ledger's input exactly as untrustworthy — the "make the measurement stop complaining" failure
the audit's own brief forbids.

### B. Tighten the age threshold (14 days → 3 days, say)

Rejected. It changes the constant, not the unit. The observed incident was 6 days old; a
3-day rule would have caught that instance and missed the next one at 2 days and 200 commits,
while firing constantly on quiet weeks. Age bounds how *old* data is, never how much the
subject moved underneath it.

### C. Commit-distance threshold (warn above N commits)

Rejected as the *gate*, kept as context. Any N is arbitrary, and the relationship between
commit count and hotspot invalidity is not monotonic — one commit to the right file
invalidates a finding that a thousand commits elsewhere leave intact. Per-path liveness needs
no threshold and is exactly right rather than approximately right.

### D. Re-run `/project-metrics` before every sentinel audit

Rejected. It converts a cheap read into a multi-minute pipeline with an LLM tier on every
audit, and still cannot help a consumer reading an existing report. It also treats freshness
as an operator ritual rather than a property a consumer can check.

## Consequences

**Positive**

- A report is self-describing: any consumer can determine what state it reflects.
- The exact historical near-miss is now caught mechanically. Reconstructed as a test, the
  checker flags `#1 metrics-dashboard.tsx` as moved — and finds **three further** stale
  entries the day-based policy never surfaced.
- The manual workaround the audit had to mandate ("verify every candidate against `git log`
  before filing") becomes a gate rather than an instruction.
- `dirty: true` makes an unreproducible capture visible instead of implied.

**Negative**

- Nine existing reports carry no provenance and will return `withheld` until regenerated.
  This is honest rather than convenient: `withheld` is a signal to re-run, not a pass.
- One `git rev-list` per ranked path per audit — bounded by `top_n` (10 by default), so a
  handful of subprocesses, not a repository sweep.
- The sentinel's TD dimension gains a check and an ordering constraint (TD06 before TD01).

## Disconfirmation

**Falsifier.** If, over several audits, `hotspots_touched` is consistently empty while TD01
still files rows against debt that later proves already paid, then per-path liveness is not
the discriminator and the invalidation mechanism lies elsewhere — most likely in complexity
drift rather than file modification. Equally falsifying: if `hotspots_touched` flags nearly
every ranked path on nearly every run, the signal carries no information and TD01 gains
nothing but friction.

**Steelmanned runner-up.** Option B — tighten the age threshold — is stronger than it first
appears. It requires no schema change, no new script, no provenance plumbing, and no ordering
constraint between sentinel checks; it is one number in one sentence. On a repository
committing a few times a week, days and commits are nearly collinear, and the whole apparatus
here would buy almost nothing over `14 → 3`. The case for commit distance rests on this
repository's actual velocity (~180 commits in 6 days), which is not a universal condition —
in a slower fleet project the simpler rule would be the better engineering.

**Reversal trigger.** Revisit if the per-path `git rev-list` cost becomes material on a large
`top_n`, or if provenance turns out to be reconstructible from another source (making the
`withheld` state unnecessary), or if a managed project's velocity is low enough that TD06
never disagrees with the age rule over a full quarter — at which point the age rule alone is
the simpler correct answer for that project and TD06 is ceremony.
