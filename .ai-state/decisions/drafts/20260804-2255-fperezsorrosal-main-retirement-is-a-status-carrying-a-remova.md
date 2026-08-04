---
id: dec-draft-5bcdc6fe
title: Retirement is a status carrying a removal list, not an archive directory
status: proposed
category: architectural
date: 2026-08-04
summary: 'A decision whose subject was removed gets the retired status plus a `retired_by` list naming the removing decisions; terminal records stay in place and the lifecycle split is delivered by status and index filtering rather than by moving files into an archive subdirectory.'
tags: [adr-conventions, decision-lifecycle, retirement, supersession, schema, decision-graph, gate-liveness]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: standard
dissent: An archive directory makes the active/terminal split visible in the filesystem itself, which no amount of status filtering achieves; a reader with `ls` sees the live corpus immediately, whereas status filtering is invisible until some tool renders it.
affected_files:
  - rules/swe/adr-conventions.md
  - skills/software-planning/references/adr-authoring-protocols.md
  - agents/sentinel.md
  - scripts/adr_health.py
---

## Context

The decision corpus had exactly two terminal transitions: `superseded` (which requires a replacing decision to exist) and `rejected`. Neither fits the commonest way a decision stops binding — its *subject* is deleted. A supersession rate near 4% across 316 records was read as decisions rarely being revisited; classifying reference decay by cause showed the opposite. Removals had been happening continuously and going unrecorded, because no vocabulary existed to record them.

A manual pass over every `removed-by-later` finding produced a sharper result than expected: **zero of them warranted a supersession link.** Most were decisions that outlived the file they cited and needed only a repaired path. The rest were decisions whose question had been abolished rather than re-answered.

Two structural facts closed the question. First, `supersedes` and `superseded_by` are typed `string`, making supersession strictly 1:1 — but one removal routinely strands several decisions at once (a subsystem deletion stranded five; a dashboard-runtime replacement stranded eight), so the reciprocal half is unwritable. Second, recording removal as supersession asserts that the removing decision weighed and replaced the removed one, which is false: it answered a different question and never considered the record it stranded.

## Decision

Add `status: retired` with a required companion `retired_by` field, typed **list**, naming the decisions whose action removed this decision's subject. The removing decisions are not modified. Retired records are preserved and re-open — back to `accepted`, `retired_by` cleared — if the subject returns.

**Terminal records stay in `.ai-state/decisions/`.** The lifecycle separation is delivered by status plus index filtering; no archive subdirectory is created.

The distinguishing test is what a reader can compare: supersession answers the same question differently, so two answers sit side by side; retirement abolishes the question, so there is no second answer.

## Considered Options

### Archive subdirectory holding terminal records (the originally planned shape)

Mirrors the tech-debt ledger's active/resolved file pair, and makes the split visible in the filesystem.

**Cons, measured rather than assumed.** The analogy breaks on the property that matters: nothing links to a ledger row by path, so migrating a row is free. ADRs are linked by path 234 distinct times across docs, rules, and skills — one record is linked 21 times — and the conventions *require* persistent documents to link the finalized path. Every link to a moved record dangles.

Worse, `finalize_adrs.py` derives the next `NNN` by iterating the decisions directory and skipping anything that is not a file. Move terminal records into a subdirectory and the scan stops seeing them, so the next promotion reissues an archived record's id the first time a recent decision goes terminal — a silent identity collision in a corpus where `dec-NNN` *is* the identity. Six further consumers glob the directory flat and would narrow silently, and the dashboard lists it flat and would drop archived records from its view.

The benefit it was to deliver — an active-only index — was already measured as negligible: terminal records numbered 12 against an index whose weight lies in a column every row carries.

### Reuse `superseded_by` for removals

No new vocabulary. But it is 1:1 where the relation is many-to-one, so the common case cannot be written at all; and it asserts a deliberation that did not occur, corrupting the meaning of every genuine supersession in the corpus.

### Leave removals unrecorded

Zero cost, and the status quo. It is also the cause being fixed: the removal edges exist in reality, and a classifier re-derives the same findings from git history on every run because nothing durable absorbs them.

## Consequences

**Positive.** The many-to-one removal relation becomes representable. Retirement stops competing with supersession, so `supersedes` keeps meaning "answered differently". Terminal records leave the decay classifier's scope automatically, since it already skips terminal statuses — the three retirements applied here were excluded with no code change. No path link breaks, no consumer narrows, no identity can collide. Re-opening is a status flip rather than a file move.

**Negative.** The active/terminal split is not visible from a directory listing; it requires a tool or the index to render. `retired_by` is one-directional, so the removing decision carries no trace of what it stranded — discoverable only by querying from the retired side. And a fourth cross-reference field enlarges a frontmatter schema that is already wide.

## Disconfirmation

**Falsifier.** If terminal records grow to a large enough share that reading `.ai-state/decisions/` becomes the bottleneck a directory split would fix — and if by then path links have migrated to id-form references, removing the dangling-link objection — the directory move becomes correct and this decision wrong. The measurable trigger is terminal share, not corpus size.

**Steelmanned runner-up.** The archive directory is genuinely better on discoverability: a filesystem split needs no tooling, survives every consumer that has not been taught about status, and fails visibly rather than silently. Status filtering is invisible until something renders it, and any new consumer that forgets to filter silently treats retired decisions as live — the same class of error this effort keeps finding, merely relocated. The counter is narrow: the id-assignment collision is unacceptable at any discoverability price, and it is a property of the move rather than of the archive concept.

**Reversal trigger.** Revisit if `finalize_adrs.py` moves to id-assignment that does not derive from a directory listing, and persistent documents move to id-form references. Both objections are properties of today's mechanisms, not of the archive idea; remove them and the trade-off inverts.
