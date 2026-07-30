# Consultation Disposition Ledger

<!-- Append-only ledger of discipline-consultant challenge dispositions.
     Producer: the convener only (the systems-architect in pipeline mode; the
     orchestrator in standalone /consult mode) -- one row appended per
     challenge, at round 2, once the challenge is dispositioned. The
     consultant itself never writes this file (Decision E, dec-299)
     -- it authors only its own CONSULT_<discipline>.md fragment.
     Schema and rationale: dec-299 (Disposition counter is a
     dedicated append-only .ai-state/CONSULT_LEDGER.md, single-writer). -->

**Schema**: 11 columns, one row per dispositioned challenge (I4, `SYSTEMS_PLAN.md § Interfaces`). See Column Definitions below.

**Append new rows at the end of this ledger.** This file is append-only -- no row is ever edited or deleted after being written. If a disposition is revisited later, append a new row rather than mutating the old one; both remain part of the record.

| timestamp | task-slug | discipline | stage | challenge-id | claim | decision-at-stake | disposition | rationale-ref | model | difficulty |
|---|---|---|---|---|---|---|---|---|---|---|

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
```

Dismiss rate = second count / first count. Swap `statistician` for any other discipline key.

**Why the column anchor is load-bearing.** An unanchored literal match (`grep -F '| statistician |'`) also matches rows belonging to *other* disciplines whose free-text cells happen to contain the name -- a `decision-at-stake` reading `statistician`, for instance. That inflates the denominator and therefore *deflates* the computed dismiss rate, which biases the discipline-expansion gate toward passing. A falsifier must fail safe. Verified against a synthetic ledger in which the unanchored form returned 3 rows for a discipline that had 2; the anchored form returns 2.

The header row does not match a discipline key, because its third column holds the literal `discipline`; the separator row does not match either. This recipe depends on free-text columns (`claim`, `decision-at-stake`, `rationale-ref`) never containing an unescaped `|` -- escape any literal pipe as `\|` when writing a row, or the row will misalign under both the grep filter and any markdown renderer.

## Single Writer

The consultant never writes this file. Only the convener appends rows, at round 2, once each challenge is dispositioned (Decision E, dec-299). This removes a write race under concurrent consultant instances and matches single-owner reconciliation -- the party that adjudicates the disposition is the party that records it.
