---
id: dec-draft-3adfda75
title: The calibration verdict is authored by the verifier, not the agent that chose the tier
status: proposed
category: architectural
date: 2026-09-07
summary: At Standard/Full, the required calibration-retrospective enum is written by the verifier (independent of tier selection); at Direct/Lightweight the orchestrator writes it but must cite a measurable.
tags: [process-economy, calibration, verifier, sentinel-ca02, quality-guard]
made_by: agent
agent_type: implementation-planner
branch: worktree-process-economy-phase0
pipeline_tier: standard
dissent: The verifier sees only the finished artifact, not the intake-time ambiguity that justified the original tier choice, so it may systematically judge "over-calibrated" in hindsight for choices that were legitimately conservative given what was known at the time.
affected_files:
  - agents/verifier.md
  - skills/spec-driven-development/references/calibration-procedure.md
  - agents/sentinel.md
---

## Context

The process-economy roadmap's evidence lens found that `.ai-state/calibration_log.md`'s
retrospective enum (`correct` / `over-calibrated` / `under-calibrated`) has recorded an
error value **zero times across 85 rows over five months** — a rate the roadmap identifies
as evidence of a Type-I-blind instrument, not evidence of perfect calibration, because the
retrospective is written by the same agent that selected the tier, in the same session,
with full knowledge of the outcome. Sentinel's CA02 dimension already checks a
recommendation-vs-actual match rate against this log but cannot detect the specific failure
mode this decision exists to fix (an agent grading its own tier choice never records the
error). No prior ADR assigns retrospective-authorship responsibility explicitly; this
decision is the first to name it.

## Decision

At Standard/Full tier, the required enum on a completed pipeline's calibration-log row is
written by the **verifier** — an agent that reads the finished plan and diff, and did not
select the tier — accompanied by a one-line evidence clause. The orchestrator copies this
verdict into the calibration log rather than authoring its own. At Direct/Lightweight
(where no verifier runs), the orchestrator still writes the enum but must cite one concrete
measurable (spawn count, a token figure, or a mid-task re-tier event) rather than asserting
`correct` bare.

## Considered Options

| Option | Pros | Cons |
|---|---|---|
| **Verifier-owned at Standard/Full; orchestrator-owned-with-citation at Direct/Lightweight (chosen)** | Introduces genuine independence from the same-agent-same-session bias exactly where a verifier already exists to provide it; Direct/Lightweight gets a cheaper, still-improved discipline where no verifier runs | Verifier now carries an extra small responsibility outside its primary review scope |
| Orchestrator-owned everywhere, with a mandatory citation requirement | Simpler — no new authorship responsibility for the verifier; preserves single-session flow | The same agent with the same incentive to justify its own tier choice remains the sole author; a citation requirement narrows but does not remove the self-grading bias this decision responds to |
| Status quo — self-graded, no enum requirement enforced | No change needed | This is literally the zero-variance failure this decision exists to fix |

## Consequences

**Positive**: the calibration log gains a plausible path to actually recording a
miscalibration, closing the specific gap the roadmap's evidence lens identified; sentinel
CA02 gains a distribution it can meaningfully analyze instead of a stale match-rate
threshold that could not fire. **Negative**: the verifier's output contract grows by one
small section; a small number of pipelines with no verifier (Direct/Lightweight) still rely
on the less-independent orchestrator-with-citation model, which is an improvement but not a
full fix for those tiers.

## Disconfirmation

**Falsifier**: if verifier-written enums show a systematic bias — for example, more than
roughly four in five Standard-tier tasks that had no viable Lightweight alternative still
get judged `over-calibrated` in hindsight — the independence this decision purchased would
be costing more (a new, differently-biased instrument) than the self-grading bias it fixed.

**Steelmanned runner-up**: keep the orchestrator as sole author everywhere but require it to
cite one of the three named measurables before ever writing `correct`. This preserves
single-session simplicity and needs no change to the verifier's contract. It loses because
citing a measurable does not remove the underlying incentive: the same agent, with the same
motivation to justify the choice it already made, remains the author — independence is what
a Type-I-blind instrument specifically needs, and a citation requirement alone does not
supply it.

**Reversal trigger**: if the verifier's enum-writing burden measurably degrades its primary
review throughput or quality, or if sentinel CA02's rewritten enum-distribution check
(roadmap P0.6/P2.6) shows no improvement in recorded variance after a meaningful number of
new rows, revisit whether the verifier should retain this responsibility.
