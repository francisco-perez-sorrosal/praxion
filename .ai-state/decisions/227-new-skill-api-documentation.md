---
id: dec-227
title: New api-documentation skill (peer to doc-management) rather than extending doc-management
status: accepted
category: architectural
date: 2026-06-16
summary: Document a project's OWN API surface (REST/Python/TS/MCP/GraphQL, human + agent) via a new deep-specialist skill, not an expansion of doc-management's shallow API section.
tags: [skill, documentation, api, progressive-disclosure, mcp, openapi]
made_by: agent
agent_type: systems-architect
branch: main
pipeline_tier: standard
affected_files:
  - skills/api-documentation/SKILL.md
  - skills/doc-management/references/documentation-types.md
  - commands/document-api.md
re_affirms: dec-226
re_affirmed_by:
  - dec-226
---

## Context

Praxion has five adjacent skills (`api-design`, `api-design-craft`, `agentic-interface-design`, `doc-management`, `external-api-docs`) but none produces best-in-class documentation for a managed project's **own** API surface for both humans and AI agents. `doc-management/references/documentation-types.md` carries a shallow API-docs section (when-to-maintain, three approaches, basic conventions, staleness indicators) — generalist-grade, not the deep per-language/per-protocol tooling a project needs (OpenAPI 3.1 spec-as-source-of-truth, Spectral/Vacuum lint, oasdiff drift gate, RFC 9457 error catalogs, MCP introspection-driven docs, agent-consumable metadata discipline). The user locked two decisions: deep tiers for REST/OpenAPI · Python · TS/Node · MCP · GraphQL with an extension seam for gRPC/Go/Rust/AsyncAPI; artifact shape = a skill plus a `/document-api` scaffolding command.

## Decision

Create a new `skills/api-documentation/` skill, peer to `doc-management`, as the deep specialist for documenting a project's own API surface for humans AND agents. Keep `doc-management`'s shallow API section in place as the generalist entry point and add a one-line pointer to the new skill. The two skills cross-reference each other; no content moves. Ship a companion `/document-api` command for per-project scaffolding.

## Considered Options

### A. Extend doc-management's API section in place
- Pros: no new skill; one place to look.
- Cons: would bloat an always-loaded generalist skill with five language/protocol tiers + agent-consumable theory; violates progressive disclosure and the token budget; conflates "general project docs" with "deep API-doc production"; no clean home for a scaffolding command.

### B. New peer skill + retain shallow generalist section (chosen)
- Pros: clean separation (generalist vs specialist); progressive disclosure keeps SKILL.md lean; mirrors the existing `api-design` vs `api-design-craft` split; the command has a natural owning skill; no duplication (pointer + cross-ref only).
- Cons: one more skill to discover; requires two-way cross-ref maintenance.

### C. Fold into api-design or api-design-craft
- Pros: API-adjacent skills already exist.
- Cons: those skills own *design* and *quality/taste*, not the *doc deliverable* — wrong boundary; would muddy three skills' scopes.

## Consequences

- Positive: a single deep home for API-doc production; generalist doc-management stays lean; the new skill is reusable by the doc-engineer and the `/document-api` command; sandbook (Python lib + REST + MCP) is an immediate multi-surface validation customer.
- Positive: this is an **additive context artifact** (a skill) — no change to Praxion's runtime system, so `.ai-state/DESIGN.md` and `docs/architecture.md` are intentionally NOT touched.
- Negative: adds a two-way cross-reference obligation (doc-management ↔ api-documentation, plus pointers from api-design / agentic-interface-design) that must not drift.
