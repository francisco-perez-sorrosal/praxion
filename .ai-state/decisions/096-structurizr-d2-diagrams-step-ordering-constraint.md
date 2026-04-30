---
id: dec-096
title: Step ordering constraint — rule update must commit before any .c4/.d2 file
status: proposed
category: implementation
date: 2026-04-30
summary: 'Rule update (rules/writing/diagram-conventions.md) must land in its own commit before any .c4, .d2, or .svg file is committed; hook script must land before live-file migrations.'
tags: [diagrams, implementation, ordering, sentinel, hooks]
made_by: agent
agent_type: implementation-planner
pipeline_tier: standard
affected_files:
  - rules/writing/diagram-conventions.md
  - scripts/diagram-regen-hook.sh
  - scripts/git-pre-commit-hook.sh
  - docs/diagrams/architecture.c4
  - .ai-state/ARCHITECTURE.md
  - docs/architecture.md
---

## Context

SYSTEMS_PLAN §10 (Prerequisites) and §9 (R3, R10) establish that two ordering constraints are
load-bearing for this pipeline:

1. **Rule-update-first**: the current `rules/writing/diagram-conventions.md` declares Mermaid-only.
   Any `.c4` or `.d2` file committed before this rule changes will trigger a sentinel violation
   and reviewer confusion — the rule still says those formats are unacceptable.

2. **Hook-before-migration**: the first `.c4` commit should auto-generate `.d2` and `.svg`
   via the pre-commit hook. If the hook does not exist at the time of the first `.c4` commit,
   the rendered artifacts are absent, leaving the referenced `<img>` tags in the architecture docs
   pointing at non-existent files.

The implementation plan decomposed these constraints into an explicit sequential ordering:
Step 1 (rule) → Step 2 (hook) → Steps 3–4 (MCP + templates) → Steps 5–6 (live migrations).

## Decision

Enforce the following commit ordering as a non-negotiable invariant during execution:

1. `rules/writing/diagram-conventions.md` is committed first, alone, before any `.c4`/`.d2`/`.svg`.
2. `scripts/diagram-regen-hook.sh` + the extension to `scripts/git-pre-commit-hook.sh` commits second,
   before any live `.c4` source files are committed.
3. `.mcp.json` and template updates (Steps 3–4) may commit in any relative order to each other,
   but must follow Step 1 and may follow or precede Step 2.
4. Live-file migrations (`docs/architecture.md`, `.ai-state/ARCHITECTURE.md`) commit only after
   the hook is in place.

The implementation-planner documents this in `WIP.md` as an explicit invariant, not just a
recommended ordering.

## Considered Options

### Option 1 — Allow any commit order; fix sentinel violations reactively

**Pros:** Simpler planning; no ordering constraint to enforce.

**Cons:** The first `.c4` commit will deterministically cause a sentinel violation under the
current rule. Reactive fixing means reverting commits, which disrupts the known-good-increment
principle. Not acceptable.

### Option 2 — Enforce ordering constraint (chosen)

**Pros:** Each commit leaves the system in a working, sentinel-clean state. The constraint is
load-bearing and prevents a predictable failure mode that the architect explicitly flagged (R3, R10).

**Cons:** Marginally more coordination overhead. Acceptable — the overhead is a single ordering
note, not a process change.

## Consequences

**Positive:**
- Sentinel does not trip at any point during implementation (AC11 satisfied continuously, not just at end).
- Each step's commit is a valid known-good increment.
- The pre-commit hook is in place before any `.c4` source is ever committed to the repo, so the
  hook's auto-generation behavior is exercised from day one.

**Negative:**
- Implementer must resist the temptation to commit template and live-file changes together in one
  batch before the rule is landed. WIP.md explicitly calls this out.

## Prior Decision

This ADR re-affirms `dec-093` (coexistence policy) — the two-toolchain rule change
is the prerequisite that makes the ordering constraint necessary. Without `dec-093`,
there would be no need for a separate rule-update-first step.
