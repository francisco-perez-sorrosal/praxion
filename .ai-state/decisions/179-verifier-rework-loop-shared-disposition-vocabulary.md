---
id: dec-179
title: CIS and rework-loop share a disposition vocabulary defined once in a skill reference
status: accepted
category: architectural
date: 2026-05-14
summary: Define switch-now / defer-with-rationale / dismiss-with-rationale once in skills/software-planning/references/disposition-vocabulary.md; both the CIS feature (researcher, architect) and the rework loop (manifest, /resume-rework, verifier) cite the shared reference rather than redefining the terms.
tags: [vocabulary, cis, rework, ecosystem-coherence, skill-reference]
made_by: agent
agent_type: systems-architect
branch: worktree-verifier-rework-loop
pipeline_tier: standard
affected_files:
  - skills/software-planning/references/disposition-vocabulary.md
  - agents/researcher.md
  - agents/systems-architect.md
  - agents/verifier.md
  - commands/resume-rework.md
re_affirmed_by:
  - dec-182
---

## Context

Two ecosystem features already use a three-option disposition vocabulary for user-facing decisions on whether to act on a signal:

- **CIS (Continuous Improvement Signals)**: when the researcher flags a strictly-better library/framework, the architect resolves with `switch-now`, `defer-with-rationale`, or `dismiss-with-rationale`. Defined inline in `agents/researcher.md` (~line 207) and `agents/systems-architect.md` (~lines 184–190).
- **Rework loop (this feature)**: when the verifier proposes rework worktrees in `REWORK_MANIFEST.md`, the user faces an equivalent decision per row: address now, defer (with rationale), or dismiss (with rationale).

The vocabulary is currently inline in two agent prompts. Adding a third use site (rework loop) is the moment to decide whether to standardize.

**Activation:** yes (cross-cutting vocabulary decision, ecosystem-coherence concern, light blast radius). Lenses applied: Simplicity (single source of truth), Consistency (one vocabulary across feature surfaces).

## Decision

Define the disposition vocabulary once in a new skill reference at `skills/software-planning/references/disposition-vocabulary.md`. The reference defines each term with one sentence plus a one-sentence "when to use this disposition" rule. Both existing consumers (`agents/researcher.md`, `agents/systems-architect.md`) and the two new consumers (`agents/verifier.md` Phase 12.5, `commands/resume-rework.md`) replace their inline definitions with a short pointer line:

> Disposition vocabulary (`switch-now` / `defer-with-rationale` / `dismiss-with-rationale`) is defined in `skills/software-planning/references/disposition-vocabulary.md`.

Each consumer still describes *how* to apply the vocabulary in its own context (when the architect must resolve CIS, when the user vetoes a manifest row, etc.), but the term definitions are not duplicated.

## Considered Options

### Option 1 — Shared skill reference (chosen)

Pros: single source of truth; one place to evolve definitions; matches Praxion's progressive-disclosure pattern (definitions in `skills/.../references/`, application in agent bodies); a user encountering a `defer-with-rationale` in one context recognizes it in another.

Cons: new ~50-line reference file; two existing agents (`researcher.md`, `systems-architect.md`) need a one-line edit each.

**Chosen.** The cost is small; the consistency win is real.

### Option 2 — Rework-specific vocabulary (`address-now`, `defer`, `dismiss`)

Pros: no edit to existing agents; rework-loop is fully self-contained.

Cons: ecosystem incoherence — users see two-different-but-similar vocabularies for two-very-similar decisions; the rework feature looks bolted-on rather than designed-with-the-grain; a future "general disposition" feature inherits the mess.

Rejected.

### Option 3 — Skip a formal disposition vocabulary; rely on the manifest's `confidence` field + user judgment

Pros: minimal surface area.

Cons: loses the explicit user-action vocabulary; the verifier-suggested-action (low confidence → review classification) becomes the only signal; the user has no canonical way to record "I considered this and chose to defer for X reason," which is exactly the kind of decision archaeology Praxion preserves elsewhere.

Rejected.

## Consequences

**Positive:**

- Vocabulary consistency across CIS, rework, and any future "decide on a surfaced signal" feature.
- The new reference file is short (~50 lines) and loaded on demand only when an agent needs it — zero always-loaded token cost.
- The researcher and architect agent bodies become slightly shorter by replacing inline definitions with a pointer.

**Negative:**

- Two existing agents (`researcher.md`, `systems-architect.md`) are touched by this PR — minor scope expansion beyond the rework-loop core.

**Mitigation:**

- The edit is mechanical (replace ~10 lines of inline definition with a 2-line pointer); doc-engineer's quality check is straightforward.
- If the reference file design proves wrong later, both consumers are easy to revert.
