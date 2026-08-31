---
id: dec-draft-57d9129b
title: Seed the permissions baseline at greenfield scaffold time; hoist Phase 5b ahead of the seed pipeline
status: proposed
category: architectural
date: 2026-08-30
summary: The bash scaffold writes a minimal .claude/settings.json carrying only the permissions.allow baseline, so the empty-.claude contract becomes a seeded-.claude contract; Phase 5b is hoisted ahead of Phase 0s in new mode to cover direct skill invocation; Phase 5 remains the idempotent authority that extends it.
tags: [onboarding, greenfield, permissions, security, subagents, td-130]
made_by: agent
agent_type: systems-architect
branch: worktree-onboarding-unification
pipeline_tier: full
affected_files:
  - scripts/onboard-project
  - skills/onboard-project/references/detection.md
  - skills/onboard-project/references/phases-core.md
  - skills/onboard-project/SKILL.md
  - tests/onboard_project_test.sh
  - .ai-state/decisions/055-hybrid-bash-slash-command-orchestration.md
dissent: >
  Hoisting Phase 5b ahead of Phase 0s alone would close the same window with no contract
  change at all — no amendment to dec-055's scaffold clause, no edit to the greenfield-shape
  predicate, no new bash-side constant to keep in agreement with the skill. The bash write
  buys determinism against a threat model (an LLM disobeying an explicit ordering instruction
  in its own engine) that Praxion nowhere else treats as real.
---

# Seed the permissions baseline at greenfield scaffold time; hoist Phase 5b ahead of the seed pipeline

## Context

td-130. The greenfield path leaves `.claude/` empty by contract at scaffold time, so `new`-mode's seed pipeline (`references/seed-pipeline.md`, Phase 0s) — which spawns researcher, systems-architect, implementation-planner, implementer and test-engineer subagents — runs **before** Phase 5 installs `.claude/settings.json` with the `permissions.allow` baseline. The subagent-`Write` exposure closed for existing projects by td-075 stays open exactly where a brand-new user meets Praxion first, and for the longest stretch of the run: the seed pipeline is the heaviest phase in the flow.

Three surfaces pin the empty contract in the built tree:

- `scripts/onboard-project::scaffold_project` creates `.claude` and writes nothing into it.
- `scripts/onboard-project::guard_greenfield_shape` and `references/detection.md § Guard — greenfield shape` both make `.claude/` **being empty** a conjunct of the greenfield-shape predicate, and the refusal message names it verbatim.
- `dec-055` (hybrid bash + slash-command orchestration) lists "create empty `.claude/`" as a literal bullet of the bash layer's contract.

The old `tests/new_project_test.sh` emptiness assertion did **not** survive the rewrite: `tests/onboard_project_test.sh::t6_empty_target_detects_new_mode_with_4line_trailer` asserts only that `.claude/` exists. So the contract is pinned by a *detection predicate*, not by a test — which is worse, because changing it silently changes routing rather than failing a test.

## Decision

**Two changes, one baseline value, defined once.**

1. **`scripts/onboard-project::scaffold_project` writes a minimal `.claude/settings.json`** containing the `permissions.allow` baseline and nothing else. The greenfield contract becomes "`.claude/` seeded with exactly `settings.json`" rather than "`.claude/` empty".
2. **Phase 5's `permissions.allow` sub-step (5b) is hoisted ahead of Phase 0s in `new` mode.** This is an ordering constraint on an existing phase, not a new mechanism: Phase 5's predicate is already per-sub-step and idempotent, so running 5b early and Phase 5 in full later costs one subset check.

Change 1 is the deterministic floor for the bash-entry path. Change 2 covers the path change 1 cannot reach: a user typing `/praxion:onboard-project` in an empty directory from inside an existing session, where no bash layer ever ran. Neither is redundant with the other, and **Phase 5 remains the single idempotent authority** that extends the baseline with the observability toggle and anything else.

**The baseline value is single-sourced.** `references/phases-core.md § Phase 5` remains its canonical statement; the bash scaffold carries a pointer comment, and a test asserts the two agree — the same agreement-test pattern already used for the state-name set shared between the script and `detection.md` (REQ-10).

