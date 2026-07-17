---
id: dec-271
title: Manifest-only version identity for canonical CLAUDE.md block refresh
status: accepted
category: architectural
date: 2026-07-16
summary: Refresh onboarded CLAUDE.md blocks via a plugin-shipped git-derived historical-hash manifest that classifies each live block (absent/current/stale/modified) with no in-file marker and no consumer-site git — auto-replacing stale boilerplate, refusing to clobber locally-modified blocks; resolves td-055.
tags: [canonical-blocks, onboarding, refresh, version-identity, token-budget, tech-debt, td-055, claude-md]
made_by: agent
agent_type: systems-architect
branch: worktree-block-refresh-mechanism
pipeline_tier: standard
affected_files:
  - scripts/sync_canonical_blocks.py
  - scripts/canonical_block_identity.py
  - scripts/refresh_claude_blocks.py
  - claude/canonical-blocks/block-history.json
  - commands/refresh-claude-blocks.md
  - commands/onboard-project.md
  - docs/existing-project-onboarding.md
re_affirms: dec-270
dissent: A bare CLAUDE.md block now carries no visible sign that it is Praxion-managed, versioned content — a human or non-Praxion-aware agent reading the file cannot tell provenance without the manifest + command, and the whole scheme leans on git-derived history whose depth stops at the canonical file's creation commit.
---

## Context

`dec-270` trimmed the `agent-pipeline` canonical block to a pointer and, as an explicit Consequence, noted that **already-onboarded projects keep the old block until refreshed — Phase 6's per-heading idempotency predicate (`heading present → skip`) skips existing headings and no refresh mechanism exists (tracked as `td-055`)**. Onboarded CLAUDE.md blocks are therefore frozen at their install-time version, and appended blocks carry no identity to distinguish stale-canonical from locally-modified content.

The fix must satisfy four constraints (researcher-verified):

1. **No `.git` at consumer install sites.** The plugin lands as a flat copy under `~/.claude/plugins/cache/<mkt>/i-am/<version>/`; `git log` fails there. Any pre-existing-estate matching must ship its own record of historical content — it cannot query git at the consumer site.
2. **Four passing test contracts** in `hooks/test_onboard_praxion_block.py` bound anything embedded in a block: byte-identity (canonical file == fence == installed body, exactly), 250-token/block budget, forbidden `dec-\d{3,}`-style patterns, and a `startswith(heading)` anchor. `behavioral-contract` (243 tok) and `praxion-process` (244 tok) sit within ~6-8 tokens of the ceiling.
3. **A locally-customized block must survive** (golden case: a project appended a bespoke naming-note paragraph *inside* a block section). A binary "regenerated, do not edit" marker (Go-style) is too coarse.
4. **`dec-270` just reclaimed ~450 always-loaded tokens/session** across managed projects; a fix that spends that back is a regression.

The brief's `td-055` sketch and one Key Signal assumed an **in-file version marker**. The open question the orchestrator posed: given the manifest is required regardless (constraint 1), does a marker earn its place at all?

## Decision

Adopt **manifest-only version identity**:

- A build-time mode in `scripts/sync_canonical_blocks.py` (`--write-history`/`--check-history`) enumerates each refresh-eligible canonical file's git history, normalizes + hashes + dedupes each historical body, and writes a deterministic JSON manifest `claude/canonical-blocks/block-history.json` (`{ blocks: { <slug>: { current, history[] } } }`) that ships in the plugin. `--check-history` is wired into pre-commit so the manifest can never drift silently from the canonical files.
- A shared stdlib module `scripts/canonical_block_identity.py` owns the *single* `normalize_block_body` + `hash_block_body` functions and `REFRESHABLE_SLUGS` (a subset of `BLOCKS`), imported by both the generator and the consumer script so their normalization cannot diverge.
- A consumer-site script `scripts/refresh_claude_blocks.py` (resolved via plugin path per `dec-113`, guarded against plugin-source repos per `dec-081`) extracts each live block body from the project's `CLAUDE.md`, hashes it, and classifies against the manifest: `absent` / `current` / `stale` / `modified`. In apply mode it appends `absent`, replaces `stale` in place, and **never touches `modified`** — emitting a diff + a pointer instead (refuse-to-clobber). It never runs `git`.
- A dedicated command `commands/refresh-claude-blocks.md` (thin wrapper, mirrors `/upgrade-project`) applies the safe actions and drives an `AskUserQuestion` disposition loop (Replace / Keep local / Skip) for each `modified` block.
- `onboard-project.md` Phase 6's per-heading predicate is upgraded to call the script in apply mode (self-healing the safe cases like Phase 4 self-heals stale hook symlinks; deferring `modified` to the command). `new-project.md` gains no refresh logic (greenfield is first-run-only).

**No in-file marker is written into any block.** The refresh-eligible set is the four unconditional byte-identical-install blocks (`agent-pipeline`, `compaction-guidance`, `behavioral-contract`, `praxion-process`); template-filled and conditional blocks are excluded by registry membership.

