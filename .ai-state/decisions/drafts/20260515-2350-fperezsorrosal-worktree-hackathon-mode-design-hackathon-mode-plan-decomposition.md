---
id: dec-draft-da975828
title: Hackathon mode — implementation plan decomposition decisions
status: proposed
category: implementation
date: 2026-05-15
summary: Three implementation-planner decisions for the hackathon-mode Standard-tier pipeline: (1) 18 ACs as sufficient acceptance basis without a formal behavioral spec; (2) canonical block before BLOCKS registration before consumer embeds ordering; (3) Phase 5b renumbering as its own dedicated step.
tags: [hackathon-mode, implementation-planning, sdd-triage, step-ordering, canonical-blocks]
made_by: agent
agent_type: implementation-planner
branch: worktree-hackathon-mode-design
pipeline_tier: standard
affected_files:
  - claude/canonical-blocks/hackathon-mode.md
  - scripts/sync_canonical_blocks.py
  - commands/onboard-project.md
  - commands/new-project.md
  - tests/test_hackathon_mode.py
re_affirms: dec-draft-ef6b8065
---

## Context

The `hackathon-mode` Standard-tier pipeline reached the implementation-planner stage with a
`SYSTEMS_PLAN.md` (v4, 1,080 lines) containing 18 Acceptance Criteria and a single load-bearing
ADR fragment (`dec-draft-ef6b8065`). Three implementation-planning decisions required resolution
before the 15-step decomposition could be produced.

## Decision

### Decision 1 — 18 ACs are a sufficient acceptance basis; no formal behavioral spec

The SYSTEMS_PLAN has 18 ACs covering testable behaviors. The task is Standard-tier brownfield.
Adding a formal `## Behavioral Specification` section with REQ IDs and a `traceability.yml` would
introduce SDD ceremony that adds no incremental value:

1. Most ACs test hook/config/text behaviors, not complex algorithms. The test surface is
   behavioral (does the hook fire? does the block appear?) not protocol-level.
2. The SYSTEMS_PLAN itself says "SDD ceremony — OFF by default" for hackathon-mode. Applying
   SDD ceremony to the feature that removes SDD ceremony is ironic and disproportionate.
3. The 18 ACs as written are concrete and testable — they are the architect's authoritative
   deliverable. REQ IDs would not make them more testable; they would only add naming overhead.

**Decision: use the 18 ACs from SYSTEMS_PLAN.md as the acceptance basis directly. No formal
behavioral spec. No `traceability.yml`. Test functions describe behaviors; no `AC-` prefixes
per `id-citation-discipline.md`.**

### Decision 2 — Canonical block before BLOCKS registration before consumer embeds

Step ordering: create `claude/canonical-blocks/hackathon-mode.md` (Step 1) → register in
`sync_canonical_blocks.py` BLOCKS dict (Step 2) → embed in consumer commands via `--write`
(Steps 4 and 5).

If the BLOCKS entry is added before the canonical file exists, `sync_canonical_blocks.py --check`
exits 2 (script error: file not found). If the embed is added to consumers before the BLOCKS
entry, the script silently ignores it. The correct ordering ensures each commit boundary keeps
`--check` returning a meaningful result (0 = in sync, 1 = drift, 2 = script error — only 2 is
a problem).

**Decision: canonical file first, registry registration second, consumer embeds third.**

### Decision 3 — Phase 5b renumbering is its own dedicated step

The renumbering of Phase 6→7, 7→8, 8→9 (and sub-phases 8b/8c) in `commands/onboard-project.md`
touches many distinct internal cross-references — §Sections list, §Flow table, §Phase Gates,
gate-map table, gate headline text ("N of 9" → "N of 10"), §Phase headings, §Idempotency
Predicates, cross-references between phases. Bundling this into the Phase 5b content step
(Step 5) would create a step too large to describe in one sentence and too broad to verify
with a single grep. Doing renumbering first then adding content has a different hazard: the
new Phase 5b section would not yet exist when its cross-references are added.

**Decision: add Phase 5b content in Step 5, then renumber in a dedicated Step 6. This preserves
a working file state after each step: Step 5 leaves onboard-project.md with correct Phase 5b
content and `--check` passing; Step 6 corrects all cross-reference numbering.**

## Considered Options

### Option A — Full behavioral spec with REQ IDs

Apply the full SDD spec protocol: add `## Behavioral Specification` to SYSTEMS_PLAN, assign
REQ-01..REQ-18, initialize `traceability.yml`, thread IDs through test steps.

- Con: over-formalized for this scope. The feature itself removes SDD ceremony; applying it
  here is self-contradicting. The 18 ACs are already concrete and testable as written.
- Rejected in favor of Decision 1.

### Option B — Embed consumers before registering in BLOCKS

Add the `<!-- canonical-source: ... -->` anchor to consumers first, before the BLOCKS dict entry.

- Con: `sync_canonical_blocks.py --check` silently ignores the anchor if the block is not in
  `BLOCKS`. The embedded content would also be empty (no canonical file yet). At the first
  `--check` run, the script misses the drift.
- Rejected in favor of Decision 2.

### Option C — Bundle renumbering into the Phase 5b content step

Do Phase 5b content + renumbering as a single step.

- Con: the step would require editing 15+ distinct sections, then verifying every occurrence
  of six old phase numbers. Fails the "describable in one sentence" criterion. Single
  responsibility is violated.
- Rejected in favor of Decision 3.

## Consequences

**Positive:**
- The 15-step plan is tightly scoped, every step leaves the system in a working state, and
  `sync_canonical_blocks.py --check` is a reliable per-step verification artifact.
- No `traceability.yml` cleanup at pipeline end (no file to delete).
- Step size is right-sized: the largest step (Step 5, Phase 5b content) is still a single
  file with a coherent set of related additions, described in one sentence.

**Negative:**
- Decision 1 means AC traceability is informal (step-to-AC table in IMPLEMENTATION_PLAN.md
  rather than a machine-readable YAML). Acceptable for Standard tier.
- Decision 3 adds one step (Step 6) that is purely renaming/renumbering — not a feature
  step. Worth it for clean step boundaries.

## Prior Decision

This ADR re-affirms `dec-draft-ef6b8065` (the architecture decision). The implementation
decomposition decisions here are implementation-layer — they do not modify the architectural
decisions captured in the architect's ADR. `re_affirms: dec-draft-ef6b8065` signals that the
planner reviewed the architectural ADR and found it sound; no supersession.
