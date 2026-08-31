---
id: dec-121
title: Pipeline Dashboard CLAUDE.md placement — Working Here mention, no philosophical block
status: superseded
superseded_by: dec-349
category: architectural
date: 2026-05-07
summary: Mention streamlit_app/ in Praxion's CLAUDE.md "Working Here" section to satisfy sentinel EC03; the SYSTEMS_PLAN's Goal section is the canonical philosophical statement, not a separate CLAUDE.md block.
tags: [dashboard, claude-md, sentinel-ec03, philosophy]
made_by: agent
agent_type: systems-architect
pipeline_tier: full
affected_files:
  - CLAUDE.md
  - dashboard_app/
affected_reqs: [REQ-11]
---

## Context

Two structural concerns:

1. **Sentinel EC03 compliance** — sentinel checks that every directory mentioned conceptually in CLAUDE.md is real, and (the inverse) every real top-level directory in the repo is at least acknowledged. A new top-level `streamlit_app/` without acknowledgment risks an EC03 WARN on next audit.
2. **Philosophical framing weight** — the user emphasized this dashboard is "embedded in the soul of our Praxion philosophy." The question is *where* that gets stated authoritatively. CLAUDE.md is always-loaded; every always-loaded token must earn its place per the token-budget rule. A philosophical mini-essay there would be self-indulgent.

The existing pattern: directories are acknowledged via either a brief mention in CLAUDE.md ("`commands/onboard-project.md` … `new_project.sh`") or via the architecture doc as the canonical structural source.

## Decision

**Acknowledge `streamlit_app/` in Praxion's CLAUDE.md `## Working Here` block** with one sentence:

```
- `streamlit_app/` — Praxion-bundled Streamlit dashboard (per-project visual entry point). Lifecycle managed by `scripts/praxion-dashboard`; see `.ai-state/ARCHITECTURE.md` "Pipeline Dashboard" component.
```

**Do not add a separate philosophical block to CLAUDE.md.** The philosophical case is made in:
- The dashboard's `SYSTEMS_PLAN.md` Goal section (canonical for design-time)
- The dashboard's "About" page in the UI itself (canonical for user-facing)
- The architecture doc's Components row (canonical for structural)

CLAUDE.md is for always-loaded operational guidance, not project advocacy.

## Considered Options

### Option A — `## Working Here` mention only (chosen)

**Pros**: Minimum surface area in always-loaded context; satisfies EC03; respects token-budget principle; philosophical case lives where it belongs (SYSTEMS_PLAN, UI, ARCHITECTURE.md).

**Cons**: A new reader of CLAUDE.md does not learn the dashboard's philosophical role from CLAUDE.md alone — they must follow the link. Acceptable.

### Option B — Dedicated `## Pipeline Dashboard` block in CLAUDE.md (~10 lines)

**Pros**: Surfaces the philosophy front-and-center; makes the dashboard discoverable. **Cons**: Adds always-loaded tokens for a single feature; sets a precedent that any sufficiently-important feature gets its own CLAUDE.md block (CLAUDE.md drift risk); the philosophical case has 3 better homes.

### Option C — No CLAUDE.md mention; rely on ARCHITECTURE.md and `## Structure` only

**Pros**: Minimum drift. **Cons**: Risks EC03 WARN if sentinel scans CLAUDE.md and finds an unacknowledged top-level directory; EC03 has triggered on similar omissions historically.

## Consequences

**Positive**: ~30-token addition to CLAUDE.md (well under any budget concern); EC03 satisfied; philosophy lives in places where it deepens design (SYSTEMS_PLAN), educates users (UI About page), and structures code (ARCHITECTURE.md). Pattern preserved: CLAUDE.md is operational, not aspirational.

**Negative**: A future contributor browsing CLAUDE.md alone may not appreciate why the dashboard exists. Mitigation: the one-line mention links to the ARCHITECTURE.md component entry which has the longer rationale and links onward.

**Risks accepted**: Sentinel may grow checks that look for per-feature CLAUDE.md blocks; if so, this decision can be re-litigated with evidence.
