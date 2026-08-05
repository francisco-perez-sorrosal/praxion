---
id: dec-129
title: Pipeline Dashboard supersedes metrics-viewer.html.tmpl — soft deprecation
status: superseded
superseded_by: dec-145
category: architectural
date: 2026-05-07
summary: 'The Streamlit dashboard supersedes the static metrics-viewer.html.tmpl with a soft deprecation: both ship for one release cycle with a banner in the static viewer pointing to praxion-dashboard; hard removal in next-after-next release.'
tags: [dashboard, metrics-viewer, deprecation, supersession, onboard-project]
made_by: agent
agent_type: systems-architect
pipeline_tier: full
affected_files:
  - claude/aac-templates/metrics-viewer.html.tmpl
  - .ai-state/metrics_reports/index.html
  - commands/onboard-project.md
affected_reqs: [REQ-09]
---

## Context

`claude/aac-templates/metrics-viewer.html.tmpl` is the existing static HTML + Chart.js viewer for `/project-metrics` data. It is byte-identically deployed as `.ai-state/metrics_reports/index.html` in onboarded projects (see the file header: "Sync via `cp` after edits; verify with `cmp -s`"). Launch is ad-hoc: `python -m http.server` from `.ai-state/metrics_reports/`.

The Streamlit dashboard's Metrics page reproduces every property of this viewer:

- KPI grid for the latest aggregate
- Trend lines for each of the 15 aggregate fields
- Hotspot top-N table

It also adds (which the static viewer cannot):

- Auto-refresh when a new report lands
- Cross-link from a hotspot file to the file's git change-coupling neighbors
- Educational tooltips explaining each metric

Hard deletion of the static viewer at v1 ship would:
- Break any user who has bookmarked the static URL
- Break any external script that depends on the byte-identical sync invariant
- Skip the courtesy of a deprecation window

## Decision

**Soft deprecation over one release cycle.**

- v1 ships with both viewers.
- The static viewer's HTML gains a top banner (added to `claude/aac-templates/metrics-viewer.html.tmpl` and re-synced to `.ai-state/metrics_reports/index.html` via the existing `cp` invariant): "**This viewer is deprecated.** Use `praxion-dashboard start` for the live dashboard. Static viewer will be removed in the next release."
- `commands/onboard-project.md` Phase 2 (which deploys the static viewer) gets a comment marker indicating deprecation; the file is still copied for the deprecation window.
- `commands/onboard-project.md` Phase 6 (or wherever the dashboard lands in the onboarding flow) deploys the dashboard ctl.
- **Next release**: `metrics-viewer.html.tmpl` and the deploy step in `onboard-project.md` Phase 2 are deleted; `.ai-state/metrics_reports/index.html` is removed from the onboarding scaffold.

A separate ADR will record the hard removal when it happens.

## Considered Options

### Option A — Hard delete at v1

**Pros**: Cleanest end state; one source of truth from day one. **Cons**: Breaks any in-flight user; violates the supersession-with-respect convention used elsewhere in Praxion (e.g., `roadmap-cartographer` retiring `ROADMAP.md` got its own ADR with a transition window).

### Option B — Soft deprecation, one release cycle (chosen)

**Pros**: Smooth transition; users see the deprecation notice in the artifact they currently use; existing scripts and bookmarks keep working through the window; pattern matches Praxion's "supersede with grace" precedent (dec-092 retiring ROADMAP.md, etc.).

**Cons**: One release of "two viewers exist" — minor maintenance overhead. The byte-identical sync invariant must keep working through the window.

### Option C — Keep both indefinitely as parallel offerings

**Pros**: Choice for the user. **Cons**: Two sources of truth permanently; metrics page logic split across HTML and Python; doubles the test surface; rejected per "every line earns its place."

## Consequences

**Positive**: Users transition gracefully; the deprecation banner is visible in the artifact they actively use, not buried in release notes; the next release's hard-removal is uncontroversial because the warning shipped one cycle earlier.

**Negative**: One release cycle of parallel maintenance. The byte-identical sync invariant must hold (`cmp -s` check stays in scope). Once the banner ships, the static viewer is "frozen with deprecation" — any bug fix to it during the window must be conservative (banner-only changes preferred).

**Risks accepted**: A user who never reads the banner is surprised when the static viewer disappears in the next release. Mitigation: the banner is prominent, and the next-release CHANGELOG also calls it out.
