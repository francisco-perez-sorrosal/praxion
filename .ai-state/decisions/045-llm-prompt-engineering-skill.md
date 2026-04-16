---
id: dec-045
title: Create `llm-prompt-engineering` skill with framework-agnostic scope
status: accepted
category: architectural
date: 2026-04-16
summary: New skill at `skills/llm-prompt-engineering/` covering few-shot, CoT/reasoning-effort, structured output, versioning, and single-prompt testing; framework-agnostic; defers platform specifics to claude-ecosystem, agent plumbing to agentic-sdks, and deep eval architecture to agent-evals
tags: [skills, prompt-engineering, architecture, progressive-disclosure, llm]
made_by: agent
agent_type: systems-architect
pipeline_tier: full
affected_files:
  - skills/llm-prompt-engineering/SKILL.md
  - skills/llm-prompt-engineering/references/few-shot-patterns.md
  - skills/llm-prompt-engineering/references/reasoning-and-cot.md
  - skills/llm-prompt-engineering/references/structured-output.md
  - skills/llm-prompt-engineering/references/versioning.md
  - skills/llm-prompt-engineering/references/prompt-testing.md
  - skills/llm-prompt-engineering/references/prompt-injection-hardening.md
  - skills/llm-prompt-engineering/contexts/python.md
  - skills/llm-prompt-engineering/contexts/typescript.md
  - skills/agent-crafting/SKILL.md
  - skills/agent-evals/SKILL.md
  - skills/claude-ecosystem/SKILL.md
  - skills/agentic-sdks/SKILL.md
  - skills/mcp-crafting/SKILL.md
---

## Context

The ROADMAP identifies the absence of a dedicated prompt-engineering skill as the "most surprising gap for an AI-focused ecosystem." Prompt-design patterns (few-shot, chain-of-thought, structured output, versioning, single-prompt testing) are currently dispersed across `agent-crafting` (subagent prompts), `agent-evals` (eval prompts), and `claude-ecosystem` (Claude API features), producing misrouted discovery: semantic matches for "prompt design" or "structured output" land in neighboring skills whose scope is different. The new skill sits in the `llm-*` name slot with no existing neighbor — there is no overlap to resolve by renaming or merging.

## Decision

Create a new skill at `skills/llm-prompt-engineering/` with progressive disclosure (SKILL.md + `references/` + `contexts/`). Framework-agnostic; explicitly defers platform specifics to `claude-ecosystem`, agent plumbing to `agentic-sdks`, and deep eval architecture to `agent-evals`.

**Confirmed slug**: `llm-prompt-engineering` (per CONTEXT_REVIEW.md §4.2 rationale).

**Description line**:

> Systematic prompt design for LLMs -- few-shot patterns, chain-of-thought, reasoning-effort control, structured output via Pydantic/Zod, prompt versioning, and single-prompt testing. Use when designing prompts for production LLM calls, writing system prompts, debugging output-quality issues, migrating across model versions, picking a prompt-management platform, or establishing prompt regression tests. Framework-agnostic; defers to claude-ecosystem for Claude-specific APIs, agentic-sdks for agent instructions, agent-evals for deeper eval design, and external-api-docs for current SDK signatures.

(~610 chars — within the 1024 limit.)

**Activation triggers** (terms to include in the description so skill-discovery semantic matching finds it):

- Primary: *prompt engineering, prompt design, few-shot, chain of thought, CoT, reasoning effort, structured output, JSON schema output, Pydantic output, Zod output, instructor, prompt versioning, prompt testing, prompt regression, system prompt, prompt template, prompt migration*
- Secondary: *in-context learning, self-consistency, DSPy, MIPRO, Promptfoo, DeepEval, Langfuse, LangSmith, PromptLayer, prompt caching friendly, output schema, XML tags*

**Excluded trigger terms** (would cause misrouting):

- *prompt caching* → owned by `claude-ecosystem` (platform feature)
- *agent instructions, subagent prompt* → owned by `agent-crafting` (Claude Code sub-agent config)
- *LLM-as-judge rubric, trajectory grading* → owned by `agent-evals`
- *MCP prompt primitive* → owned by `mcp-crafting` (wire protocol)

**Reference file inventory** (6 files, each ≤800 lines): `few-shot-patterns.md`, `reasoning-and-cot.md`, `structured-output.md`, `versioning.md`, `prompt-testing.md`, `prompt-injection-hardening.md`.

**Contexts** (language-specific implementation guides): `contexts/python.md` (instructor + Pydantic retry loop; Anthropic/OpenAI SDK shapes; pytest integration) and `contexts/typescript.md` (Zod + `instructor-js` or native SDK `strict: true`; Promptfoo YAML-from-TS; Node test-runner integration).

Rationale for having both `references/` and `contexts/`: the five prompt-design disciplines are language-agnostic and go under `references/`. The last-mile implementation (Pydantic vs Zod, instructor library choice, retry-loop code) is language-specific and goes under `contexts/`. Mirrors the established pattern in `agentic-sdks` and `communicating-agents`.

**Inbound cross-reference stubs** added to: `agent-crafting/SKILL.md`, `agent-evals/SKILL.md`, `claude-ecosystem/SKILL.md`, `agentic-sdks/SKILL.md`, `mcp-crafting/SKILL.md`.

**Decision on pre-carving a `context-engineering` skill**: Defer. Creating an empty-shell skill now produces a placeholder anti-pattern. The prompt skill can reference the *concept* in its terminology note without a sibling skill existing. If a future use case surfaces with deep retrieval/memory-curation guidance, carve it then — with concrete content from day one.

## Considered Options

### Option 1 — Rule instead of skill

Rejected per rule-crafting decision table (procedural, artifact-producing, progressive-disclosure appropriate).

### Option 2 — Two skills: `prompt-design` + `prompt-ops`

Rejected; the five areas are tightly coupled and a user's entry point is the use-case (e.g., "I'm designing a structured-output prompt"), which crosses design/ops. Splitting fragments the mental model.

### Option 3 — Rename `agent-evals` to `llm-evals`

Rejected as out-of-scope for this phase; the researcher proposed it, but the boundary works cleanly with a narrow §5 in the new skill plus a "see agent-evals" pointer. No rename needed.

### Option 4 — Single skill, framework-agnostic (chosen)

One skill with progressive disclosure, framework-agnostic scope, explicit deferrals to near-neighbors. Mirrors existing ecosystem patterns.

## Consequences

**Positive**: fills the "most surprising gap for an AI-focused ecosystem" (ROADMAP). Reduces misrouting to `agent-crafting` and `agent-evals`. Adds ~1 description-line cost at skill index startup (~90 bytes) — negligible.

**Negative**: one more skill to maintain. Content drift risk (model-family table, platform comparison) — mitigated by 4.3 staleness markers applied on day one.

**Risk accepted**: description might collide with `agent-evals` search-matching for queries like "prompt testing." Mitigated by explicit trigger-term exclusions in both descriptions and the §5 "defer to agent-evals" callout.
