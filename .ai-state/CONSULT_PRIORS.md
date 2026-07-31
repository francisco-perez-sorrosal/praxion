# Consultation Prior Register

<!-- Append-only. Producer: the convener only -- the party that spawns the
     consultant. Two tables, two moments: `## Sealed Priors` is written BEFORE
     the spawn and committed before the spawn; `## Challenge Classification` is
     written at Round 2 alongside that consult's CONSULT_LEDGER.md rows. The
     consultant never writes this file and never READS it -- it is the
     convener's compressed statement of concerns about the very draft round-0
     isolation withholds. Sibling of .ai-state/CONSULT_LEDGER.md and
     .ai-state/CONSULT_COSTS.md, joined on the same (task-slug, discipline,
     stage) triple. Schema and rationale: dec-draft-2c51b2f6. -->

**Schema**: two tables. `## Sealed Priors` is 7 columns, one row per prior concern.
`## Challenge Classification` is 8 columns, one row per dispositioned challenge.

**Series begins**: 2026-07-31T03:00:00Z

Consults timestamped before that instant are exempt: no consult before it was sealed,
and none can be retro-classified without inventing the very record this file exists to
fix. The exemption is by construction -- there is no skip-list.

**Append new rows as the last row of the table they belong to** (the two `| ... |` tables
below, each ending just before the next `##` heading) -- never after a prose section.
This file is append-only -- no row is ever edited or deleted. A Round-3 loop-back
re-spawn appends further classification rows for the same triple rather than mutating
the first.

## Sealed Priors

| timestamp | task-slug | discipline | stage | prior-id | source | concern |
|---|---|---|---|---|---|---|
| 2026-07-31T05:25:00Z | td-081-sealed-prior | statistician | architecture | P-01 | lens | No minimum detectable effect. The plan never states what novelty rate, at what n, would confirm or falsify dec-306's criterion. 'Not yet informative' is defined only for n=1; nothing says when it becomes informative for THIS statistic, so the criterion inherits the asserted-threshold defect dec-304 corrected for the dismiss rate. |
| 2026-07-31T05:25:00Z | td-081-sealed-prior | statistician | architecture | P-02 | lens | The two published recipes disagree with the mandated denominator. 'Reading the series' computes the rate over CHALLENGES; 'Named consumer' mandates denomination in DISTINCT CONSULTS per the clustering caveat. Those are different statistics, and the file supplies the grep for the one it forbids. |
| 2026-07-31T05:25:00Z | td-081-sealed-prior | statistician | architecture | P-03 | lens | The matched-versus-novel classification is an unsealed subjective judgment, made by an interested party at Round 2 with full knowledge of the challenges. The seal constrains the priors only. G4 checks that a matched-prior-id exists, not that the match is defensible, and no inter-rater or second-reader check exists anywhere in the design. |
| 2026-07-31T05:25:00Z | td-081-sealed-prior | statistician | architecture | P-04 | lens | Lens-pass effort is an uncontrolled confounder. A rushed lens pass yields fewer priors and a higher novelty rate, flattering the consultant -- the same direction of bias the plan's Q1 identifies for un-primed priors, reintroduced through effort rather than through priming, and invisible to every check. |
| 2026-07-31T05:25:00Z | td-081-sealed-prior | statistician | architecture | P-05 | lens | Convening is self-selected, not random. A consult is convened when the convener already suspects a problem, which correlates with holding priors, so sampled consults are not exchangeable with the population dec-306's criterion generalises over. |
| 2026-07-31T05:25:00Z | td-081-sealed-prior | statistician | architecture | P-06 | lens | No noise floor. The run-to-run spread of the novelty rate is uncharacterised, so a difference between two disciplines' rates -- or between two consults -- cannot be called observed rather than estimated. |
| 2026-07-31T05:25:00Z | td-081-sealed-prior | statistician | architecture | P-07 | lens | The reading point is unbounded. 'Any ADR re-opening the criterion' permits reading at will, which is optional stopping. dec-304 dissolved that for the dismiss rate by demoting it to an estimate; the plan does not state whether the same demotion governs this statistic. |
| 2026-07-31T05:25:00Z | td-081-sealed-prior | statistician | architecture | P-08 | lens | The multiple-comparisons family is undeclared. The rate can be computed per discipline, pooled, or per stage, and nothing fixes the family before looking. |

## Challenge Classification

| timestamp | task-slug | discipline | stage | challenge-id | classification | matched-prior-id | seal-witness |
|---|---|---|---|---|---|---|---|

## Column Definitions

**Table 1 — `## Sealed Priors`** (7 columns, written before the spawn):

