---
id: dec-331
title: Widen the finalize rewrite allowlist to cover `.ai-state/idea_ledgers/`, rather than forbid draft-id citations there
status: accepted
category: behavioral
date: 2026-08-07
summary: The idea ledger legitimately cites `dec-draft-<hash>` at authoring time, so finalize's rewrite allowlist gains `.ai-state/idea_ledgers/*.md` (and the three named `.ai-state/` files the rule text had already drifted from); a cite-finalized-only rule is rejected as unsatisfiable at authoring time.
tags: [adr, finalize, idea-ledger, cross-references, allowlist, dangling-reference]
made_by: agent
agent_type: systems-architect
branch: main
pipeline_tier: full
affected_files:
  - scripts/finalize_adrs_crossrefs.py
  - rules/swe/adr-conventions.md
  - skills/software-planning/references/adr-authoring-protocols.md
  - .ai-state/idea_ledgers/IDEA_LEDGER.md
dissent: A one-entry-at-a-time allowlist widening is a local fix to a general defect — every `.ai-state/` artifact family added in future re-opens the same hole, and the honest terminal design may be to invert to `.ai-state/**/*.md` minus a small exclusion set.
---

## Context

`.ai-state/idea_ledgers/IDEA_LEDGER.md` grounded its most recent idea cluster in six
`dec-draft-<hash>` ids. None of them resolved: the drafts were promoted to `dec-216`…`dec-221`
roughly two and a half hours after the ledger entry was written, and finalize left the ledger
untouched because `.ai-state/idea_ledgers/` is not in its rewrite allowlist.

This is not a one-off. Every future finalize strands idea-ledger citations the same way, because
the causal chain is structural:

1. Ideas are promoted to the ledger *during or immediately after* a pipeline, when the grounding
   ADRs exist only as drafts. The dangle here was authored at 15:54 and finalized at 18:34 the
   same day — the ledger was correct when written.
2. `rules/swe/adr-conventions.md § Linking to ADRs` explicitly sanctions this: "While a pipeline
   is in flight, cite an unfinalized ADR inline by its `dec-draft-<hash>` id … the id survives
   finalize as a rewritten `dec-NNN`." The ledger author followed the convention.
3. `_cross_reference_targets()` in `scripts/finalize_adrs_crossrefs.py` does not yield anything
   under `.ai-state/idea_ledgers/`, so the promise in (2) was never kept for this file.

Two further facts bound the decision. First, finalize's own allowlist-gap detector
(`detect_unrewritten_ids`) **already scans every markdown file under `.ai-state/`** — including
`idea_ledgers/` — and its warning prescribes the remedy in words: *"outside the rewrite scope; add
it to `_cross_reference_targets()`"*. The detector and the rewriter disagree about what counts as
legitimate citation territory, and that disagreement is the defect. (The detector post-dates the
2026-06-05 dangle, so nothing warned at the time.)

Second, the rule text describing the scope had already drifted from the code it describes: the
allowlist yields `CONSULT_COSTS.md`, `CONSULT_PRIORS.md`, and `SYSTEM_DEPLOYMENT.md`, none of which
the rule listed. A reader checking whether their file was covered would have been told "no" for
three files that were in fact covered — the same class of failure as the idea ledger, inverted.

## Decision

Add `.ai-state/idea_ledgers/*.md` to finalize's cross-reference rewrite allowlist, and correct
`rules/swe/adr-conventions.md § Finalize Protocol` to match the allowlist the code actually walks.

State the operating principle in the rule so the next dangle is resolved the same way: **the scope
is widened, never worked around.** A citation that dangles because its file is unlisted is fixed by
listing the file — not by forbidding the citation.

The bounded-scope contract is preserved. The code's own docstring defines it as "an explicit
allowlist of named files and bounded subtrees — never an arbitrary whole-repo sweep." One named
subtree is added; the shape is identical to the `docs/` sweep already present, and nothing moves
toward a repo sweep. `scripts/` remains excluded for the reason it always was: its only draft-id
occurrences are test fixtures that must stay literal.

