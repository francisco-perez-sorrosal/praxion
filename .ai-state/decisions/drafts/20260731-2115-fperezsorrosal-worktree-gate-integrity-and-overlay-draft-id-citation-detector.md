---
id: dec-draft-a8d0f148
title: The draft-id detector is an exact pattern plus an explicit per-line exemption, not a heuristic
status: proposed
category: architectural
date: 2026-07-31
summary: Enforce the draft-ADR-id prohibition with a literal pattern and the existing per-line ignore marker, remediating every live citation first; reject lexical-shape discrimination and path allowlists.
tags: [id-citation-discipline, gate-liveness, scope-fidelity, adr, detection-strategy]
made_by: agent
agent_type: systems-architect
branch: worktree-gate-integrity-and-overlay
pipeline_tier: full
affected_files:
  - scripts/check_id_citation_discipline.py
  - rules/swe/id-citation-discipline.md
  - tests/test_check_id_citation_discipline.py
dissent: >
  A pattern-scoped path allowlist for the four fixture-bearing files would cost four
  entries instead of eighteen scattered per-line markers, and eighteen markers is real
  visual noise in files that will accrue more; the marker route wins only because a path
  allowlist blinds the gate to a genuinely new dangling citation added to an exempted file.
---

# The draft-id detector is an exact pattern plus an explicit per-line exemption, not a heuristic

## Context

`rules/swe/id-citation-discipline.md`'s own lifecycle table lists `dec-draft-<hash>` as
**never** allowed in code, and `scripts/check_id_citation_discipline.py` — the mechanical
enforcer of that table — has no pattern for it. A documented prohibition with zero
enforcement.

Two repairs were considered and rejected before this pipeline began, correctly: widening
`finalize_adrs.py`'s rewrite allowlist contradicts that script's explicit NOTE and treats the
citations as an addressing problem rather than the defect they are; and a blanket pattern
shipped against an unremediated tree reddens thirteen files and can never merge.

The corpus was enumerated directly. Sixteen distinct draft-id literals appear across
thirteen scannable code files, splitting into eight synthetic fixture ids and eight ids that
are real citations to promoted ADRs. The synthetic set — `abcd1234`, `c0ffee11/22/33`,
`feedface`, `aaaaaaaa`, `a1b2c3d4`, `e5f6a7b8` — is uniformly word-shaped, repeated, or
sequential, and this observation was offered as the detector's design affordance.

## Decision

**The discriminator is the exemption surface, not the pattern.**

- Add one entry to `PATTERNS` in `scripts/check_id_citation_discipline.py` matching the
  exact literal `\bdec-draft-[0-9a-f]{8}\b`.
- Every legitimate fixture literal carries the **existing per-line
  `id-citation-discipline:ignore` marker** — the route the rule file already names as
  sanctioned for "detector scripts describing the forbidden patterns".
- **Every live citation is remediated to its finalized `dec-NNN` before the pattern ships.**
  The remediation is mechanical, not a judgment call: a draft id is `sha1(fragment
  filename)[:8]`, the fragment filename survives in git history, and its slug maps one-to-one
  onto a finalized `<NNN>-<slug>.md`. All eight ids were resolved by this route and verified
  in the authoring worktree.
- Where a draft id appears in **prose narrating the historical bug**, the sentence is
  rewritten to name the finalized `dec-NNN` rather than carrying a marker. `dec-NNN` in a
  comment is explicitly permitted, and it resolves for the reader where the hash does not.
- No new exemption data structure is introduced. `EXEMPT_EXACT_PATHS` and
  `EXCLUDED_PATH_FRAGMENTS` are left untouched.

## Considered Options

### Option A — A lexical-shape heuristic separating authored-looking from random-looking hex (rejected)

Separate `c0ffee11`, `feedface`, `aaaaaaaa` from `b068ad8e`, `c566b978`, `4dc602ce` by their
appearance. It fits the present corpus perfectly and requires no remediation.

