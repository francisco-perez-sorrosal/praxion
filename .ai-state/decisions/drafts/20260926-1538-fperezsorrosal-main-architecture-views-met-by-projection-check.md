---
id: dec-draft-c9daa73a
title: Architecture views (roadmap P2.9, D4) are met by the id-bound projection check; the per-subsystem partition is declined
status: accepted
category: behavioral
date: 2026-09-26
summary: "Measured, P2.9's costs are not being paid: agents already read DESIGN.md and docs/architecture.md in slices, the two files conflicted once in 90 days, and the update mandate is already conditional. D4's non-drifting component map is delivered by binding each §3a row to its LikeC4 element id under a blocking checker, not by generating the table."
tags: [process-economy, roadmap-p2-9, architecture-docs, design-md, likec4, aac, partition]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - .ai-state/DESIGN.md
  - docs/architecture.md
  - scripts/check_architecture_projection.py
  - agents/systems-architect.md
affected_reqs: []
dissent: "D4 said 'generated', and a checker still makes a human write every new row; generation would remove that step."
---

## Context

Roadmap item P2.9, under the user's settled decision D4, proposed four changes:

- partition `.ai-state/DESIGN.md` §3b and `docs/architecture.md` per subsystem;
- stop mandating a full update of both per pipeline;
- generate the component map from the LikeC4 model;
- keep rationale in prose.

Its evidence was churn (118 + 79 commits in 120 days) and size (~45k + ~23k tokens "no agent can read whole").

## Decision

Close P2.9 as met. D4's intent, a component map that cannot drift from the model, is already delivered. Every §3a row names its element id, and `scripts/check_architecture_projection.py` fails any commit where rows and elements disagree in either direction. The partition is declined.

Measured over the last 60–90 days of transcripts and history:

| Premise | Measurement |
|---|---|
| Files too large to read whole | 24 sliced Reads vs 1 whole Read of `DESIGN.md`; 16 vs 0 of `docs/architecture.md` |
| Concurrent pipelines collide | 1 merge conflict on either file in 90 days |
| The two docs duplicate each other | 7–16% of 8-word shingles shared between the two §3b sections |
| A full update is mandated per pipeline | The architect already updates only "if the current architecture changes the structural picture" |

## Considered Options

| Option | Value | Cost |
|---|---|---|
| Generate §3a from the model | Removes hand-adding a row per new component (§3a changed in 9 commits in 60 days) | Moves ~15k chars of per-row rationale (dec links, Built/Designed status) into `.c4`, against P2.9's own "prose keeps rationale" |
| Partition §3b per subsystem | No measured problem to remove | Churns two heavily edited files and their section-owner contracts |
| **Keep the id-bound check (chosen)** | Drift is already impossible to commit | None |

## Consequences

- The process-economy programme has no remaining P2.9 work.
- Reversal trigger:
  - whole-file reads become common;
  - or ≥ 3 merge conflicts on these files in 90 days;
  - or §3a rows start being added without rationale, making generation lossless.