## Considered Options

### Option A — In-file marker (`<!-- praxion-block:<slug>@<hash> -->`)
Self-describing to a bare reader; matches the brief's Health-Guard allowance. **Rejected:** costs ~15-19 always-loaded tokens/block forever (partially reverses `dec-270`); flips the 250-token test red on two blocks; must live *inside* the canonical file to satisfy byte-identity, entangling every canonical edit with a self-referential hash regeneration; leaks into `AGENTS.md.tmpl` via the Codex bridge — **and still needs the manifest for the pre-marker case** (constraint 1). Marker = manifest + net cost.

### Option B — Sidecar `blocks:{slug:hash}` in `.ai-state/.praxion-onboard.json`
Zero token cost; strongest external precedent (chezmoi/copier/cruft anchor identity in a sidecar). **Rejected:** still needs the manifest for estates predating the field (constraint 1); adds a Phase-6 write path and a consistency invariant that *lies* when a user hand-edits CLAUDE.md; its only unique benefit (an O(1) "is-installed-version-current" fast-path) saves nothing over a small-dict manifest lookup, and detecting local modification still requires hashing the live body. Sidecar = manifest + a second, lie-prone mechanism.

### Option C — Manifest-only — chosen
The manifest is *required regardless* (constraint 1). Once it exists it classifies **every** estate — marker-stamped or not — by hashing the live body. So the manifest alone is a complete solution; A and B are each "manifest **plus** a second mechanism." Manifest-only preserves `dec-270`'s budget, perturbs no test contract or byte-identity mirror (no canonical body changes), and derives history from git rather than hand-maintenance. Cost: CLAUDE.md is not self-describing to a bare reader (weak — HTML comments are invisible in rendered views anyway, and `dec-270` already located provenance outside the block).

## Consequences

**Positive:** `td-055` resolved with zero always-loaded token growth; the four existing block tests, the sync `--check`, and the byte-identical mirror all stay green with no edits; pre-history estates are refreshable *by construction* (no `.git`, no marker needed); one build-time source of truth derived from git; the extraction boundary (`heading → next ## heading`) *is* the customization-protection mechanism — appended local content lands in the hashed body → `modified` → refused.

**Negative:** a bare CLAUDE.md block carries no inline provenance (dissent); normalization sensitivity is a real correctness risk (mitigated by the shared-module single-normalization invariant + round-trip test; fails safe toward refusal); git-history depth stops at the canonical file's creation commit, so content installed by a Praxion predating the canonical-file extraction falls to `modified` (safe-failing, rare); a new deterministic manifest must stay in sync with the canonical files (gated by `--check-history` in pre-commit).

## Disconfirmation

- **Falsifier:** a real onboarded estate whose block is genuinely stale-unmodified is classified `modified` (or vice-versa) because normalization between the shipped canonical and the appended consumer copy diverges — i.e., the shared-normalization invariant fails to make generation-time and match-time hashes agree on real CLAUDE.md shapes. If refresh routinely refuses blocks it should auto-replace, the manifest-only approach's core promise (safe automatic stale-replacement) is unmet and a marker/sidecar recording the *exact* installed bytes would have avoided the normalization guess.
- **Steelmanned runner-up:** the **hybrid sidecar-cache** (manifest for correctness + a `.ai-state/.praxion-onboard.json` `blocks:{slug:hash}` map written at install/refresh recording the *exact* installed hash). This sidesteps normalization entirely for post-field estates — the recorded hash is compared to the live hash with the *same* extraction, and any divergence is unambiguously a local edit; the manifest is consulted only to decide current-vs-stale. It is the more robust design *if* normalization proves fragile in the field. It was rejected on Simplicity First (a second mechanism, a write path, a lie-risk on direct edits) and because the shared-normalization invariant is expected to hold — but if R1 (normalization) bites in practice, this is the pre-designed escalation.
- **Reversal trigger:** normalization misclassification is observed on ≥1 real managed project (the shared function can't reconcile shipped vs. appended bytes across the estate), **or** the plugin packaging changes so canonical-file git history is no longer enumerable at build time (breaking the manifest generator's history source). Either signal should promote the hybrid sidecar-cache from steelman to design.

## Prior Decision

Re-affirms `dec-270` (agent-pipeline block → minimal pointer). `dec-270`'s ~450-token/session budget win was re-challenged here by Option A (the in-file marker would spend part of it back on every block, every session, every managed project). That option was considered and rejected specifically to preserve `dec-270`'s posture: the refresh mechanism adds **zero** always-loaded tokens. `dec-270` remains `accepted` and unchanged; this ADR realizes the refresh mechanism its Consequences deferred to `td-055`. A future supersession of this re-affirmation would require evidence that the marker's self-description benefit outweighs its measured always-loaded cost across the managed-project fleet.
