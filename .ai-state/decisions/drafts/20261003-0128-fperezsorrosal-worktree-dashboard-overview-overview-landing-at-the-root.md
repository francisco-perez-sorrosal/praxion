---
id: dec-draft-8ec17bb1
title: The dashboard front door is an Overview composed at the root; dec-374's falsifier fired
status: proposed
category: architectural
date: 2026-10-03
summary: "The operator asked for a dashboard that presents the core status in one viewport and reaches the rest through progressive disclosure, which is the falsifier dec-374 named; / now renders an Overview composed from the existing view-models (no new store), the quality-eval reports gain a reader and a surface, and the sidebar carries the composed signals."
tags: [dashboard, information-architecture, overview, web-ui, progressive-disclosure, quality-evals]
made_by: agent
agent_type: orchestrator
branch: worktree-dashboard-overview
pipeline_tier: standard
supersedes: dec-374
dissent: "A separate /overview route with / redirecting to it (dec-160's shape) keeps the root a stable redirect that a future landing can retarget without changing what / means; folding the Overview into / is a cheaper URL today but couples the root to one page's identity."
affected_files:
  - dashboard_app/src/app/page.tsx
  - dashboard_app/src/server/view-models/overview.ts
  - dashboard_app/src/server/view-models/praxion-evals.ts
  - dashboard_app/src/server/view-models/sidebar-signals.ts
  - dashboard_app/src/components/sidebar-nav.tsx
  - dashboard_app/src/components/overview/overview-grid.tsx
  - dashboard_app/README.md
---

## Context

`dec-160` (2026-05-12) designed an `/overview` landing composed from the existing view-models. `dec-374` (2026-09-06) superseded it: nothing had been built in four months, no operator had asked, and the design target should not claim three components that did not exist. `dec-374` also named its own falsifier: "an operator reports that answering 'is anything on fire?' requires touring the surfaces, and that a landing page would have saved the tour. One concrete instance of it makes this decision wrong."

On 2026-10-02 the operator asked for exactly that: a dashboard that "presents the core information and allows access to the rest in an elegant and useful progressive disclosure". Verified in the checkout at `a1f1b1b6`: `/` redirects to `/architecture` (the densest surface); the Praxion quality-eval reports under `.ai-state/praxion_eval_reports/` have no surface; the Evals page renders ten rows of dashes because `.ai-state/eval_ledger/EVAL_LOG.md` on Praxion is not leaderboard-shaped; the Workshops page lists every stale `.ai-work/` directory as active; and `layout.tsx` mounts `LiveRefresh`, so every page polls against the narrow-refresh rule.

## Decision

**`/` renders an Overview page composed from the existing view-models** — sentinel, metrics (with readiness), workshops, decisions, plus two new readers (quality-eval reports, tech-debt ledger counts) — each reader isolated so a failing family reads as absent (logged, never thrown), every family nullable, every tile degrading to a placeholder that names its producer. No new store, no persisted cache, no client fetch: the composition reads the same files the surfaces read, exactly as `dec-160` designed; the readers are memoized per request with React `cache()` so the layout's sidebar signals and the page share one read, and nothing survives the request. The Overview lives at `/` rather than at a separate `/overview` route: there is one fewer redirect and one fewer URL, and the sidebar's first entry is "Overview" pointing at `/`.

Alongside it, the sidebar groups the surfaces by intent (Overview; Health: Sentinel, Metrics, Evals; Work: Workshops, Roadmap; Knowledge: Architecture, ADRs, Documentation) and carries the composed live signals; the Evals surface leads with the quality-eval history and digest and gates the experiment leaderboard on the ledger's shape; the Sentinel surface leads with a grade-first digest; workshops carry a last-activity time and group active / stale / done; only the Workshops and Overview pages poll; every surface shows "data as of".

`dec-374` flips to `status: superseded` with `superseded_by: dec-draft-8ec17bb1` (finalize rewrites the id). `dec-160` stays `superseded` by `dec-374`; its composition design is re-used, not re-decided, so no relation edge is added to it beyond the prose here.

## Considered Options

### A — Keep `/` → `/architecture`; add overview widgets to the Architecture page

Pros: no new route. Cons: `dec-160` option C's objection stands — it conflates two surfaces and makes the densest page denser; the operator's request is for a front door, not a heavier Architecture page.

### B — `/overview` route plus a `/` redirect (dec-160's shape)

Pros: the root stays a redirect that can be retargeted; the landing has its own URL. Cons: one more redirect on every first load, two URLs for one page, and a redirect is a poor front door. This is the runner-up and the `dissent:` line.

### C (chosen) — The Overview is `/`

Pros: the front door is the root; nothing to retarget; the sidebar reads naturally (Overview first). Cons: the root's identity is now one page's identity; a future landing that is not the Overview would change what `/` means (reversal is one file).

### D — Client-side aggregation of the surfaces' data

Rejected on the dashboard's own rules: filesystem access is server-only; no client fetches.

## Consequences

**Positive.** The operator answers "is anything on fire, what is in flight, what changed?" from one screen; the quality-eval reports — the LLM-judged checks the operator pays for — finally have a surface; the sidebar signals and the page agree on what "active" means; the layout stops polling reference pages; one tone vocabulary replaces four grade maps.

**Negative.** Read amplification on `/`: six readers run per load (parallel, localhost, measured in the verification pass). The `affected_files` above include paths created by this pipeline; until merge they exist only on the branch. Phone widths are not designed (desktop operator console; the layout must not break at 1024 px).

## Prior Decision

`dec-374` decided the Overview was not adopted because the need `dec-160` named had not been voiced by an operator and the design target should not carry phantom components. **What changed:** the operator voiced the need, in the words `dec-374` set as its falsifier; the components now exist on the branch this record ships with; and the quality-eval family, which did not have a reader in May, now needs one. `dec-374`'s reasoning about corpus hygiene (an accepted ADR must describe what exists) is kept: this record lands with the code, not ahead of it.

## Disconfirmation

**Falsifier.** Operators keep bookmarking a specific surface and bypass `/`; or the Overview's load time on a real managed project exceeds the slowest surface it composes by more than a second, so the front door is the slowest door. Either shows the composition is not earning its place.

**Steelmanned runner-up (Option B).** `dec-160` put the landing at `/overview` with `/` redirecting on purpose: the root stays a stable, retargetable redirect, so when the dashboard grows a different landing (a per-pipeline cockpit, a multi-project switcher) nothing already linked to `/overview` changes meaning. Folding the landing into `/` saves one redirect today and spends that flexibility.

**Reversal trigger.** A second landing-class surface is requested (multi-project, per-pipeline cockpit) — then `/` should become a router again and the Overview should move to `/overview`, which is a one-file change plus one sidebar href.
