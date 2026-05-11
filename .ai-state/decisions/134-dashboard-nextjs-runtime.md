---
id: dec-134
title: Dashboard rewrite uses Next.js with isolated local Node runtime
status: accepted
category: architectural
date: 2026-05-10
summary: Replace the Streamlit dashboard runtime with a Next.js App Router TypeScript app while preserving /dashboard, praxion-dashboard, project-root selection, deterministic local ports, and read-only filesystem semantics.
tags: [dashboard, nextjs, runtime, typescript, pnpm, isolation]
made_by: agent
agent_type: systems-architect
branch: dashboard-redesign
pipeline_tier: full
affected_files:
  - dashboard_app/
  - scripts/praxion-dashboard
  - commands/dashboard.md
  - streamlit_app/
  - rules/writing/html-output-conventions.md
  - .ai-state/DESIGN.md
  - docs/architecture.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07]
---

## Context

Praxion's current dashboard is a Streamlit app that reads `.ai-state/`, `.ai-work/`, docs, ADRs, metrics reports, and roadmap artifacts directly from disk. The rewrite goal is not to change the source-of-truth model; it is to raise the dashboard from a functional Streamlit control room into a professional, extensible local web application.

The user prefers Python when it is not materially worse. The research pass compared Next.js, Remix, and Python-first FastHTML. Python-first keeps the toolchain simpler, but does not offer the same mature product-shell and component ecosystem for this specific multi-surface dashboard. FastHTML also carries documentation maturity risk for a core Praxion product surface.

Activation: yes — this decision changes technology selection, runtime/install boundaries, and the dashboard component path.

## Decision

Use **Next.js App Router + TypeScript + React + pnpm** for the rewritten dashboard.

Preserve the product contract:

- `/dashboard` remains the user-facing slash command.
- `praxion-dashboard` remains the lifecycle CLI.
- `PRAXION_PROJECT_ROOT` remains the runtime project selection contract.
- Deterministic per-project local ports remain.
- The server binds to `127.0.0.1`.
- The dashboard remains read-only over canonical filesystem artifacts.
- Dependencies install under a dedicated user-scoped dashboard home, not the target project and not Praxion's root Python environment.

The implementation should create the new app under a neutral path such as `dashboard_app/`, leaving `streamlit_app/` as a temporary migration reference until parity is reached.

## Considered Options

### Next.js App Router + TypeScript + pnpm

Pros: server-first rendering, route handlers for narrow live endpoints, mature React UI ecosystem, high UX ceiling, clean separation between server-only filesystem reads and client interaction.

Cons: introduces Node and pnpm; requires porting Python readers/parsers to TypeScript; needs discipline to avoid client-heavy complexity.

### FastHTML + Python + uv

Pros: preserves Python-first project shape; direct filesystem reads are straightforward; user-scoped install would closely resemble the current venv model.

Cons: lower leverage for polished dashboard UX; more custom frontend construction; documentation maturity risk; does not materially advance the primary reason for the rewrite.

### Remix / React Router stack

Pros: strong server-loader model and credible filesystem-read fit.

Cons: less compelling than Next.js for an app-shell-heavy read-only portal with rich component composition and limited mutation behavior.

## Consequences

Positive:

- The dashboard can become a durable product surface rather than a Streamlit page collection.
- Filesystem access remains server-only and testable.
- The existing user-facing launch contract survives the rewrite.
- Future dashboard surfaces have a clearer extension model through routes, typed view models, and shared components.

Negative:

- Praxion adopts a Node/TypeScript toolchain for this subsystem.
- `scripts/praxion-dashboard` must manage build/start/install concerns for a Node app.
- Existing Streamlit-specific ADRs and rules need follow-on migration or clarification so agents do not receive stale instructions.

Risk controls:

- Pin exact package versions from the live npm registry verification captured in `SYSTEMS_PLAN.md` (`next` 16.2.6, `react`/`react-dom` 19.2.6, `typescript` 6.0.3, `pnpm` 11.0.9 as latest targets at architecture time).
- Keep all dashboard dependencies in `~/.praxion-dashboard/`.
- Add tests/static checks that prevent server-only artifact readers from being imported into client components.
- Remove or archive `streamlit_app/` after feature parity to avoid split-brain maintenance.
