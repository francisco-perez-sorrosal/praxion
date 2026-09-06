# Consultation Prior Register

<!-- Append-only. Producer: the convener only -- the party that spawns the
     consultant. Two tables, two moments: `## Sealed Priors` is written BEFORE
     the spawn and committed before the spawn; `## Challenge Classification` is
     written at Round 2 alongside that consult's CONSULT_LEDGER.md rows. The
     consultant never writes this file and never READS it -- it is the
     convener's compressed statement of concerns about the very draft round-0
     isolation withholds. Sibling of .ai-state/CONSULT_LEDGER.md and
     .ai-state/CONSULT_COSTS.md, joined on the same (task-slug, discipline,
     stage) triple. Schema and rationale: dec-310. -->

**Schema**: two tables. `## Sealed Priors` is 7 columns, one row per prior concern.
`## Challenge Classification` is 9 columns, one row per dispositioned challenge.

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
| 2026-07-31T19:12:50Z | verify-multidisciplinary | statistician | verification | P-01 | lens | Clause 'is the sample or run count adequate to detect the effect being claimed' fails at Section 4's 'all 17 checks bite, zero uncanaried': that is a NEGATIVE claim from exactly one neutering pass per check, and no minimum detectable effect was declared for what an uncanaried check would look like, so the pass has unstated power. |
| 2026-07-31T19:12:50Z | verify-multidisciplinary | statistician | verification | P-02 | lens | Clause 'was that asked before collection rather than after' fails at Section 1 'what independence bought': three corrections are reported as the yield of lens independence with no denominator -- the number of corrections MISSED is unmeasured, n=1 spawn per lens, and between-spawn variance is uncharacterised, so the yield cannot be called observed. |
| 2026-07-31T19:12:50Z | verify-multidisciplinary | statistician | verification | P-03 | lens | Clause 'is multiple-comparisons exposure across the reported set accounted for' fails at the '8 FAIL, 15 WARN' headline: eight lenses each scanned an unbounded surface (D6's charter is literally 'every comparison in this initiative'), the comparison family was never declared before looking, and the report neither corrects for multiplicity nor states why no correction applies. |
| 2026-07-31T19:12:50Z | verify-multidisciplinary | statistician | verification | P-04 | lens | Clause 'is any trend claim exposed to confounding' fails at Section 3 W15: 38 challenges are pooled across 6 consults, 2 disciplines and 2 stages to assert the evidence is understated '~3x', but challenges cluster within a consult -- the exact clustering caveat dec-304 and this file both mandate -- so 38 is not 38 independent observations and the multiplier is not licensed. |
| 2026-07-31T19:12:50Z | verify-multidisciplinary | statistician | verification | P-05 | lens | Clause 'is any trend claim exposed to Simpson's-paradox reversal' fails at Section 2 FAIL-6: the 51.2% dedup_key conformance is pooled over the whole td-NNN history while the non-conformance is time-stratified with a reported boundary at td-073, so a pooled rate conflates a possibly-conforming recent regime with a non-conforming older one and was never stratified. |
| 2026-07-31T19:12:50Z | verify-multidisciplinary | statistician | verification | P-06 | lens | Clause 'is a tolerance band derived from an error model or merely asserted' fails at the FAIL/WARN/PASS verdict scheme itself: no rule separates FAIL from WARN, the boundary is applied inconsistently across lenses (D5 returned 0 FAIL for defects comparable to D2's FAILs), and the report's own gate therefore has exactly the asserted-threshold defect it charges others with. |
| 2026-07-31T19:12:50Z | verify-multidisciplinary | statistician | verification | P-07 | lens | Clause 'was the stopping rule fixed in advance of looking' fails at Sections 1-2: the set of lens claims re-derived by the orchestrator was chosen AFTER reading the returns, on salience, so dramatic findings were audited and quiet ones were not -- optional stopping applied to verification effort, biasing toward confirming what looked interesting. |
| 2026-08-31T09:05:00Z | adr-living-view | data-structure-specialist | architecture | NONE | lens | Tombstone, recorded post-hoc: the convener spawned this consult before performing a lens pass or reading the seal protocol (learned mid-pipeline; UNSEALED note in the matching CONSULT_COSTS row). No priors existed to seal, so no P-NN row is backfilled — all 8 classification rows are 'novel' by construction and the novelty rate of this consult must not be read as informative about the discipline. |
| 2026-09-02T07:19:17Z | sidecar-placement | data-structure-specialist | architecture | P-01 | lens | Placement x mode is a product type: 4 modes x 2 placements = 8 combinations but only some are legal (hackathon+sidecar? promote+sidecar? new+sidecar?); no sum type or table enumerates the legal pairs, so onboarding can be driven into an illegal combination |
| 2026-09-02T07:19:17Z | sidecar-placement | data-structure-specialist | architecture | P-02 | lens | Manifest `shadows: relpath -> kind(dir\|file)` is boolean-blind: the one hard illegal state (a directory shadow at `.claude/`, which breaks worktree creation) has no named enforcer; kind should be derivable from the relpath or the constraint should live in a smart constructor |
| 2026-09-02T07:19:17Z | sidecar-placement | data-structure-specialist | architecture | P-03 | lens | `state_repo_root()` returns a bare path and consumers branch on `!= project_root`; the resolver actually has three outcomes (in-repo, sidecar-owned, dangling/foreign symlink) and a path cannot carry that distinction, so every consumer re-derives it |
| 2026-09-02T07:19:17Z | sidecar-placement | data-structure-specialist | architecture | P-04 | lens | Hook-chain state (`core.hooksPath` unset / team dir / Praxion wrapper / unknown) and the self-heal predicate are unnamed; without an explicit state machine the self-heal can ping-pong with husky's `prepare` re-pointing the path |
| 2026-09-02T07:19:17Z | sidecar-placement | data-structure-specialist | architecture | P-05 | lens | Project identity for the sidecar has two derivations (sanitised origin URL, path hash) with no owner and no identity-vs-value decision; an origin rename or remote change silently orphans the sidecar |
| 2026-09-02T07:19:17Z | sidecar-placement | data-structure-specialist | architecture | P-06 | lens | Manifest `schema: 1` declares no evolution contract (additive-only vs migration) and `autocommit`/`remote.push` are free strings rather than closed enums with exhaustive handling |
| 2026-09-02T07:19:17Z | sidecar-placement | data-structure-specialist | architecture | P-07 | prior | The `.git/info/exclude` Praxion block has no parse-at-boundary: re-running onboarding can duplicate entries and no marker names which lines Praxion owns, so `absorb`/`promote` cannot remove exactly what was added |
| 2026-09-02T07:19:17Z | sidecar-placement | data-structure-specialist | architecture | P-08 | prior | The worktree `link` step's target slot has four legal states (absent / symlink to this sidecar / symlink elsewhere / real directory) and only one is safe to overwrite; a real directory at `.ai-state` must be refused, not replaced — no enforcer is named |
| 2026-09-06T18:17:43Z | rust-first-class | evidence-appraiser | architecture | NONE | lens | Tombstone, recorded post-hoc during the praxion-health pass (not the convener of this consult): no Sealed Priors rows existed before the 2026-08-30T19:20:45Z spawn, so no P-NN row is backfilled — all 8 classification rows are 'novel' by construction and this consult's novelty rate must not be read as informative about the discipline. seal-witness carries the consultant's own Round-0 HEAD, not a pre-spawn seal commit. |

## Challenge Classification

| timestamp | task-slug | discipline | stage | challenge-id | classification | matched-prior-id | seal-witness | prompt-areas |
|---|---|---|---|---|---|---|---|---|
| 2026-07-31T06:40:00Z | td-081-sealed-prior | statistician | architecture | CH-01 | novel |  | cd128039e225aab9ec504542b42b673feb44feae | 7 |
| 2026-07-31T06:40:00Z | td-081-sealed-prior | statistician | architecture | CH-02 | novel |  | cd128039e225aab9ec504542b42b673feb44feae | 7 |
| 2026-07-31T06:40:00Z | td-081-sealed-prior | statistician | architecture | CH-03 | matched | P-01 | cd128039e225aab9ec504542b42b673feb44feae | 7 |
| 2026-07-31T06:40:00Z | td-081-sealed-prior | statistician | architecture | CH-04 | matched | P-02 | cd128039e225aab9ec504542b42b673feb44feae | 7 |
| 2026-07-31T06:40:00Z | td-081-sealed-prior | statistician | architecture | CH-05 | matched | P-06 | cd128039e225aab9ec504542b42b673feb44feae | 7 |
| 2026-07-31T06:40:00Z | td-081-sealed-prior | statistician | architecture | CH-06 | novel |  | cd128039e225aab9ec504542b42b673feb44feae | 7 |
| 2026-07-31T06:40:00Z | td-081-sealed-prior | statistician | architecture | CH-07 | novel |  | cd128039e225aab9ec504542b42b673feb44feae | 7 |
| 2026-07-31T19:33:43Z | verify-multidisciplinary | statistician | verification | CH-01 | novel |  | 37df0f33084e0268ec85b85fe6c34e7997150560 | 0 |
| 2026-07-31T19:33:43Z | verify-multidisciplinary | statistician | verification | CH-02 | novel |  | 37df0f33084e0268ec85b85fe6c34e7997150560 | 0 |
| 2026-07-31T19:33:43Z | verify-multidisciplinary | statistician | verification | CH-03 | novel |  | 37df0f33084e0268ec85b85fe6c34e7997150560 | 0 |
| 2026-07-31T19:33:43Z | verify-multidisciplinary | statistician | verification | CH-04 | matched | P-01 | 37df0f33084e0268ec85b85fe6c34e7997150560 | 0 |
| 2026-07-31T19:33:43Z | verify-multidisciplinary | statistician | verification | CH-05 | novel |  | 37df0f33084e0268ec85b85fe6c34e7997150560 | 0 |
| 2026-07-31T19:33:43Z | verify-multidisciplinary | statistician | verification | CH-06 | matched | P-02 | 37df0f33084e0268ec85b85fe6c34e7997150560 | 0 |
| 2026-07-31T19:33:43Z | verify-multidisciplinary | statistician | verification | CH-07 | matched | P-04 | 37df0f33084e0268ec85b85fe6c34e7997150560 | 0 |
| 2026-07-31T19:33:43Z | verify-multidisciplinary | statistician | verification | CH-08 | novel |  | 37df0f33084e0268ec85b85fe6c34e7997150560 | 0 |
| 2026-07-31T19:33:43Z | verify-multidisciplinary | statistician | verification | CH-09 | matched | P-05 | 37df0f33084e0268ec85b85fe6c34e7997150560 | 0 |
| 2026-08-31T07:45:00Z | adr-living-view | data-structure-specialist | architecture | CH-01 | novel |  | 9021caae0055b72e4be42d21e7d29767a645d58d | 5 |
| 2026-08-31T07:45:00Z | adr-living-view | data-structure-specialist | architecture | CH-02 | novel |  | 9021caae0055b72e4be42d21e7d29767a645d58d | 5 |
| 2026-08-31T07:45:00Z | adr-living-view | data-structure-specialist | architecture | CH-03 | novel |  | 9021caae0055b72e4be42d21e7d29767a645d58d | 5 |
| 2026-08-31T07:45:00Z | adr-living-view | data-structure-specialist | architecture | CH-04 | novel |  | 9021caae0055b72e4be42d21e7d29767a645d58d | 5 |
| 2026-08-31T07:45:00Z | adr-living-view | data-structure-specialist | architecture | CH-05 | novel |  | 9021caae0055b72e4be42d21e7d29767a645d58d | 5 |
| 2026-08-31T07:45:00Z | adr-living-view | data-structure-specialist | architecture | CH-06 | novel |  | 9021caae0055b72e4be42d21e7d29767a645d58d | 5 |
| 2026-08-31T07:45:00Z | adr-living-view | data-structure-specialist | architecture | CH-07 | novel |  | 9021caae0055b72e4be42d21e7d29767a645d58d | 5 |
| 2026-08-31T07:45:00Z | adr-living-view | data-structure-specialist | architecture | CH-08 | novel |  | 9021caae0055b72e4be42d21e7d29767a645d58d | 5 |
| 2026-09-02T08:11:24Z | sidecar-placement | data-structure-specialist | architecture | CH-01 | matched | P-03 | 41903c1616203497999819f57a49d4f774896b82 | 7 |
| 2026-09-02T08:11:24Z | sidecar-placement | data-structure-specialist | architecture | CH-02 | matched | P-05 | 41903c1616203497999819f57a49d4f774896b82 | 7 |
| 2026-09-02T08:11:24Z | sidecar-placement | data-structure-specialist | architecture | CH-03 | matched | P-02 | 41903c1616203497999819f57a49d4f774896b82 | 7 |
| 2026-09-02T08:11:24Z | sidecar-placement | data-structure-specialist | architecture | CH-04 | novel |  | 41903c1616203497999819f57a49d4f774896b82 | 7 |
| 2026-09-02T08:11:24Z | sidecar-placement | data-structure-specialist | architecture | CH-05 | matched | P-06 | 41903c1616203497999819f57a49d4f774896b82 | 7 |
| 2026-09-02T08:11:24Z | sidecar-placement | data-structure-specialist | architecture | CH-06 | matched | P-08 | 41903c1616203497999819f57a49d4f774896b82 | 7 |
| 2026-09-02T08:11:24Z | sidecar-placement | data-structure-specialist | architecture | CH-07 | matched | P-02 | 41903c1616203497999819f57a49d4f774896b82 | 7 |
| 2026-09-06T18:17:43Z | rust-first-class | evidence-appraiser | architecture | CH-01 | novel |  | d7b26028d29c61e1d6ae6e8c6394b57fad630dd2 | 5 |
| 2026-09-06T18:17:43Z | rust-first-class | evidence-appraiser | architecture | CH-02 | novel |  | d7b26028d29c61e1d6ae6e8c6394b57fad630dd2 | 5 |
| 2026-09-06T18:17:43Z | rust-first-class | evidence-appraiser | architecture | CH-03 | novel |  | d7b26028d29c61e1d6ae6e8c6394b57fad630dd2 | 5 |
| 2026-09-06T18:17:43Z | rust-first-class | evidence-appraiser | architecture | CH-04 | novel |  | d7b26028d29c61e1d6ae6e8c6394b57fad630dd2 | 5 |
| 2026-09-06T18:17:43Z | rust-first-class | evidence-appraiser | architecture | CH-05 | novel |  | d7b26028d29c61e1d6ae6e8c6394b57fad630dd2 | 5 |
| 2026-09-06T18:17:43Z | rust-first-class | evidence-appraiser | architecture | CH-06 | novel |  | d7b26028d29c61e1d6ae6e8c6394b57fad630dd2 | 5 |
| 2026-09-06T18:17:43Z | rust-first-class | evidence-appraiser | architecture | CH-07 | novel |  | d7b26028d29c61e1d6ae6e8c6394b57fad630dd2 | 5 |
| 2026-09-06T18:17:43Z | rust-first-class | evidence-appraiser | architecture | CH-08 | novel |  | d7b26028d29c61e1d6ae6e8c6394b57fad630dd2 | 5 |

## Column Definitions

**Table 1 — `## Sealed Priors`** (7 columns, written before the spawn):

| Column | Definition |
|---|---|
| `timestamp` | ISO 8601 UTC of the seal write (pre-spawn). Must be **earlier** than this consult's ledger rows |
| `task-slug` / `discipline` / `stage` | The join key to `CONSULT_LEDGER.md` and `CONSULT_COSTS.md`. The **triple** is the consult's identity |
| `prior-id` | `P-01`, `P-02`, … unique within the triple. Reserved value **`NONE`** — the explicit empty declaration; when present it must be the only row for the triple |
| `source` | `lens` (surfaced by the lens pass over the `binds-to` skill) \| `prior` (the convener already held it before the pass). Recording provenance costs one enum column and lets a later analyst compute both the literal lens-arm estimand and the wider "would have caught it anyway" one from the same file |
| `concern` | One line, specific enough that a reader can judge whether a given challenge is the same concern: name the element of the draft and the property at issue, not the topic. Escape any literal `\|`. Must be non-empty and non-placeholder |

**Table 2 — `## Challenge Classification`** (9 columns, written at Round 2):

| Column | Definition |
|---|---|
| `timestamp` | ISO 8601 UTC of the disposition. Written independently of this consult's `CONSULT_LEDGER.md` rows -- the two are not expected to match. Only the write order is guaranteed: the ledger disposition is written first, this classification row after, so this timestamp is **later than or equal to** the corresponding ledger row's, never earlier. No check enforces this beyond the ordering itself |
| `task-slug` / `discipline` / `stage` | Same triple |
| `challenge-id` | The `### CH-NN` id from the consultant's fragment; the same value the ledger row carries |
| `classification` | `novel` \| `matched`. `matched` means the sealed list already contained this concern |
| `matched-prior-id` | The `P-NN` when `matched`; **empty** when `novel`. Must resolve to a `Sealed Priors` row of the same triple |
| `seal-witness` | The consultant's `**Round-0 HEAD:**` sha, transcribed verbatim. Denormalized across the triple's rows exactly as `model`/`difficulty` are denormalized in the cost series, and checked for agreement for the same reason |

The two enums are chosen **disjoint** (`{lens, prior}` vs `{novel, matched}`) so a
discipline-anchored `grep` can tell the tables apart with a single cell match and no parser.
- `prompt-areas` — the number of attack areas the spawn prompt explicitly enumerated; `0` when it
  named none. The convener authors the spawn prompt as well as the sealed list, and prompt
  specificity moves the novelty rate without touching a sealed row or a classification — so it
  trips no gate and leaves no trace inside these files. This is a **crude proxy, not a digest**:
  the prompt is not a committed artifact, so its sha cannot be recorded. It exists so the series
  can be stratified on its largest uncontrolled covariate rather than confounded by it silently.

## What counts as one concern

The granularity of a sealed prior sets the denominator's grain, so leaving it to the
convener's pen leaves the comparison arm's scale in the hands of the party the
measurement is about. Sealing fixes *when* that choice is made; it does not fix the
choice. And the bias it admits is not noise -- a standing habit of writing narrow,
specific priors raises novelty across every consult in the series and never averages out.

So the unit is anchored to the registry, not to the convener:

- **One concern = one `challenge-obligations` clause of the bound skill, failing at one
  identified site in the draft.** Two sites failing the same clause are two rows. One site
  failing two clauses is two rows. A concern that names no clause is not a sealed prior.
- **A `source: lens` row must name the clause it derives from** in its `concern` cell, in
  the clause's own words. That is what makes the granularity checkable by a reader who was
  not present, rather than asserted by the party who benefits from it.
- **A `source: prior` row** -- a concern the convener already held, independent of the lens
  pass -- carries no clause anchor by construction, and is expected to be rare. If a series
  shows many, the lens pass is being run after the fact rather than before.

This does not make granularity objective; two careful parties will still split some
concerns differently. It makes the split *arguable from the registry* instead of
unfalsifiable, which is the most a definition can do here.

## Reading the series

The recipes below are column-anchored on `discipline` at position 3, identical in form
to `.ai-state/CONSULT_LEDGER.md` § Falsifier and for the identical reason: an unanchored
match also catches rows whose free text happens to contain the name.

```
# PRIMARY -- the criterion's statistic. One rate per consult, reported per
# consult and never pooled. Challenges cluster within a consult (one convener,
# one sealed list, one draft), so the consult is the independent unit. This is
# the same correction dec-304 applied to the sibling dismiss rate; pooling
# challenges here would reintroduce the defect that decision removed.
D=statistician
grep -E "^\|[^|]*\|[^|]*\| *$D *\|" .ai-state/CONSULT_PRIORS.md \
  | grep -E '\| *(novel|matched) *\|' \
  | awk -F'|' '{ gsub(/^ +| +$/,"",$3); gsub(/^ +| +$/,"",$5); gsub(/^ +| +$/,"",$7);
                 k=$3" / "$5; n[k]++; if ($7=="novel") v[k]++ }
               END { for (k in n) printf "%-46s novel %d/%d  rate %.2f\n", k, v[k]+0, n[k], (v[k]+0)/n[k] }'

# distinct sealed consults for a discipline (the denominator of the series --
# how many independent observations exist at all)
grep -E "^\|[^|]*\|[^|]*\| *$D *\|" .ai-state/CONSULT_PRIORS.md \
  | grep -E '\| *(lens|prior) *\|' | cut -d'|' -f3,5 | sort -u | wc -l

# NOT THE CRITERION'S STATISTIC -- the pooled challenge-level ratio.
# Recorded here only so a reader who computes it recognises what it is. It
# ignores clustering, so a single talkative consult dominates it; on the worked
# example the live statistician consult raised, it diverges from the per-consult
# reading by 0.73 vs 0.46. Do not publish it, and do not cite it in an ADR.
#   grep ... | grep -c '| novel |'   over   grep ... | grep -cE '\| *(novel|matched) *\|'

# priors sealed but never matched by any challenge (the lens's own miss rate is
# NOT computable from this; a prior nobody challenged may simply have been fixed
# before the spawn -- see § What is not recorded here)
```

The authoritative implementation of the primary recipe is
`novelty_rate_by_consult()` in `fitness/tests/test_discipline_registry_invariants.py`,
which is canaried against a worked example showing the pooled and per-consult
readings diverging. If this shell recipe and that function ever disagree, the
function is correct and this block is stale.

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
