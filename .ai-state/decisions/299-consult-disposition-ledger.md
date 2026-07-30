---
id: dec-299
title: Disposition counter is a dedicated append-only .ai-state/CONSULT_LEDGER.md, single-writer, shipped as a prerequisite
status: accepted
category: architectural
date: 2026-07-30
summary: The accept/defer/dismiss counter lands as a new dedicated append-only markdown ledger in .ai-state/ written only by the convener, rather than as tech-debt-ledger rows (which would break the four-writer contract) or a metrics-report triple (over-built); it ships before or with the first discipline because it is the router's calibration loop, not a report card.
tags: [multidisciplinary-identities, discipline-consultant, instrumentation, disposition-vocabulary, calibration, falsifier, tech-debt-ledger, sentinel-p07]
made_by: agent
agent_type: systems-architect
branch: worktree-multidisciplinary-identities
pipeline_tier: full
affected_files:
  - .ai-state/CONSULT_LEDGER.md
  - rules/swe/agent-intermediate-documents.md
  - agents/systems-architect.md
  - agents/sentinel.md
affected_reqs:
  - REQ-13
  - REQ-14
  - REQ-17
dissent: The ledger measures the architect's own judgment of the consultant's value, and a removal-based-attribution study shows introspective LLM judges fail to faithfully approximate ablation ground truth — so a low dismiss rate may record an agreeable architect rather than a useful consultant, and shipping this particular instrument as the initiative's falsifier risks certifying the mechanism with a measurement the same literature says is unfaithful.
re_affirmed_by:
  - dec-304
---

## Context

The initiative's own falsifier is the accept/defer/dismiss ratio per discipline. **No countable, persistent
artifact for it exists today.** The disposition vocabulary itself is settled convention, and one sentinel check
already greps for disposition *presence* in an ephemeral file — but nothing counts a ratio, and two of the three
outcomes do not survive `.ai-work/` cleanup:

| Bucket | Existing home | Survives cleanup? |
|---|---|---|
| `switch-now` | An ADR is written to `.ai-state/decisions/` | **Yes** |
| `defer-with-rationale` | Folded into `SYSTEMS_PLAN.md` or `LEARNINGS.md` prose — both ephemeral | **No**, unless manually promoted |
| `dismiss-with-rationale` | Same ephemeral homes, with no ledger equivalent | **No** — and this is the bucket the falsifier needs counted most |

Wave A elevated this from instrumentation to **precondition**, by two independent routes. The external lens found
that the one validated bounded-roster router beats random *because* its gate correlates with the measured persona
effect (Pearson r=0.65, Spearman ρ=0.75) — a hand-authored trigger table has **no such feedback loop and can be
arbitrarily miscalibrated**, so the counter *is* the mechanism that makes authored routing work at all. The
internal lens found no countable artifact exists. Shipping the selection tiers without the counter would make the
value question permanently unanswerable — which is itself the measurement blind spot this initiative claims to fix.

