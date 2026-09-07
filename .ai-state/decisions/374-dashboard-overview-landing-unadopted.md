---
id: dec-374
title: The dashboard /overview landing is not adopted; / continues to redirect to /architecture
status: accepted
category: architectural
date: 2026-09-06
summary: dec-160's three components never existed in git history and no code references them. Rather than leave an accepted decision asserting a design target that was never built, this record decides the question the other way and supersedes it.
tags: [dashboard, information-architecture, adr-hygiene, web-ui]
made_by: agent
agent_type: systems-architect
branch: worktree-praxion-health
pipeline_tier: full
supersedes: dec-160
dissent: Superseding is a heavier instrument than the situation needs. dec-160 was self-described as second-cut work and reads as a proposal that was mis-statused accepted; downgrading it to proposed would state the truth ("nobody has decided against this, nobody has built it") without manufacturing a decision the project never actually deliberated. This record decides the question mainly because an accepted-but-unbuilt ADR is inconvenient for the checkpoint machinery, and that is a poor reason to close a live design question.
affected_files:
  - dashboard_app/src/app/page.tsx
---

## Context

`dec-160` (2026-05-12, `accepted`, `category: architectural`) decided to add a dashboard
`/overview` landing composed from the existing view-models, and to change `/`'s redirect from
`/architecture` to `/overview`. Its `affected_files` name five paths, three of which are new
components:

- `dashboard_app/src/app/overview/page.tsx`
- `dashboard_app/src/server/view-models/overview.ts`
- `dashboard_app/src/components/overview-grid.tsx`

Verified in this checkout on 2026-09-06: **none of the three has ever existed in git
history**. `dashboard_app/src/app/` carries `adrs`, `api`, `architecture`, `documentation`,
`evals`, `metrics`, `roadmap`, `sentinel`, `workshops` — no `overview`. `dashboard_app/src/app/page.tsx`
still reads `redirect("/architecture")`. The only `overview` matches anywhere in
`dashboard_app/src` are `sidebar-signals.ts` and `renderers/plan-view.tsx`, neither of which
is this surface.

The decision was recorded as "recommended as **second-cut** work ... but recorded now so it is
in the implementation plan". Four months later it is not in any implementation plan, the
sidebar live-signal need it was to feed has been served by `sidebar-signals.ts`, and no
consumer has asked for the surface.

An `accepted`, `architectural` ADR asserts something about the **design target**: that the
system's component inventory includes these three components. That assertion is false and has
been false since the day it was written. It also carries three dangling `affected_files`
paths, which any code-to-ADR triangulation reads as a defect in the code rather than in the
record.

## Decision

**The `/overview` landing is not adopted. `/` continues to redirect to `/architecture`.**
`dec-160` is superseded: it flips to `status: superseded` with `superseded_by:
dec-374`, and its three phantom components leave the design target.

**Why supersession and not retirement.** The retirement protocol is for the case where a later
decision's *action removed this decision's subject* — the question itself is gone. That is not
what happened here. The question "should the dashboard have an at-a-glance landing?" is still a
perfectly live question; nothing removed it. What happened is that the question is now being
answered *differently*, which is exactly what supersession is for. Recording this as
`retired` would misstate the history and would require naming a removing decision that does
not exist.

**Why not simply leave it accepted as tracked debt.** An `accepted` architectural ADR is a
claim about what the system is designed to be. Keeping it means the design target permanently
includes three components nobody intends to build, and every checkpoint pass, triangle check
and new reader has to re-derive that the claim is stale. A record that must be explained is
worse than a record that is closed.

**Frontmatter edits required** (planner schedules; the implementer applies them as mechanical
edits specified here):

- `.ai-state/decisions/160-overview-landing-surface.md`: `status: accepted` → `status: superseded`;
  add `superseded_by: dec-374` (finalize rewrites it to the assigned `dec-NNN`).
- `affected_files` on `dec-160` is **left as written**. The list is part of the historical
  record of what was proposed; this record explains why three of its entries never
  materialised. Editing it would erase the evidence for this decision.
- No `DECISIONS_INDEX.md` regeneration by hand — finalize regenerates it.

## Considered Options

### A — Retire (`status: retired`, `retired_by: [...]`)

Rejected on protocol grounds: nothing removed the subject, no removing decision exists to name
in `retired_by`, and the question is still live. Retirement would be a category error.

### B — Leave `accepted`, open a tech-debt row for "build it or decide"

Pros: no ADR churn; keeps the option visibly open. Cons: the design target keeps asserting
three components that do not exist, indefinitely; a debt row about an ADR is a note that a
decision needs deciding, which is the decision this record is making anyway.

### C — Downgrade to `status: proposed`

Pros: arguably the most literally accurate description of the record's actual standing — it
reads as a proposal and was never acted on. Cons: leaves a four-month-old proposal in limbo
with no rationale attached and no closure; and a backwards status transition on a finalized
record has no protocol and no precedent in this corpus. See `dissent:` — this is the runner-up
and it is not a weak one.

### D (chosen) — Supersede with a decision not to adopt

Pros: protocol-clean; closes the question with reasons; removes three phantom components from
the design target; leaves a durable trail for whoever asks "why is there no overview page?".
Cons: manufactures a decision event that the project did not deliberate at the time (see
`dissent:`).

## Consequences

**Positive.** The design target stops claiming three components that do not exist. Three
dangling `affected_files` paths stop reading as code defects. A future reader asking why `/`
lands on `/architecture` finds the answer instead of a contradicting ADR. `dec-160`'s
substantive analysis — the composition-over-new-store reasoning, the degradation ladder —
stays readable in the superseded record for whoever revisits the question.

**Negative.** A live design question is closed by an agent rather than by the operator who
would use the surface. The `/` landing remains `/architecture`, which is the densest surface
and a debatable front door — the need `dec-160` identified was real even if the response was
not built.

## Prior Decision

`dec-160` decided to add an `/overview` route backed by a composing view-model, plus a
`/` redirect change and sidebar live badges. **What changed:** four months elapsed with none of
the three new components created in any commit; the sidebar-signal need was met by
`sidebar-signals.ts` without the landing page; and no operator request for the surface has been
recorded. The design target should reflect what the project intends, and it does not intend
this. `dec-160`'s reasoning about *how* to build it — pure composition of existing
view-models, no new store, tile-by-tile degradation — remains correct and is the starting point
if the question is re-opened.

## Disconfirmation

**Falsifier.** An operator (or a managed-project user of the dashboard) reports that answering
"is anything on fire?" requires touring the surfaces, and that a landing page would have saved
the tour. That is the need `dec-160` named; one concrete instance of it makes this decision
wrong.

**Steelmanned runner-up (Option C, downgrade to `proposed`).** Nothing about the project's
situation changed between 2026-05-12 and today except that nobody got to it. Reading "not yet
built" as "decided against" attributes an intention to the project that the project never
formed, and it does so under pressure from a checkpoint validator rather than from any design
argument. The honest record of an un-acted-on proposal is a proposal, and `proposed` is
already in the status enum precisely for records whose question is open. This decision's real
justification is corpus hygiene, and corpus hygiene is a weak reason to close a design
question.

**Reversal trigger.** Either (i) the falsifier above; or (ii) the dashboard grows past roughly
a dozen surfaces, at which point "where do I start?" becomes a navigation problem an operator
will hit before any of the individual pages, and `dec-160`'s composition design should be
re-opened rather than re-derived.
