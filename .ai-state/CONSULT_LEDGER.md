# Consultation Disposition Ledger

<!-- Append-only ledger of discipline-consultant challenge dispositions.
     Producer: the convener only (the systems-architect in pipeline mode; the
     orchestrator in standalone /consult mode) -- one row appended per
     challenge, at round 2, once the challenge is dispositioned. The
     consultant itself never writes this file (Decision E, dec-299)
     -- it authors only its own CONSULT_<discipline>.md fragment.
     Schema and rationale: dec-299 (Disposition counter is a
     dedicated append-only .ai-state/CONSULT_LEDGER.md, single-writer). -->

**Schema**: 11 columns, one row per dispositioned challenge. See Column Definitions below.

**Append new rows at the end of this ledger.** This file is append-only -- no row is ever edited or deleted after being written. If a disposition is revisited later, append a new row rather than mutating the old one; both remain part of the record.

| timestamp | task-slug | discipline | stage | challenge-id | claim | decision-at-stake | disposition | rationale-ref | model | difficulty |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-07-30T17:05:00Z | multidisciplinary-identities | statistician | architecture | CH-01 | Challenges cluster within consults, so the effective sample size of "≥10 challenges spanning ≥3 tasks" is ~5-6, not 10 | Whether the discipline-#2 gate's denominator is challenges or consults, and therefore the numeric floor | defer-with-rationale | CONSULT_SMOKE_TEST.md § Disposition Rationale | opus | standard |
| 2026-07-30T17:05:00Z | multidisciplinary-identities | statistician | architecture | CH-02 | At n=10 a true 70% dismiss rate passes the gate 35% of the time and a discipline at the 60% bar is blocked 38% of the time | Whether the "≥10 challenges" floor rises to an MDE-derived value or the gate is demoted to an estimate-with-interval | defer-with-rationale | CONSULT_SMOKE_TEST.md § Disposition Rationale | opus | standard |
| 2026-07-30T17:05:00Z | multidisciplinary-identities | statistician | architecture | CH-03 | "≥10 challenges" is a floor rather than a fixed evaluation point, so the gate is evaluated under unbounded optional stopping biased toward shipping | Whether §17.4 pre-registers the gate's evaluation point | defer-with-rationale | CONSULT_SMOKE_TEST.md § Disposition Rationale | opus | standard |
| 2026-07-30T17:05:00Z | multidisciplinary-identities | statistician | architecture | CH-04 | The 60% threshold is asserted rather than derived, though the dossier's own cost envelope supplies the error model needed to derive it | The threshold value in §17.4, and whether §14 falsifier 1 gets a number | defer-with-rationale | CONSULT_SMOKE_TEST.md § Disposition Rationale | opus | standard |
| 2026-07-30T17:05:00Z | multidisciplinary-identities | statistician | architecture | CH-05 | The gate is one-sided, so a ledger showing 0% dismissals passes a criterion whose own prose demands a non-degenerate distribution | Whether the discipline-#2 gate gains a lower bound alongside the 60% ceiling | defer-with-rationale | CONSULT_SMOKE_TEST.md § Disposition Rationale | opus | standard |
| 2026-07-30T17:05:00Z | multidisciplinary-identities | statistician | architecture | CH-06 | The Tier-3 gate reuses this statistic without naming its aggregation unit, letting one discipline's failure be masked by another's volume | Whether the Tier-3 rate is pooled across disciplines or required per discipline | defer-with-rationale | CONSULT_SMOKE_TEST.md § Disposition Rationale | opus | standard |
| 2026-07-30T17:20:00Z | multidisciplinary-identities | statistician | architecture | CH-01 | Challenges cluster within consults, so the effective sample size of "≥10 challenges spanning ≥3 tasks" is ~5-6, not 10 | Whether the discipline-#2 gate's denominator is challenges or consults, and therefore the numeric floor | switch-now | dec-304 (revises the 2026-07-30T17:05:00Z defer on this challenge; Denominator restated on the independent unit: distinct consults) | opus | standard |
| 2026-07-30T17:20:00Z | multidisciplinary-identities | statistician | architecture | CH-02 | At n=10 a true 70% dismiss rate passes the gate 35% of the time and a discipline at the 60% bar is blocked 38% of the time | Whether the "≥10 challenges" floor rises to an MDE-derived value or the gate is demoted to an estimate-with-interval | switch-now | dec-304 (revises the 2026-07-30T17:05:00Z defer on this challenge; Gate demoted to a reported estimate with a Wilson interval) | opus | standard |
| 2026-07-30T17:20:00Z | multidisciplinary-identities | statistician | architecture | CH-03 | "≥10 challenges" is a floor rather than a fixed evaluation point, so the gate is evaluated under unbounded optional stopping biased toward shipping | Whether §17.4 pre-registers the gate's evaluation point | switch-now | dec-304 (revises the 2026-07-30T17:05:00Z defer on this challenge; Dissolved by the demotion: nothing decided automatically, so no error rate to inflate) | opus | standard |
| 2026-07-30T17:20:00Z | multidisciplinary-identities | statistician | architecture | CH-04 | The 60% threshold is asserted rather than derived, though the dossier's own cost envelope supplies the error model needed to derive it | The threshold value in §17.4, and whether §14 falsifier 1 gets a number | switch-now | dec-304 (revises the 2026-07-30T17:05:00Z defer on this challenge; Dissolved by the demotion: no threshold remains; §14 falsifier 1 restated as a judgment call) | opus | standard |
| 2026-07-30T17:20:00Z | multidisciplinary-identities | statistician | architecture | CH-05 | The gate is one-sided, so a ledger showing 0% dismissals passes a criterion whose own prose demands a non-degenerate distribution | Whether the discipline-#2 gate gains a lower bound alongside the 60% ceiling | switch-now | dec-304 (revises the 2026-07-30T17:05:00Z defer on this challenge; Two-sided standing condition added: all three disposition values must have been observed) | opus | standard |
| 2026-07-30T17:20:00Z | multidisciplinary-identities | statistician | architecture | CH-06 | The Tier-3 gate reuses this statistic without naming its aggregation unit, letting one discipline's failure be masked by another's volume | Whether the Tier-3 rate is pooled across disciplines or required per discipline | switch-now | dec-304 (revises the 2026-07-30T17:05:00Z defer on this challenge; Tier-3 criterion stated per discipline, not pooled) | opus | standard |

