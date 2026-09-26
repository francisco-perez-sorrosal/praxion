---
id: dec-draft-8f0e1c8f
title: Blind-reader classification of consult challenges (td-102)
status: proposed
category: architectural
date: 2026-09-26
summary: "Move novel/matched classification of consult challenges from the convener to a blind second reader, recorded verbatim; the classification regime is derived from timestamp vs. a boundary header, never a stored column"
tags: [consult, measurement, bias-correction, process-economy]
made_by: agent
agent_type: implementation-planner
branch: worktree-process-economy-td102
pipeline_tier: standard
affected_files:
  - .ai-state/CONSULT_PRIORS.md
  - fitness/tests/test_discipline_registry_invariants.py
  - skills/software-planning/references/coordination-details.md
  - commands/consult.md
  - agents/discipline-consultant.md
  - agents/CLAUDE.md
  - skills/onboard-project/references/phases-core.md
---

## Context

`docs/multidisciplinary-identities-evidence.md` §17.16 measured the defect td-102 predicted: a
blind `opus` second reader agreed with the convener's own novel/matched call on only 13/22
challenges (Wilson 95% CI [39%, 77%]), and every one of the 9 disagreements was convener
`matched` → reader `novel`. The recorded novelty series in `.ai-state/CONSULT_PRIORS.md` is
therefore biased low: the convener classifies its own challenges against a list it wrote itself,
with full knowledge of the challenge text, and no inter-rater check exists anywhere in the
protocol. The remedy §17.16 measured against is the one td-102 named at open: move the
classification call out of the interested party's hands.

**Revision**: the first version of this decision stored the classification regime as a 10th
`classified-by` column, backfilled `convener` into all 39 historical rows. That design was found
to violate `fitness/tests/test_consult_append_only.py`'s append-only gate before any code was
written (see Considered Options, rejected option D) and is replaced here by a derived-property
design that touches no existing row.

## Decision

The convener no longer classifies challenges itself. At Round 2, the convener builds a **blind
packet** — per consult, the sealed prior concerns with their `prior-id`s, plus, per challenge,
its id, claim, decision-at-stake and full text **with its `Disposition:` and `Rationale:` lines
removed** (they are filled before the packet is built). Every passed field is checked for
disclosure first, since a free-text ledger field can itself disclose a disposition, as td-081
`CH-05` did. It spawns **one `general-purpose` agent at
`opus`** to classify each challenge as `novel`/`matched` (+ `prior-id`) against that packet alone,
and records the reader's call **verbatim**, never overriding it; the convener records no view of
its own. A convener that cannot spawn (a pipeline agent without the Agent tool) hands the packet
to the orchestrator.

