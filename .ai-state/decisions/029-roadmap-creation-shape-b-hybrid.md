---
id: dec-029
title: Shape B-hybrid for roadmap-creation capability (agent + skill + command)
status: accepted
category: architectural
date: 2026-04-12
summary: 'Implement roadmap-creation as a `roadmap-cartographer` agent + `roadmap-synthesis` skill + `/roadmap` command; no new rule content beyond an offset-balanced Available Agents row'
tags: [architecture, roadmap, agent, skill, command, shape-b, spirit]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - agents/roadmap-cartographer.md
  - skills/roadmap-synthesis/
  - commands/roadmap.md
  - rules/swe/swe-agent-coordination-protocol.md
  - .claude-plugin/plugin.json
---

## Context

The user asked for a roadmap-creation feature enabling coordinator agents to produce a `ROADMAP.md` at the caliber of Praxion's own spring-cleaning roadmap for any project (deterministic or agentic, any language). The research pipeline surfaced 14 capability gaps (8 Total, 4 Partial) between the SPIRIT and Praxion's current state. The existing `roadmap-planning` skill is prioritization-only; `promethean` is feature-level ideation; `sentinel` is Praxion-tuned audit. No artifact orchestrates the six-dimension ultra-in-depth audit → synthesis → user-gated roadmap workflow.

Five candidate shapes were analyzed by the context-engineer (see `.ai-work/roadmap-creation/CONTEXT_REVIEW.md` §2):

- Shape A — enhance `roadmap-planning` skill only
- Shape B — skill + new `roadmap-cartographer` agent
- Shape C — skill + `/roadmap` command
- Shape D — full stack including a new rule
- Shape E — extend `promethean` agent

Always-loaded token budget is at 106% of ceiling (56,164 / 52,500 chars). SPIRIT dimension 1 (automation with user gates for architecture/design/deployment) maps natively to an agent's `AskUserQuestion` phase loop. SPIRIT dimension 2 (coordinator awareness) favors a formal delegation-table entry. The combined pressure of user-gate depth, coordinator discoverability, and multi-phase procedure exceeds what a skill alone can cleanly serve.

## Decision

Implement roadmap-creation as **Shape B-hybrid**: `roadmap-cartographer` agent + new `roadmap-synthesis` skill + `/roadmap` command + supporting reference files and template assets under the skill. No new rule; only offset-balanced edits to the existing coordination-protocol rule (see dec-034).

Composition:

- **Agent** (`agents/roadmap-cartographer.md`, ≤290 lines, model `opus`) owns the end-to-end 7-phase workflow in isolated context. Spawns parallel researchers, gates user at architectural/design/deployment decisions, emits `ROADMAP.md`.
- **Skill** (`skills/roadmap-synthesis/`, SKILL.md ≤260 lines) packages domain expertise (six-dimension lens, audit methodology, paradigm detection, grounding protocol, template) as progressive-disclosure knowledge injected via the agent's `skills:` frontmatter.
- **Command** (`commands/roadmap.md`, ≤50 lines) is the user-facing entry point with mode parsing (`fresh`/`diff`/`<focus>`); delegates to the cartographer.
- **Existing `roadmap-planning` skill** is preserved unchanged and composed by the cartographer at Phase 6 (see dec-030).

## Considered Options

### Option A — Enhance `roadmap-planning` skill only

Expand the existing skill to include audit-synthesis, six-dimension lens, template machinery.
**Pros:** zero new artifacts; no delegation-table change; fits the existing pipeline slot.
**Cons:** pushes orchestration onto the main coordinator (amplifies W3 coordinator-burden from ROADMAP.md); user-gate shape is awkward (skill cannot own an `AskUserQuestion` loop — the coordinator must); skill body grows past the 500-line target; skill would mix two distinct responsibilities (prioritization mechanics + audit synthesis) in one file.

### Option B — Skill + new `roadmap-cartographer` agent (chosen, hybrid form)

Agent owns the workflow; skill owns domain knowledge.
**Pros:** `AskUserQuestion` gates native to the agent; coordinator burden flat; skill content offloaded from agent prompt (respects 300-line ceiling); matches `skill-genesis` + `skill-crafting` precedent; budget-neutral via the dec-034 offset plan.
**Cons:** three artifacts to maintain (agent + skill + command); trigger-phrase tuning needed to disjoin from the existing `roadmap-planning` skill; one line added to coordinator cognitive load.

### Option C — Skill + `/roadmap` command only

Command delegates to skill without an agent loop.
**Pros:** discoverability via slash command; zero always-loaded cost (command body loads only on invocation).
**Cons:** depth still owned by the coordinator; weak user-gate shape (command body is a short prompt; the coordinator owns the actual loop); works well layered with Shape A or B but is rarely sufficient alone.

### Option D — Full stack including a new rule

Agent + skill + command + template + new always-loaded rule.
**Pros:** strongest integration; declarative constraints guaranteed to load.
**Cons:** new rule content violates the 106%-of-ceiling budget; any offset would have to exceed the agent-row offset already planned; the six SPIRIT dimensions are *procedural* (evaluation lenses), not *declarative* constraints, so they do not belong in a rule. Rejected.

### Option E — Extend `promethean`

Add a "roadmap mode" phase or branch to the existing promethean agent.
**Pros:** zero new agents; reuses promethean's pipeline slot.
**Cons:** promethean is feature-level ideation (single validated idea); roadmap-creation is project-level altitude (ordered multi-item set). Conflating altitudes breaks promethean's scope. Promethean already at ~310 lines (past the ≤300 ceiling); adding phases pushes further. Additionally, promethean's explicit constraints forbid external research and redesign proposals — both of which roadmap-creation requires. Rejected.

### Option B-hybrid (chosen)

Same as Option B plus the `/roadmap` command layer and a net-≤0 budget offset to add a formal delegation-table row. Absorbs the discoverability benefit of Option C while preserving the depth benefit of Option B.

## Consequences

**Positive:**

- SPIRIT dimension 1 (user gates) natively supported by agent's `AskUserQuestion` loop.
- SPIRIT dimension 2 (coordinator awareness) served by three reinforcing layers: slash command, delegation-table row, description-based semantic activation.
- Coordinator burden (W3) does not compound — orchestration lives in the agent's isolated context.
- Token-budget ceiling respected via paired offset (dec-034).
- Skill references and template asset stay on-demand (tier 4/5 disclosure); zero always-loaded cost for the six-dimension content.
- Existing `roadmap-planning` skill preserved unchanged; no breaking rewrite.

**Negative:**

- Three new artifacts to maintain (agent + skill + command) plus four reference files and two template assets.
- Trigger-phrase disjointness with `roadmap-planning` requires careful `description` tuning (validated in dec-030 and by context-engineer Phase 2).
- Agent prompt size needs disciplined skill offload to stay under the 300-line ceiling.
- Graceful-degradation escape hatch (skip rule edits) reduces coordinator-awareness to two layers if the dec-034 offset proves infeasible at implementation time.

**Operational:**

- Files created by the implementer per the `IMPLEMENTATION_PLAN.md` decomposition.
- `plugin.json` updated to register the new agent.
- ARCHITECTURE.md gains a Components row (Status: Designed → Built).
- The existing `roadmap-planning` skill's description may need minor clarification to strengthen trigger-phrase disjointness (see dec-030).
