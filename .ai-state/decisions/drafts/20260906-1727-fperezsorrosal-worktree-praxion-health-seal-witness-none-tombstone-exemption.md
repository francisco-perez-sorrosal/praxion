---
id: dec-draft-fd158a05
title: The seal-witness equality check exempts NONE tombstones as vacuous, and the priors parsers honour the escape convention the files document
status: proposed
category: behavioral
date: 2026-09-06
summary: Two root causes behind four fitness failures — the CONSULT_* escape convention is unparseable by the gate's own splitter, and G6 set-equality is unsatisfiable for any honestly post-hoc NONE tombstone. Fixed by escape-aware splitting, a paid-for G6 vacuity exemption, and two record repairs that restore what was actually recorded.
tags: [consult-ledger, seal, discipline-consultant, fitness, gate-liveness, parser, integrity]
made_by: agent
agent_type: systems-architect
branch: worktree-praxion-health
pipeline_tier: full
supersedes_in_part: [dec-310]
dissent: 'An exemption is an exemption. dec-310 named "the gate goes red and the proposed remedy is a skip-list entry" as grounds for reopening the whole mechanism, and a NONE-shaped carve-out is a skip-list with a predicate instead of a literal. A convener who wants the seal check off now has a documented shape to write — a tombstone — and the three compensating checks all constrain the same convener who chose to write it. Part 5 compounds this: legalising restore-to-witness rewrites means the append-only gate stops being the thing that catches an in-place edit at the moment it happens, because drift followed by restore now nets to green. The gate that fired correctly on nine rows is being taught to accept the ninth kind of correct-looking rewrite.'
affected_files:
  - .ai-state/CONSULT_PRIORS.md
  - .ai-state/CONSULT_COSTS.md
  - fitness/tests/test_discipline_registry_invariants.py
  - fitness/tests/test_consult_append_only.py
affected_reqs: [REQ-03, REQ-04, REQ-05]
---

## Context

Four `fitness/tests/test_discipline_registry_invariants.py` failures trace to two distinct
root causes, neither of which is convener dishonesty.

### Root cause 1 — the documented escape convention is unparseable by the gate's own splitter

`.ai-state/CONSULT_PRIORS.md` § Column Definitions instructs: *"Escape any literal `|`"* in
the `concern` cell. `CONSULT_LEDGER.md` and `CONSULT_COSTS.md` carry the same instruction for
their free-text cells. But `parse_prior_table_rows` (and its ledger/cost siblings) split with
`line.strip().strip("|").split("|")` — a bare split that does not honour the escape. A cell
written to the documented convention therefore splits into an extra column and fails the
row-shape check.

This is not hypothetical. The `sidecar-placement` seal witness `41903c16` holds P-02's concern
as ``kind(dir\|file)`` — written to the convention. Running the gate's own parser over that
commit's copy of the file returns **8 columns for that row**, which
`check_prior_row_has_seven_columns` flags. The convener, at some point after the seal, edited
the working file (commit `5e9be8aa`) to ``kind(dir or file)`` — a change that is cosmetically
trivial, makes the row parse, and silently breaks the seal. The result is the
`test_the_witness_commit_contains_the_sealed_prior_rows[sidecar-placement-…]` failure, which
reports P-02 as simultaneously *added* and *removed* because the identity tuple is
`(prior-id, source, concern)`.

So the file's own convention and its own gate disagree, and the only way a convener could make
the gate green was to violate the seal. **Restoring the sealed text without fixing the parser
would move the failure from G6 to G0a, not remove it** — verified by running both checks over
both texts.

### Root cause 2 — G6 is unsatisfiable for any honestly post-hoc NONE tombstone

`check_witness_priors_equal_working_priors` (G6) asserts set equality between the sealed
priors in the **witness commit** and the working file. The recorded `seal-witness` is, by
`dec-310`'s design, the consultant's `**Round-0 HEAD:**` — the one datum the convener did not
author. That commit is by construction *earlier than the consult*. A `NONE` tombstone recorded
honestly after the fact can therefore never appear in it. G6 sees `sealed = ∅`,
`working = {NONE}`, and fails.

