---
id: dec-485
draft_id: dec-draft-cd34787e
title: A re-runnable spawn-model check over recorded transcripts
status: accepted
category: architectural
date: 2026-10-31
summary: New stdlib checker scripts/check_spawn_models.py reads recorded parent and subagent transcripts, classifies each spawn as floor, override, unexplained or unknown against the definitions' model floors and the directive's sanctioned set, exits 1 only on an unexplained spawn, and starts no model session.
tags: [rules, startup-context-diet, moves, model-routing, path-scope]
made_by: agent
agent_type: systems-architect
branch: worktree-model-routing-move
pipeline_tier: standard
affected_files:
  - scripts/check_spawn_models.py
  - scripts/test_check_spawn_models.py
---
## Context

With the table off session start, the claim "spawns route by their definitions" needs a deterministic, $0 reading. None exists: `check_agent_routing.py` measures delegation with paid sessions; `capture_session.py` records models but judges nothing.

## Decision

`python3 scripts/check_spawn_models.py <transcripts-dir> [--repo-root DIR] [--json]`, exit 0/1/2. Spawns are parsed once into frozen values; classification is a pure function over a closed verdict set, with model identity by family. A session of two or more spawns with differing floors all on one model reads as the kill switch; a lone off-floor spawn without a marker reads unknown, never unexplained. Advisory: its readers are the verifier of a routing change and the sentinel's routing audit; it is not a commit gate (transcripts are local and unversioned).

## Considered Options

### Standalone checker (chosen)
Small, testable, re-runnable on any transcript directory.

### Extend `capture_session.py` to judge at SubagentStop
Live, but couples a judgment to a hot hook and cannot re-read history.

## Consequences

- Positive: KS6's reading is mechanical and repeatable.
- Negative: the sanctioned set lives in two places (the directive list and the checker constant), held together by a checklist comment at both sites.

Activation: no — the honest-uncertainty gate does not fire; dec-480's precedent and concrete option costs decide it.
