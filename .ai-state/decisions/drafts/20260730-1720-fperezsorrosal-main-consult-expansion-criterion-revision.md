---
id: dec-draft-c6b4fca6
title: The discipline-expansion criterion is a reported estimate over consults, not a binary threshold over challenges
status: proposed
category: architectural
date: 2026-07-30
summary: The Wave-2 discipline-expansion gate is demoted from an automatic "dismiss rate not >60% over >=10 challenges" pass/fail to a human-dispositioned estimate with a Wilson interval, denominated in distinct consults rather than challenge rows, with a two-sided standing condition requiring all three disposition values to have been observed.
tags: [multidisciplinary-identities, discipline-consultant, expansion-gate, falsifier, statistics, clustering, disconfirmation, consult-ledger]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: standard
re_affirms: dec-299
affected_files:
  - docs/multidisciplinary-identities-evidence.md
  - .ai-state/CONSULT_LEDGER.md
  - .ai-state/DESIGN.md
  - .ai-state/decisions/298-consult-dialogue-protocol.md
  - .ai-state/decisions/300-consult-selection-tiers-wave1-scope.md
  - .ai-state/decisions/302-parameterized-consultant-registry.md
dissent: A pre-registered numeric threshold that a party cannot argue with is worth more than a statistically honest estimate that same party gets to interpret -- the 60% bar's value was never its calibration, it was that it removed the expander's discretion, and replacing it with "report an interval and let a human disposition it" hands that discretion straight back to the person who wants the second discipline to ship. The clustering and operating-characteristic critiques are both correct and both survivable by simply raising n; choosing demotion over a larger sample trades a bounded, known error rate for an unbounded, unmeasurable one called judgment.
---

## Context

Wave 1 of the multidisciplinary-identities initiative shipped exactly one discipline (`statistician`)
behind a pre-registered gate governing whether a second may ship. As originally written
(`docs/multidisciplinary-identities-evidence.md` §14 and §17.4), that gate read:

> dismiss rate **not >60%** over **≥10 challenges** spanning **≥3 tasks**

The gate's stated purpose is to keep the initiative honest — §14 frames a high dismiss rate as grounds
to *delete, not tune*. It was authored before any data existed, which is the correct ordering, and its
counting recipe in `.ai-state/CONSULT_LEDGER.md` was deliberately built to be `grep`-derivable with a
documented fail-safe direction.

Step 15 of the pipeline ran the consultant mechanism end-to-end for the first time. The target chosen
for that live proof was this gate — a genuine stopping rule plus threshold plus sample-size claim,
squarely inside the `statistician` registry row's `fires-when` predicate. The consult raised six
challenges. All six were accepted on the merits. The gate as written did not survive them.

The core finding is quantitative and was verified by exact computation rather than assertion. Under the
rule "pass iff observed dismiss rate ≤ 0.60" at n=10:

| true dismiss rate | P(gate passes) |
|---|---|
| 0.40 | 0.945 |
| 0.50 | 0.828 |
| 0.60 (the bar itself) | 0.618 |
| 0.70 | 0.350 |
| 0.80 | 0.121 |

A discipline whose *true* dismiss rate is 0.70 passes 35% of the time; one sitting exactly at the bar
is blocked 38% of the time. The Wilson 95% interval for an observed 6/10 is [0.31, 0.83] — passing and
failing observations overlap across nearly the entire decision-relevant range.

Compounding this, the denominator was wrong in kind, not merely in size. Challenges are not independent
observations: every challenge within one consult shares a consultant instance, a draft, and — decisively
— the same convener, whose dismissal propensity is a rater effect. At ~3.3 challenges per consult and an
intra-cluster correlation of 0.3–0.5 (unremarkable for a one-rater-per-cluster rating task), the design
effect `1 + (m−1)ρ` puts the effective sample size of "≥10 challenges spanning ≥3 tasks" at **~5–6**.
The binding constraint was really the "≥3 tasks" floor, and three is not a sample.

Three further defects were structural rather than numeric: the gate was evaluated under unbounded
optional stopping by the party who wants expansion; the 60% figure was asserted rather than derived and
collided with §14 falsifier 1 (if 60% is also the delete line, a discipline at 59% simultaneously
survives deletion and unlocks expansion); and the criterion was one-sided while its own prose demanded a
"non-degenerate" distribution, so a ledger of ten `switch-now` rows and zero dismissals passed cleanly.

## Decision

The discipline-expansion criterion is **a reported estimate with an interval, dispositioned by a human**,
not an automatic threshold. Concretely:

1. **Denominator is the consult**, not the challenge. `n` counts distinct `task-slug` values in
   `.ai-state/CONSULT_LEDGER.md` for the discipline. This is the independent unit; challenges are a
   cluster within it.
2. **Report `k/n` with a Wilson 95% interval.** The interval is reported alongside the point estimate,
   never suppressed. A human reads it and decides.
3. **Two standing conditions gate informativeness**, both required before the number is read as evidence
   at all: (a) all three disposition values (`switch-now` / `defer-with-rationale` /
   `dismiss-with-rationale`) have been observed at least once; (b) `n` ≥ 3 distinct consults.
4. **No pre-registration burden.** Because nothing is decided automatically, the estimate may be read at
   any time without inflating an error rate.
5. **Tier-3 aggregation is per discipline, not pooled.**
6. **§14 falsifier 1 is explicitly a judgment call**, not a threshold test. No number is pre-registered
   there.

The counting recipe in `.ai-state/CONSULT_LEDGER.md` gains the consult-count and
disposition-values-observed commands. The column anchoring, the single-writer rule, the append-only
discipline, and the 11-column schema are all unchanged.

