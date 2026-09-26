---
id: dec-395
draft_id: dec-draft-a064b32a
title: Keep WIP.md separate from IMPLEMENTATION_PLAN.md — decline the roadmap's P2.4 merge clause
status: accepted
category: behavioral
date: 2026-09-26
summary: A timeboxed Spike measured the WIP/plan pair over 18 harvested pipelines and found no duplication (median 1% restated prose) and no split-caused incident, so WIP stays its own status artifact; the roadmap's merge clause is declined, not deferred.
tags: [process-economy, pipeline, artifact-floor, wip, implementation-plan, spike, roadmap-p2-4]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: spike
affected_files:
  - docs/independent-analysis/process-economy-roadmap.md
affected_reqs: []
dissent: "Title restatement is real (median 14%, up to 85%) and WIPs grow to 35–50 KB of append-only narrative; one document would at least give that narrative a single home."
---

## Context

The process-economy roadmap's P2.4 row folds `WIP.md` checkboxes into `IMPLEMENTATION_PLAN.md`, citing Böckeler's "repetitive with each other" critique. dec-394 kept WIP as its own floor artifact and left the merge to a separate value Spike. About 143 tracked files name `WIP.md`, roughly 18 of them load-bearing source (the dec-393 step parsers, `compose_handoff.py`, dashboard view-models, compaction hooks, the eval manifest) plus about 20 shape-asserting tests and one shipped canonical block (`hackathon-mode.md`).

## Decision

Keep the two files separate. The plan stays the stable description of the work; WIP stays the volatile status ledger. The merge clause is declined.

Criteria were pre-registered before measurement: merge only on ≥ 2 split-caused incidents with a nameable cost, or on WIP restating > 40% of the plan.

- **Prose overlap:** median 1% of WIP 8-word shingles occur in the plan (max 11%, n = 18); a line-exact method gives 0%.
- **Incidents:** 0 of 5 candidates qualify. Two are parser bugs, already resolved by dec-393. Three are status fields nobody flipped, and those would recur inside a merged document.
- **Source:** Böckeler's critique targets spec-kit's generated-document pile, not a stable-plan/volatile-status pairing.

## Considered Options

| Option | Measured value | Cost / risk |
|---|---|---|
| Merge WIP into the plan | None: nothing duplicated to remove; imports up to 50 KB of per-batch narrative into a file every writer spawn reads | Rewrite the dec-393 parsers, ~18 consumers, ~20 tests and a shipped block (fleet-wide one-way door) |
| Slim WIP to a pure status ledger | Small: only step titles repeat (median 14%), and they are the checklist's index key | Low, but no measured problem to fix |
| **Keep (chosen)** | Plan and WIP change for different reasons at different rates | None |

## Consequences

- P2.4's "19 → 6 documents" target must find its reduction elsewhere, if duplication exists among the other artifacts. This Spike did not measure those.
- WIP growth is a separate observation: an append-only narrative (per-batch logs, rework rounds, a 21 KB "Current Step") that belongs in `LEARNINGS.md` once a batch closes. That is a compaction question, not a merge question.
- Reversal trigger: ≥ 2 split-caused incidents with a nameable cost, or median shingle overlap above 20% on a re-measure.