The existing precedent shows the pressure this creates. The `adr-living-view` tombstone
(`CONSULT_PRIORS.md` line 47) is recorded honestly, and its `CONSULT_COSTS.md` note says the
`seal-witness` column "carries the consultant's Round-0 HEAD, not a pre-spawn seal commit".
But the witness commit's own copy of the file records that consult's seal-witness as
`9021caae…` on all eight classification rows, while the working file records `166c5084…` — a
commit that *does* contain the tombstone. The value was re-pointed post-hoc, uniformly, to a
later commit. Whatever the intent, the mechanical effect is that G6 was satisfied by moving
the witness rather than by the witness attesting anything, and the fragment check that would
have caught the drift skips because `.ai-work/` was cleaned. **G6 as written does not admit an
honest tombstone; it admits only a re-pointed one.** That is the defect.

### The two records at stake

- `('rust-first-class', 'evidence-appraiser', 'architecture')` @ `2026-08-30T19:29:00Z`:
  eight ledger rows, **no** Sealed Priors row and **no** Challenge Classification rows. The
  WAL shows `agent_start` at `2026-08-30T19:20:45Z`; no seal commit exists. The consultant's
  fragment survives at
  `…/worktrees/data-structures-pillar/.ai-work/rust-first-class/CONSULT_evidence-appraiser.md`
  carrying `**Round-0 HEAD:** d7b26028d29c61e1d6ae6e8c6394b57fad630dd2` (reachable). The
  consult was genuinely **unsealed**.
- `('sidecar-placement', 'data-structure-specialist', 'architecture')`: genuinely **sealed** at
  `41903c16`; only the working file's P-02 text drifted, for the parser reason above.

## Decision

Five parts. Parts 1 and 2 are the mechanism repair; parts 3 and 4 are record repairs that
restore what was actually recorded; part 5 makes those repairs legal under the append-only
contract without weakening it.

**1. The three `CONSULT_*` parsers honour the escape convention.** Row splitting becomes
`re.split(r"(?<!\\)\|", line)` with `\|` unescaped to `|` in each cell value, applied
uniformly to `parse_ledger_table_rows`, `parse_cost_table_rows`, `parse_prior_table_rows` and
`parse_classification_table_rows`. The existing unescaped-pipe canaries keep biting — they
supply a *raw* `|`, which still inflates the count. A new positive canary asserts that a row
carrying `\|` parses to exactly its column count. This removes an entire latent failure class:
today no shipped data row uses the escape, so the defect is invisible until the first concern
that needs a pipe.

**2. G6 exempts a NONE-only seal as vacuous, and the exemption is paid for.** When the working
file's seal for a triple is a single `prior-id: NONE` row, `check_witness_priors_equal_working_priors`
returns `None` without consulting the witness — there is no prior list for a witness to
attest, and comparing two empty sets proves nothing. In exchange, three checks must hold for
an exempt triple, all of them assertions the exemption did not previously require:

- **C1 — NONE-exclusivity**: the triple has exactly one Sealed Priors row and its `prior-id`
  is `NONE`. (The existing `test_flags_a_none_declaration_coexisting_with_listed_priors`
  already encodes the rule; C1 makes it a precondition of the exemption.)
- **C2 — all-novel**: every Challenge Classification row for the triple is `novel` with an
  empty `matched-prior-id`. A `matched` classification under a NONE seal is a contradiction —
  it names a prior that does not exist — and must fail loudly.
- **C3 — declared cost note**: the triple's `CONSULT_COSTS.md` row's `notes` cell begins with
  the `UNSEALED:` marker. The admission must exist in the sibling file, where a cost-series
  reader will meet it, not only in the tombstone's prose.

This is **not** the skip-list `dec-310` § Reversal trigger (ii) warned about. A skip-list
names a triple and stops checking it. This narrows an invariant to the domain where it has
content, and adds three checks over the domain it releases. The cheat G6 exists to catch —
a convener appending a prior after reading the challenges and citing it as `matched` — is
*more* tightly closed under the exemption than before: C1 forbids the append and C2 forbids
the citation.

**3. Record repair — restore the sealed `sidecar-placement` P-02 text.** With part 1 landed,
`.ai-state/CONSULT_PRIORS.md`'s P-02 concern reverts to the witness commit's bytes,
``Manifest `shadows: relpath -> kind(dir\|file)` is boolean-blind: …``. This is a **revert of
an unauthorised post-seal edit**, not a new edit: the file's append-only rule exists to make
sealed content immutable, and restoring the sealed content is what compliance looks like. The
seal is **not** re-pointed; `41903c16` stands.

**4. Record repair — the `rust-first-class` tombstone, its classifications, and the
`adr-living-view` witness value.**

