---
id: dec-draft-aae88f1f
title: Finalize rewrites draft ids across one citation net shared with its detector, replacing the enumerated allowlist
status: proposed
category: behavioral
date: 2026-09-04
summary: The finalize cross-reference rewriter walks the same bounded net its post-condition detector scans (every markdown file under .ai-state/ and docs/ minus the frozen subtree, the in-flight .ai-work/ documents, ROADMAP.md) instead of an enumerated allowlist of named files; dec-331's own reversal trigger (a second widening) fired, so this adopts its deferred Option C.
tags: [adr, finalize, cross-references, citation-net, dangling-reference, tech-debt, td-163, td-153]
made_by: agent
agent_type: orchestrator
branch: worktree-sidecar-placement
pipeline_tier: lightweight
affected_files:
  - scripts/finalize_adrs_crossrefs.py
  - scripts/finalize_adrs.py
  - scripts/test_finalize_adrs.py
  - rules/swe/adr-conventions.md
  - skills/software-planning/references/adr-authoring-protocols.md
supersedes: dec-331
dissent: "Every markdown file under .ai-state/ is a wider write surface than an enumerated list, and a timestamped report or archived spec is a snapshot some readers expect finalize never to touch; the counter is that a rewrite replaces only a concrete 8-hex draft id, which alters no meaning and can collide with nothing."
---

## Context

The sidecar-placement merge (2026-09-04) promoted twelve drafts and left this branch's
own archived spec, `.ai-state/specs/SPEC_sidecar-placement_2026-09-03.md`, carrying
thirty-three `dec-draft-<hash>` citations that had to be rewritten by hand (td-163).
The cause is structural. `finalize_adrs_crossrefs.py` selected archived specs by
matching their filename against task slugs derived from `.ai-work/` subdirectories in
the checkout finalize runs in -- but a Standard/Full pipeline's `.ai-work/` is
worktree-local and gitignored by design, so at merge-to-main in the canonical checkout
the slug set was empty and the rule never fired for any worktree pipeline. The rule
text promised specs were in scope; the code could not keep the promise.

A second finding on the same run (td-153) showed seven pre-existing files still
carrying dangling draft ids: `DESIGN_CHANGELOG.md` and three sentinel snapshots were
never in the allowlist at all, while `calibration_log.md` and `TECH_DEBT_LEDGER.md`
were listed and drifted anyway because their originating finalize predated their
listing.

dec-331 (2026-08-07) had already named this outcome. It widened the allowlist for
`idea_ledgers/`, deferred the inversion to `.ai-state/**/*.md` as Option C, and set its
reversal trigger at "a *second* allowlist widening for a different `.ai-state/`
artifact family -- the next one should adopt Option C rather than extend the list a
third time." `calibration_log.md` was the second widening. Specs, the changelog and the
report families would have been the third, fourth and fifth.

The defect class is a data-structure one: the rewriter and its detector held two
different definitions of where a citation may live, and the allowlist could only ever
be a strict subset of the detector's net. Every gap between them was a finalize that
reported success while stranding a citation.

## Decision

`finalize_adrs_crossrefs.py` exposes one generator, `citation_net(repo_root)`, and
both `rewrite_cross_references` and `detect_unrewritten_ids` walk exactly that. The
net is bounded subtrees and named files, never a repo sweep and never code:

- every markdown file under `.ai-state/` -- decisions (drafts and finalized),
  `DESIGN.md` and its changelog, both tech-debt ledgers, the three `CONSULT_*` files,
  `calibration_log.md`, `SYSTEM_DEPLOYMENT.md`, the idea ledgers, every archived spec,
  and the timestamped report families;
- every markdown file under `docs/` except `docs/independent-analysis/` (frozen);
- the in-flight `.ai-work/*/LEARNINGS.md`, `SYSTEMS_PLAN.md`, `IMPLEMENTATION_PLAN.md`;
- a project-root `ROADMAP.md`.

`scripts/` stays outside for the reason it always was: its only concrete draft ids are
test fixtures that must stay literal. The archived-spec slug derivation is deleted;
nothing persistent is scoped through `.ai-work/` again.