**The classification regime is a derived property, not stored data.** `.ai-state/CONSULT_PRIORS.md`
gains one new header line, `**Blind classification begins**: 2026-09-26T00:00:00Z`, plus new prose
paragraphs (pure additions — no existing row, cell, or line is edited). A consult's regime is
inferred by comparing its `## Challenge Classification` rows' `timestamp` against that header: at
or after it, the row is understood to be blind-reader-classified; before it, convener-classified.
**No mechanical check can prove any individual row's classifier** — the `## Challenge
Classification` table keeps its existing 9-column shape, unchanged for every row past and future.
The boundary header and this decision's protocol text are the whole contract; a fitness check
proves only that the header itself is well-formed (present exactly once, valid ISO-8601 UTC, not
earlier than the pre-existing `**Series begins**:` boundary) and equal to a constant pinned in
the gate, so moving the boundary (which would relabel convener rows) means editing the gate — it
cannot and does not attempt to verify which regime actually produced a given row.

No new agent, skill, or file is added — the reader is an ordinary `general-purpose` spawn. The
decision is nevertheless `architectural` under `rules/swe/adr-conventions.md`'s **published**
clause: it changes the `CONSULT_PRIORS.md` skeleton that onboarding ships
(`skills/onboard-project/references/phases-core.md`), and it moves the classification
responsibility from the convener to a separate reader.

## Considered Options

### Reader identity

#### A — `general-purpose` agent at `opus` (chosen)

Follows §17.16's measured method (an independent opus reader, blind to the convener's calls). It
is not identical: §17.16's reader judged from each challenge's one-line claim and decision, because
the full text survived for only 2 of 8 consults, while the protocol gives the reader the full text
when it exists. No new agent definition, no
new `skills:`/`tools:` surface, no registry row — the lowest-footprint option, and the reader
needs nothing beyond the packet: no discipline-specific skill, no `challenge-obligations`
checklist, no draft access.

#### B — Repurpose the `discipline-consultant` agent as its own reader

Rejected: `discipline-consultant` resolves a `Discipline: <name>` directive that binds a
discipline's own skill and works its `challenge-obligations` against a draft — machinery built
for producing challenges, not classifying someone else's against a sealed list. Forcing it into a
reader role would need a second invocation mode (a `Round: classify`-shaped directive) with its
own isolation contract, which is a behavior change to a shipped agent's contract for a task that
needs none of its existing machinery — more surface for the same job, not less.

#### C — A new dedicated `blind-classifier` agent

Rejected outright: the task brief names this an explicit non-goal (a new agent definition is a
component change this task does not need), and a single-purpose agent for a packet-in/verdict-out
task is exactly the kind of ceremony `general-purpose` already exists to avoid.

### Regime representation

#### D — Store `classified-by` as a 10th column, backfilled across history (rejected)

The original design: append `classified-by` ∈ {`convener`, `blind-reader`} as the table's last
column, backfilling `convener` into all 39 existing rows and enforcing the new value via a
boundary-gated fitness check. **Rejected**: `fitness/tests/test_consult_append_only.py` enforces
`.ai-state/CONSULT_*.md` append-only against `merge-base(origin/main, HEAD)`, with no per-file
exception, by scanning every pipe-delimited line in the whole file (confirmed by reading
`extract_data_rows` directly) and requiring every baseline row to survive byte-identical. A 39-row
backfill changes 39 rows' bytes — none of the old 9-cell rows exist anymore in the edited file, so
the gate reports all 39 as lost/edited, and no witnessed-restoration exemption applies (that
exemption is scoped to restoring bytes a `seal-witness` commit already recorded, not to a
schema-wide rewrite). Rewording an existing row inside either `## Column Definitions` pipe table
— itself pipe-delimited — would trip the identical defect. The column design was structurally
sound (a genuine invariant, a real enum, a real enforcement point) but incompatible with the one
constraint that actually governs this specific file's mutability.

#### E — Derived property: timestamp vs. a boundary header (chosen)

No existing row, cell, or table line is ever touched. A new header line and new prose paragraphs
are pure additions, safe under the append-only gate regardless of where in the file they land
(confirmed: the gate ignores every non-`|`-prefixed line entirely). The cost is honesty, stated
directly rather than hidden: no mechanical check can prove any individual row's classifier — the
boundary and the protocol text are the contract, and a convener who silently classified a
post-boundary row itself, then recorded it as if a blind reader had, would not be caught by any
gate. This is accepted as the correct trade — the alternative (a verifiable per-row marker) is not
reachable without changing what "append-only" means for this file, which is out of this decision's
scope.

## Consequences

**Positive**: the recorded novelty series stops being self-graded; the boundary header lets any
future reader separate the two regimes rather than treating the whole series as one comparable
run; zero new components; zero existing rows touched, so the append-only history stays intact;
the packet-construction discipline (excluding any field that could disclose its own disposition,
per the td-081 `CH-05` precedent) closes a leak the sealed-prior design left open.

**Negative**: one additional spawn per consult (cost, not correctness); the historical
`convener`-classified rows remain in the series as a lower-quality regime rather than being
corrected retroactively — by design (`.ai-state/CONSULT_PRIORS.md`'s own rule 4: no
retro-classification); and — the honest cost of choosing option E over D — the protocol is
**unenforced at the row level**: nothing prevents a convener from classifying a post-boundary
challenge itself and recording it exactly as a blind reader's row would look. The boundary and the
protocol text are trusted, not verified, per row.

## Disconfirmation

- **Falsifier.** A later blind audit that re-reads post-boundary consults with a second,
  independent reader: if agreement between that reader and the recorded (first-reader) calls is no
  better than §17.16's convener-vs-reader 13/22, moving the classification did not remove the
  classifier's influence, and this decision was wrong about where the bias lived.
- **Steelmanned runner-up.** Option D, the stored `classified-by` column: it makes the regime
  explicit in every row and gives a per-row enforcement point — at the price of 39 in-place edits
  the append-only gate forbids, and a cell that proves blindness no better than the boundary does.
- **Reversal trigger.** If the append-only contract for `CONSULT_*.md` ever gains a sanctioned
  schema-migration path, revisit storing the regime; if a later blind audit finds the reader
  plainly wrong on a material share of calls, revisit giving the convener a recorded dissent.
