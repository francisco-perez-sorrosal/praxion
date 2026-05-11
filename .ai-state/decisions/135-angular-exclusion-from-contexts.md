---
id: dec-135
title: Angular intentionally excluded from first-class typescript-development contexts
status: accepted
category: architectural
date: 2026-05-11
summary: Praxion will not ship contexts/angular.md as a first-class context in typescript-development. Angular projects use Angular's own CLI and opinionated toolchain.
tags: [skills, polyglot, typescript, angular, scope-decision, exclusion]
made_by: agent
agent_type: systems-architect
branch: worktree-multi-language-support
pipeline_tier: full
affected_files:
  - skills/typescript-development/SKILL.md
re_affirms: dec-137
---

## Context

Phase 1b research surveyed the frontend framework matrix (React, Vue, Angular, Svelte, Astro, SolidJS) and locked first-class Praxion coverage to **React 19** and **Vue 3**. Angular was explicitly excluded from this lock. The exclusion needs a durable rationale so a future maintainer doesn't quietly add Angular coverage in response to a single project request, and so revisitation is gated on explicit evidence.

Angular has materially different ecosystem properties from React/Vue: its CLI (`ng`) is opinionated, comprehensive, and self-updating across major versions (currently v19), and Angular projects typically follow CLI-driven scaffolding for routing, state, testing, and build configuration. Most "what tooling do I use?" questions in an Angular project are answered by the CLI itself.

## Decision

Praxion will NOT ship `typescript-development/contexts/angular.md` as a first-class context. Angular projects benefit from:

1. The baseline `typescript-development/contexts/typescript.md` (TS strictness, type checking, generic TS conventions)
2. Angular's own CLI (`ng generate`, `ng test`, `ng build`, `ng update`) — which Praxion does NOT attempt to mirror or wrap
3. Angular's own opinionated docs — which Praxion does NOT attempt to summarize or supersede

Angular projects should consult Angular CLI docs directly for framework-specific concerns. Praxion's first-class frontend contexts are React 19 and Vue 3.

**Revisitation criteria** — Praxion adds `contexts/angular.md` if and only if at least TWO of the following are true:

1. Three or more Praxion-managed projects in the past 12 months are Angular-primary
2. Angular CLI fundamentally changes its opinionation (e.g., abandons its current "one CLI does everything" stance), creating a gap Praxion could fill
3. A specific Angular pattern emerges that materially diverges from generic TS practice and lacks CLI coverage (e.g., a multi-Angular-app monorepo pattern not addressed by Nx Angular)

If any review finds these conditions met, the next polyglot pipeline opens this ADR for supersession.

## Considered Options

### Option 1 — Include Angular for ecosystem completeness

**Pros**: No framework conspicuously absent from Praxion's frontend story.

**Cons**: Angular CLI is comprehensive and self-contained; Praxion contexts would parallel-document content the CLI already owns; high drift risk (Angular's release cadence is fast and breaking-change-heavy); Praxion has limited expertise/throughput to maintain quality on Angular's surface; small adoption in Praxion's user base.

### Option 2 — Exclude with documented rationale (chosen)

**Pros**: Avoids parallel-docs drift; concentrates Praxion's first-class coverage on frameworks where it adds value (React, Vue); leaves the door open for revisitation with clear criteria.

**Cons**: Angular projects miss Praxion-curated first-class framework context (but inherit the TS baseline and benefit from Angular's own docs).

### Option 3 — Soft-include — stub `contexts/angular.md` with "use Angular CLI"

**Pros**: A landing page for Angular-aware agents.

**Cons**: Adds noise without value; agents would still defer to Angular CLI docs; the stub itself becomes a maintenance liability (sentinel will eventually flag it as stale); duplicates information findable in Angular's own docs.

## Consequences

### Positive

- Praxion's frontend coverage stays focused and high-quality on React/Vue
- Avoids the inevitable drift between Praxion-curated and Angular-CLI-published guidance
- Establishes a precedent: frameworks with comprehensive opinionated CLIs need not be re-documented by Praxion
- Future polyglot scope decisions have a template for principled exclusion (CLI-completeness criterion)

### Negative

- Angular projects working in a Praxion ecosystem don't get Praxion-curated framework context — but DO get baseline TS context (`typescript-development/contexts/typescript.md`)
- If Praxion later acquires Angular-heavy users, the exclusion becomes inconvenient; mitigated by the explicit revisitation criteria

### Neutral

- The exclusion is durable but reversible — the revisitation criteria provide a structured path to inclusion if evidence warrants
