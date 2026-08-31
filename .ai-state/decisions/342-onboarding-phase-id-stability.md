---
id: dec-342
title: Preserve onboarding phase identifiers verbatim across the skill migration
status: accepted
category: behavioral
date: 2026-08-30
summary: Phase ids 0.5, 1-7, 5b, 8, 8b-8e, 9 and every "Sub-step N.M" heading survive the commands-to-skill move unchanged; the seed phase takes the new id 0s.
tags: [onboarding, contracts, testing, migration]
made_by: agent
agent_type: systems-architect
branch: worktree-onboarding-unification
pipeline_tier: full
affected_files:
  - skills/onboard-project/SKILL.md
  - skills/onboard-project/references/phases-core.md
  - skills/onboard-project/references/phases-optional.md
  - tests/consumer_layout/contract.py
affected_reqs: [REQ-09]
---

# Preserve onboarding phase identifiers verbatim across the skill migration

## Context

Onboarding phase numbers are a published contract far beyond the command file that defines them. A cross-reference sweep found roughly 26 sites outside the two command files citing a specific phase by number — architecture docs (`.ai-state/DESIGN.md`, `docs/architecture.md`), rules (`coding-style`, `shipped-artifact-isolation`), agents, four other commands, seven skills, `scripts/CLAUDE.md`'s lock-step documentation with `upgrade_project_pins.sh`, and five test files that assert on exact `§Phase N` / `Sub-step N.M` headings.

`tests/consumer_layout/contract.py` goes further: it *parses* the heading grammar (`## §Phase N` where `N` matches `[0-9]+(?:\.5)?[a-z]?`, `### Sub-step N.M`, the `§Flow` and `§Idempotency Predicates` tables) and executes the extracted shell fragments against a scratch tree. Its module docstring rejects a hand-written expectation list by design.

The sub-phase lettering (`8b`–`8e`, `5b`, `0.5`) is an artifact of incremental growth rather than a design, which makes renumbering tempting during a restructuring.

## Decision

Keep every existing phase identifier verbatim: `0.5, 1, 2, 3, 4, 5, 5b, 6, 7, 8, 8b, 8c, 8d, 8e, 9`, including every `### Sub-step N.M` heading and the `## §Phase N` / `## §Flow` / `## §Idempotency Predicates` grammar. Introduce exactly one new id, `0s`, for the greenfield seed phase — chosen because `contract.py`'s existing `_PHASE_ID` regex already accepts it (verified by inspection), so the parser needs no regex change. One further id, `5b.t`, names the hackathon teardown sub-step under the existing `Sub-step` grammar.

Consequently `tests/consumer_layout/contract.py` re-anchors by replacing a single file constant with a three-file tuple joined by an internal sentinel; every extraction function below `onboard_text()` is unchanged.

## Considered Options

### Option A — Stable ids (chosen)

- Pro: ~21 prose citations and 5 test assertions need no edit; the parser re-anchors by file list alone; the lock-step documentation with `upgrade_project_pins.sh` keeps naming live phases.
- Con: the new design inherits an accreted numbering vocabulary it would not have chosen greenfield.

### Option B — Renumber into a clean 1..N sequence

- Pro: the phase list finally reads as designed rather than grown; new phases append naturally instead of acquiring a letter.
- Con: a coordinated rewrite across ~26 sites whose dominant failure mode is silent — only the 5 test files fail loudly; the 21 prose citations would simply become wrong, and nothing gates them.

## Consequences

**Positive** — the largest single migration risk (a 367-line parser over a heading grammar) reduces to a file-list change. External citations are unaffected, so the blast radius of this refactor stops at the onboarding surface itself.

**Negative** — a future reader still meets `8b`, `8c`, `8d`, `8e` and must learn that the lettering means "opt-in sub-phase of 8", not a sequence. The `0s`/`0.5` pair is likewise non-obvious ordering.

## Disconfirmation

**Falsifier.** If after the move `phase_headings()` (parsed from the concatenated skill files) does not equal the `§Flow` table's id set, a phase has landed in neither reference file or in both, and the "ids survived" claim is false. Equally: any external site citing a phase number that no longer resolves to a heading in the skill falsifies it.

**Steelmanned runner-up.** Renumbering is defensible precisely *because* this is the one moment the whole surface is being rewritten anyway. The 26 citations must be read during the migration regardless (each names a file path that is changing), so the marginal cost of also correcting the number is small, and it is the only opportunity for the next decade. Choosing stability locks in an accreted scheme to avoid a cost that will never again be this low.

**Reversal trigger.** Revisit if the phase set grows past the point where the lettering collides (a second sub-phase of 5, or a phase needing a third level), or if `contract.py` is rewritten to a non-regex extraction strategy that no longer depends on the heading grammar — either removes the main reason for stability.
