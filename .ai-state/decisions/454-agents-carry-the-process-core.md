---
id: dec-454
draft_id: dec-draft-03487ff2
title: Every Praxion agent carries the process core inline, and the shared-block gate requires it
status: accepted
category: behavioral
date: 2026-10-11
summary: "All 17 agent definitions carry three byte-identical universal blocks whose canonical text lives in scripts/check_agent_shared_blocks.py: the behavioral contract with the rule's self-test, a Praxion-links rule (relative skills/ and rules/ links resolve under ${CLAUDE_PLUGIN_ROOT} outside the Praxion checkout), and a return contract (~15-line pointer, one terminal marker). The gate now fails a definition that lacks one, computed from frontmatter rather than a roster; the completion handshake's marker check covers report producers too; promethean, roadmap-cartographer and skill-genesis join the contract-bound roster."
tags: [agents, alignment, behavioral-contract, return-contract, completion-handshake, shared-blocks, plugin-root, gate-liveness, startup-context]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - scripts/check_agent_shared_blocks.py
  - scripts/test_check_agent_shared_blocks.py
  - scripts/check_behavioral_contract.py
  - scripts/test_check_behavioral_contract.py
  - agents/agentic-transactions-architect.md
  - agents/architect-validator.md
  - agents/cicd-engineer.md
  - agents/context-engineer.md
  - agents/discipline-consultant.md
  - agents/doc-engineer.md
  - agents/implementation-planner.md
  - agents/implementer.md
  - agents/interface-designer.md
  - agents/promethean.md
  - agents/researcher.md
  - agents/roadmap-cartographer.md
  - agents/sentinel.md
  - agents/skill-genesis.md
  - agents/systems-architect.md
  - agents/test-engineer.md
  - agents/verifier.md
  - agents/CLAUDE.md
  - skills/software-planning/references/agent-pipeline-details.md
  - skills/agent-crafting/SKILL.md
affected_reqs: []
supersedes: null
superseded_in_part_by: [dec-460]
superseded_by: null
re_affirms: null
re_affirmed_by: null
retired_by: null
---

## Context

The subagent alignment map (`docs/independent-analysis/subagent-alignment-map.md`) traced what each of the 17 agents needs to follow the Praxion process and found gaps that hold under today's full inheritance, before any token diet:

- Three agents (promethean, roadmap-cartographer, skill-genesis) never cited the behavioral contract, and 15 never stated its self-test.
- Twelve of 17 stated no terminal marker of their own, so the completion handshake could check a marker only for step executors; report producers were judged by their report title alone.
- Agent bodies link Praxion references relatively (`../skills/software-planning/references/...`). In a managed project those paths resolve against the project's working directory and fail silently. A probe on 2026-10-11 (Claude Code 2.1.296) showed a `praxion:researcher` reaching its reference only by inferring the plugin root from a preloaded skill's base directory; agents with no Praxion skill preloaded have nothing to infer from. The same probe showed that Claude Code substitutes `${CLAUDE_PLUGIN_ROOT}` inside a plugin agent's body.

`scripts/check_agent_shared_blocks.py` already held one replicated sentence (task-slug scoping) byte-identical across its carriers, but checked agreement only, never presence. That is how the contract gap stayed invisible: every copy that existed agreed.

This is stage 0 of the map's additive-first migration: close the gaps in the agent files, with no new mechanism and nothing removed. It complements the decision that report artifacts are born `[PARTIAL]` and unmarked last, which the return contract cites.

## Decision

1. **Three universal blocks**, each one paragraph, byte-identical in every agent definition, canonical text as module constants in `scripts/check_agent_shared_blocks.py` (`--print-canonical <slug>`):
   - `behavioral-contract`: the existing contract line plus the rule's own self-test question. A test binds the question to `rules/swe/agent-behavioral-contract.md`, which stays the sole author of the wording.
   - `praxion-links`: a path into `skills/` or `rules/` names a Praxion file; read it from the working directory when it exists there, otherwise under `${CLAUDE_PLUGIN_ROOT}`, described also as the parent of the definition's `agents/` directory so that a reader without substitution (a Codex wrapper reading the file from disk) can resolve it.
   - `return-contract`: the final message is a pointer of at most ~15 lines (or the agent's tighter cap) and ends with exactly one of `[COMPLETE]`, `[BLOCKED]`, `[CONFLICT]`, `[PARTIAL]`.
2. **Presence is gated without a roster.** A `universal` block must appear in every agent definition, where a definition is computed from the file: under `agents/*.md`, with frontmatter declaring `name:`. A definition without one is a new `missing` finding; canaries cover each block's missing and drifted cases.
3. **The completion handshake's marker check covers every Praxion-native agent**, report producers included. Host-native agents (`Explore`, `Plan`, `general-purpose`) stay on the artifact check alone.
4. **The contract-bound roster widens to all 17 agents.** Promethean plans features, the roadmap cartographer plans the roadmap and skill-genesis reviews accumulated learnings, which is the rule's own scope ("every agent that writes, plans, or reviews code").

## Considered Options

### Inline universal blocks, gated for presence (chosen)

Pros: closes the gaps today, in every harness that reads the agent file (Claude Code, and Codex through its wrapper); one source of truth per block; the gate makes recurrence a commit failure. Cons: about 300 tokens per agent definition (299 on the budget gate's `claude-sonnet-4-5` ruler, 437 on `claude-opus-5-5`), paid on each spawn; some overlap with agents' own return lists.

### Wait for injected role kernels (stage 2)

A `SubagentStart` hook injecting a generated core would deliver the same text without editing 17 files. Rejected for now: it needs a manifest, a generator, a hook and a process-adherence eval first, the gaps are live meanwhile, and Codex has no injection path. The inline blocks are what a later stage derives and removes.

### Add the blocks only to the agents that lacked them

Rejected: the gaps arose because presence was unchecked; without a universal requirement the next agent repeats them.

### Preload `software-planning` into the eight agents that link it

Rejected: about 5K tokens per spawn of each of those agents, to make optional depth reachable.

### Rewrite every relative link as `${CLAUDE_PLUGIN_ROOT}/...`

Rejected: breaks the links for human readers and GitHub rendering, leaves Codex readers with an unresolved variable, and touches dozens of lines where one universal rule covers them all.

## Consequences

- Every agent states the contract and its self-test, how to reach Praxion references from any project, and how to finish. A missing marker from a report producer is now a truncation signal, not an expected shape.
- The marker extension changes no consumer contract: the step-loop driver already records `partial` as a stop reason.
- Substitution of `${CLAUDE_PLUGIN_ROOT}` was probed with a `--plugin-dir` plugin. Marketplace installs load agents through the same plugin loader, which is assumed, not yet probed; verify after the next release.
- Each agent's system prompt grows by about 300 tokens; `sentinel` and `systems-architect` were already past their prompt-size warn ceilings and gain 4 lines each.
- `interface-designer` and `agentic-transactions-architect` keep their stricter, role-specific self-tests alongside the generic one.

## Disconfirmation

- **Falsifier:** a process-adherence run in which report producers omit the terminal marker as often with the block as without it, or a managed-project spawn that still cannot read a linked reference.
- **Steelmanned runner-up:** waiting for injected kernels avoids touching 17 files twice. It loses because the gaps are live now and Codex would never receive injected text.
- **Reversal trigger:** stage 2 ships injected kernels for every agent; then the inline blocks become generated or are deleted, and this gate's universal requirement moves to the kernel generator.