## Considered Options

### Option A — Demote to a reported estimate with an interval (chosen)

- **Pros.** Honest at any `n`; no arbitrary floor to defend; states the uncertainty the decision actually
  faces rather than hiding it behind a boolean. Dissolves CH-03 (nothing decided automatically means no
  error rate to inflate) and CH-04 (no threshold remains to derive) rather than merely patching them.
  §17.4's own Leave-One-Out row already contemplated exactly this demotion — "a disagreeing LOO result
  demotes the ratio from falsifier to indicator" — so the shape was pre-sanctioned by the design.
- **Cons.** Expansion is no longer mechanical: a human must read and disposition the number, which
  reintroduces the discretion the pre-registered bar was designed to remove. This is the substance of the
  `dissent:` field above and is not dismissed.

### Option B — Keep the binary gate, raise `n`

- **Pros.** Preserves mechanical, argument-free expansion. The required sample is not extravagant:
  requiring a true 0.45 rate to pass ≥90% of the time and a true 0.75 rate to be blocked ≥80% of the time
  is met at **n=15 independent observations** (P(pass|0.45)=0.923, P(pass|0.75)=0.148) — fifteen, not fifty.
- **Cons.** Composed with the clustering correction, fifteen *effective* observations is ~25 challenges
  across ≥8 tasks. At Wave 1's one-discipline roster that is a long delay before discipline #2 can ship,
  and the delay buys a discrimination the project may not need. It also keeps a pre-registered threshold
  that still has to be derived from something rather than asserted — CH-04 survives this option intact.

### Option C — Two-stage hybrid: mechanical block, human yes

- **Pros.** Retains a fast automatic *no* for clearly-bad rates while refusing to fake an automatic *yes*.
  Arguably the best of both.
- **Cons.** Two criteria to maintain and explain, and the blocking threshold is itself an asserted number
  inheriting CH-04. At `n` = 1 consult the extra machinery buys nothing today; the deferred-condition
  pattern used elsewhere in this initiative applies — adopt it if and when the reported estimate proves
  too easy to argue with.

### Option D — Do nothing; record the defects and keep the gate

- **Pros.** Zero churn; the gate does not bind until discipline #2 is proposed.
- **Cons.** The defects are free to fix now and progressively harder later. Leaving a known-broken
  falsifier in place while documenting that it is broken is the worst of both worlds: it retains the
  appearance of pre-registration without the property.

## Consequences

**Positive.** The criterion now states the uncertainty it actually has. The denominator matches the
independent unit, so the evidence is no longer overstated by roughly a factor of two. The two-sided
standing condition closes the degenerate-ledger hole. CH-03 and CH-04 are dissolved rather than patched.
Applied to the ledger as it stands, the revised criterion correctly reads **not yet informative**
(`n` = 1 consult, one disposition value observed) where the old gate would have read "0% dismiss rate,
passes" — the repair is immediately load-bearing, not cosmetic.

**Negative.** Expansion now requires human judgment, which is exactly the discretion the original bar
removed, and the party exercising it is typically the party who wants the second discipline. There is no
mechanical protection against a motivated reading of a wide interval. The reversal trigger below is the
only guard, and it depends on someone noticing.

**Neutral.** Three finalized ADRs (`dec-298`, `dec-300`, `dec-302`) cite the old threshold in their
Disconfirmation sections; their reversal triggers are retargeted to this decision so that no trigger
references a threshold that no longer exists.

## Disconfirmation

**Falsifier.** If, after ≥3 consults with all three disposition values observed, the reported estimate
and its interval are read by two independent people who reach opposite expansion verdicts on the same
ledger, then the demotion has replaced a badly-calibrated rule with no rule at all, and the criterion
needs a mechanical component back (Option C).

**Steelmanned runner-up.** Option B is genuinely strong, and its strength is not statistical but
political. The gate's job was never really to measure — it was to *bind the future decider*, including
when that decider is the person who authored the gate and now wants to expand. n=15 preserves that
binding at a cost the project can actually pay (~25 challenges across ≥8 tasks is perhaps two quarters of
normal pipeline activity, not a decade). Against that, an estimate-with-interval is precisely the artifact
a motivated reader can rationalize in either direction: "the interval includes 0.4, so it's fine" and
"the interval includes 0.8, so it isn't" are both available from the same data. The chosen option is
better statistics and weaker governance, and the honest framing is that this trade was made deliberately,
not that the trade does not exist.

**Reversal trigger.** Two distinct signals, either sufficient: (a) discipline #2 ships on a reported
estimate whose interval was wide enough to support the opposite verdict, and the resulting discipline is
later judged decoration — the exact outcome the gate existed to prevent, achieved through the discretion
this decision introduced; or (b) the ledger reaches ≥15 consults for a discipline, at which point the
sample supports Option B's binary rule at a defensible error rate and the governance argument for
mechanically binding the decider reasserts itself with no statistical cost.

## Prior Decision

This decision does not supersede `dec-299` (the ledger as an append-only, single-writer, `grep`-countable
disposition counter); it **re-affirms** it. Every one of the six defects was found *because* `dec-299`
made the measurement exist before the data did, and the consult explicitly endorsed
instrumentation-before-roster as "the single most important statistical property of the whole plan." The
ledger's schema, single-writer rule, append-only discipline, and column-anchored counting recipe are all
unchanged. What changes is only how the recorded numbers are *aggregated and read* — a consumer-side
revision, not a producer-side one.
