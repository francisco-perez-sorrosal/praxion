---
id: dec-053
title: Prompt-over-template discipline for greenfield project scaffolding
status: accepted
category: architectural
date: 2026-04-18
summary: Praxion ships prose specifications and discovery hooks (external-api-docs) for the greenfield onboarding flow rather than code templates or pinned SDK signatures, so SDK drift cannot be baked into the product.
tags:
  - onboarding
  - scaffolding
  - prompt-engineering
  - external-api-docs
  - sdk-drift
made_by: user
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - new_project.sh
  - commands/new-project.md
  - docs/greenfield-onboarding.md
affected_reqs:
  - REQ-ONBOARD-15
  - REQ-ONBOARD-16
  - REQ-ONBOARD-17
  - REQ-ONBOARD-18
  - REQ-ONBOARD-20
  - REQ-ONBOARD-26
---

## Context

The greenfield onboarding feature creates a new project that includes generated Python code calling the Claude Agent SDK, a `pyproject.toml` consumed by `uv`, FastAPI scaffolding, and a per-run `onboarding_for_mushi_busy_ppl.md` documentation artifact. The naive way to ship this is to include those files as templates inside the Praxion repo (under `templates/`, `claude/config/`, or similar) with placeholder substitution at run time.

Three forces argue against that:

1. **The Claude Agent SDK is drift-sensitive.** Symbol names, module paths, the `query()` vs `ClaudeSDKClient` choice, and the streaming protocol have changed materially across releases. A pinned template snapshot is wrong on the day it ships.
2. **`uv` and FastAPI evolve as well**, though more slowly. A pinned `pyproject.toml` template ages.
3. **The mushi documentation should reference real paths and real lines** in the just-generated app. A static template cannot do that without complex post-processing.

Templates also create a synchronization burden: every Praxion contributor who touches the SDK or `uv` defaults must remember to update the templates, and reviewers must catch drift in code review.

A second option is to inline the current SDK signatures into the slash command body itself. That has the same drift problem at a different scope and additionally bloats the command.

The available alternative is to ship *prose specifications* of what to build (responsibilities, allowed dependency directions, file structure, safety patterns) plus a *discovery hook* (the `external-api-docs` skill, which fetches current SDK docs from context-hub at run time) and let Claude assemble the actual files at run time. This is the prompt-over-template discipline.

## Decision

Praxion's greenfield onboarding ships **no code templates** and **no pinned SDK signatures**. Instead:

- `commands/new-cc-project.md` contains prose specifications for the default app (file structure, dependency directions, safety patterns) and the mushi documentation (section order, lesson contents, anchor conventions).
- The slash command **mandates** that Claude invoke the `external-api-docs` skill to fetch current Claude Agent SDK and `uv` documentation from context-hub before generating any code that uses those libraries. The fetched signatures override training-data assumptions.
- The canonical "What is Praxion?" paragraph is the only static text shipped, lives inside the slash command's body between sentinel markers, and is copied verbatim into each generated mushi doc.
- The mushi doc is generated per-run, not derived from a template file, so it can reference real file paths and real lines that exist on disk after generation.

Validation happens at run time: after the slash command runs `uv add claude-agent-sdk` (or the current package name surfaced by chub), it imports the symbols it intends to use as a smoke check before writing source code. If the import fails, the command falls back to the alternate symbol surfaced by chub, and if that also fails it surfaces a diagnostic to the user.

## Considered Options

### Option A — Ship code templates under `claude/config/templates/` with placeholder substitution

**Pros:**
- Deterministic output across runs.
- No external dependency at run time.
- Easy to inspect what will be generated.

**Cons:**
- SDK signatures rot the moment they are committed.
- Every SDK release requires a Praxion PR to keep templates current.
- Templates accumulate baked-in assumptions (Python version, FastAPI version) that are invisible to reviewers.
- Mushi doc cannot reference real generated paths without secondary post-processing.

### Option B — Inline current SDK signatures into the slash command body

**Pros:**
- Single file to update; no separate templates directory.
- Easier to read alongside the prose flow.

**Cons:**
- Same drift problem at a different scope.
- Slash-command body grows large and mixes prose-spec with code-spec.
- Reviewers must catch drift in command markdown — no clear signal.

### Option C — Prose specs + run-time discovery via `external-api-docs` (chosen)

**Pros:**
- Praxion never holds a stale signature. The current SDK release is fetched at the moment of code generation.
- Slash command body is pure prose: structure, invariants, dependency directions, safety patterns.
- Mushi doc references real, generated paths because generation and documentation are co-temporal.
- Existing Praxion infrastructure (`external-api-docs` skill, context-hub) is reused; no new mechanism.

**Cons:**
- Generated output is non-deterministic across SDK releases.
- Failures in chub or in the live SDK package surface to the user.
- Requires that contributors writing the slash command resist the urge to inline "just one more snippet."

## Consequences

**Positive:**
- The greenfield flow is durable across SDK releases without Praxion changes.
- Onboarding sessions exercise `external-api-docs` and chub feedback loops as part of normal flow, hardening that infrastructure.
- The mushi doc gains the "this is about *your* project" quality that static templates cannot achieve.
- New contributors to the greenfield feature are not tempted to embed code in prose-only files.

**Negative:**
- Run-time generation has a longer first-turn latency (chub lookup + SDK install) than pure substitution.
- A chub outage degrades the flow to fallback (training-data assumptions), with reduced reliability. The user sees the degradation through a clear diagnostic, not silent failure.
- Two specifications must align — the prose spec in `commands/new-cc-project.md` and the actual SDK shape from chub — and a slash-command author who writes prose contradicting the live SDK creates a conflict the user must resolve. Mitigated by keeping the prose spec at the level of *structure and invariants*, never at the level of *symbol names or method signatures*.