## Column Definitions

- **timestamp** -- ISO 8601 UTC timestamp of when the row was appended (round 2, at disposition time), e.g. `2026-07-30T10:05:00Z`.
- **task-slug** -- the task slug of the pipeline that convened this consult; matches the `.ai-work/<task-slug>/` directory the consult ran under.
- **discipline** -- the registry discipline key (e.g. `statistician`), from `skills/multi-perspective-analysis/references/discipline-registry.md`.
- **stage** -- the pipeline stage that convened the consult (e.g. `research`, `architecture`), matching one of the registry row's `attaches-to` values.
- **challenge-id** -- the `### CH-NN` identifier from the consultant's `CONSULT_<discipline>.md` fragment.
- **claim** -- the one-line falsifiable claim from that challenge, verbatim or tightly summarized. Escape any literal `|` in free text as `\|` -- see Falsifier below for why this matters.
- **decision-at-stake** -- the decision the claim would change, copied from the challenge's own field.
- **disposition** -- exactly one of `switch-now` | `defer-with-rationale` | `dismiss-with-rationale`.
- **rationale-ref** -- pointer to where the disposition's rationale lives: an ADR id (`dec-NNN` or, pre-finalize, `dec-draft-<hash>`) or a plan section (e.g. `SYSTEMS_PLAN.md § Risk Assessment`).
- **model** -- the model tier that ran the consult (e.g. `sonnet`, `opus`).
- **difficulty** -- the `difficulty-hint` value used for this consult (`routine` | `standard` | `high-stakes`).

## Falsifier

Dismiss rate per discipline must be derivable with a `grep` and a count -- no parser. Rows are pipe-delimited with single-space padding and `discipline` is the third column, so the filter is anchored to that column *position* rather than matching the name anywhere in the row:

```
# total dispositioned challenges for a discipline
grep -E '^\|[^|]*\|[^|]*\| *statistician *\|' .ai-state/CONSULT_LEDGER.md | wc -l

# dismissed challenges for that discipline
grep -E '^\|[^|]*\|[^|]*\| *statistician *\|' .ai-state/CONSULT_LEDGER.md | grep -c 'dismiss-with-rationale'

# INDEPENDENT observations for that discipline -- distinct consults, i.e. distinct task-slugs.
# This is the denominator the expansion criterion uses; the challenge count above is NOT.
grep -E '^\|[^|]*\|[^|]*\| *statistician *\|' .ai-state/CONSULT_LEDGER.md | cut -d'|' -f3 | sort -u | wc -l

# which disposition values have been observed at all (the two-sided standing condition)
grep -E '^\|[^|]*\|[^|]*\| *statistician *\|' .ai-state/CONSULT_LEDGER.md \
  | grep -oE 'switch-now|defer-with-rationale|dismiss-with-rationale' | sort -u
```

Swap `statistician` for any other discipline key.

**Which denominator to use.** For the raw dismissed/total ratio, the first two counts suffice. For the
**discipline-expansion criterion**, the denominator is the *consult* count (third command), not the
challenge count: challenges raised within one consult share a consultant, a draft, and a convener, so
they are a cluster rather than independent observations. Counting challenge rows overstates the
evidence by roughly a factor of two at typical cluster sizes. The criterion also requires that all
three disposition values have been observed (fourth command) before the ratio is read as evidence at
all — a ledger with no dismissals is equally consistent with a well-calibrated router and with a
convener who never adjudicates. Both conditions and their derivation:
`docs/multidisciplinary-identities-evidence.md` §17.4 and §17.11.

**Why the column anchor is load-bearing.** An unanchored literal match (`grep -F '| statistician |'`) also matches rows belonging to *other* disciplines whose free-text cells happen to contain the name -- a `decision-at-stake` reading `statistician`, for instance. That inflates the denominator and therefore *deflates* the computed dismiss rate, which biases the discipline-expansion gate toward passing. A falsifier must fail safe. Verified against a synthetic ledger in which the unanchored form returned 3 rows for a discipline that had 2; the anchored form returns 2.

The header row does not match a discipline key, because its third column holds the literal `discipline`; the separator row does not match either. This recipe depends on free-text columns (`claim`, `decision-at-stake`, `rationale-ref`) never containing an unescaped `|` -- escape any literal pipe as `\|` when writing a row, or the row will misalign under both the grep filter and any markdown renderer.

## Single Writer

The consultant never writes this file. Only the convener appends rows, at round 2, once each challenge is dispositioned (Decision E, dec-299). This removes a write race under concurrent consultant instances and matches single-owner reconciliation -- the party that adjudicates the disposition is the party that records it.
