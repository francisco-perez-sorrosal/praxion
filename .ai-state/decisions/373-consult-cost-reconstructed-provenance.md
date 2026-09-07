---
id: dec-373
title: The cost series admits a second, labelled provenance class — a transcript-reconstructed figure — rather than a non-numeric "unrecorded" sentinel
status: accepted
category: behavioral
date: 2026-09-06
summary: CONSULT_COSTS.md's tokens column widens from "raw observation only" to "raw observation, or a RECONSTRUCTED figure carrying its formula, its calibration and its residual direction in notes". The rust-first-class/evidence-appraiser row is recorded this way; the gate's positive-integer requirement is untouched.
tags: [consult-ledger, cost, instrumentation, provenance, discipline-consultant, fitness]
made_by: agent
agent_type: systems-architect
branch: worktree-praxion-health
pipeline_tier: full
supersedes_in_part: [dec-308]
dissent: At n=6 the series' whole value is that every figure is the same raw quantity. Admitting a second provenance class for one row changes the series' character for a 0.1% accuracy gain in a figure no live threshold depends on, and it does so by widening a definition rather than by admitting an omission. A reader who greps the series and does not read notes now sums two different statistics.
affected_files:
  - .ai-state/CONSULT_COSTS.md
  - fitness/tests/test_discipline_registry_invariants.py
affected_reqs: [REQ-06]
---

## Context

The consult `('rust-first-class', 'evidence-appraiser', 'architecture')` at
`2026-08-30T19:29:00Z` carries eight `CONSULT_LEDGER.md` rows (all `switch-now`) and **no**
`CONSULT_COSTS.md` row, so `check_every_post_boundary_consult_has_a_cost_row` fails with
`no CONSULT_COSTS.md row for post-boundary consult`. The gate requires a positive integer
`tokens` cell; `""`, `"n/a"` and `"0"` are all rejected by construction.

**Why no figure was recorded.** The consult was launched as an *async* subagent. The
session transcript records the spawn as
`{"isAsync": true, "status": "async_launched", "agentId": "a78b9d5b0d15db26a", "resolvedModel": "claude-opus-5"}`
and nothing else — an async launch surfaces no completion summary to the convener, so the
"aggregate the harness surfaces at completion" that `dec-308` defines as the observation was
never displayed. This is a *mechanism* gap, not convener negligence: the writing seam
`dec-308` chose assumes a synchronous return.

**What is recoverable.** Claude Code persists a per-subagent transcript at
`~/.claude/projects/<project>/<session-id>/subagents/agent-<agent-id>.jsonl`, carrying
per-assistant-message `usage`. Summing those fields does *not* reproduce the recorded
figures — but one derivation does, to within 0.2%:

> `tokens ≈ (final assistant message's input_tokens + cache_read_input_tokens + cache_creation_input_tokens) + that message's output_tokens`

Calibrated against the two nearest recorded rows, both independent of this decision:

| consult | recorded | reconstructed | residual |
|---|---|---|---|
| `sidecar-placement / data-structure-specialist` | 156,321 | 156,232 | −89 (−0.06%) |
| `adr-living-view / data-structure-specialist` | 167,070 | 166,789 | −281 (−0.17%) |

The residual is small and **consistently negative** — the reconstruction is a slight
undercount of what the harness displayed, in both cases. Applying the same derivation to
`agent-a78b9d5b0d15db26a.jsonl` (44 assistant messages, `claude-opus-5`) gives **171,245**.

## Decision

**Widen the `tokens` column's provenance to two labelled classes, and record the missing row
as the second class.** Specifically:

1. `.ai-state/CONSULT_COSTS.md` § Column Definitions' `tokens` entry gains a second sentence:
   the figure is the harness-surfaced aggregate **or**, when the harness never surfaced one
   (an async spawn), a transcript-reconstructed figure whose `notes` cell begins with the
   literal marker `RECONSTRUCTED:` and states the derivation, its calibration points and the
   residual direction. The "never a derived or price-weighted figure" clause narrows to
   "never a *price-weighted* figure" — the `cost_usd` prohibition `dec-308` actually argued
   for is untouched.
2. The `RECONSTRUCTED:` prefix follows the file's own established `notes`-prefix convention
   (`UNSEALED:` on the `adr-living-view` row, `Backfilled from …` on the pre-boundary seed),
   so it is greppable and an analyst can exclude the class in one pass. No new column.
