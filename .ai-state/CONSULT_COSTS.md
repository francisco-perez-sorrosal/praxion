# Consultation Cost Series

<!-- Append-only per-consult cost observations. Producer: the convener only (the
     systems-architect in pipeline mode; the orchestrator in standalone /consult
     mode) -- one row per consult spawn, written at Round 2 alongside that
     consult's CONSULT_LEDGER.md rows. The consultant never writes this file.
     Sibling of .ai-state/CONSULT_LEDGER.md, deliberately separate: the ledger's
     grain is one row per dispositioned challenge, and cost is a property of the
     consult, not of the challenge. Schema and rationale: dec-308. -->

**Schema**: 8 columns, one row per consult spawn. See Column Definitions below.

**Series begins**: 2026-07-31T01:00:00Z

Consults timestamped before that instant are exempt from the coverage gate: their
token figures were never recorded and are unrecoverable. One pre-boundary row is
seeded below because its figure survived in the evidence dossier.

**Append new rows as the last row of the data table directly below (the `| timestamp | ... |` table
that ends just before the `## Column Definitions` section) -- never after that section.** This file
is append-only -- no row is ever edited or deleted. A consult that runs a second time (a Round-3
loop-back re-spawn) appends a *second* row for the same triple rather than mutating the first;
aggregation sums rows per triple.

| timestamp | task-slug | discipline | stage | tokens | model | difficulty | notes |
|---|---|---|---|---|---|---|---|
| 2026-07-30T17:20:00Z | multidisciplinary-identities | statistician | architecture | 101030 | opus | standard | Backfilled from docs/multidisciplinary-identities-evidence.md §17.12; pre-boundary seed -- the only prior consult whose figure survived in a durable artifact |
| 2026-07-31T02:30:00Z | multidisciplinary-identities-wave2 | statistician | architecture | 161321 | opus | high-stakes | First consult recorded under the series (post-boundary). Convened to challenge the convener's own roster verdict; seven challenges, six switch-now, one defer, zero dismissed. |
| 2026-07-31T06:10:00Z | td-081-sealed-prior | statistician | architecture | 202830 | opus | standard | Second consult of the series and the first sealed one. Convened against this task's own SYSTEMS_PLAN.md as AC-02. 8 priors sealed at cd12803 before the spawn; 7 challenges, 6 switch-now, 1 defer, 0 dismissed. |

## Column Definitions

- **timestamp** -- ISO 8601 UTC, `YYYY-MM-DDTHH:MM:SSZ`, of the disposition at which
  the row was appended. Matches the corresponding `CONSULT_LEDGER.md` rows' timestamp.
- **task-slug**, **discipline**, **stage** -- the join key to `.ai-state/CONSULT_LEDGER.md`.
  The **triple** is the consult's identity; `(task-slug, discipline)` alone is not
  unique, because one discipline may attach at both `research` and `architecture`
  within a single task.
- **tokens** -- the aggregate subagent token count the harness surfaces to the convener
  at that consult's completion. A positive integer, digits only, no separators. This is
  a **raw observation**, never a derived or price-weighted figure.
- **model** -- the model tier that actually ran the consult (`opus` / `sonnet` / `haiku`).
  Load-bearing: tokens without a tier are not re-priceable, and an all-`opus` numerator
  over a mixed-tier denominator is exactly the bias `dec-306` corrected. Must equal the
  `model` value on this consult's ledger rows.
- **difficulty** -- the `difficulty-hint` used (`routine` / `standard` / `high-stakes`).
  AC15 carries a different envelope per class, so an observation without this field
  cannot be assigned to an envelope. Must equal the `difficulty` value on this consult's
  ledger rows.
- **notes** -- free text: provenance, loop-back increments, anything a later reader needs.
  Escape any literal `|` as `\|`, for the same reason the ledger does.

**Why no `cost_usd` column.** A dollar figure is a point-in-time claim that decays with
every price change, and writing one would require the convener to apply a price table --
injecting a derivation into a file of raw observations. `tokens` + `model` is durable and
re-priceable; re-pricing the whole series later is one `awk` pass.

**What is not recorded here.** Spawns that never became consults (a probe blocked at
discipline resolution) produce no ledger rows and no cost row -- folding a resolution
failure into the consult-cost distribution would contaminate it. And this file records
the consult side only: the *denominator* of AC15's ratio (non-consult pipeline agent
cost) is not knowable at this writing seam and has no series.

## Reading the series

Column-anchored on `discipline` at position 3, identical to
`.ai-state/CONSULT_LEDGER.md` § Falsifier -- and for the identical reason: an unanchored
match also catches rows whose free text happens to contain the name.

```
# raw token series for a discipline
grep -E '^\|[^|]*\|[^|]*\| *statistician *\|' .ai-state/CONSULT_COSTS.md \
  | cut -d'|' -f6 | tr -d ' '

# number of observations for a discipline
grep -E '^\|[^|]*\|[^|]*\| *statistician *\|' .ai-state/CONSULT_COSTS.md | wc -l

# price-weighted (opus-equivalent) total across the whole series
grep -E '^\| *2[0-9]{3}-' .ai-state/CONSULT_COSTS.md \
  | awk -F'|' '{gsub(/ /,"",$6); gsub(/ /,"",$7);
      w=($7=="opus")?1.0:($7=="sonnet")?0.2:($7=="haiku")?0.07:1.0; s+=$6*w} END {print s}'

# observations in the high-stakes envelope (the class §17.12 records as unmeasured)
grep -E '^\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\| *high-stakes *\|' \
  .ai-state/CONSULT_COSTS.md | wc -l
```

`cut -d'|' -f6` is the `tokens` cell and `-f7` the `model` cell only while the schema
has these 8 columns in this order; a schema change must restate these recipes.

## Single Writer

Only the convener appends, at Round 2, at the same moment it appends this consult's
`CONSULT_LEDGER.md` rows. Two files, one writer, one seam -- which is what makes the
cross-file coverage check in `fitness/tests/test_discipline_registry_invariants.py`
possible, and what makes an omission fail loudly instead of silently.
