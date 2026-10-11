---
id: dec-014
title: Skill + Command composition for upstream issue stewardship
status: accepted
category: architectural
date: 2026-04-06
summary: Upstream stewardship uses a skill (methodology) + command (user trigger) + persistent tracker, not a dedicated agent
tags: [upstream-stewardship, skills, commands, architecture, oss-contribution]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - skills/upstream-stewardship/SKILL.md
  - skills/upstream-stewardship/references/sanitization-patterns.md
  - skills/upstream-stewardship/references/issue-templates.md
  - skills/upstream-stewardship/references/contribution-workflow.md
  - commands/report-upstream.md
  - .ai-state/UPSTREAM_ISSUES.md
superseded_in_part_by: [dec-449]
---

## Context

The project needs a formalized capability for responsibly reporting bugs to upstream open-source projects. The filed issue #44075 on anthropics/claude-code bypassed templates, missed required fields, and did not deduplicate -- demonstrating the need for a structured workflow.

Four artifact composition options were evaluated: skill only, agent only, skill + command, and skill + agent. The decision affects token cost, reusability, user ergonomics, and ecosystem complexity.

## Decision

Use a **Skill + Command + Persistent Tracker** composition:

- **Skill** (`upstream-stewardship`): Core methodology (dedup, sanitization, template compliance, etiquette, responsible disclosure) with progressive disclosure via reference files.
- **Command** (`report-upstream`): User-facing trigger that drives the multi-phase workflow in the main conversation context.
- **Tracker** (`.ai-state/UPSTREAM_ISSUES.md`): Append-only log of filed issues, committed to git.

No dedicated agent is introduced.

## Considered Options

### Option 1: Skill Only

Methodology consumable by agents via `skills` field. No dedicated user trigger.

**Pros:** Minimal footprint. Reusable by any agent.
**Cons:** No ergonomic user entry point. Requires agents to manually invoke methodology.

### Option 2: Dedicated Agent

A new `upstream-steward` agent with its own context window.

**Pros:** Full context isolation. Could auto-detect upstream bugs.
**Cons:** Adds a 13th agent to a 12-agent roster for an infrequent workflow. Heavy context-window overhead. Filing upstream issues should be deliberate, not autonomous.

### Option 3: Skill + Command (chosen)

Skill provides methodology. Command provides user trigger.

**Pros:** Best user ergonomics via `/report-upstream`. Skill reusable by agents. No agent count increase. Command runs in main context (no overhead). Follows dec-007 skill-centric precedent.
**Cons:** No autonomous detection. User must invoke manually.

### Option 4: Skill + Agent

Skill provides methodology. Agent provides automation.

**Pros:** Most powerful. Agent could auto-detect bugs during pipeline work.
**Cons:** Adds ecosystem complexity. Filing issues without user judgment is risky. Agent would be single-purpose.

## Consequences

**Positive:**
- Ecosystem agent count stays at 12
- Command is immediately discoverable via `/` slash-command menu
- Skill methodology is reusable by researcher, implementer, or verifier when they encounter upstream bugs
- Tracker provides git-committed audit trail of all upstream interactions
- Pattern follows the skill-centric precedent established in dec-007

**Negative:**
- No autonomous upstream bug detection -- agents can flag but not file
- User must remember to invoke `/report-upstream` (mitigated by agent discovery protocol in the skill)