3. The missing row is appended with `tokens = 171245`, `model = opus`, `difficulty = standard`
   (both must equal the ledger's values, which the gate checks), `timestamp =
   2026-08-30T19:29:00Z` (the join key to the ledger — the disposition instant, not a
   fabricated observation time), and a `RECONSTRUCTED:` note carrying the formula, both
   calibration points with their residuals, the transcript path, and the async-spawn reason
   the harness surfaced nothing.
4. **The gate is not weakened.** `tokens` stays a positive integer; no sentinel value is
   admitted; `check_every_post_boundary_consult_has_a_cost_row` is unchanged. The only
   fitness-side addition is optional and cheap: a check that a `RECONSTRUCTED:`-prefixed
   `notes` cell is non-trivial, so the marker cannot become a bare label.

**The pre-existing definition was already inaccurate.** The series' first row is annotated
`Backfilled from docs/multidisciplinary-identities-evidence.md §17.12` — not a live harness
observation either. This decision corrects a standing mismatch between the column definition
and the file's own contents as much as it enables a new case.

## Considered Options

### A — Record `tokens` as `unrecorded` and narrow the gate to accept it

Pros: keeps the series a single, pure statistic; makes the omission permanently visible; is
the most literally honest thing to write when the defined observation does not exist. Cons:
requires weakening the gate's positive-integer check into a sentinel-aware branch, which
creates a reusable escape hatch — the next convener who does not want to look up a figure can
write `unrecorded` and the gate agrees. It also discards a recoverable figure accurate to
0.2%, which is real information.

### B (chosen) — Reconstructed figure, labelled, gate untouched

Pros: preserves the strongest property (the gate's numeric requirement); records real
information; the label lets any analyst exclude the class; the calibration is stated so a
reader can judge the claim rather than trust it. Cons: the series now mixes two derivations
(see `dissent:`); requires narrowing `dec-308`'s "raw observation" clause.

### C — Leave the row absent and add the triple to a gate skip-list

Rejected outright. `dec-310` § Reversal trigger (ii) names "the gate goes red and the proposed
remedy is a skip-list entry" as grounds for reopening that whole mechanism. The same objection
applies here. A skip-list makes the omission invisible, which is the inverse of what both
files exist to do.

## Consequences

**Positive.** The cost gate goes green on a true record rather than an exemption. The series
gains a sixth post-boundary observation with a bounded, stated error. The `RECONSTRUCTED:`
convention gives every future async-spawned consult a defined honest path, so the same gap
does not recur as a judgment call. The reconstruction formula is now documented and
calibrated, which is itself a reusable artifact.

**Negative.** Anyone computing a statistic over the `tokens` column without reading `notes`
sums two slightly different quantities — see `dissent:`. The `dec-308` "raw observations, not
derivations" framing is narrowed, and that framing was load-bearing for the `cost_usd`
argument (which survives intact, but a careless reader may not notice the narrowing was
scoped). One more convention for a convener to remember.

## Prior Decision

`dec-308` established `.ai-state/CONSULT_COSTS.md` as an append-only, single-writer,
one-row-per-consult side-record and argued (body, "The field set records raw observations,
not derivations") that `tokens` + `model` are raw while `cost_usd` would inject a decaying
derivation. **This decision narrows only the "raw" clause of that argument, and only for the
case where the harness surfaced nothing.** Everything else in `dec-308` stands: the file's
location, grain, writer, append-only discipline, the `model` and `difficulty` columns and
their load-bearing rationale, the cross-file gate, and the `cost_usd` prohibition — which is
the derivation `dec-308` was actually defending against, and which this decision does not
touch. `dec-308` accordingly stays `accepted` and gains
`superseded_in_part_by: [dec-373]`.

## Disconfirmation

**Falsifier.** A third calibration point where the reconstruction diverges materially — say
>2% — from the recorded figure. Two points establish a pattern; they do not establish a law,
and both happen to be `data-structure-specialist` consults of similar shape. If a future
synchronous consult's displayed figure disagrees with its own reconstruction by more than a
percent, the formula is coincidental and the `RECONSTRUCTED:` class should be retired in
favour of Option A.

**Steelmanned runner-up (Option A).** The series exists to make an omission *loud*. A
reconstructed figure is a quiet repair: the gate goes green, the row looks like its five
siblings, and the fact that Praxion's async-spawn path silently destroys cost observability
survives only as prose inside a `notes` cell nobody greps. `unrecorded` would keep that defect
in the numerator forever, visible in every reading of the series, and would price the async
mechanism gap honestly instead of papering it. The strongest version of this objection is that
Option B optimises for a green gate and Option A optimises for a true one.

**Reversal trigger.** Any of three: (i) the falsifier above — a third point diverging >2%;
(ii) a second `RECONSTRUCTED:` row appears, meaning the async gap is recurrent rather than
a one-off, at which point the right fix is to make the async path record its own cost, not to
keep reconstructing; (iii) any artifact cites a cost ratio computed over this column without
stratifying on provenance, which would mean the label failed at its one job.
