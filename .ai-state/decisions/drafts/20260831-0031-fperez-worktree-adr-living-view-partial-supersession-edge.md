---
id: dec-draft-9faf4a80
title: Partial supersession is an edge property — reciprocal id lists, no new status value
status: proposed
category: behavioral
date: 2026-08-31
summary: 'A decision narrowing one clause of an earlier decision records supersedes_in_part / superseded_in_part_by as reciprocal optional id lists; the narrowed record stays `accepted` and the clause text stays in `## Prior Decision`, so index, health, and dashboard consumers need no change.'
tags: [adr-conventions, decision-lifecycle, supersession, schema, frontmatter, data-structure]
made_by: agent
agent_type: systems-architect
branch: worktree-adr-living-view
pipeline_tier: standard
affected_files:
  - rules/swe/adr-conventions.md
  - skills/software-planning/references/adr-authoring-protocols.md
  - agents/sentinel.md
  - scripts/query_adrs.py
  - scripts/finalize_adrs_crossrefs.py
  - .ai-state/decisions/219-project-profile-yaml-archetype-record.md
---

## Context

`dec-263` supersedes exactly one clause of `dec-219` — its "Phase 8f output" producer clause — leaving the schema and `.ai-state/` location in force. The relation exists only in `dec-263`'s prose. Frontmatter can express neither side: `dec-219` stays flatly `accepted`, `dec-263` carries no `supersedes`. A consumer reading frontmatter alone gets a **wrong answer** about the narrowed clause, and `dec-347` made that frontmatter load-bearing for retrieval.

The gap is already visible in the enforcement layer: sentinel DL06 carries a hand-written carve-out paragraph instructing the checker to infer partial supersession from `## Prior Decision` prose, using a `supersedes` + `re_affirmed_by` combination that `rules/swe/adr-conventions.md` never documents. The convention exists in the checker but not in the authoring rule, so authors cannot follow it — and did not.

## Decision

Partiality is recorded **on the edge, not on the node**. Two optional list-typed frontmatter fields:

| Field | On | Meaning |
|---|---|---|
| `supersedes_in_part` | the narrowing record | ids of prior decisions whose *some* clauses this one replaces; those records' `status` is **not** changed |
| `superseded_in_part_by` | the narrowed record | ids of later decisions that replaced some of this record's clauses; this record's `status` stays `accepted` |

Clause identification lives in the narrowing record's `## Prior Decision` section, which becomes required when `supersedes_in_part` is present. No `clause:` frontmatter string is added.

Consumers: DL04 extends its existence check to both fields; DL06 extends its reciprocity check and **deletes** its prose-inference carve-out paragraph; the finalize cross-reference rewrite scope adds both fields; `query_adrs.py` prints a partial-supersession caveat naming the narrowing id while keeping the record in the default view. `regenerate_adr_index.py`, `adr_health.py`, and the dashboard ADR reader change **not at all** — the payoff of the edge-vs-node choice. `dec-219`/`dec-263` are retrofitted (frontmatter only; bodies untouched) so the schema ships with a live instance.

**Why not a `status` value.** `status: partially-superseded` would force every current-streamline consumer into an include-or-exclude decision with no correct answer: excluding drops clauses still in force — strictly worse than today — and including hides the narrowing. That is an illegal state made representable. Keeping `status: accepted` and putting partiality on the relation makes it unrepresentable. Lists, not scalars, for the same reason `retired_by` is a list (`dec-317`): one decision routinely narrows clauses in several predecessors, and a scalar silently under-records the rest.

**Category note.** Recorded as `behavioral`, not `architectural`, under `dec-318`'s falsifier: no component is added, removed, or moved. `dec-317` — the closest precedent, adding `status: retired` + `retired_by` — is categorized `architectural`, but it predates `dec-318` by one day. Following the current test rather than the older precedent is deliberate.

## Considered Options

### A — Reject; prose suffices
Pros: zero schema growth, zero always-loaded tokens; the case is rare (1 of 30 sampled). Cons: leaves a known wrong-answer in a schema that retrieval now depends on, and leaves DL06 inferring intent from prose.

### B — List of objects carrying clause anchors in frontmatter
Pros: the clause becomes machine-addressable. Cons: no consumer could parse or act on a free-text clause anchor; Simplicity First forbids a field nothing uses.

### C — Reciprocal id lists, clause text in the body (chosen)
Pros: makes the *relation* mechanically visible to the four consumers that can use it, while leaving the inherently-prose part in prose; purely additive optional fields; three consumers untouched. Cons: two new schema keys and ~85 always-loaded tokens for a case seen once in thirty records.

### D — New `status: partially-superseded`
Pros: one field, immediately visible in every status-rendering surface. Cons: creates a state with no correct filtering answer, and touches all six frontmatter consumers.

## Consequences

Positive: a consumer reading frontmatter alone can no longer inherit a narrowed clause as if in force. Net rule complexity **decreases** — the schema grows by two optional keys and DL06 shrinks by a paragraph of prose inference. Existing records parse unchanged; absence means "no partial relation".

Negative: two more optional keys in a frontmatter schema that is already wide, for a rare case. Authors must remember a protocol they will use a handful of times a year — the retrofit and the DL06 rewrite are the mitigation, not a solution. A finalize rewrite that misses the new fields would leave dangling `dec-draft-<hash>` ids post-merge; a finalize test asserting rewrite of a draft-stage `supersedes_in_part` is required alongside.