The internal lens also surfaced two directly-analogous in-repo precedents: a plain append-only row format written
into the already-existing `.ai-state/calibration_log.md` (same repository, same "record one categorical outcome
per pipeline event" need), and a timestamped report-triple collector explicitly designed as a *baseline* that
"stands the infrastructure up so the recalibration can accrue."

## Decision

**A new dedicated append-only file, `.ai-state/CONSULT_LEDGER.md`, one row per challenge, single writer.**

Schema — one row per challenge, appended at round 2:

| timestamp | task-slug | discipline | stage | challenge-id | claim | decision-at-stake | disposition | rationale-ref | model | difficulty |

`disposition` takes exactly one of the three shared vocabulary values. `rationale-ref` points at the ADR draft id
or the plan section carrying the reasoning. `model` and `difficulty` are recorded so the routing axis that is
genuinely per-spawn becomes correlatable with outcomes. The falsifier is a one-liner —
`grep -c 'dismiss-with-rationale'` over rows filtered by discipline — with **no parser**, which is the whole point
of the placement.

**Single writer = the convener** (the systems-architect in pipeline mode; the orchestrator in standalone
`/consult` mode). The consultant writes only its own fragment and never touches the ledger. This removes a write
race under the N-concurrent-instance model and matches single-owner reconciliation: the party that adjudicates is
the party that records.

An un-reconciled challenge would leave no row, so **the presence gate is separate from the ratio counter**:
sentinel `P07`'s scope is extended **in place** to `CONSULT_*.md` — an edit to an existing check rather than a new
one, matching the sanctioned inline-grep form for exactly this obligation. The ledger counts ratios; `P07` catches
silence. Neither can substitute for the other.

**Ordering is part of the decision.** The ledger ships **before or with** the first discipline, never after. The
implementation plan must sequence it first.

## Considered Options

### Option 1 — New dedicated append-only markdown ledger in `.ai-state/` (chosen)

- **Pros:** cheapest option; mirrors an exact in-repo precedent; `grep`-countable with no parser; persists past
  `.ai-work/` cleanup, closing the gap for the two buckets that vanish today; preserves the four-writer
  tech-debt contract untouched; append-only markdown merges trivially across worktrees.
- **Cons:** one more `.ai-state/` file to maintain; unbounded growth (bounded in practice by the convening gate).

### Option 2 — Extend `TECH_DEBT_LEDGER.md` with a `discipline-challenge` class

- **Pros:** reuses a live schema, a live sentinel-reads-ledger pattern, and an existing merge/dedupe protocol;
  no new artifact at all.
- **Cons:** rejected on two independent grounds. It would break the **four-writer contract** (only verifier,
  sentinel, orchestrator, and architect-validator add rows — a contract a prior production-gate decision went out
  of its way to preserve, explicitly keeping an ownership assignment awkward rather than widening the writer set).
  And a *dismissed* challenge is not debt at all, so the majority of rows would be semantically wrong. The
  genuinely-debt subset — a `defer-with-rationale` carrying residual risk — already has a path: the verifier
  promotes it through the existing mechanism. Complementary, not the counter.

### Option 3 — Dedicated `CONSULT_REPORT_<ts>.{json,md}` + `_LOG.md` triple with a collector script

- **Pros:** matches the established baseline-collector pattern; machine-readable JSON; dashboard-ready; naturally
  extends to derived metrics (dismiss rate by discipline, by model, over time).
- **Cons:** over-built for Wave 1 by the repository's own stated rule ("script only if frequent"). Expected volume
  is a handful of rows per convened pipeline, and a collector plus report generator buys nothing a markdown table
  does not. Promotable later from Option 1's rows without data loss.

### Option 4 — Extra rows inside the existing `.ai-state/calibration_log.md`

- **Pros:** no new file; reuses the exact append-only precedent this ADR cites.
- **Cons:** that file already carries a fixed seven-column tier-selection schema parsed by two sentinel checks,
  *and* a second row shape appended by the design-synthesis logging obligation. A third shape makes "count the
  dismiss rate" require disambiguation — the one property a falsifier instrument must not have. One schema per
  file keeps the falsifier a `grep`.

## Consequences

**Positive:** the initiative becomes falsifiable within roughly ten tasks; the authored trigger table gains the
feedback loop the literature says it needs to beat random; `defer` and `dismiss` outcomes persist for the first
time; the four-writer contract stays intact; recording `model` and `difficulty` makes the one real heterogeneity
axis auditable against outcomes.

**Negative:** a new persistent artifact with its own conventions; the ratio is only as honest as the convener's
rationales.

**Risks accepted:** concurrent-worktree appends can conflict — accepted because append-only markdown tables
resolve trivially and a merge-driver precedent already exists if volume warrants one. More importantly, the
measure is **introspective** and a 2026 removal-based-attribution result shows introspective LLM judges fail to
faithfully approximate ablation ground truth, and that an agent's contribution to *outcome quality* and to a
*secondary objective* are often decoupled — so a single ratio cannot separate "raised accepted challenges" from
"improved the artifact." This limitation is recorded in the ledger's own header rather than papered over, and the
faithful alternative (Leave-One-Out: run the same task with and without the consultant) is dispositioned
`defer-with-rationale` — it doubles cost on the sampled task and needs a comparable-artifact metric for design
outputs that have no ground truth, so it becomes the periodic audit that keeps the cheap daily instrument honest,
gated on the same evidence threshold as the deferred selection tier.

## Disconfirmation

- **Falsifier:** the ledger accumulating rows that nobody reads. Concretely — reaching ≥20 rows without the
  dismiss rate ever having informed a registry `fires-when` predicate, a discipline retirement, or a routing
  change. That would mean the instrument is a report card after all, and the argument that it is a calibration
  loop was wrong.
- **Steelmanned runner-up:** Option 3 (the report triple with a collector). Its strongest case is that the
  falsifier this ledger exists to serve is a *rate over time by discipline and by model* — genuinely a derived
  metric, not a row count — and markdown tables are a poor substrate for anything a human will not read in full.
  The established collector pattern was created for exactly this posture ("the value is the ready-to-accrue
  collector, not the first numbers"), and the same project already runs a metrics surface that would consume the
  JSON directly. If the roster ever reaches four or more disciplines, Option 3 becomes the right answer and
  Option 1's rows are its input, so nothing is lost by starting cheap.
- **Reversal trigger:** ≥4 active disciplines, **or** a demonstrated need for a rate-over-time series that a
  `grep` cannot produce (for example, correlating dismiss rate against `model` to validate the routing policy).
  Either promotes the ledger to a collector-plus-report shape, migrating existing rows rather than restarting.
  Separately, evidence that the introspective ratio is misleading — a Leave-One-Out audit disagreeing with the
  ledger's verdict — would demote the ratio from falsifier to indicator.
