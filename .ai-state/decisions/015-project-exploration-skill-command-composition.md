---
id: dec-015
title: Skill+Command composition for project exploration (no agent)
status: accepted
category: architectural
date: 2026-04-06
summary: Project exploration uses Skill+Command pair for interactive developer onboarding, not an agent -- interactivity requires main conversation context
tags: [project-exploration, skills, commands, architecture, onboarding]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files: [skills/project-exploration/SKILL.md, commands/explore-project.md]
---

## Context

The project exploration feature helps developers understand unfamiliar software projects through layered, adaptive analysis. Four parallel research agents investigated the design space, producing a tension between three component decomposition options:

1. Skill+Command only (no agent) -- interactive, main conversation context
2. Skill+Agent+Command (three components) -- autonomous analysis in separate context
3. Hybrid -- static generation via command, interactive exploration in main context

The key question was whether project exploration needs its own context window (agent) or benefits from staying in the main conversation (skill+command).

## Decision

Use a Skill+Command pair without an agent. The `project-exploration` skill provides the analysis methodology; the `/explore-project` command provides the user entry point. Both auto-register via directory globs -- no plugin.json changes needed.

## Considered Options

### Option 1: Skill+Command only

- **Pro**: Natural follow-up interaction -- developer asks "tell me more about X" in the same conversation
- **Pro**: Auto-registration for both components (no plugin.json update)
- **Pro**: Skill methodology reusable by other agents (researcher, systems-architect)
- **Pro**: Follows the proven dec-014 pattern (upstream-stewardship)
- **Con**: Analysis tokens compete with conversation tokens in main context

### Option 2: Skill+Agent+Command

- **Pro**: Context isolation keeps main conversation clean
- **Pro**: Agent can perform deep autonomous analysis
- **Con**: Agent completes and returns -- follow-up questions break conversational flow
- **Con**: Requires manual plugin.json registration
- **Con**: Higher implementation complexity (three components)

### Option 3: Hybrid (command for static, main context for interactive)

- **Pro**: Best of both worlds in theory
- **Con**: Split interaction model confuses the user -- when do they get static output vs interactive?
- **Con**: Two different execution paths to maintain

## Consequences

- **Positive**: Developers get natural, conversational project exploration with immediate follow-up capability
- **Positive**: Consistent with ecosystem pattern (dec-014) and prior learning (`skill-command-not-agent-for-interactive-exploration`)
- **Positive**: Lower implementation complexity -- two components instead of three
- **Negative**: For very large projects (1M+ LOC), analysis may consume significant main context tokens -- mitigated by phased analysis (each phase produces summaries, not raw data)
- **Negative**: Cannot run project exploration in the background -- but background analysis is not the use case; the developer wants to interact
