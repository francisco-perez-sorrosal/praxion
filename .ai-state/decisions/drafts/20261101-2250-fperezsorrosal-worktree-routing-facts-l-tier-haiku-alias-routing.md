---
id: dec-draft-47003576
title: "The L tier routes by the haiku alias, passable per spawn and through the step-loop driver"
status: proposed
category: behavioral
date: 2026-11-01
summary: "The L tier is the haiku alias, not the pinned claude-haiku-4-5. The researcher's lookup mode and the implementer's tier: L hint pass haiku per spawn, and the step-loop driver requests haiku for a tier: L step. tier: L is reserved for short mechanical steps. The routing texts state the harness's current resolution order with the env var's FORCE condition."
tags: [model-routing, haiku, l-tier, step-loop, spawn-directive, resolution-order]
made_by: agent
agent_type: systems-architect
branch: worktree-routing-facts
pipeline_tier: standard
affected_files:
  - rules/swe/agent-model-routing.md
  - rules/swe/agent-model-routing-resident.md
  - skills/agent-crafting/references/model-routing-policy.md
  - agents/doc-engineer.md
  - scripts/_plan_steps.py
  - scripts/_step_loop_render.py
  - scripts/check_spawn_models.py
supersedes_in_part:
  - dec-484
re_affirms:
  - dec-078
  - dec-372
---

## Context

The routing texts pinned the L tier to `claude-haiku-4-5` on the grounds that the bare `haiku` alias resolved to Haiku 3.5. The Claude Code docs, re-read on 2026-11-01 (sub-agents and model-config pages), contradict that. `haiku` resolves to Haiku 5.5 on the Anthropic API and to Haiku 4.5 on Bedrock, Google Cloud's Agent Platform, Foundry and Claude Platform on AWS. It never resolves below 4.5 and never to Haiku 3.5, which is retired.

The Agent tool's per-spawn `model` takes only `sonnet`, `opus`, `haiku` or `fable`. The pin was therefore unpassable, so the researcher's simple-lookup mode and the implementer's `tier: L` hint could not be applied as written. The restated directive accordingly called the L tier "not a value to pass". The step-loop driver sent every step without a `tier: H` hint to `sonnet`, so the L tier was unreachable through it.

The texts also listed `CLAUDE_CODE_SUBAGENT_MODEL` first as an unconditional kill switch. Since Claude Code v2.1.251 the order is: per-spawn `model`, then frontmatter `model:`, then the environment variable, then the main session. The variable overrides the other layers only with `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` (v2.1.257+), which also makes Claude Code ignore frontmatter and stops a per-spawn model being passed.

## Decision

1. The L tier is the `haiku` alias everywhere it is named: the Tier Table row, the doc-engineer's `model:` floor and the policy reference.
2. The researcher's simple-lookup mode and the implementer's `tier: L` hint are passed per spawn as `haiku`. The step-loop driver requests `haiku` for a `tier: L` step, `opus` for `tier: H`, and the definition's floor otherwise. The doc-engineer gains no per-spawn deviation and is never routed up.
3. The quality-cliff guard is restated beside the implementer override. `tier: L` is for short mechanical steps only, and long-horizon autonomous coding (more than ten tool calls) stays at `sonnet` or above.
4. Every routing text states the harness's current resolution order (per-spawn `model`, frontmatter, the environment variable, the session) and calls the variable a kill switch only together with its FORCE condition.

The L tier keeps no `effort` setting, because the alias still resolves to Haiku 4.5 off the Anthropic API and Haiku 4.5 rejects the parameter.

Activation: no. The design-synthesis gate did not fire: the remaining option space was two documented harness behaviours, not contested evidence.

## Considered Options

### Keep the `claude-haiku-4-5` pin (steelmanned runner-up)

The pin is version-stable. It is byte-identical across every provider. It changes nothing in the frozen acceptance fixtures or the exports, and it avoids any surprise in output or cost from a newer Haiku.

Against it:

- Its only stated reason is false.
- On the Anthropic API it is now older than the alias, so it is a downgrade, not a guard.
- The Agent tool refuses it per spawn, so both L-tier deviations stay unusable, and the driver cannot honour `tier: L` without a second, alias-valued representation of the same tier.

Version-locking remains available by pinning a full ID in frontmatter when a real need appears.

### The `haiku` alias, passable everywhere (chosen)

It is never below today's pin (Haiku 4.5 off the Anthropic API) and newer on the API. One value serves the frontmatter floor, the per-spawn deviations and the driver.

### Keep the L-tier hint unreachable through the driver

This leaves the driver as it is and avoids Haiku on implementer steps. It contradicts the directive that names `tier: L` as passable, and it leaves a planner annotation that no path honours.

## Consequences

**Positive:**

- The L tier tracks the newest Haiku on the Anthropic API.
- Both downward deviations and the driver apply the plan's hint as written.
- The routing texts no longer contradict the harness.
- The Codex exports keep their per-agent model settings, because the Codex adapter keys on the Tier column (dec-372).

**Negative:**

- An implementer step hinted `tier: L` now runs on Haiku. Its quality depends on the planner honouring the restated guard.
- The doc-engineer's model changes on the Anthropic API, from Haiku 4.5 to 5.5.
- Earlier frozen acceptance observations pinning the old tokens were amended through answered Spec Questions.

**Partial supersession of dec-484:**

- *Retired:* only its clause identifying the L tier by the pin "not a value to pass".
- *Still holds:* its floor contract (omit `model` by default; pass one only for a listed deviation).

**Re-affirmed:**

- dec-078: the central table with sparing per-spawn overrides for researcher modes and the implementer hint.
- dec-372: its Tier-keyed Codex adapter, whose stated motivation (the Haiku 3.5 claim) is corrected here while the decision itself stands.

## Disconfirmation

**Reversal trigger.** The L tier moves back up to `sonnet` (the doc-engineer floor, and `tier: L` implementer and goal-step routing) if either of these holds over a window of 20 `tier: L` steps or 90 days, whichever comes first.

- **Implementer and goal steps.** Steps routed at `haiku` show a worse verifier FAIL rate, or a worse `revise` rate in intra-step light review, than `sonnet` steps in the same window. Worse means an excess of more than 10 percentage points on either rate.
- **Doc-engineer.** Its runs on `haiku` produce verifier findings against its documentation output at a higher rate than its last 20 runs on the Haiku 4.5 pin.

**Who reads it.** The verifier records the step's routing beside each FAIL. The sentinel's routing audit compares the rates. Each run's verdicts are read with the spawn-model check, so that only spawns that ran at the routed model are counted. A sustained breach opens a ledger row proposing the reversal, and that row then goes to the systems-architect, who decides it.

## Prior Decision

**dec-484 (partially superseded).** It restated the spawn directive as a floor contract, and that contract stands. What changes is its researcher and implementer bullets. They identified the L tier by the pin `claude-haiku-4-5` as "not a value to pass". They now pass `haiku`, because the Agent tool accepts the alias and the alias never resolves below Haiku 4.5. dec-484 stays accepted.

**dec-078 (re-affirmed, unchanged).** Its hybrid routing is unchanged: a central table, with per-spawn overrides only for researcher modes and the implementer step hint. This record makes those named overrides usable for the L tier.

**dec-372 (re-affirmed, unchanged).** It keys the Codex adapter on the Tier column and is unchanged. Its context cited the Haiku 3.5 claim, which is false, but its decision is what keeps the Codex per-agent model settings stable through this alias change.
