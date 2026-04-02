---
id: dec-001
title: "Skill wrapper as primary context-hub integration"
status: accepted
category: architectural
date: "2026-03-31"
summary: "Use a skill wrapper for context-hub integration instead of bundling an MCP server in plugin.json"
tags: [context-hub, skills, integration]
made_by: agent
agent_type: systems-architect
affected_files: ["skills/external-api-docs/SKILL.md"]
---

## Context

Context-hub provides external API documentation for agent workflows. The integration pattern needed to be decided: either bundle an npm/Node.js MCP server in `plugin.json` (creating a hard runtime dependency) or create a skill wrapper that agents load on demand.

## Decision

Use a skill wrapper as the primary integration for context-hub, not an MCP server in `plugin.json`. The skill is opt-in, zero cost when not loaded, and follows existing patterns in the ecosystem.

## Considered Options

### Option 1: Bundled MCP server in plugin.json

Adding the context-hub MCP server to `plugin.json` makes it available to all sessions automatically.

- (+) Always available without explicit loading
- (-) Creates a hard runtime dependency on npm/Node.js for all users in a Python-primary ecosystem
- (-) Adds startup cost to every session regardless of need

### Option 2: Skill wrapper (selected)

A skill that wraps context-hub CLI invocations, loaded on demand by agents.

- (+) Opt-in: zero cost when not loaded
- (+) Follows existing skill loading patterns
- (+) No Node.js runtime requirement for users who do not need external API docs
- (-) Requires explicit loading in agent prompts

### Option 3: Both MCP and skill simultaneously

- (-) Redundant integration paths create confusion about which to use
- (-) Maintenance burden of two interfaces

## Consequences

### Positive

- No runtime dependency on npm/Node.js for users who do not use context-hub
- Consistent with the ecosystem's progressive disclosure model

### Negative

- Agents must explicitly load the skill when external API docs are needed
