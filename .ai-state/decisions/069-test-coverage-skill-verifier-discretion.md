---
id: dec-draft-f008ca29
title: Verifier loads test-coverage skill at its own discretion (not hard trigger)
status: proposed
category: behavioral
date: 2026-04-24
summary: The verifier receives test-coverage in its skills list plus narrow prose guidance on when it's worth invoking; no hard/automatic coverage trigger is added.
tags: [verifier, coverage, testing, pipeline, behavior]
made_by: user
pipeline_tier: standard
affected_files:
  - agents/verifier.md
  - skills/test-coverage/SKILL.md
---

## Context

The test-coverage skill is useful to the verifier — the verifier often needs to answer "did the new code raise or lower coverage?" and "are critical paths covered?". But forcing the verifier to invoke coverage measurement on every run would be expensive (coverage runs are the longest step in most pipelines), often pointless (many verifications touch no test-relevant code), and cognitively noisy (the verifier's report already has ten phases).

The user's settled position on this, verbatim: "option B (conditional automatic) — but at verifier's discretion, not a hard trigger." The design must preserve verifier autonomy while giving it the skill and clear guidance on when to reach for it.

## Decision

Two things change in `agents/verifier.md`:

1. `test-coverage` is added to the verifier's `skills:` frontmatter list. The skill is *available* on every verifier run.
2. Prose guidance (likely inside Phase 10 "Test Coverage Assessment" or as a dedicated subsection) names the conditions where invoking coverage measurement is likely worth the time:
   - Pipeline tier is Standard or Full,
   - Test files were changed in the current pipeline,
   - Acceptance criteria reference coverage or test completeness,
   - The implementer's `TEST_RESULTS.md` is missing or ambiguous.

No hard trigger, no automatic "always run coverage," no pre-commit gate. The verifier reads the guidance, judges the current run, and either invokes the skill or doesn't. Non-invocation is a valid outcome and never produces a FAIL on its own.

## Considered Options

### Option A — Hard automatic trigger on every verifier run (rejected)

Every verification invokes coverage measurement.

- **Pros.** Guaranteed coverage data on every pipeline.
- **Cons.** Expensive (coverage runs dominate verifier wall-clock); often irrelevant (docs-only changes, config-only changes); adds a failure mode where a flaky coverage run blocks an otherwise-clean verification.

### Option B — Conditional automatic, verifier discretion (chosen)

The skill is loaded; the prose guidance points at it; the verifier decides each run.

- **Pros.** Preserves the verifier's phase-budget discipline (the verifier already self-manages turn budget at 60% / 80% thresholds); respects the user's stated preference; no new failure modes on runs where coverage is irrelevant.
- **Cons.** Verifier autonomy means verifier inconsistency — two runs on the same change could produce different coverage-assessment outputs. Mitigation: the prose guidance is narrow (four concrete signals), not open-ended.

### Option C — Opt-in only (rejected as too weak)

The skill loads only when the user explicitly requests coverage measurement.

- **Pros.** Zero verifier cost on any run the user doesn't trigger.
- **Cons.** The verifier loses the ability to flag missing coverage on a change that clearly warrants it (e.g., a new auth flow with no tests); the user has to know to ask.

## Consequences

**Positive.**
- The verifier retains its existing phase-budget discipline; coverage is one more tool in a well-managed belt, not a new mandate.
- The guidance doubles as documentation: when a pipeline change later wants to make coverage a hard requirement, it has a concrete anchor to argue against.

**Negative.**
- Verifier-to-verifier variance: reviewers may invoke coverage on Monday and skip it on Tuesday for superficially-similar changes. Acceptable — the verifier's reports are already inherently non-deterministic on softer conventions; coverage invocation joins that set.
- The prose guidance is load-bearing; if the criteria drift in practice, the verifier may stop invoking the skill ever, or start invoking it always. Periodic sentinel spot-check recommended (outside the scope of this feature).
