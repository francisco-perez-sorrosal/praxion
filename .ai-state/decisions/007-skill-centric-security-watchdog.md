---
id: dec-007
title: "Skill-centric security watchdog instead of dedicated agent"
status: accepted
category: architectural
date: "2026-04-01"
summary: "Shared context-security-review skill consumed by CI workflow and verifier agent instead of a dedicated security-reviewer agent"
tags: [security, skills, architecture]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files: ["skills/context-security-review/SKILL.md", "agents/verifier.md", ".github/workflows/context-security-review.yml"]
---

## Context

The project needed security review capability for PRs and on-demand audits. The architectural question was whether to create a dedicated `security-reviewer` agent or to build a shared skill that existing consumers (CI workflow, verifier agent) could load.

## Decision

Use a shared `context-security-review` skill consumed by both the GitHub Actions workflow (via `claude-code-action`) and the verifier agent, rather than creating a dedicated security-reviewer agent.

## Considered Options

### Option 1: Dedicated security-reviewer agent

A new agent in the pipeline specifically for security review.

- (+) Clear single-responsibility agent
- (-) `claude-code-action` accepts prompts, not agent names -- mapping is awkward
- (-) Adds pipeline coordination complexity
- (-) The verifier already demonstrates dual-use patterns (code review + acceptance criteria)

### Option 2: Shared security-review skill (selected)

A skill that encapsulates security review methodology, loadable by multiple consumers.

- (+) CI workflow loads it via prompt; verifier loads it as a phase
- (+) Single source of truth for security knowledge
- (+) No new agent coordination overhead
- (+) Follows the ecosystem's skill-as-knowledge pattern
- (-) Security review is distributed across consumers rather than centralized in one agent

## Consequences

### Positive

- Security knowledge is centralized in one skill, consumed by multiple entry points
- No pipeline coordination overhead from a new agent
- CI and local review use identical security criteria

### Negative

- No single "security reviewer" agent to point to -- responsibility is distributed
- Skill must support two operating modes (diff mode for CI/verifier, full-scan mode for command)
