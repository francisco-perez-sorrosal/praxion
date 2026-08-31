---
id: dec-draft-25d94017
title: One idempotency mechanism for canonical CLAUDE.md blocks; one embedding site for the canonical-block sync
status: proposed
category: architectural
date: 2026-08-30
summary: Phase 6 becomes the sole writer of canonical CLAUDE.md blocks — refresh_claude_blocks.py's 4-state classifier for the four refreshable blocks, heading-grep for the three conditional ones — and sync_canonical_blocks.py's onboarding consumer pair collapses to a single file.
tags: [onboarding, canonical-blocks, idempotency, deduplication, sync]
made_by: agent
agent_type: systems-architect
branch: worktree-onboarding-unification
pipeline_tier: full
affected_files:
  - skills/onboard-project/references/claude-md-blocks.md
  - skills/onboard-project/references/phases-core.md
  - scripts/sync_canonical_blocks.py
  - scripts/check_architecture_projection.py
  - .pre-commit-config.yaml
  - scripts/test_sync_canonical_blocks.py
affected_reqs: [REQ-07, REQ-08]
dissent: >
  The two-class split (4-state classifier for four blocks, heading-grep for three) is still two
  mechanisms wearing one name. A uniform flat heading-grep for all seven would be genuinely
  single-mechanism, materially simpler to read, and would drop a script dependency — at the cost
  of drift detection that no evidence yet shows users actually rely on.
---

# One idempotency mechanism for canonical CLAUDE.md blocks; one embedding site for the canonical-block sync

## Context

Today the same four canonical `CLAUDE.md` headings are classified by two different mechanisms. `/new-project` Flow step 10 uses flat `grep -q '^## X$'` heading predicates; `/onboard-project` Phase 6 delegates the same four blocks to `scripts/refresh_claude_blocks.py --apply`, which classifies each live block `absent` / `current` / `stale` / `modified` against a historical-hash manifest and self-heals stale blocks while refusing to clobber modified ones. A block installed by the simpler path acquires drift detection only if the user later runs the other command.

Separately, all seven onboarding canonical blocks are embedded **twice** — once in each command file — with `scripts/sync_canonical_blocks.py`'s `_ONBOARDING_PAIR` and 641 lines of machinery existing to keep the two copies byte-identical. The pair is also a transitive dependency of `scripts/check_architecture_projection.py`'s §4 "published half" reconciliation and of a `.pre-commit-config.yaml` `files:` regex.

The task mandate requires picking one idempotency mechanism, with justification.

## Decision

**One writer.** Phase 6 of the unified engine is the sole writer of canonical `CLAUDE.md` blocks, in every mode. The `/new-project` flat-grep path is deleted.

**Two block classes, one rule each — and the classes track a real distinction:**

- *Versioned payload* — the four refreshable blocks (`agent-pipeline`, `compaction-guidance`, `behavioral-contract`, `praxion-process`): `refresh_claude_blocks.py`'s 4-state classifier. These have a stable canonical body, so a content hash is meaningful and staleness is a real state.
- *Conditional payload* — `project-essentials` (placeholder-filled per project, so no stable hash exists), `hackathon-mode` and `obsidian-integration` (presence is a mode/opt-in fact, not a version fact): heading-grep predicate.

**One embedding site.** The seven blocks are embedded once, in `skills/onboard-project/references/claude-md-blocks.md`. `_ONBOARDING_PAIR` becomes `_ONBOARDING_CONSUMERS`, a one-element tuple. `sync_canonical_blocks.py` survives — canonical-source-to-consumer drift is still a real defect class — with half the surface it guards today.

## Considered Options

### Option A — 4-state for the four refreshable blocks, heading-grep for the three conditional ones (chosen)

- Pro: preserves drift detection where it is meaningful; deletes the drift-blind path; the split follows an existing boundary (`REFRESHABLE_SLUGS` in `canonical_block_identity.py`) rather than inventing one.
- Con: a reader must learn a two-class distinction.

### Option B — Flat `grep -q` for all seven

- Pro: genuinely one mechanism, trivially readable, no script dependency at onboarding time.
- Con: loses drift detection entirely. A user-edited block is either silently left stale forever or silently re-appended; `/refresh-claude-blocks` and `block-history.json` lose their consumer.

### Option C — 4-state for all seven (extend `REFRESHABLE_SLUGS`)

- Pro: uniform, and the strongest guarantee.
- Con: impossible for `project-essentials`, whose body is filled with per-project commands and therefore has no stable hash; wrong for the two conditional blocks, where absence is a legitimate steady state rather than drift.

## Consequences

**Positive**

- The same heading can no longer be classified two ways.
- The byte-identity-across-two-files problem ceases to exist; the pre-commit gate and the architecture-projection reconciliation each watch one file instead of two.
- Six `tests/commands/test_onboard_*.py` files shed their `NEW_PROJECT_FILE` regression half.

**Negative**

- Every mode now depends on `refresh_claude_blocks.py` being resolvable (previously only the existing-project path did). The degraded branch — plugin path undetected — must skip Phase 6 with a warning rather than fall back to a grep append, or the deleted mechanism returns by the back door.
- Two consumers re-anchor in ways that fail *open*: the `.pre-commit-config.yaml` `files:` regex (a wrong pattern means the gate silently never fires) and `check_architecture_projection.py`'s textual `BLOCKS` parse against a now-1-tuple consumers list.

## Disconfirmation

**Falsifier.** If `sync_canonical_blocks.py --check` passes while `COMMAND_FILES` contains no onboarding consumer — or if the pre-commit `files:` regex matches nothing under `skills/` — the sync is green because it is checking nothing, and the consolidation removed the guarantee instead of the duplication. Each is covered by a dedicated canary test.

**Steelmanned runner-up.** Option B's case is stronger than the drift-detection argument admits. The 4-state classifier exists to handle a scenario nobody has measured: a user hand-editing a canonical block and later wanting Praxion to notice. Every managed project gets `/refresh-claude-blocks` as an explicit, on-demand remedy for exactly that case, so onboarding does not need to carry the machinery inline. Choosing B would give a genuinely single mechanism (which is what the mandate literally asks for), delete a runtime dependency from the onboarding path, and let `block-history.json` serve only the refresh command that actually needs it. The chosen option keeps two rules and calls the split principled — which is true, but it is still two rules.

**Reversal trigger.** Revisit if `refresh_claude_blocks.py`'s `modified` classification proves to fire mostly on false positives (formatting normalization, line-ending drift) in real managed projects, or if the plugin-path-undetected degraded branch turns out to be common enough that Phase 6 skips frequently — either would mean the classifier is costing more than the drift detection is worth.
