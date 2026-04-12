---
id: dec-032
title: `ROADMAP.md` at project root as a living document with preserved Decision Log
status: accepted
category: architectural
date: 2026-04-12
summary: 'Single `ROADMAP.md` at project root, living with section ownership and Decision Log section preserved across regenerations; no per-run archive'
tags: [architecture, roadmap, living-document, lifecycle, output-location]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - ROADMAP.md
  - skills/roadmap-synthesis/assets/ROADMAP_TEMPLATE.md
---

## Context

Two dimensions to decide: **where** the roadmap file lives and **how** it evolves over time.

Location options:
- **Project root** (`ROADMAP.md`): user-visible, conventional for OSS projects, matches Praxion's exemplar placement.
- **`.ai-state/ROADMAP.md`**: aligns with ADR / specs / living-doc pattern precedent; hidden from casual browsing.

Lifecycle options:
- **Living document**: single file, section ownership, updated in place (like `SYSTEM_DEPLOYMENT.md` per dec-019 and `ARCHITECTURE.md` per dec-020).
- **Timestamped archive**: new `ROADMAP_YYYY-MM-DD.md` per run (like `IDEA_LEDGER_*.md`).
- **Hybrid**: living canonical + timestamped archive of each regeneration.

The research findings note that major agentic projects (LangChain, LangGraph, Goose, Aider) deliberately avoid committed roadmaps; Praxion's exemplar is closer to CNCF maintainer roadmaps (internal/self-improvement artifacts). The living-document precedent in Praxion is already established (dec-019, dec-020, dec-021).

## Decision

`ROADMAP.md` lives at **project root** as a **living document** with section ownership. Key lifecycle properties:

- Single canonical file; no per-run timestamped archive.
- **Decision Log section** is preserved across regenerations (append-only; never truncated).
- **Methodology footer** (mirroring Praxion's exemplar) records how *this specific* generation was produced (audit lenses used, researcher count, evidence sources consulted).
- Section ownership: the cartographer owns section generation; individual sections can be manually edited by the user between generations (e.g., the Decision Log accepts user annotations).
- **Incremental mode** (`/roadmap diff`): re-runs the audit, diffs against the existing roadmap, surfaces deltas, and updates in place — preserving Decision Log entries verbatim.
- **Fresh mode** (`/roadmap`): full regeneration; old Decision Log is preserved and carried into the new roadmap.
- Historical archive is provided by git history, not by per-run filesystem artifacts.

Template at `skills/roadmap-synthesis/assets/ROADMAP_TEMPLATE.md` encodes the 9-section exemplar structure plus a new Decision Log section.

## Considered Options

### Option 1 — `ROADMAP.md` at project root, living document (chosen)

**Pros:** user-visible (conventional location); matches exemplar; consistent with the living-document pattern (dec-019, dec-020); single source of truth; Decision Log preservation supports cross-run continuity; git history provides archival.

**Cons:** no filesystem-level per-run archive (cannot "read the roadmap from 3 months ago" without `git show`); section-ownership discipline required to avoid merge conflicts if user edits simultaneously.

### Option 2 — `.ai-state/ROADMAP.md` hidden location

**Pros:** aligns with ADR / specs / sentinel report placement; hidden from casual browsing (reduces pressure to keep it polished for public consumption).

**Cons:** user-invisible (users expect `ROADMAP.md` at project root); breaks convention for OSS/internal docs; hides the artifact the feature is designed to produce.

### Option 3 — Timestamped archive

Each run produces a `ROADMAP_YYYY-MM-DD.md` like `IDEA_LEDGER_*.md`.
**Pros:** per-run history on the filesystem; clean separation of runs.
**Cons:** clutters project root or `.ai-state/`; no single canonical "current roadmap" unless a separate pointer file is maintained; contradicts the exemplar pattern (`ROADMAP.md`, not `ROADMAP_2026-04-06.md`).

### Option 4 — Hybrid (living canonical + timestamped archive)

Both forms coexist.
**Pros:** canonical file + per-run history.
**Cons:** maintenance burden for MVP; deferred — can be added later without breaking changes if demand emerges.

## Consequences

**Positive:**

- User-visible at the conventional location.
- Decision Log preservation provides cross-run memory (prevents the "regeneration destroys institutional memory" anti-pattern R16).
- Consistent with `SYSTEM_DEPLOYMENT.md` and `ARCHITECTURE.md` living-document patterns.
- Methodology footer makes each generation auditable.
- Git history provides archival at zero additional implementation cost.
- Incremental mode (`diff`) supports low-cost regeneration aligned with agentic-cycle guidance.

**Negative:**

- Section-ownership discipline required. The cartographer must not blow away user annotations in sections marked user-editable (Decision Log). Implementer must honor this contract.
- No filesystem-level per-run archive; recovering historical versions requires `git log --oneline ROADMAP.md` + `git show <sha>:ROADMAP.md`.
- Hybrid archival (Option 4) is deferred; adding it later is a supersession decision, not a breaking change.

**Operational:**

- Template asset at `skills/roadmap-synthesis/assets/ROADMAP_TEMPLATE.md` encodes the 9-section structure: Executive Summary, What's Working (Preserve), Weaknesses, Improvement Roadmap (phased), Deprecation & Cleanup, Quality Metrics, Guiding Principles for Execution, Methodology Footer, Decision Log.
- Cartographer's Phase 7 self-verify pass confirms the Decision Log section is preserved across regenerations.
- `.gitignore` is unchanged — `ROADMAP.md` is committed.
