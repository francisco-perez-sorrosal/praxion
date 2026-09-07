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
| 2026-07-31T19:33:43Z | verify-multidisciplinary | statistician | verification | 197631 | opus | high-stakes | Third consult of the series and the second sealed one. Convened against this verification's OWN report rather than against the initiative. 7 priors sealed at 37df0f3 before the spawn; 9 challenges, 9 switch-now, 0 dismissed. Spawn prompt enumerated ZERO attack areas, against 7 for the prior consult -- a second point on the series' largest uncontrolled covariate. |
| 2026-08-31T07:45:00Z | adr-living-view | data-structure-specialist | architecture | 167070 | opus | standard | First consult of the data-structure-specialist discipline. UNSEALED: the convener spawned without writing Sealed Priors rows (decide-seal-spawn missed; recorded honestly rather than backdated — all 8 classifications are 'novel' by construction and the seal-witness column carries the consultant's Round-0 HEAD, not a pre-spawn seal commit). 8 challenges, 8 switch-now (CH-08's registry half deferred to a td row), 0 dismissed. Spawn prompt enumerated 5 attack areas. CH-01 independently re-verified on disk by the convener before disposition. |
| 2026-09-02T08:11:24Z | sidecar-placement | data-structure-specialist | architecture | 156321 | opus | standard | First consult of the data-structure-specialist discipline on this task. 8 priors sealed at 41903c1 before the spawn; 7 challenges, 7 switch-now, 0 dismissed. Spawn prompt enumerated the 7 load-bearing representations as attack areas. Round-0 corpus read in isolation; seal witness 41903c1. |
| 2026-08-30T19:29:00Z | rust-first-class | evidence-appraiser | architecture | 171245 | opus | standard | RECONSTRUCTED: tokens = final assistant message's (input_tokens + cache_read_input_tokens + cache_creation_input_tokens + output_tokens) from ~/.claude/projects/-Users-fperez-dev-praxion/dee467d0-eb81-475a-9974-e09ee647921b/subagents/agent-a78b9d5b0d15db26a.jsonl. Calibration: sidecar-placement/data-structure-specialist recorded 156321 vs reconstructed 156232 (-0.06%); adr-living-view/data-structure-specialist recorded 167070 vs reconstructed 166789 (-0.17%) -- a consistent undercount. Nothing was harness-surfaced because the consult was spawned async (status: async_launched) with no completion summary displayed to the convener. UNSEALED: no Sealed Priors rows existed before the 2026-08-30T19:20:45Z spawn; tombstone recorded post-hoc by the praxion-health pass. |

## Column Definitions

- **timestamp** -- ISO 8601 UTC, `YYYY-MM-DDTHH:MM:SSZ`, of the disposition at which
  the row was appended. Matches the corresponding `CONSULT_LEDGER.md` rows' timestamp.
- **task-slug**, **discipline**, **stage** -- the join key to `.ai-state/CONSULT_LEDGER.md`.
  The **triple** is the consult's identity; `(task-slug, discipline)` alone is not
  unique, because one discipline may attach at both `research` and `architecture`
  within a single task.
- **tokens** -- the aggregate subagent token count the harness surfaces to the convener
  at that consult's completion, **or**, when an async spawn surfaced nothing, a
  transcript-reconstructed figure whose `notes` cell begins with the literal marker
  `RECONSTRUCTED:` and states the derivation, its calibration points and the residual
  direction. A positive integer, digits only, no separators. Never a **price-weighted**
  figure (dec-373 narrows this from "never derived").
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

## Named consumer

Required by the gate-liveness clause that a computed value must have a named reader — the clause this
file's own wave authored, and which it did not itself satisfy until now.

The token series here **is** the numerator of the consult cost-ratio recorded in
`docs/multidisciplinary-identities-evidence.md` § 17.12. Any artifact that states a consult's cost, a
cost ratio, or a break-even consult count — an ADR, the evidence dossier, a roadmap, an evaluation —
must cite the rows in this file rather than an in-session recollection, and must carry two caveats with
the figure: it is **hand-recorded** from what the harness surfaced at completion (the residual `dec-308`
accepted explicitly), and it instruments the **numerator only**. The denominator — non-consult
pipeline-agent cost — is not knowable at this writing seam and has no series, which is why every
threshold derived from these figures is asserted rather than derived.

`§ 17.12` previously asserted that *"nothing is accumulating this series"* while this file held three
rows. That is the exact drift this section exists to prevent: a human-authored claim contradicting a
gate's own output, indefinitely, with nothing to surface the mismatch.

## Single Writer

Only the convener appends, at Round 2, at the same moment it appends this consult's
`CONSULT_LEDGER.md` rows. Two files, one writer, one seam -- which is what makes the
cross-file coverage check in `fitness/tests/test_discipline_registry_invariants.py`
possible, and what makes an omission fail loudly instead of silently.
