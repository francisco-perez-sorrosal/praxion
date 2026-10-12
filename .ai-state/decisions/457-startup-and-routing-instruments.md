---
id: dec-457
draft_id: dec-draft-18262e44
title: Startup payload and agent routing are measured by two committed instruments
status: accepted
category: architectural
date: 2026-10-11
summary: "Two new scripts become the gate every startup-context change must pass: scripts/measure_startup_payload.py reads the real first-request tokens of a headless session and of each spawned Praxion agent (stream-json, stopped once seen) and keeps a per-profile baseline in .ai-state/startup_baseline.json with a compare mode; scripts/check_agent_routing.py asks a single-turn session which agent or skill handles each of 24 user-style requests and keeps the routes in .ai-state/agent_routing_baseline.json. A change to resident context lands only with a measured saving on the probe, and a description change only with no moved route."
tags: [startup-context, instruments, measurement, agent-routing, token-budget, baseline, lean-spawns]
made_by: user
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - scripts/measure_startup_payload.py
  - scripts/test_measure_startup_payload.py
  - scripts/check_agent_routing.py
  - scripts/test_check_agent_routing.py
  - scripts/agent_routing_cases.json
  - .ai-state/startup_baseline.json
  - .ai-state/agent_routing_baseline.json
  - scripts/CLAUDE.md
affected_reqs: []
supersedes: null
superseded_by: null
re_affirms: null
re_affirmed_by: null
retired_by: null
dissent: "The routing check reads the model's stated route in a one-line answer, a proxy for the delegation it would make inside a real task; the two can diverge, and the probe's numbers are for one machine's plugin set and settings."
---

## Context

The startup-context spike (`docs/independent-analysis/startup-context-diet-research.md`, §6.6 and §9) ended with a rule: nothing structural lands without an instrument showing the saving and another showing no regression. Two instruments it named did not exist. The always-loaded budget gate (`measure_token_budget.py`) counts the bytes Praxion ships, not what the harness renders into the first request: it cannot see the listings, the hook injections, the MCP instructions or the memory index, which together are more than half of what a session pays. And every agent description is routing text: the spike held back a 1.6K-token description trim because nothing could tell whether it changed where a request is delegated.

The spike's own ablations were a shell script in a scratch directory, run by hand, with numbers copied into a table. The lean-spawn pilot (Phase 2) and the rule split (Phase 3) each need those numbers before and after, per agent, on demand.

## Decision

1. **`scripts/measure_startup_payload.py`** measures the real first request. One headless `claude -p --output-format stream-json` session per target, stopped the moment the target's first `assistant` message arrives: the session's own first request (`main`) or a spawned `praxion:<name>` agent's (`agent:<name>`), read as `input + cache_creation + cache_read`. A reading carries a profile (session kind, model, `--setting-sources`, `--strict-mcp-config`, `--plugin-dir`) and compares only within one. `--record` writes the profile's targets into the committed `.ai-state/startup_baseline.json`; `--compare` names every target past a tolerance; a target with no first request is withheld with a reason, never zero. MCP servers connecting or not before the first request move a reading by about 1.7K tokens, so each reading names every server's status and the `--strict-mcp-config` profile, reproducible within 3 tokens, is the gating profile; the default profile reports what a user actually pays.
2. **`scripts/check_agent_routing.py`** measures routing. One single-turn headless session per case, carrying the real agent and skill listings, asked for one line: `agent:<type>`, `skill:<name>` or `none`; a denied Agent or Skill call (a session-scoped `permissions.deny`, never `--disallowedTools`, which would remove the listing with the tool) is read as the answer too. Cases in `scripts/agent_routing_cases.json` name the expected route and the near-miss routes whose hit is a confusion, not a miss. Routes are recorded in `.ai-state/agent_routing_baseline.json`; a plain miss, an unreadable answer or a route that moved since the baseline fails the check.
3. **Both are gates on the diet, not on commits.** They cost metered sessions, so neither runs in a hook. The probe runs before and after a change to resident context; the routing check before and after a change to any description. The calibration row and the ADR of such a change cite their readings.

## Considered Options

### Instrument the real first request through stream-json (chosen)

Pros: the number is what the model is billed for, per session kind and per agent, with no estimate and no category table; subagent messages carry `parent_tool_use_id`, `subagent_type` and `usage`, so one run yields the session and the agent; stopping at the first message keeps a target at 5–10 seconds. Cons: metered; one machine's plugin set; MCP timing noise, handled by the profile.

### Read `/context`

Rejected: its figures are estimates (it under-reports the eager core tools as a few tokens and caps the listing), and it has no per-agent view.

### Derive per-spawn startup from recorded transcripts (`context_baseline.py`)

Rejected for this purpose: it needs real sessions to have run, mixes the work with the startup, and cannot be asked for a reading of a checkout before it ships. It stays the right instrument for what spawns cost over real pipelines.

### Lint descriptions mechanically before a trim

Rejected: length and example blocks do not say where a request routes.

### Observe real spawns under full tasks

Rejected as the routine check: each case would run an agent. The stated route is the cheap proxy; `.ai-state/observations.jsonl` records real delegations and can arbitrate when the two disagree.

## Consequences

- The spike's projections become measurements. On the gating profile (Claude Code 2.1.296, Sonnet 5.5 session): this repository 63,373 tokens, an empty directory 52,479, a managed project 57,664; agents from 40,644 (doc-engineer) to 70,699 (sentinel).
- The routing baseline records two stable confusions in today's catalogue: backlog prioritisation routes to `roadmap-cartographer` instead of the `roadmap-planning` skill, and a test-suite refactor to the `refactoring` skill instead of `test-engineer`. Phase 4's catalogue work starts from them, and no description change may add a third.
- The baselines are committed data; a plugin update that changes a reading shows in the diff of the next `--record`.
- Each full probe run costs about 20 headless sessions; the routing check about 24 short requests on a cached prefix.

## Disconfirmation

- **Falsifier:** a change the probe reports as a saving that an interactive session does not show, or a routing case whose stated route disagrees with the delegation the observation log records for the same request shape. Either would mean the instrument measures something other than what it claims.
- **Steelmanned runner-up:** transcript-derived measurement over real sessions covers the real distribution of tasks and settings, where a synthetic one-word session covers one point. It loses because the diet needs a reading of a checkout before it ships, and a before/after pair on the same point is what a gate compares.
- **Reversal trigger:** Claude Code reports first-request tokens or routing itself, or stream-json stops carrying subagent usage, at which point the probe reads the native source or is retired.
