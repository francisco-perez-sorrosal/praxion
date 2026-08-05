---
id: dec-318
title: Architectural means the inventory changed, not that the trade-off was hard
status: accepted
category: architectural
date: 2026-08-05
summary: 'Replace the unfalsifiable "significant trade-off" definition with a two-part test — a decision is architectural iff it changes the component inventory or a boundary between components, or it changes a published contract — and ship a measurement of the resulting category mix rather than a gate the test cannot support.'
tags: [adr-conventions, decision-taxonomy, falsifiability, category, corpus-volume, measurement, gate-liveness]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: standard
dissent: A definition with no mechanical gate is an exhortation, and exhortations are exactly what produced a category holding 84% of recent decisions; a measurement watched by an auditor is weaker than a check that refuses the commit.
affected_files:
  - rules/swe/adr-conventions.md
  - skills/software-planning/references/adr-authoring-protocols.md
  - agents/systems-architect.md
  - skills/software-planning/references/coordination-details.md
  - scripts/adr_health.py
---

## Context

`category: architectural` was defined as "significant trade-offs: system boundaries, data model, technology selection, security". Every feature involves a significant trade-off, so the category grew to hold **227 of 317 decisions (72%)** — and **84% of the most recent 50**, meaning it was not merely broad but widening. A category holding most records distinguishes nothing, and the cost lands on every consumer that treats `architectural` as a filter.

The planned replacement bound the category to the architecture model: architectural iff the decision constrains a model element or edge. Measurement refuted it. Read as "touches a component" it bounds nothing, because the 16 structural components tile essentially the whole repository. Read as "edits the model" it admits **2 of 227**, which would mean two architectural decisions in four months.

Sampling the 192 decisions the strict test would demote showed they are not miscategorised. They decide which components exist and how responsibility divides — *implement this capability as an agent rather than a skill*, *prevent duplication with existing agents rather than a new one*, *this is where one agent's remit ends*, *introduce a pluggable backend abstraction*. Those are architectural in the strongest available sense, and they do not touch the model because **the model does not represent that layer**: it describes structural containment, while ADRs decide capability composition. The planned test was measuring the wrong axis.

## Decision

A decision is `architectural` **iff it changes what exists or what connects**: it adds, removes, merges, or splits a component in any artifact family; moves a responsibility between components; or introduces or removes a boundary between them — **or** it changes a canonical block, shipped template, or onboard-contract phase. If the inventory and its boundaries are unchanged once the decision lands, it is not architectural *however consequential the trade-off*.

The falsifier is a question a reviewer can answer: **name the component added, removed, or whose responsibility moved.** No name, wrong category.

The published half is kept verbatim from the plan — it is exact and mechanically checkable. Only the internal half is replaced.

**A measurement ships, not a gate.** Whether a decision changed the component inventory is not derivable from its frontmatter, so `adr_health.py` reports the category mix across the corpus and a recent window, and a sentinel check surfaces the recent architectural share against the adoption baseline (72% corpus / 84% recent). No retroactive migration.

## Considered Options

### Bind the category to the architecture model (as planned)

Would have bounded decision volume to model size — the original and appealing argument.

Refuted by measurement in both readings, as above. Adopting it anyway would demote genuine agent-boundary and composition decisions while promoting nothing comparable, corrupting the category in the opposite direction.

### Ship only the published half, leave the internal half undefined

Honest and minimal: the published half needs no judgment. But it covers 33 of 227 records, leaving the overwhelming majority of decisions with no test at all — which is the status quo for everything that matters most.

### Require architectural ADRs to name the changed component in frontmatter

Would make the claim self-evidencing and its presence mechanically checkable. Rejected for now on the same ground that declined an earlier field: a schema addition should follow a consumer that needs it, and the falsifier already asks the question in prose. Reconsider if the measurement shows the share unmoved.

### A blocking gate on the category

There is nothing sound to gate on. A gate that cannot see its own subject is the failure this effort has now found six times, and adding a seventh deliberately would be indefensible.

## Consequences

**Positive.** The test is answerable rather than felt, and its falsifier is a single question. It admits every genuine composition and boundary decision in the sample and excludes every process, policy, and feature one. The published half stays exact. The category mix becomes observable, so whether the definition works is a measurement rather than an opinion. Nothing migrates, so the historical corpus stays legible as evidence of what the old definition permitted.

**Negative.** The internal half rests on judgment, and judgment drifts — two architects may disagree on whether a responsibility "moved". The measurement reports the ratio but cannot attribute a wrong call to a specific decision, so a slow slide back is visible in aggregate and invisible per record. And the recent-window share is noisy at 50 records; a single burst of genuine architectural work will move it without meaning anything.

## Disconfirmation

**Falsifier.** If the recent architectural share sits at or above the 84% baseline several audits after adoption, the test is not being applied and a definition change was the wrong instrument — the constraint would then have to move to the authoring surface, most plausibly the frontmatter field declined above.

**Steelmanned runner-up.** The model-binding test had one decisive virtue this one lacks: it was mechanically checkable, so it could never be quietly ignored. A judgment-based test in a prompt is exactly the kind of instruction that erodes, and the honest reading of "84% and rising" is that the previous prose definition eroded completely. A test that cannot refuse anything may simply produce the same outcome more articulately.

**Reversal trigger.** Revisit when ADRs gain a durable link to the model or to fitness invariants — the link whose absence refuted the planned test. Should decisions routinely cite the element or invariant they constrain, the mechanical binding becomes available and this definition should yield to it.