Rejected, and this is the load-bearing rejection. Such a discriminator cannot be proven
correct and cannot be scope-checked: clause 5 of `rules/swe/gate-liveness.md` requires diffing
a gate's *computed* input set against its *documented* one, and a "looks random" predicate has
no statable computed set. It fails the first time someone writes a plausible-looking fixture
or a real `sha1` prefix happens to contain a repeated run — both of which are ordinary events
in an eight-hex-digit namespace. The observed split is a correct description of today's data;
it is not a rule, and a gate built on it would be unfalsifiable in exactly the way this
pipeline exists to eliminate.

### Option B — A path allowlist for the four fixture-bearing files (rejected)

Add the four files to `EXEMPT_EXACT_PATHS`, or introduce a pattern-scoped
`DRAFT_ID_FIXTURE_PATHS` that exempts only this pattern there. Four entries instead of
eighteen per-line markers, and no visual noise.

Rejected because it blinds the gate to a genuinely new dangling citation added to an
exempted file, and `scripts/test_finalize_adrs.py` — the test suite for the draft-id
rewriter — is precisely the file most likely to accrue both kinds. `EXEMPT_EXACT_PATHS` is
additionally all-pattern, so it would also stop enforcing `REQ-`/`AC-`/`Step N` in those
files, which no evidence justifies.

### Option C — Widen `finalize_adrs.py`'s rewrite allowlist to include `tests/` and `fitness/` (rejected upstream, restated)

Contradicts the script's own NOTE and, more importantly, misidentifies the defect: the rule
forbids draft ids in **any** committed code, so rewriting them automatically would keep the
tree green while the prohibition stayed unenforced. The citations are the bug, not the
allowlist.

### Option D — Ship the pattern first, remediate afterwards (rejected)

Rejected on the principle that a gate the tree fails is not a shipped gate — it is a broken
commit hook that every contributor learns to bypass.

## Consequences

**Positive.**

- Perfect scope fidelity. The computed input set is a literal pattern over a known file
  corpus; the exemptions are enumerable with one `grep`, and each one is individually visible
  in diff review.
- The checker change is a single tuple entry. No new data structure, no new code path, no new
  concept for a future maintainer to learn.
- Each future fixture literal costs one deliberate marker — friction proportional to the risk,
  applied at the moment the literal is written.
- Thirteen real citation sites become resolvable references rather than dangling ones, and
  the rewrite target is derivable rather than guessed.

**Negative / accepted.**

- Eighteen per-line markers is real visual noise, concentrated in four test files.
- A contributor can silence a genuine violation by pasting the marker. This is true of every
  escape hatch in the repository and is mitigated only by review; the marker's virtue is that
  it is conspicuous in a diff where a path allowlist entry is not.
- The remediation pass touches eleven files that are otherwise unrelated to this work,
  widening the change's surface.

## Disconfirmation

**Falsifier.** If per-line markers accumulate past roughly thirty sites, or if a marker is
ever found on a line carrying a genuine dangling citation, the per-site discipline has failed
to scale and a pattern-scoped path allowlist — Option B's narrower variant — becomes the
better instrument. Symmetrically, if a real draft id is ever added to code and merged with the
pattern shipped and no marker present, the gate is not wired where it claims to be.

**Steelmanned runner-up.** Option B's pattern-scoped variant is stronger than the rejection
concedes. It exempts only this one pattern in only four named files, leaving every other
citation class enforced there; it costs four reviewable entries rather than eighteen scattered
markers; and the "blinds the gate to a new violation in an exempted file" objection is
speculative, whereas the noise cost is certain and immediate. If the marker count grows, the
correct move is to migrate to that variant rather than to keep adding markers — and the
migration is mechanical, because every marker site is greppable.

**Reversal trigger.** Revisit when any of: (a) marker sites exceed thirty; (b) a fifth
fixture-bearing file appears, suggesting the pattern is systemic rather than incidental to
ADR-tooling tests; or (c) the fragment-id scheme changes such that draft ids are no longer
eight-hex-digit, which would invalidate the pattern's exactness and force a re-derivation.
