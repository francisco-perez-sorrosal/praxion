---
id: dec-019
title: Living SYSTEM_DEPLOYMENT.md artifact in .ai-state/
status: accepted
category: architectural
date: 2026-04-06
summary: Persistent deployment architecture document maintained by pipeline agents via section ownership, stored in .ai-state/
tags: [deployment, documentation, ai-state, living-document, agent-pipeline]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - .ai-state/SYSTEM_DEPLOYMENT.md
  - skills/deployment/assets/SYSTEM_DEPLOYMENT_TEMPLATE.md
  - skills/deployment/references/deployment-documentation.md
  - skills/deployment/SKILL.md
  - agents/systems-architect.md
  - agents/implementer.md
  - agents/implementation-planner.md
  - agents/verifier.md
  - agents/cicd-engineer.md
  - agents/doc-engineer.md
  - agents/sentinel.md
  - rules/swe/agent-intermediate-documents.md
  - rules/swe/swe-agent-coordination-protocol.md
---

## Context

The Praxion ecosystem has deployment knowledge (the `deployment` skill with primitives, patterns, and decision frameworks) but no place to capture a project's specific deployment state -- what is actually deployed, where, how, and why. This information is scattered across compose.yaml, Dockerfiles, Caddyfiles, and developer memory.

The systems-architect's Operations lens (Phase 6) asks "Is this deployable? Can it be rolled back?" but the answers are not persisted. The implementer writes deployment configs but does not document the intent and failure analysis they encode. The verifier has no deployment-specific validation.

Prior decisions dec-017 (Docker Compose as gravity center) and dec-018 (opinionated tool defaults) established the deployment tool choices. This decision establishes where and how the deployment architecture is documented.

## Decision

Introduce `.ai-state/SYSTEM_DEPLOYMENT.md` as a persistent, living document maintained by pipeline agents through a section ownership model. The document has 10 sections (Overview, System Context, Service Topology, Configuration, Deployment Process, Failure Analysis, Monitoring, Scaling, Decisions, Runbook) with clear agent ownership per section. A template is provided at `skills/deployment/assets/SYSTEM_DEPLOYMENT_TEMPLATE.md`.

This introduces a new `.ai-state/` pattern: a living document (versus the existing immutable, append-only, or timestamped patterns). Section boundaries provide natural ownership lanes, and git version control provides history.

## Considered Options

### Option 1: Living document in `.ai-state/` (chosen)

**Pros:** Consistent with persistent artifact location; clear agent ownership; version-controlled; pipeline-aware.

**Cons:** Lower discoverability than project root; new pattern for `.ai-state/` (living vs immutable).

### Option 2: Project root `DEPLOYMENT.md`

**Pros:** Most discoverable for human developers; peers with README.md.

**Cons:** Mixes agent-maintained artifacts with human-maintained docs; no established convention for agent-updated project-root files; risks being treated as a static doc rather than a pipeline artifact.

### Option 3: Generated from deployment configs

**Pros:** Always in sync; no staleness risk.

**Cons:** Cannot capture intent, failure analysis, runbooks, or operational context that config files do not express; loses the human-readable overlay value.

### Option 4: Inline in agent prompts (template approach only)

**Pros:** Zero-file-overhead; agents always have the structure.

**Cons:** Bloats agent prompts; not versioned separately; cannot be customized per project.

## Consequences

**Positive:**
- Deployment architecture is documented persistently and maintained automatically
- Failure analysis, operational runbooks, and deployment decisions have a canonical location
- Sentinel and verifier can detect drift between documentation and actual configs
- The deployment skill gains a project-specific complement (generic knowledge + specific state)

**Negative:**
- Seven agent definitions need small modifications (~3-15 lines each)
- A new `.ai-state/` pattern (living document) is introduced -- requires learning
- Staleness risk exists despite triple defense (implementer + verifier + sentinel)
- Sentinel definition grows closer to the 500-line threshold (459 → ~465)

**Praxion instance deferred:** For Praxion itself, the `.ai-state/SYSTEM_DEPLOYMENT.md` instance is deferred — this repo is an ecosystem library of skills/agents/rules, not a deployable service. The mechanism (template, references, agent definitions) is shipped and ready for downstream projects that are deployables.
