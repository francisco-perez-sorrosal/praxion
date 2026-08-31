---
id: dec-115
title: program.md is a project-local meta-prompt — sibling artifact category to CLAUDE.md
status: accepted
category: architectural
date: 2026-05-03
summary: program.md is recognized as a new Praxion artifact category — a project-local meta-prompt that guides an autonomous experiment loop. It lives at the project root (sibling of CLAUDE.md), is discovered by file presence, and is consumed by implementation-planner and verifier alongside CLAUDE.md.
tags: [ml-training, program-md, artifact-category, meta-prompt, autoresearch, archetype-extension]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - skills/ml-training/SKILL.md
  - rules/ml/experiment-tracking-conventions.md
  - skills/onboard-project/SKILL.md
affected_reqs: []
---

# ADR — `program.md` as a project-local meta-prompt artifact

## Context

Karpathy's `autoresearch` introduces `program.md` — a 7 KB Markdown document at the project root that specifies the rules of an autonomous experiment loop: what hypotheses the agent explores, what constraints it respects (VRAM budget, simplicity criterion), what it reads between experiments. Unlike a research paper or a feature spec, it is the agent's "operating system" for the loop. The human iterates on `program.md`; the agent iterates on `train.py`.

Praxion's existing artifact taxonomy has no slot for this:

- Not a behavioral spec (no REQ IDs, no When/and/system/so-that format)
- Not a skill (project-local; not reusable across projects; no progressive disclosure)
- Not a CLAUDE.md block (too domain-specific; project-scoped not session-scoped)
- Not an ADR (description of intent, not a record of a decision)
- Not project documentation (it is *operative*, not *descriptive* — agents read it as instructions, not background)

`RESEARCH_FINDINGS.md` "Theme 5" enumerates four candidate mappings: project-local rule, `systems-architect` mode input, `.ai-state/` artifact, SDD spec extension. None is a clean fit. The user's binding constraint says: "provisional framing — project-local meta-prompt, sibling of CLAUDE.md."

This is genuinely novel and warrants explicit recognition rather than retrofitting an existing category.

## Decision

**`program.md` is a recognized Praxion artifact category: a project-local meta-prompt.**

- **Location**: project root, alongside `CLAUDE.md`. Discovered by file presence (no manifest entry needed).
- **Authorship**: human-authored. Praxion agents may *suggest edits* but do not autonomously modify it (analogous to how agents do not autonomously rewrite CLAUDE.md without user direction).
- **Onboarding**: `/onboard-project` Phase 8c (ML branch) creates a scaffold if missing and the project has ML signals; existing `program.md` files are detected and preserved.
- **Pipeline reading**: `implementation-planner` and `verifier` load `program.md` as part of their input context when the project is flagged ML. `systems-architect` reads it during baseline-audit mode and during feature pipelines.
- **Conventions**: defined in `rules/ml/experiment-tracking-conventions.md` (path-scoped to `program.md`, `runs/**`, `experiments/**`). Required content shape: Goal, Constraints (compute budget, VRAM cap, time budget), Hypothesis space, Simplicity criterion, Autonomy contract. Optional: per-experiment notes, references to read. Vocabulary detail also lives in `skills/ml-training/SKILL.md` `## program.md` section.
- **Validation**: the `experiment-tracking-conventions.md` rule (path-scoped to `program.md` and `runs/**`) declares the minimum content shape; sentinel may audit completeness.
- **Distinction from CLAUDE.md**: CLAUDE.md guides an agent *session* (interactive, one task at a time, human in the loop); `program.md` guides an *autonomous experiment loop* (overnight, no human, repeats N times until interrupted).

## Considered Options

### Option 1 — Project-local rule (auto-loaded into context globally)

**Pros:** Already a recognized Praxion category; loaded automatically.

**Cons:** Rules are *declarative* and *global* — they cross projects. `program.md` is project-specific operative content. Forcing it into a rule deforms both concepts.

### Option 2 — Architect input mode (consumed only by `systems-architect`)

**Pros:** Familiar pipeline pattern.

**Cons:** `program.md` should be visible to the implementer (it sets simplicity criterion) and the verifier (it sets autonomy contract). Restricting consumption to architect breaks the loop.

### Option 3 — New `.ai-state/` artifact category

**Pros:** Praxion-shaped; under existing intelligence umbrella.

**Cons:** `.ai-state/` is committed but Praxion-managed; `program.md` is human-authored, project-canonical content. Migrating it into `.ai-state/` would surprise users and break the autoresearch convention. The autoresearch project uses `program.md` at root *because the human is the canonical author*.

### Option 4 — Project-local meta-prompt sibling of CLAUDE.md (chosen)

**Pros:** Matches autoresearch's existing convention exactly (zero migration). Discovered by file presence (no special config). Sits beside CLAUDE.md, mirroring the session-vs-loop distinction in vocabulary. New category but justified by genuinely new use case.

**Cons:** Another root-level Markdown file. No manifest entry — discovered by convention. Future projects could misuse the slot for non-experiment-loop purposes.

### Option 5 — SDD spec extension (When/and/system/so-that format extended for ML)

**Pros:** Reuses existing format.

**Cons:** SDD is for behavioral specs of *what the system does*; `program.md` is *what the agent should do during the loop*. Different abstraction level. Forcing into SDD format strips the meta-prompt's natural prose form.

## Consequences

**Positive:**
- `program.md` joins Praxion's vocabulary as a first-class category, no retrofit needed
- The autoresearch convention works without migration
- Future ML projects with autonomous experiment loops have a Praxion-named home for their loop instructions
- Sibling-of-CLAUDE.md framing makes the session-vs-loop distinction visible at the file level

**Negative:**
- One more discoverable artifact at project root
- Convention-only discovery means no centralized validation surface (mitigated by `experiment-tracking-conventions.md` rule)

**Neutral:**
- If a future Claude Code convention adopts `program.md` for a different purpose, we rename to `experiment-program.md` (R4 in SYSTEMS_PLAN)
- The artifact is mode-agnostic (works in modes A/B/C); the loop runs in whatever environment Praxion is in

## Open follow-up (not blocking this ADR)

- Q: Should `experiment-tracking` rule path-scope to `program.md` specifically, or use a more general "ML project root" detection? Recommendation: explicit path. Decided in implementation-planner step.
