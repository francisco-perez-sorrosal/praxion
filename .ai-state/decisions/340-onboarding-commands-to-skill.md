---
id: dec-340
title: Unify the two onboarding commands into one user-invocable skill plus one entry script
status: accepted
category: architectural
date: 2026-08-30
summary: Retire /new-project and commands/onboard-project.md in favor of skills/onboard-project/ (SKILL.md + 5 references) driven by one phase engine, with new_project.sh replaced by scripts/onboard-project.
tags: [onboarding, skills, commands, architecture, deduplication]
made_by: agent
agent_type: systems-architect
branch: worktree-onboarding-unification
pipeline_tier: full
affected_files:
  - skills/onboard-project/SKILL.md
  - skills/onboard-project/references/phases-core.md
  - skills/onboard-project/references/phases-optional.md
  - skills/onboard-project/references/claude-md-blocks.md
  - skills/onboard-project/references/seed-pipeline.md
  - skills/onboard-project/references/detection.md
  - skills/onboard-project/references/shared-procedures.md
  - scripts/onboard-project
  - commands/onboard-project.md
  - commands/new-project.md
  - new_project.sh
  - docs/onboarding.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-09, REQ-10]
dissent: >
  Keeping two thin command stubs that dispatch into the shared skill would have preserved
  /new-project, the pre-commit regex, and the ~/.local/bin/new-project symlink at near-zero
  migration cost — the duplication being removed lives in the phase bodies, not in the entry
  points, so deleting the entry points buys deduplication we would already have had.
---

# Unify the two onboarding commands into one user-invocable skill plus one entry script

## Context

Praxion carries two onboarding surfaces that converge on one end state: `commands/new-project.md` (837 lines, greenfield, launched by `new_project.sh`) and `commands/onboard-project.md` (1,650 lines, existing-project retrofit). Research established that the overlap is not incidental — the AaC sub-flow is authored twice, the Obsidian sub-flow once plus once by reference, all seven canonical `CLAUDE.md` blocks are embedded twice (with a 641-line script, `sync_canonical_blocks.py`, existing solely to hold the two copies byte-identical), the greenfield-shape and plugin-source guards are hand-encoded twice each and synced by nothing, and the same four `CLAUDE.md` headings are classified by two different idempotency mechanisms.

Claude Code has merged custom commands into skills: a command file and a skill directory both produce `/<name>` and behave identically, with skills a strict superset (`disable-model-invocation`, `argument-hint`, and supporting files for progressive disclosure). Plugin commands and plugin skills are both namespaced `/praxion:<name>`, so the invocation name is preserved exactly. Verified against `code.claude.com/docs/en/skills.md` (2026-08-30).

## Decision

Replace the two commands and the root script with:

- `skills/onboard-project/SKILL.md` — the phase-engine driver (pre-flight, mode resolution, `§Flow`, `§Phase Gates`, `§Idempotency Predicates`), `disable-model-invocation: true`.
- Five `references/` files loaded on demand: `phases-core.md`, `phases-optional.md`, `claude-md-blocks.md` (the seven canonical blocks, embedded once), `seed-pipeline.md` (the ex-`/new-project` greenfield content as Phase 0s), `detection.md` (single source for state classification and the two hard guards), `shared-procedures.md` (stack-command resolution, hub-SHA resolution, version-aware staleness).
- `scripts/onboard-project` — single bash entry: prereqs, six-state detection, minimal scaffold when empty, editor launch, `exec claude` with a seed prompt carrying a four-line trailer.
- `docs/onboarding.md` — replaces both onboarding docs.

The three entry modes (`new`, `existing`, `hackathon`) parameterize one engine: they select which phases run and with what gate default. No phase body is authored twice. `/new-project` retires; `/praxion:onboard-project` is unchanged. The delete and the add land in one commit (never two live surfaces under one name).

## Considered Options

### Option A — One skill plus one entry script (chosen)

- Pro: one phase engine; ~2,500 lines of duplicated prose collapse to one authored copy; the seed prompt shrinks from an 837-line command body to a ~400-line `SKILL.md`; progressive disclosure means hackathon mode never loads the opt-in phase bodies; `disable-model-invocation` *enforces* what the command regime could only intend.
- Con: `/new-project` and the `~/.local/bin/new-project` symlink go away; `.pre-commit-config.yaml`, `install_claude.sh`, `rules/_manifest.yaml`, `sync_canonical_blocks.py`, and 8 test files must be re-anchored in the same change.

### Option B — Two thin command stubs dispatching into a shared skill

- Pro: `/new-project` survives; the pre-commit regex, the bin symlink, and the plugin registration need no edit; the deduplication (which lives in the phase bodies) is achieved anyway.
- Con: preserves an entry point whose only remaining content is "call the other thing" — a name users must still choose between, which is precisely the UX problem the task exists to remove. Three files where one suffices, and the stubs' guards would still need to agree with `detection.md`.

### Option C — Merge both commands into one command file

- Pro: no migration of the parser, the sync registry, or the plugin surface; the smallest possible diff.
- Con: a single ~2,000-line command with no supporting-file mechanism — the whole body enters context on every invocation, including hackathon mode, and the file exceeds any sane ceiling. Forfeits `disable-model-invocation`.

## Consequences

**Positive**

- One authored copy of every phase body, payload, guard, and shared procedure.
- The canonical-block sync surface halves: seven blocks × one consumer instead of two.
- Six test files lose their `NEW_PROJECT_FILE` regression half, because the duplication it guarded no longer exists.
- Progressive disclosure becomes available to onboarding for the first time.

**Negative**

- A user-visible CLI rename (`new-project` → `onboard-project` in `~/.local/bin/`), with no shim.
- The cut must be atomic; a partial landing produces duplicate `/praxion:onboard-project` surfaces.
- Two consumers can fail *open* if re-anchored wrongly (the pre-commit `files:` regex; `contract.py`'s parser returning empty sets). Each gets a dedicated canary test.

## Disconfirmation

**Falsifier.** If, after the migration, `tests/consumer_layout/` reports the same phase set and payloads it does today *only because* the parser is silently returning empty results — or if `sync_canonical_blocks.py --check` passes because it now iterates zero onboarding consumers — the consolidation would have removed the verification rather than the duplication. Concretely: `phase_headings()` returning fewer than 15 ids, or `COMMAND_FILES` not containing `claude-md-blocks.md`, falsifies the claim that the contract survived the move.

**Steelmanned runner-up.** Option B is stronger than it looks. Every duplication the research found lives in the phase *bodies*; none of it lives in the entry points. A shared skill with two 20-line stubs removes 100% of the duplication while touching zero consumers: `.pre-commit-config.yaml`'s regex, `install_claude.sh`'s eight symlink sites, `rules/_manifest.yaml`'s path globs, and `sync_canonical_blocks.py`'s `_ONBOARDING_PAIR` all keep working unchanged, and the atomic-cut risk disappears entirely. The case against it is a UX judgment (one entry point beats two) rather than a structural one — and UX judgments are exactly the kind that get overturned by user feedback.

**Reversal trigger.** Revisit if (a) users report confusion or breakage from the retired `/new-project` name within one release cycle, (b) the skill's `references/` loading proves unreliable in a seeded session that has no prior plugin-path resolution, or (c) Claude Code changes skill discovery such that `disable-model-invocation` skills stop surfacing as `/praxion:<name>`.
