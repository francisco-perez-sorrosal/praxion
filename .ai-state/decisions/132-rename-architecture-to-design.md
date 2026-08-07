---
id: dec-132
title: Rename .ai-state/ARCHITECTURE.md to .ai-state/DESIGN.md for Diátaxis clarity
status: accepted
category: architectural
date: 2026-05-08
summary: Rename the architect-facing design-target document from ARCHITECTURE.md to DESIGN.md to make audience and Diátaxis quadrant unambiguous from filename alone
tags: [architecture, documentation, diataxis, naming, ai-state]
made_by: agent
agent_type: implementation-planner
branch: docs-strategy-p1-foundation
pipeline_tier: standard
affected_files:
  - .ai-state/ARCHITECTURE.md
  - .ai-state/ARCHITECTURE_CHANGELOG.md
  - .ai-state/DESIGN.md
  - .ai-state/DESIGN_CHANGELOG.md
  - docs/architecture.md
  - agents/sentinel.md
  - agents/systems-architect.md
  - agents/implementer.md
  - agents/implementation-planner.md
  - agents/verifier.md
  - agents/researcher.md
  - agents/doc-engineer.md
  - agents/promethean.md
  - agents/roadmap-cartographer.md
  - rules/swe/agent-intermediate-documents.md
  - rules/swe/swe-agent-coordination-protocol.md
  - skills/software-planning/references/architecture-documentation.md
  - skills/software-planning/references/coordination-details.md
  - skills/software-planning/SKILL.md
  - commands/onboard-project.md
  - commands/new-project.md
  - claude/canonical-blocks/agent-pipeline.md
  - claude/config/CLAUDE.md.tmpl
  - eval/src/praxion_evals/behavioral/artifact_manifest.py
  - streamlit_app/data/discovery.py
re_affirms: dec-021
---

## Context

Dec-021 (dual-audience architecture docs) correctly split architecture documentation into two purpose-built documents:
- `.ai-state/ARCHITECTURE.md` — architect-facing design target (Diátaxis: Explanation)
- `docs/architecture.md` — developer-facing navigation guide (Diátaxis: Reference)

The split is Diátaxis-clean, but the names don't communicate that. Both files contain "architecture" in their path, which is ambiguous from the filename alone:

- A reader navigating to `.ai-state/ARCHITECTURE.md` does not know from the name that this is the *future-state design target*, not a description of what currently exists.
- A reader navigating to `docs/architecture.md` does not know from the name that this is the *code-verified present-state map*, not the architect's design document.

The docs-strategy P1 initiative (2026-05-08) surfaced this as a naming clarity problem. Diátaxis recommends that document classification be surfaced at the page level — frontmatter labels alone are insufficient when file paths appear in cross-references, agent prompts, and rules.

The IMPROVEMENT_PLAN.md decision D2 (locked by user on 2026-05-08) resolves this in favor of the rename.

## Decision

Rename `.ai-state/ARCHITECTURE.md` → `.ai-state/DESIGN.md` and `.ai-state/ARCHITECTURE_CHANGELOG.md` → `.ai-state/DESIGN_CHANGELOG.md`.

Add `diataxis:` frontmatter to both architecture documents:
- `.ai-state/DESIGN.md` → `diataxis: explanation`, `audience: architect`
- `docs/architecture.md` → `diataxis: reference`, `audience: developer`

Migrate all 71 reference sites across agents, rules, skills, commands, eval, streamlit, and `.ai-state/` files in a single atomic commit. Sentinel section-ownership checks (AC01–AC10) that hardcode the path `.ai-state/ARCHITECTURE.md` are updated to `.ai-state/DESIGN.md` in the same commit.

The dual-file split established by dec-021 is preserved. This ADR re-affirms dec-021's core decision (keep two files, distinct audiences, distinct validation models) while superseding only the *naming choice* for the architect-facing file.

## Considered Options

### Option A — Keep names, add Diátaxis frontmatter only (original D2 recommendation in IMPROVEMENT_PLAN.md §3)

**Pros:** Zero migration cost. Frontmatter adds the Diátaxis signal without touching 71 reference sites.

**Cons:** Path-level ambiguity persists in every agent prompt, rule, and skill reference. The name `ARCHITECTURE.md` signals "authoritative architecture" to readers, which is exactly the confusion dec-021 was designed to avoid. Cross-references in always-loaded rules and agent prompts — read by agents without the benefit of frontmatter — remain ambiguous.

This option was the IMPROVEMENT_PLAN.md's initial recommendation for D2 before the P1 planning phase.

### Option B — Rename .ai-state/ARCHITECTURE.md → .ai-state/DESIGN.md (chosen)

**Pros:** `DESIGN.md` clearly signals "intent / future state / design target" rather than "description of what is". `docs/architecture.md` (the developer guide) retains "architecture" since it describes the actual architecture. After rename, the two files tell their story from filenames alone: design intent lives in DESIGN.md; architecture facts live in architecture.md.

**Cons:** 71 reference sites require migration. Migration must be atomic (rename + all references in one commit) to avoid a half-renamed state that breaks sentinel checks.

### Option C — Rename docs/architecture.md → docs/architecture-guide.md

**Pros:** Less impactful (fewer references to the docs/ file than to .ai-state/).

**Cons:** The docs/ file is the *reference* document; "architecture" in its name is accurate. The ambiguity is in the .ai-state/ file (design target vs. description), not the docs/ file.

## Consequences

**Positive:**
- From filenames alone: design target = DESIGN.md, architecture map = architecture.md. No frontmatter required to understand the split.
- Consistent with uv's pattern (design-intent files use different naming than code-verified docs).
- Sentinel checks become unambiguous: AC01–AC04 operate on DESIGN.md, AC05–AC09 on docs/architecture.md.
- Agents prompts and rules that reference the path now correctly communicate "this is the design document" at the path level.

**Negative:**
- One-time migration of 71 reference sites. Must be atomic; the commit is large but mechanical.
- Historical sentinel reports (6 files in .ai-state/sentinel_reports/) contain old paths — these are frozen artifacts and should NOT be updated (updating history is misleading). Note this exception explicitly in the migration step.
- observations.jsonl (36 references) is an append-only merge-driver-managed file — update references where they appear inline in text; do not rewrite the JSON event history.
- Any managed project that has already received `.ai-state/ARCHITECTURE.md` via `/onboard-project` will have the old path. Those projects are NOT affected (they have their own independent architecture docs). The rename only touches the Praxion metaproject.

## Prior Decision

This re-affirms dec-021's core decision (dual-audience split, distinct validation models, same 8-section structure) but supersedes the naming choice embedded in dec-021's `affected_files` list. The pair survives; only `.ai-state/ARCHITECTURE.md` changes name to `.ai-state/DESIGN.md`.

The original D2 recommendation in IMPROVEMENT_PLAN.md §3 was "A — label, don't rename." The user's sign-off gate (§15) locked D2 as "rename + frontmatter." This ADR records the rationale for that override.
