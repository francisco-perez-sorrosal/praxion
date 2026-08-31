---
id: dec-draft-39713c4d
title: Dashboard CLAUDE.md acknowledgment lives in the Repository-layout table
status: proposed
category: architectural
date: 2026-08-31
summary: Supersedes dec-121, whose three referents (streamlit_app/, the "Working Here" block, .ai-state/ARCHITECTURE.md) all vanished in later refactors; the surviving substance — acknowledge the dashboard operationally, no philosophical CLAUDE.md block — is carried by the Repository-layout table row for dashboard_app/
tags: [dashboard, claude-md, supersession, audit, referent-rot]
made_by: agent
agent_type: orchestrator
branch: worktree-adr-living-view
pipeline_tier: lightweight
supersedes: dec-121
affected_files: ["CLAUDE.md", "dashboard_app/"]
dissent: "Recording a supersession for a decision whose substance survived intact arguably inflates the log; a frontmatter-only repair (updating affected_files, as the 2026-08-31 remediation did) could be read as sufficient, and this record exists mainly because the decided mechanism — not just the paths — died."
---

## Context

The 2026-08-30 still-current audit (adr-read-path) found dec-121 a supersede-candidate with high confidence: every referent it decided about is gone. `streamlit_app/` was replaced by the Next.js `dashboard_app/`; CLAUDE.md no longer contains a `## Working Here` section; `.ai-state/ARCHITECTURE.md` became `DESIGN.md`. The 2026-08-31 remediation repaired its `affected_files` paths but could not repair the body's mechanism, which names all three dead referents. Reality answered the question differently and no ADR recorded it — the precise gap the supersession protocol closes.

## Decision

The dashboard's CLAUDE.md presence is an operational row in the **Repository-layout table** (`dashboard_app/` — "Active Next.js dashboard runtime reading `.ai-state/`…"), plus its build/test commands under *Build / test / lint*. No philosophical or narrative dashboard block exists in CLAUDE.md, preserving dec-121's substantive stance: acknowledge the dashboard operationally where agents need it; keep philosophy out of the always-loaded surface.

## Considered Options

### A — Record the supersession (chosen)
The question ("where and how does CLAUDE.md acknowledge the dashboard?") is still live and is now answered by a different mechanism in a different structure. Recording it keeps frontmatter truthful for every status-reading consumer (query tools, index, health checks, dashboard).

### B — Leave dec-121 accepted with repaired paths
Cheaper, but leaves a record whose decided mechanism is unimplementable (its named sections and files do not exist) marked as the current answer — exactly the silent-obsolescence class the audit exists to catch.

## Consequences

Positive: the only confirmed stale record in the 30-record sample is repaired through the sanctioned vocabulary; the audit loop (sample → disposition → status flip) is exercised end-to-end for the first time.

Negative: one more record in the log — accepted, per the append-only invariant.

## Disconfirmation

- **Falsifier**: a philosophical/narrative dashboard block reappearing in CLAUDE.md, or the Repository-layout table dropping the `dashboard_app/` row, would make this record's stated mechanism false.
- **Steelmanned runner-up**: Option B respects log minimalism — most path rot is repairable in place, and the 2026-08-31 pass proved repair-not-retire is usually right. It loses only when the *mechanism*, not the paths, died — which is the case here.
- **Reversal trigger**: a future CLAUDE.md restructure that removes the Repository-layout table should re-open this question explicitly.

## Prior Decision

dec-121 (2026-05-07, Full pipeline) decided: mention `streamlit_app/` in CLAUDE.md's "Working Here" section to satisfy sentinel EC03, with the SYSTEMS_PLAN Goal section as the canonical philosophical statement rather than a CLAUDE.md block. What changed: the Streamlit dashboard, the "Working Here" section, and `.ai-state/ARCHITECTURE.md` were all replaced in later refactors; what survives: operational-acknowledgment-without-philosophy, now delivered by the Repository-layout table.