| Column | Definition |
|---|---|
| `timestamp` | ISO 8601 UTC of the seal write (pre-spawn). Must be **earlier** than this consult's ledger rows |
| `task-slug` / `discipline` / `stage` | The join key to `CONSULT_LEDGER.md` and `CONSULT_COSTS.md`. The **triple** is the consult's identity |
| `prior-id` | `P-01`, `P-02`, … unique within the triple. Reserved value **`NONE`** — the explicit empty declaration; when present it must be the only row for the triple |
| `source` | `lens` (surfaced by the lens pass over the `binds-to` skill) \| `prior` (the convener already held it before the pass). Recording provenance costs one enum column and lets a later analyst compute both the literal lens-arm estimand and the wider "would have caught it anyway" one from the same file |
| `concern` | One line, specific enough that a reader can judge whether a given challenge is the same concern: name the element of the draft and the property at issue, not the topic. Escape any literal `\|`. Must be non-empty and non-placeholder |

**Table 2 — `## Challenge Classification`** (8 columns, written at Round 2):

| Column | Definition |
|---|---|
| `timestamp` | ISO 8601 UTC of the disposition; matches this consult's `CONSULT_LEDGER.md` rows |
| `task-slug` / `discipline` / `stage` | Same triple |
| `challenge-id` | The `### CH-NN` id from the consultant's fragment; the same value the ledger row carries |
| `classification` | `novel` \| `matched`. `matched` means the sealed list already contained this concern |
| `matched-prior-id` | The `P-NN` when `matched`; **empty** when `novel`. Must resolve to a `Sealed Priors` row of the same triple |
| `seal-witness` | The consultant's `**Round-0 HEAD:**` sha, transcribed verbatim. Denormalized across the triple's rows exactly as `model`/`difficulty` are denormalized in the cost series, and checked for agreement for the same reason |

The two enums are chosen **disjoint** (`{lens, prior}` vs `{novel, matched}`) so a
discipline-anchored `grep` can tell the tables apart with a single cell match and no parser.

## Reading the series

The recipes below are column-anchored on `discipline` at position 3, identical in form
to `.ai-state/CONSULT_LEDGER.md` § Falsifier and for the identical reason: an unanchored
match also catches rows whose free text happens to contain the name.

```
# challenges classified for a discipline (denominator)
grep -E '^\|[^|]*\|[^|]*\| *statistician *\|' .ai-state/CONSULT_PRIORS.md \
  | grep -cE '\| *(novel|matched) *\|'

# novel challenges (numerator)
grep -E '^\|[^|]*\|[^|]*\| *statistician *\|' .ai-state/CONSULT_PRIORS.md \
  | grep -c '| novel |'

# distinct sealed consults for a discipline (the independent unit -- challenges
# within one consult cluster, exactly as CONSULT_LEDGER.md § Falsifier records)
grep -E '^\|[^|]*\|[^|]*\| *statistician *\|' .ai-state/CONSULT_PRIORS.md \
  | grep -E '\| *(lens|prior) *\|' | cut -d'|' -f3,5 | sort -u | wc -l

# priors sealed but never matched by any challenge (the lens's own miss rate is
# NOT computable from this; a prior nobody challenged may simply have been fixed
# before the spawn -- see § What is not recorded here)
```

## Named consumer

The novelty rate computed from this file **is** the estimand of the lens-versus-consultant
falsifier recorded in `dec-306`. **It estimates framing + standing jointly, never standing
alone** — the sealed arm holds knowledge fixed and the second party out, but it also holds
the *convener's own* framing in place of the discipline's, so the two effects are confounded
by construction. Isolating them needs a third arm (a generic challenger holding the same
skill), which is named and not built. Any ADR that re-opens, re-affirms, or supersedes that
criterion must cite the rate computed from this file, denominated in **distinct consults**
per the ledger's clustering caveat, and must state the joint quantity rather than the narrow
one. Until this file carries observations from more than one consult the correct reading is
**not yet informative** — one observation licenses no verdict, exactly as the disposition-rate
criterion already records.

## What is not recorded here

Four scope limits, so the file is never read as more instrumented than it is:

1. Consults **not convened** after a lens pass leave no row and no trace. The ordering
   constraint (decide → seal → spawn) is the only mitigation; it is a convention, not a gate.
2. A sealed prior that no challenge matched is **not** evidence the lens was wrong — the
   convener may have fixed the draft before spawning, which is the encouraged behaviour.
3. The classification is the convener's judgement. The gate checks that it is *present,
   well-formed and resolvable*, never that it is *right*. Its correction mechanism is that
   a stranger can read the prior and the challenge and disagree.
4. No consult before the series boundary is classified, and none will be retro-classified.

## Single Writer

The convener only, at two moments; the consultant never writes it and never reads it.