The six existing citations were repaired in place by resolving each hash through
`git log -S<hash>` to the fragment that carried it and then through the finalize rename commit;
all six resolved (`9c30645e`→`dec-221`, `52949236`→`dec-220`, `ccb70b10`→`dec-217`,
`11bc9d23`→`dec-218`, `7df1a638`→`dec-219`, `7aac9824`→`dec-216`), none dropped.

## Considered Options

### A. Widen the allowlist to include `.ai-state/idea_ledgers/` (chosen)

- **Pro** — keeps the authoring convention and the finalize promise consistent; the author writes
  the id the convention tells them to write, and it resolves after merge with no manual step.
- **Pro** — the rewrite matches *concrete promoted ids*, not the `dec-draft-` shape, so it cannot
  corrupt an unrelated hash-like string. The ledger holds no fixture wanting a literal hash.
- **Pro** — resolves the detector/rewriter disagreement in the direction the detector already
  assumes, rather than narrowing the detector to match a rewriter gap.
- **Con** — one more entry in a list that only ever grows; each new `.ai-state/` artifact family
  re-opens the question.

### B. Require the idea ledger to cite finalized `dec-NNN` only

- **Pro** — no code change; the rewrite scope stays exactly as narrow as it is today.
- **Con — decisive** — unsatisfiable at authoring time. When an idea is promoted, the grounding
  ADR usually has no `dec-NNN` yet. The author's only options are to invent an NNN (forbidden —
  finalize assigns it), to omit the grounding (which is the entire value of the citation), or to
  return after merge and hand-patch. The third is what nobody did, and there is no gate that would
  have caught it.
- **Con** — carves a per-artifact exception out of a general convention with no principled basis.
  Every other citing artifact (`DESIGN.md`, the tech-debt ledgers, `docs/`) is allowed to cite
  drafts; singling out the idea ledger would make the rule harder to state than to follow.

### C. Invert the allowlist to `.ai-state/**/*.md` + `docs/**/*.md` minus an exclusion set

- **Pro** — closes the defect *class* rather than this instance; matches the detector's scan
  exactly, so the two can never disagree again.
- **Con** — a larger change than the finding warrants today, and it inverts a deliberate default
  (allowlist over denylist) that was chosen for a reason. Deferred, with a stated trigger below.

## Consequences

**Positive.** Idea-ledger citations resolve after merge without manual intervention. The rule text
now matches the code for all ten named locations, so a reader can trust it when deciding where to
cite from. The stated widen-never-work-around principle gives the next dangle a default resolution.

**Negative.** The allowlist grows by one, and the general defect (a new `.ai-state/` artifact
family arriving uncovered) is unaddressed. The mitigation is that the gap detector *does* cover
`.ai-state/**/*.md`, so the next such gap surfaces as a warning at finalize time rather than as a
dangling id discovered months later by an audit — which is what happened here.

**Neutral.** No component is added, removed, or reassigned: `finalize_adrs_crossrefs.py` already
owns the allowlist and continues to. Category is `behavioral`, not `architectural` — the falsifier
in `rules/swe/adr-conventions.md § What makes a decision architectural` asks for the name of a
component that moved, and there is none; `affected_files` touches no canonical block, shipped
template, or onboard-contract phase.

## Disconfirmation

Recorded voluntarily; not required at `category: behavioral`.

- **Falsifier** — the decision is wrong if the idea ledger turns out to legitimately need literal
  `dec-draft-<hash>` text preserved across finalize (as `scripts/` fixtures do). Evidence would be
  a ledger entry whose meaning depends on the pre-finalize id. No such entry exists today, and the
  ledger's purpose — grounding ideas in durable decisions — argues it never should.
- **Steelmanned runner-up** — Option C. Its case is genuinely strong: the allowlist and the
  detector scan two different sets, and every one-entry widening is a patch on that mismatch rather
  than a fix. If the exclusion set stayed small and legible (`scripts/`, fixtures), C would deliver
  the same benefit permanently for comparable effort. It loses today only on scope discipline — one
  finding does not license redesigning a mechanism that is otherwise working.
- **Reversal trigger** — a *second* allowlist widening for a different `.ai-state/` artifact
  family. Two instances make it a pattern, and the next one should adopt Option C rather than
  extend the list a third time.
