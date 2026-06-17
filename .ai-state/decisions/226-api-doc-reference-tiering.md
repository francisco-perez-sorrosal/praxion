---
id: dec-226
title: api-documentation reference tiering — universal core in SKILL.md, per-surface references, one extension seam
status: accepted
category: architectural
date: 2026-06-16
summary: Lean SKILL.md carries only cross-validated universal core; deep tiers split per-surface (rest-openapi, agent-consumable, python, typescript, graphql, mcp-docs); extended set is one extending.md seam + seeded stubs.
tags: [skill, progressive-disclosure, documentation, api, reference-structure, token-budget]
made_by: agent
agent_type: systems-architect
branch: main
pipeline_tier: standard
affected_files:
  - skills/api-documentation/SKILL.md
  - skills/api-documentation/references/
re_affirms: dec-227
---

## Context

The research converged on a clear universal core (spec-as-source-of-truth; rich metadata discipline; RFC 9457 errors + pagination/rate-limit/changelog; drift detection as CI byproduct; the two-doc-surfaces mental model: library-from-docstrings vs service-from-spec; the human-vs-agent divergence model where the spec IS the agent surface). Around that core sit fast-moving, contested, or tooling-specific bodies of knowledge (renderer choice, llms.txt adoption evidence, OpenAPI→MCP curation, per-language toolchains). Progressive disclosure is load-bearing: SKILL.md is metadata + always-loaded-on-activation body and must stay token-lean. The open question is the exact `references/*.md` decomposition — split by protocol, by language, or a universal core plus per-surface — and what stays in the body vs goes on-demand.

## Decision

**SKILL.md body = the universal core only**, plus a reference-routing table. Specifically the body carries: the two-doc-surfaces model; spec-as-source-of-truth; the agent-vs-human divergence table + agent-metadata discipline (operationId/summary/description/examples — the least-contested, highest-value area); the mandatory doc sections (quickstart, auth, reference, RFC 9457 error catalog, pagination, rate-limit, changelog/versioning); docs-as-CI-artifact (lint + diff + contract-test); Diátaxis+AaC fence mapping; and the boundary table vs adjacent skills.

**Deep references split per-surface** (a hybrid of by-protocol and by-language, because Python/TS each carry two surfaces — library + service — while GraphQL/MCP are single-surface):
- `references/rest-openapi.md` — OpenAPI 3.1 pipeline: spec-first vs code-first stance, Spectral/Vacuum, oasdiff, Schemathesis, renderer trade-offs, x-codeSamples, publishing/versioning/deprecation.
- `references/agent-consumable.md` — the differentiator: spec-as-agent-surface deep-dive, token economy, llms.txt/llms-full.txt (with the contested adoption evidence), .well-known/api-catalog + machine-readable changelogs (forward-looking), OpenAPI Overlays.
- `references/python.md` — library (mkdocstrings vs Sphinx vs pdoc; Google/NumPy docstrings) + service (FastAPI → OpenAPI 3.1).
- `references/typescript.md` — library (TypeDoc + TSDoc + API Extractor) + service (tsoa / nestjs-zod / zod-to-openapi).
- `references/graphql.md` — SDL-as-docs, SpectaQL, GraphQL Inspector, GraphiQL/Apollo Sandbox.
- `references/mcp-docs.md` — documenting an existing MCP server from live `tools/list` introspection; the explicit seam vs agentic-interface-design (DESIGN vs DOCUMENT); OpenAPI→MCP curation cross-ref.
- `references/extending.md` — the single extension seam: the documented pattern for adding a surface (universal checklist) + seeded gRPC/Go/Rust/AsyncAPI stubs (one canonical source + minimal setup each), inline as labeled sections rather than four separate files.

**Assets** the skill ships: `assets/api-docs-skeleton/` (Diátaxis directory tree with aac fences), `assets/spectral-ruleset.yaml` (baseline ruleset requiring operationId/descriptions/examples/error-responses/tags), `assets/ci-snippet.yml` (lint → diff → contract-test gate), `assets/doc-manifest-entry.yaml` (registration stub).

## Considered Options

### Split purely by protocol (rest, graphql, mcp, async)
Cons: orphans Python/TS library-doc tooling (mkdocstrings, TypeDoc) which is language- not protocol-shaped; forces library guidance into a "rest" file where it doesn't belong.

### Split purely by language (python, typescript, go, rust...)
Cons: REST/OpenAPI, agent-consumable, GraphQL, and MCP guidance is cross-language and would duplicate across every language file.

### Hybrid: universal core + per-surface references + one extension seam (chosen)
Pros: each reference maps to a real decision the user faces; no duplication; Python/TS two-surface complexity gets a home; extended set is cheaply seeded without four near-empty files; keeps SKILL.md lean.
Cons: a reader documenting a Python REST service loads two references (python.md + rest-openapi.md) — acceptable, and exactly the two-surface split the universal core teaches.

### Extended set as four separate stub files
Cons: four near-empty files add navigation noise; a single `extending.md` with a reusable pattern + labeled stubs is more honest about their seeded (not deep) status and gives future contributors one obvious place to deepen.

## Consequences

- Positive: SKILL.md stays token-lean (universal core + routing only); contested/fast-moving evidence (llms.txt, renderer wars) is loaded only when the user pursues that path.
- Positive: the extension seam is a *documented pattern*, so adding gRPC/Go/Rust/AsyncAPI depth later is a known move, not a redesign.
- Negative: multi-surface projects load 2+ references — mitigated by the SKILL.md routing table making the combination explicit.
- This ADR refines (re-affirms, does not supersede) the structure left open by dec-227 (the new-skill decision); the two are complementary sibling decisions.
