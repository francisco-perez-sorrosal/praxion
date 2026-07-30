---
id: dec-300
title: Wave-1 selection scope — Tier 1 registry predicates and Tier 2 self-nomination ship; Tier 3 identity genesis defers behind an evidence gate
status: accepted
category: architectural
date: 2026-07-30
summary: The authored trigger table lives in the discipline registry's fires-when column (zero always-loaded cost) and self-nomination reuses the existing nomination path unchanged; Tier-3 identity genesis is deferred because skill-genesis has no discipline-proposal slot and because proposing new routes before the existing route has produced one measured disposition is an uncalibrated router breeding routers.
tags: [multidisciplinary-identities, discipline-consultant, selection-tiers, identity-genesis, skill-genesis, scope-fence, deferral, wave-1]
made_by: agent
agent_type: systems-architect
branch: worktree-multidisciplinary-identities
pipeline_tier: full
affected_files:
  - skills/multi-perspective-analysis/references/discipline-registry.md
  - rules/swe/swe-agent-coordination-protocol.md
  - agents/researcher.md
  - agents/systems-architect.md
  - agents/implementation-planner.md
  - agents/verifier.md
  - agents/skill-genesis.md
affected_reqs:
  - REQ-04
  - REQ-15
  - REQ-18
dissent: Deferring Tier 3 keeps the roster under human curation indefinitely, and the user's stated sub-goal was that identities be ideally auto-identified — a gate keyed to twenty ledger rows on a mechanism convened rarely and only behind an honest-uncertainty gate may take many months to clear, so "deferred with a recorded path" is in practice a decision not to build the auto-discovery the user asked for.
---

## Context

The requirement is that identities be managed by the agents themselves, optionally user-proposed, ideally
auto-identified by orchestrators or specialist agents. That requirement collides head-on with the strongest
negative result in the persona literature: aggregating the *oracle-best* persona per question improves accuracy
significantly, while **automatically identifying it performs no better than random**. Implemented as free-form
model self-selection over an open-ended persona space, auto-identification is specifically predicted to fail.

A three-tier model was proposed at intake to deliver automation without that failure mode: an authored
signal→discipline trigger table evaluated mechanically (Tier 1), specialist-agent self-nomination citing the
triggering signal and the decision at stake (Tier 2), and identity genesis in which recurring "we needed an X
here" signals are harvested and a **new** discipline is *proposed* for user disposition (Tier 3).

Wave A tested each claim and returned two findings that change the scope:

- **Tier 1's placement was unresolved and nearly went wrong.** Guided routing over a bounded roster does beat
  random, replicated across two 2026 studies with large margins (routed 73.5 > always-on 72.2 > random 70.5;
  capability-aware assignment better than random by up to 29.7%, with random's σ=3.5% naming the reliability cost
  of unguided selection). But **every validated router retrieved is learned or model-scored — hand-authored
  routing remains untested.** Separately, the context-engineer's review *provisionally recommended* putting a
  discipline-enumerating predicate list into an always-loaded rule, then **retracted** it on the grounds that
  doing so violates the extensibility criterion by construction — a documented near-miss worth preserving.
- **Tier 3's "reuses existing machinery" claim was aspirational, not true.** Verified directly against the
  harvesting agent's definition: its triage decision tree has exactly three leaf types (rule / skill / CLAUDE.md
  addition) and its proposal-entry `Type:` enum has no `discipline (new)` value, with no delegation row for one.
  Tier 3 is build-not-wire.

## Decision

**Tier 1 and Tier 2 ship in Wave 1. Tier 3 defers behind an explicit evidence gate with a recorded build path.**

**Tier 1 — the registry *is* the trigger table.** The authored signal→discipline predicates live in the discipline
registry's `fires-when` column. This is the placement that costs nothing always-loaded: the registry is an
on-demand reference file inside a skill already HARD-gated by the honest-uncertainty gate, so the gate Tier 1
needs already exists and is already enforced. **No rule file enumerates a discipline.** The always-loaded
Proactive-Agent-Usage bullet names the **mechanism** ("a registry trigger predicate matches"), never the roster —
which is exactly what makes the extensibility invariant assertable by the fitness test. Tier 1 still satisfies the
"bounded, authored predicate table, not free-form guessing" property that distinguishes it from the refuted
mechanism; it is evaluated by the convener reading a bounded table, not by a model improvising over an open space.

**Tier 2 — self-nomination ships unchanged.** `researcher`, `systems-architect`, `implementation-planner`, and
`verifier` may convene a consultant, and a nomination **must cite the triggering signal and the decision at
stake** — the same two fields a challenge carries, so a bad nomination surfaces as a dismissed challenge and is
counted in the ledger. This is auditable and falsifiable rather than free-form. No new mechanism is required: it
is mechanically identical to nominating either existing sub-architect today.

**Tier 3 — deferred.** Two independent reasons:

1. **It is build, not wire.** It requires one new triage leaf, one new `Type:` enum value, and one new
   Recommended-Delegations row in the harvesting agent, routing to `context-engineer` (mirroring the existing
   skill and rule rows). That is a small, well-understood change — but it is a change, and the intake claim that
   it was free was wrong.
2. **The ordering is epistemically wrong.** Tier 3 proposes **new disciplines**. Proposing new routes before the
   existing route has produced a single measured disposition is an uncalibrated router breeding routers. The
   authored table is itself the untested mechanism; automating its expansion first compounds the risk rather than
   reducing it.

**Gate:** ≥20 ledger rows spanning ≥2 disciplines, with a dismiss rate below the pre-registered falsifier
threshold. **Path:** the three edits named above.