**Rejected: reordering the core phases wholesale ahead of Phase 0s (option B as posed).** Phases 0.5, 6, 8c, 8d and 8e are all *detection-dependent*: `/init` needs a codebase to read, Project Essentials needs resolved typecheck/test/lint/build commands, and `ml` / `obsidian` / `quality` defaults are derived from stack and signal detection. Running them against an empty directory would produce a `CLAUDE.md` describing nothing, unresolved placeholders, and every stack-derived capability defaulting off — it would break the capability-default model to close a permissions window. Only the sub-step that has no codebase dependency (5b) moves.

## Considered Options

### Option A — Bash-layer seed only

- Pro: deterministic; the file exists before Claude is exec'd, so no instruction-following is on the critical path.
- Con: does not protect direct skill invocation in an empty directory; requires amending `dec-055`'s scaffold clause and the greenfield-shape predicate.

### Option B — Phase reorder for `new` mode only

- Pro: no contract change, no predicate edit, no bash-side constant to keep in agreement.
- Con (as posed, full core-before-seed): breaks five detection-dependent phases. Con (narrowed to 5b): the guarantee rests on the engine executing phases in the documented order — a prompt-ordering instruction, not a filesystem fact.

### Option C — Status quo plus documentation

- Pro: zero change; the exposure is at least named.
- Con: documents a hole at the exact moment a first-time user is least equipped to evaluate it, in the flow with the most subagent activity. td-075 established that this exposure is worth closing; leaving it open only where the user is newest inverts that judgment.

### Option A + narrowed B (chosen)

Both paths covered, one baseline value, no new mechanism.

## Consequences

**Positive** — the td-075 exposure closes on the greenfield path; the seeded file is the same shape Phase 5 would have written, so re-running is a no-op subset check; the greenfield-shape predicate becomes *more* specific (contents ⊆ `{settings.json}`) rather than merely different.

**Negative** — `dec-055`'s "create empty `.claude/`" bullet is narrowed and must carry a pointer at finalize; the bash layer gains its first content-bearing write into `.claude/`, so a second site now knows the baseline value and can drift from `phases-core.md` (mitigated by the agreement test, not by hope); the greenfield-shape predicate must be edited in two conforming implementations at once or a freshly-scaffolded-then-abandoned directory silently stops being routed as greenfield.

## Prior Decision

`dec-055` decided the hybrid layering: bash owns deterministic prereqs and the minimal filesystem scaffold; the session owns conversational flow and app generation. That principle is **unchanged and is what justifies this decision** — a static permissions baseline is a deterministic filesystem scaffold by dec-055's own definition. What changes is one enumerated bullet of the scaffold's content ("create empty `.claude/`" → "create `.claude/` containing the permissions baseline"). `dec-053` (prompt-over-template) is untouched: `settings.json` is a permissions declaration, not a code template or a pinned SDK signature, and nothing about the seed app's generation changes.

## Disconfirmation

**Falsifier.** If a `new`-mode run is observed spawning a Phase 0s subagent while `.claude/settings.json` is absent or lacks the baseline entry, the decision has not been implemented as specified. Conversely, if the greenfield-shape guard stops firing on a freshly-scaffolded directory — routing a greenfield dir into `existing` mode — the predicate amendment is wrong and the change has traded a permissions hole for a routing bug.

**Steelmanned runner-up.** Narrowed option B alone is genuinely strong. The bash write exists to defend against the engine not executing its own documented phase order — a threat model Praxion does not treat as real anywhere else in the pipeline, where every ordering guarantee in every agent is exactly such an instruction. If phase ordering is trustworthy enough to gate hook installation, merge-driver registration and the ADR finalize chain, it is trustworthy enough to gate a subset check. Choosing A+B also creates the one thing this whole task existed to remove: a second site that knows a value the skill already owns. A single hoisted sub-step would have closed td-130 with a one-line ordering change and no contract amendment at all.

**Reversal trigger.** Revisit if the bash-side baseline and `phases-core.md` are ever observed to disagree (the agreement test firing in anger proves the duplication is a live cost, not a theoretical one), or if Claude Code gains a first-class mechanism for declaring subagent permissions at session launch — which would make both the seeded file and the hoist obsolete in favor of a launch flag.
