---
id: dec-009
title: Dual-layer memory architecture (curated + observations)
status: proposed
category: architectural
date: 2026-04-03
summary: Memory v2.0 uses two complementary stores -- curated JSON for institutional knowledge and append-only JSONL for automatic tool observations
tags: [memory, architecture, observations]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
---

## Context

Praxion's memory system v1.3 relies exclusively on curated memories -- agents must explicitly call `remember()` to persist knowledge. Research shows agents rarely call `remember()` without enforcement (~40-60% compliance with prompt-only instructions). Meanwhile, claude-mem demonstrates that automatic observation capture via PostToolUse hooks provides comprehensive session history, but at the cost of an LLM call per tool invocation and a complex worker daemon architecture.

The core tension: curated memories are high-signal but sparse; automatic observations are comprehensive but noisy. Neither alone solves the problem of institutional memory + session continuity.

## Decision

Memory v2.0 uses a dual-layer architecture:

- **Layer A (Curated)**: The existing `.ai-state/memory.json` store. Agents call `remember()`. Entries are edited, consolidated, and scored. This is institutional knowledge -- facts, decisions, gotchas, patterns.
- **Layer B (Observations)**: A new append-only `.ai-state/observations.jsonl` log. PostToolUse and lifecycle hooks capture structured events using pattern matching (zero LLM cost). Events are cheap, numerous, and queryable by time.

The two layers serve different questions: curated answers "what do we know?", observations answer "what happened?"

## Considered Options

### Option 1: Curated-only (enhance v1.3)

Improve the existing system with better hooks, scaling, and enforcement. No observation layer.

- **Pros**: Simpler, single data store, no new file format
- **Cons**: Still depends on agents calling `remember()`. Session history remains invisible. The LEARNINGS.md -> memory gap persists as the primary knowledge loss vector.

### Option 2: Observer-first (claude-mem style)

Capture every tool invocation automatically with LLM compression. Replace curated memories with auto-generated observations.

- **Pros**: Comprehensive, zero agent effort required
- **Cons**: Expensive (LLM call per tool use), noisy (routine reads become "observations"), complex infrastructure (worker daemon, ChromaDB), unreliable (claude-mem's 72% summary failure rate, 115 GitHub issues)

### Option 3: Dual-layer (selected)

Both curated and observation layers, with clear separation and complementary tools.

- **Pros**: Best of both -- institutional knowledge is curated, session history is automatic. Zero LLM cost at capture. Each layer serves a distinct need.
- **Cons**: Two data stores, two file formats, more surface area

## Consequences

**Positive:**
- Session history is captured automatically without requiring agent cooperation
- Curated memories retain their high-signal quality
- Timeline and narrative tools provide temporal navigation that curated-only cannot
- ADR decisions, commits, and implementation activity appear in the observation timeline without manual `remember()` calls

**Negative:**
- Two data stores to maintain (JSON + JSONL)
- JSONL file grows continuously -- requires rotation strategy
- Agents must learn which tool to use for which layer (mitigated by clear tool naming)
- Git repository includes observation history (mitigated by rotation keeping active file bounded)
