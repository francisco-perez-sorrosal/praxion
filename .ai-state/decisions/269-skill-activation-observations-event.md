---
id: dec-269
title: First-class `skill_activation` observations event via the single PostToolUse WAL emitter
status: accepted
category: architectural
date: 2026-07-16
summary: Emit a first-class `skill_activation` event (with a `skill_name` field) into observations.jsonl by extending capture_memory.py's Skill branch — not a new hook; deliberately excludes agent-frontmatter availability and leaves the relay's `skill_use` name unchanged.
tags: [observability, observations-jsonl, skill-activation, hooks, efficacy-measurement, roadmap-2-2, additive-schema]
made_by: agent
agent_type: systems-architect
branch: worktree-efficacy-measurement
pipeline_tier: standard
affected_files:
  - hooks/capture_memory.py
  - hooks/test_capture_memory.py
  - .ai-state/DESIGN.md
  - docs/architecture.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05]
dissent: Excluding agent-frontmatter `skills:` loads leaves availability→usage uncorrelatable in-band; if a future analysis proves the static offline join (agent_start × agent frontmatter) is impractical, a `skill_available` event may be warranted after all.
---

## Context

Praxion runs 56 skills but has zero dedicated skill events. Skill activations land in
`.ai-state/observations.jsonl` only as generic `event_type: "tool_use"` rows whose `summary`
happens to read "Activate skill: <name>" (via `capture_memory.py::build_summary`). This makes
"which skills are actually used?" (ROADMAP 2.2 / weakness W7) unanswerable without brittle
string-matching. `capture_memory.py` is the single PostToolUse-all writer to the durable WAL
(fcntl-locked, merge-driver-reconciled). Mechanically observable skill signals are: (a) explicit
`Skill` tool calls (PostToolUse-visible), and (b) agent-frontmatter `skills:` declarations at
Agent spawn. Implicit description-triggered loads emit no hook signal.

## Decision

Emit a **first-class `skill_activation` event** into `observations.jsonl` by adding a
`tool_name == "Skill"` branch to `capture_memory.py`: set `event_type: "skill_activation"`
(instead of `"tool_use"`) and add a top-level `skill_name` field, while preserving the full
existing envelope (`timestamp`, `session_id`, `agent_type`, `agent_id`, `project`,
`tool_name: "Skill"`, `summary`, `file_paths`, `outcome`, `classification`). No new hook is
added — the single existing emitter is extended (dec-266 "one emitter" spirit).

Three scoping calls are part of this decision:

1. **Only explicit `Skill` tool calls emit `skill_activation`.** Agent-frontmatter `skills:`
   declarations do **not** emit — they express *availability*, not *activation*, and would
   pollute the usage signal. Availability is statically derivable offline by joining the
   existing `agent_start` event (`agent_type`) against `agents/<name>.md` frontmatter.
2. **`inject_subagent_context.py` is left untouched.** Resolving `i-am:<agent>` → its
   definition file from that PreToolUse hook is fragile (plugin-cache path resolution) and
   would burden dec-266's deliberately filesystem-walk-free single emitter.
3. **The relay's `skill_use` name is unchanged.** `send_event.py` already POSTs a `skill_use`
   event to the Chronograph MCP; renaming it to match `skill_activation` would be a
   non-additive change to a live consumer for no benefit. The durable WAL and the ephemeral
   relay stay on separate rails with separate names (documented in DESIGN.md §5).

The change is envelope-additive: the new `skill_name` field is optional to every existing
reader (all use `dict.get` / ignore unknown keys), and the merge dedup key
(`timestamp|session_id|event_type|tool_name`) stays fully populated.

## Considered Options

### A — Extend `capture_memory.py` with a Skill branch (CHOSEN)
- Pros: one WAL writer; no new hook wiring; reuses the envelope + `append_observation`;
  dec-266-consistent; `measure_context_surface.py`'s `context_surface_measurement` is direct
  precedent for a non-`tool_use` event in the same WAL.
- Cons: re-classifies Skill rows from `tool_use`→`skill_activation` (a value change, not purely
  additive) — verified safe: no consumer branches on Skill-as-`tool_use` (Skill rows carry empty
  `file_paths`, so `reconcile_pipeline_state`'s file-containment correlation never used them).

### B — Add a dedicated PostToolUse(Skill) hook
- Pros: isolates skill logic in its own file.
- Cons: splits the WAL-writer responsibility (the exact anti-pattern dec-266 consolidated on the
  Agent side); doubles the `.ai-state/` stat + append cost per skill call; more hook wiring to
  register and keep in sync.

### C — Also emit for agent-frontmatter `skills:` at Agent spawn
- Pros: closes the availability→usage completeness gap in-band.
- Cons: conflates availability with usage (every `systems-architect` spawn would log 5
  "activations" it may never trigger), defeating the very W7/O6 signal; requires fragile
  plugin-cache path resolution from the PreToolUse hook; burdens the dec-266 single emitter.
  Availability is already recoverable offline via a static join.

## Consequences

- **Positive:** skill usage becomes a first-class, groupable event; `skill_name` enables
  aggregation without string-parsing; additive to all readers and the merge driver; no new hook,
  no always-loaded token cost; `PRAXION_DISABLE_OBSERVABILITY` still fully gates it.
- **Negative / constraint:** implicit description-triggered skill loads remain uncaptured (no
  mechanical signal — a documented coverage boundary, not a regression). A mild two-name wart
  (`skill_activation` WAL vs `skill_use` relay) persists by design.
- **Follow-on:** any future "skill availability per spawn" need should be a distinct
  `skill_available` event with a `source` discriminator, not an overload of `skill_activation`.

## Disconfirmation

- **Falsifier:** a consumer that reads `observations.jsonl` and *relies* on Skill invocations
  appearing as `event_type: "tool_use"` (e.g., a metric that counts tool_use including skills)
  would break under this reclassification — none exists today (enumerated readers:
  `reconcile_ai_state`, `reconcile_pipeline_state`, the merge driver; none qualify).
- **Steelmanned runner-up (Option C):** if the primary analytical question turns out to be
  "does an agent that *has* skill X available ever use it?", then in-band availability events
  would make that a one-pass query instead of an offline join against agent definitions; for a
  small, fixed agent roster the join is cheap, but if agent frontmatter churns or third-party
  agents appear, the static-join assumption weakens and C becomes attractive.
- **Reversal trigger:** revisit if (a) a built consumer needs Skill-as-`tool_use`, or (b) an
  efficacy analysis demonstrates the offline availability join is impractical at scale — at
  which point add `skill_available` (not rename `skill_activation`).