The detector's meaning changes from "allowlist-gap finder" to "rewrite post-condition":
a survivor can only mean the rewrite of that one file failed (unreadable, unwritable,
changed underneath the run), and the finalize log now says so instead of instructing
the operator to widen a list. The rewriter catches a failed write and leaves the id in
place for the detector to report, rather than crashing the run.

The rule text (`rules/swe/adr-conventions.md` § Finalize Protocol) and the protocol
table (`adr-authoring-protocols.md` § Finalize at Merge-to-Main) describe the net and
the shared-definition contract. dec-331's operating principle survives in narrowed
form: a citation that dangles because it sits *outside* the net is fixed by extending
the net, never by forbidding the citation -- but inside the net there is no list left to
widen.

The eleven historical citations whose drafts were promoted were repaired by resolving
each hash through the finalize rename records (the draft id is `sha1(fragment
filename)[:8]`, so every promoted fragment's id is recoverable from history), then
running the new rewriter over them; the five whose drafts never entered git are
annotated as never promoted rather than left looking like finalize gaps.

## Considered Options

### A. Widen the allowlist a third time (specs, changelog, report subtrees)

- **Pro** -- smallest diff; keeps the enumerated shape dec-331 preferred.
- **Con -- decisive** -- dec-331's own reversal trigger fired one widening ago. A list
  that must learn every new `.ai-state/` artifact family after that family has already
  stranded a citation is the wrong data structure for an invariant ("the rewriter covers
  what the detector scans") that can simply be made true by construction.

### B. One citation net shared by rewriter and detector (chosen)

- **Pro** -- deletes the failure class rather than an instance; the two consumers cannot
  disagree because there is one definition.
- **Pro** -- the rewrite is safe wherever it walks: it replaces a concrete 8-hex draft id,
  never a shape, so a snapshot or a spec is not altered in meaning.
- **Pro** -- fixes td-163 without any dependency on `.ai-work/`, which is exactly the
  dependency that made the worktree case fail.
- **Con** -- the net is wider than the list; see the dissent line and the falsifier below.

### C. Forbid draft-id citations in archived specs and reports

- **Con -- decisive** -- the same unsatisfiable-at-authoring-time objection dec-331 raised
  for the idea ledger: the spec is archived while the ADRs are still drafts, and the
  authoring convention sanctions the draft citation.

## Consequences

**Positive.** A worktree pipeline's archived spec resolves after merge with no manual
step. New `.ai-state/` artifact families are covered the day they appear. The finalize
warning now names a real failure to act on instead of a list to grow. The test suite
proves the shared-net contract directly (one representative per member, a `scripts/`
fixture as the control, and a canary for the post-condition biting on an unwritable
file).

**Negative.** `.ai-state/` snapshots (sentinel, metrics, skill-genesis reports) are now
rewritten when they cite a promoted draft. That is the intended reading -- the id
resolves afterwards -- but it is a write into files some readers think of as frozen.

**Neutral.** No component is added, removed, or reassigned; `finalize_adrs_crossrefs.py`
still owns the scope. Category is `behavioral` by the rule's falsifier.

## Disconfirmation

Recorded voluntarily; not required at `category: behavioral`.

- **Falsifier** -- an `.ai-state/` markdown file whose meaning depends on the literal
  pre-finalize id (as `scripts/` fixtures do). No such file exists; a report quoting a
  dangling id as a *finding* still reads correctly once the id resolves.
- **Steelmanned runner-up** -- Option A with a sentinel check that diffs the allowlist
  against the detector's net at audit time. It would catch the next gap earlier, but
  still after a finalize had stranded it; it treats the symptom the shared net removes.
- **Reversal trigger** -- a second `.ai-state/` file family that must keep a draft id
  literal. One instance is an exclusion (`_FROZEN_DOCS_SUBTREE` already shows the shape);
  two would argue the net needs an explicit exclusion list of its own, with the same
  drift risk in the other direction.

## Prior Decision

dec-331 chose to widen the enumerated allowlist for `idea_ledgers/` and to state the
"widened, never worked around" principle, explicitly deferring the inversion to
`.ai-state/**/*.md` (its Option C) until a second widening proved the pattern. That
second widening (`calibration_log.md`) happened; this record adopts Option C as
dec-331 said the next one should. What changes: the mechanism (a shared net replaces
the list, and the detector becomes a post-condition). What survives: the stance that
draft-id citations in persistent state are legitimate and finalize must resolve them.