> **Amendment 2026-07-30 (`dec-304`).** There is no longer a "pre-registered falsifier threshold"
> to be below — the discipline-#2 criterion was demoted from a binary threshold to a reported estimate with a
> Wilson interval, denominated in distinct consults rather than challenge rows. Read this gate as: ≥20 ledger
> rows spanning ≥2 disciplines, with the discipline-#2 criterion satisfied **per discipline, not pooled**
> (pooling lets one discipline's failure be concealed by another's volume). Current definition:
> `docs/multidisciplinary-identities-evidence.md` §17.4; reasoning: §17.11.

**User override remains available at every tier** through the `/consult` command — the human half of the dialogue
requirement, and the escape hatch that makes the tier gating safe rather than restrictive.

Two further items are fenced out of Wave 1 by the same reasoning:

- **The portable distillation reference** (a generalized "how to add domain consultants to any pipeline" excerpt
  destined for the multi-perspective skill's reference set) is deferred to the same gate. The split-placement
  analysis behind it is accepted and unchanged — this project's own byte counts and skill-gap analysis do not
  transfer to a managed project, while a genuinely portable kernel exists — but shipping design advice into
  managed projects before the mechanism has produced one measured disposition would export unvalidated guidance.
- **Wave-2 disciplines** are out of scope per the one-discipline ruling. Each is a future registry row; the one
  that shares an existing lens's owning artifact additionally needs its escalation relationship written first.

## Considered Options

### Option 1 — All three tiers in Wave 1

- **Pros:** delivers the full stated requirement including auto-identification; the harvesting-agent edits are
  small and well-understood; the roster could grow without human curation from day one.
- **Cons:** automates expansion of a routing table that is itself unvalidated; the harvesting extension is real
  work whose value cannot be assessed until Tier 1 has produced data; and it front-loads the exact mechanism the
  literature predicts will fail if it degrades toward open-ended self-selection.

### Option 2 — Tier 1 + Tier 2, Tier 3 gated (chosen)

- **Pros:** day-one automation via mechanical predicate matching; specialist judgment enters at Tier 2 at zero
  cost using a proven path; the untested component (authored routing) gets measured before its expansion is
  automated; the deferral is gated on a concrete threshold with a three-edit path recorded, not left vague.
- **Cons:** the roster stays under human curation until the gate clears, which may be a long time given how
  rarely a gated mechanism is convened — so the user's "ideally auto-identified" goal is met later rather than now.

### Option 3 — Tier 1 only

- **Pros:** the smallest possible surface; a single selection mechanism to evaluate.
- **Cons:** discards a free, proven capability — Tier 2 requires no new mechanism at all — and removes the
  channel through which the specialist agents' own domain judgment enters. Also removes a useful cross-check on
  Tier 1: a discipline that is repeatedly self-nominated but never fires on its authored predicate is direct
  evidence that the predicate is miswritten.

## Consequences

**Positive:** the authored trigger table costs zero always-loaded bytes and is co-located with the roster it
routes over, so a new discipline's predicate arrives with its row; self-nomination costs nothing and adds an
independent signal for validating Tier 1's predicates; the gated deferral keeps the roster from growing before
there is any evidence the routing works.

**Negative:** auto-identification is postponed; the roster's growth remains a human decision in Wave 1; two
deferred items now depend on the same evidence gate, so a stalled ledger stalls both.

**Risks accepted:** the registered objection that hand-authored routing is untested against a random baseline
**stands unrefuted** and is carried forward rather than resolved. Tier 1 is *analogous to* a validated mechanism,
not an instance of one — every validated router in the retrieved literature is learned or model-scored. The
falsifier should be measured on **variance as well as mean** accepted-challenge rate, since random assignment's
concrete cost showed up as a 3.5% standard deviation rather than only as a lower mean. The ledger is the only
thing that can retire this objection, which is the second independent reason it is a prerequisite.

## Disconfirmation

- **Falsifier:** Tier-1 trigger-table selection performing no better than random discipline assignment on
  accepted-challenge rate (mean *or* variance). Concretely — if `statistician` fires on its authored predicate
  and its challenges are dispositioned no better than challenges from a discipline convened arbitrarily, the
  authored table is decoration and selection should be replaced by a learned or model-scored gate. A second,
  sharper signature: a discipline repeatedly convened by Tier-2 self-nomination on tasks where its Tier-1
  predicate did *not* match means the predicate is miswritten, which is a cheap fix rather than a refutation.
- **Steelmanned runner-up:** Option 1 (all three tiers now). Its strongest case is that the gate as written may
  never realistically clear. A mechanism convened only behind an honest-uncertainty gate, on a repository that
  runs a handful of Standard/Full pipelines a month, could take many months to accumulate twenty dispositioned
  challenges across two disciplines — and Wave 1 ships only *one* discipline, so the "≥2 disciplines" clause
  cannot be satisfied at all until a Wave-2 discipline lands, which is itself gated. That is a plausible deadlock,
  and under it "deferred with a recorded path" is functionally a decision not to build the auto-discovery the
  user asked for. The honest counter is that the harvesting extension is genuinely small and can be revisited on
  request rather than only on the metric.
- **Reversal trigger:** the gate clearing (≥20 rows, ≥2 disciplines, dismiss rate under threshold) — **or** the
  gate demonstrably deadlocking, evidenced by fewer than five ledger rows accumulated after two calendar quarters.
  The second is as important as the first: a gate that cannot clear is not a gate, and its failure should reopen
  the tier question rather than silently freeze the roster.