- Append one Sealed Priors row for `rust-first-class / evidence-appraiser / architecture` with
  `prior-id = NONE`, `source = lens`, timestamped at the **actual moment of writing** (this
  pass), never backdated before the spawn — following the `adr-living-view` tombstone's
  precedent exactly, whose own timestamp postdates its classification rows for the same
  reason.
- Append eight Challenge Classification rows, `CH-01`..`CH-08`, all `novel` with empty
  `matched-prior-id` (true by construction — no priors existed),
  `seal-witness = d7b26028d29c61e1d6ae6e8c6394b57fad630dd2` (the consultant's genuine Round-0
  HEAD, transcribed from the surviving fragment), `prompt-areas = 5` (the spawn prompt's
  Round-0 paragraph enumerates five challenge-obligation questions).
- Restore `adr-living-view`'s `seal-witness` on all eight of its classification rows to
  `9021caae0055b72e4be42d21e7d29767a645d58d` — the value its own witness commit records, i.e.
  what was actually written at the time. Under part 2 that triple is exempt from G6, so the
  re-point to `166c5084` is no longer needed for any gate, and the honest value costs nothing.
  **This is a discovered item, outside the brief's stated scope** — surfaced here rather than
  silently left, and flagged for the user in the plan's handoff.

**These are record repairs, not convener acts.** The praxion-health pipeline is not the
convener of either consult. The tombstone's `concern` cell must say so in its own words, so no
future reader mistakes a post-hoc repair for a seal.

**5. The append-only gate gains a restore-to-witness exemption.**
`fitness/tests/test_consult_append_only.py` enforces "no row is ever edited or deleted" against
`merge-base(origin/main, HEAD)`, and its remedy text says to append a new row referencing the old
one. Parts 3 and 4 are in-place rewrites of nine rows, so the gate flags all nine — correctly,
under the contract as written. Appending cannot satisfy G6 without backdating, and backdating is
the one thing forbidden outright, so the contract as written admits **no** legal repair of a
post-seal edit. That is the defect this part closes.

An in-place row change is permitted **iff the new row bytes equal that row's bytes in the
seal-witness commit recorded for that row's triple**; the gate resolves the witness from the
triple's Challenge Classification rows and reads `git show <witness>:<file>`. Any other in-place
edit still fails, and deletion is never permitted. A canary proves a non-witness rewrite is still
flagged.

The predicate is **monotone toward the witness**: the only rewrite it admits is one whose result
equals an already-committed, independently-witnessed byte sequence. It can therefore restore a
drifted row and can never fabricate one, introduce new text, or remove a row — the same shape of
argument as part 2, narrowing an invariant to the domain where it has content rather than naming
a triple and stopping.

Two implementation constraints the gate must pin, because both are otherwise ambiguous:

- **Resolve the witness from the *baseline* copy of the file, not the post-edit one.** For the
  `adr-living-view` rows the `seal-witness` cell is itself the thing being restored, so resolving
  from the new value would let a row nominate the very commit that vindicates it. Baseline
  resolution closes that circularity. (Both resolutions happen to accept the two real cases —
  `git show 166c5084:…` and `git show 9021caae:…` both carry `9021caae` on those rows — so this
  is a specification choice, not a behaviour change today.)
- **Compare bytes, not parsed cells.** The whole point of part 3 is restoring an exact byte
  sequence containing `\|`; a comparison over parsed values would defeat it.

## Considered Options

### A — Restore the sealed P-02 text only, and leave the tombstone problem to a skip-list

Rejected. Restoring without part 1 moves the failure from G6 to G0a (verified empirically),
and a skip-list is what `dec-310` names as grounds for reopening the mechanism.

### B — Re-point `rust-first-class`'s seal-witness to a commit containing the tombstone

This is what `adr-living-view` did, and it is the only way to satisfy G6-as-written for a
post-hoc tombstone. Rejected: the surviving fragment records `d7b26028`, so recording anything
else is a fabrication of the one datum the convener did not author — precisely what the seal
mechanism exists to prevent. It would also be undetectable here, since the fragment lives in
another worktree's gitignored `.ai-work/` and G5 skips.

### C (chosen) — Escape-aware parsers + paid-for G6 vacuity exemption + two record repairs

Pros: fixes both root causes rather than four symptoms; strengthens the cheat-detection the
exemption releases; removes a latent parser defect before it bites; both record repairs
restore what was actually recorded rather than inventing anything. Cons: touches a gate whose
whole claim is tamper-evidence (see `dissent:`); five distinct edits across two files and one
test module.

### D — Widen G6 to compare normalised (escape-stripped) concern text

