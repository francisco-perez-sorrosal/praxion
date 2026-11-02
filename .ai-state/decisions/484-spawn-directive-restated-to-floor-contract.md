---
id: dec-484
draft_id: dec-draft-fb3831ad
title: "The orchestrator directive is restated: omit model by default, pass one only for a listed deviation"
status: accepted
category: behavioral
date: 2026-10-31
summary: "The routing directive no longer says pass the row's alias on every spawn or that a skipped alias falls through to the session model; it says a spawn passing no model runs at its definition's floor, held equal to the table by the parity gate, and lists the closed set of per-spawn deviations: consultant opus unless routine, test-engineer acceptance design opus, verifier light review sonnet, researcher modes, implementer step hint."
tags: [rules, startup-context-diet, moves, model-routing, path-scope]
made_by: agent
agent_type: systems-architect
branch: worktree-model-routing-move
pipeline_tier: standard
affected_files:
  - rules/swe/agent-model-routing.md
  - rules/swe/agent-model-routing-resident.md
  - skills/agent-crafting/references/model-routing-policy.md
superseded_in_part_by: [dec-draft-47003576]
---
## Context

dec-078's "pass `model` on every spawn" guarded roles that had no frontmatter floor. Today all 17 definitions carry one, 16 equal to the table and the consultant's floor deliberate; the parity gate blocks drift at commit. The old text's fall-through claim is false, and its always-pass form asks the orchestrator to pass `claude-haiku-4-5`, an id the Agent tool refuses: its `model` parameter takes only the aliases `sonnet`, `opus`, `haiku` and `fable` (Claude Code subagent docs, read 2026-11-01), inviting the `haiku` alias that lands on Haiku 3.5.

## Decision

Replace the one directive paragraph with the restated directive and its closed deviation list (wording in the plan's Architecture; the deviation set equals the spawn-model check's sanctioned set). The policy reference's direct-invocation entry points are restated to match.

## Considered Options

### Restate (chosen)
True text; no unpassable id; deviations named where the orchestrator reads them.

### Keep the always-pass directive
Redundant with the floor and parity gate; keeps a false claim; cannot be honoured for the L tier.

## Consequences

- Positive: the session-start text is short, true and complete for every sanctioned deviation.
- Negative: the always-pass redundancy as a drift guard is gone, replaced by the parity gate and the spawn-model check; a non-routine consult now needs an explicit `opus`.

Activation: no — the honest-uncertainty gate does not fire; dec-480's precedent and concrete option costs decide it.