Considered for the `sidecar-placement` half alone. Rejected: it makes the gate tolerate the
exact class of edit it exists to detect — a "cosmetic" change is only cosmetic until someone
argues a substantive one is. Fixing the parser removes the pressure to edit at all, which is
strictly better than teaching the gate to forgive edits.

## Consequences

**Positive.** Four fitness failures close on two root-cause fixes. The escape convention
becomes usable, so the next concern needing a pipe does not force a silent seal violation.
Honest post-hoc tombstones gain a path that does not require re-pointing a witness, which
removes the structural incentive that produced the `adr-living-view` drift. The cheat G6
targets is more tightly closed for exempt triples than it was. Two records now say what
actually happened.

**Positive (part 5).** A post-seal edit becomes *repairable* rather than permanently
un-green — the contract previously admitted no legal remedy at all, which is what made
witness re-pointing look like the only way out and produced the `adr-living-view` drift in the
first place. The exemption is mechanically checkable against git, not against a reviewer's
judgement.

**Negative.** A gate whose claim is tamper-evidence acquires a predicate-shaped carve-out —
see `dissent:`. The `adr-living-view` seal-witness is edited a second time, and an
append-only file has now been edited three times in its short life, which is itself a signal
worth watching. Part 5 costs one more: drift-then-restore now nets to green, so the append-only
gate no longer catches an in-place edit at the moment it happens — only a *net* divergence from
the witness. And the gate's baseline is `merge-base(origin/main, HEAD)`, so it could not have
caught either of the two edits this pass repairs; both were already in `origin/main` history. The
gate protects forward from its baseline and makes no retrospective claim. `prompt-areas = 5` is a judgement about a prompt that is not a committed
artifact, and is unfalsifiable by a later reader (the column definition already concedes this
is a crude proxy).

## Prior Decision

`dec-310` established `.ai-state/CONSULT_PRIORS.md`, the decide-seal-spawn ordering, the
two-table schema, the `(task-slug, discipline, stage)` join, the Round-0-HEAD witness, and the
gate family G0–G6, and claimed **tamper-evidence, not tamper-proofness**. This decision
narrows exactly one clause: **G6's set-equality assertion, and only over triples whose working
seal is a NONE-only declaration**, where the assertion has no content. Everything else in
`dec-310` stands — the ordering, the schema, the witness datum's provenance, the append-only
discipline, G0–G5, and the tamper-evidence framing (which this decision arguably restores,
since it removes the one path by which a witness re-point was the only way to be green).
`dec-310` accordingly stays `accepted` and gains `superseded_in_part_by: [dec-draft-fd158a05]`.

The escape-aware parser change is not a narrowing of `dec-310` at all — it is the
implementation catching up to a convention `dec-310`'s own file already documented.

## Disconfirmation

**Falsifier.** A consult appears whose seal is a NONE tombstone *and* whose challenges include
a genuine `matched` — i.e. the convener demonstrably held a prior but recorded NONE. C2 would
fail it, which is the intended behaviour; but if that case turns out to be *common* rather
than a contradiction, then NONE is being used as a convenience rather than an admission, the
exemption is being farmed, and the `dissent:` is correct.

**Steelmanned runner-up (Option B, generalised).** The whole tombstone construct may be the
mistake. `dec-310`'s decide-seal-spawn ordering is a convention with no gate; an unsealed
consult is a *protocol violation*, and the honest response to a protocol violation is arguably
to exclude that consult from the series entirely — not to invent a record shape that makes it
countable. Two of the six post-boundary consults are now unsealed tombstones; a series
one-third composed of admissions that the protocol was not followed is not measuring what
`dec-306`'s falsifier needs, and building machinery to keep those rows green may be
sophisticated avoidance of the simpler finding that the protocol is not being followed.

**Reversal trigger.** Any of three: (i) the falsifier above — NONE tombstones become the
common case rather than the exception; (ii) **the restore-to-witness exemption fires for drift
introduced *after* this decision** — the two rows it repairs are historical, so a third occurrence
means append-only is not holding prospectively and the remedy is process, not gate design. Part 5
changes how this trigger must be watched: a post-decision drift-then-restore now passes the gate,
so the trigger needs a **counter** (how many times the exemption fired, and against which
baseline) rather than a red test. If the gate cannot report that count, part 5 is under-built;
(iii) `dec-306`'s criterion is re-opened and the analyst finds the tombstone rows must be
excluded, at which point the exemption bought nothing and the rows should be moved out of the
series rather than exempted inside it.
