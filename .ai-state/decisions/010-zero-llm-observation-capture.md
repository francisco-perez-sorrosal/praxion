---
id: dec-010
title: Zero-LLM observation capture via pattern extraction
status: proposed
category: architectural
date: 2026-04-03
summary: Observations captured via regex/pattern matching on tool payloads, not LLM compression -- zero cost per event, LLM intelligence reserved for session narratives
tags: [memory, observations, performance, hooks]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
---

## Context

claude-mem uses LLM calls (via Claude Agent SDK) to compress every tool invocation into a structured observation with title, subtitle, narrative, facts, and concepts. This produces readable summaries but costs an API call per tool use, adds 60-90 seconds in Endless Mode, and has a 72% summary failure rate. The core question: is LLM-quality compression worth the cost and reliability risk at capture time?

## Decision

Observations are captured using pattern matching on the hook payload -- tool name, file paths from `tool_input`, outcome from `tool_response`, and classification from regex patterns (e.g., writes to `decisions/` -> "decision" classification). No LLM calls during capture.

LLM intelligence is applied only at query time via the `session_narrative()` tool, which reads raw observations and produces a structured Markdown summary. This inverts claude-mem's architecture: capture is cheap and reliable; intelligence is applied on-demand.

## Considered Options

### Option 1: LLM compression per event (claude-mem)

- **Pros**: High-quality, readable observation records
- **Cons**: Expensive ($0.01-0.05 per tool call), adds latency, requires API availability, 72% failure rate in practice, complex worker daemon architecture

### Option 2: Pattern-based extraction (selected)

- **Pros**: Zero cost, <5ms per capture, works offline, no API dependency, simple append-only architecture, no failure modes beyond disk I/O
- **Cons**: Raw observations are structured but not "readable" -- they record what happened, not a narrative interpretation

### Option 3: Batch LLM summarization

- **Pros**: Cheaper than per-event, better summaries than pattern-only
- **Cons**: Adds background processing complexity, delayed intelligence, still requires API availability

## Consequences

**Positive:**
- Observation capture never fails due to API issues
- Zero cost per tool invocation -- hooks are pure Python I/O
- Capture latency is <5ms (JSONL append)
- System works fully offline
- No Claude Agent SDK or worker daemon dependency

**Negative:**
- Raw observations require the `session_narrative()` or `timeline()` tools to be useful to humans
- Classification accuracy depends on regex patterns, which may miss edge cases
- No semantic compression -- observation volume is proportional to tool call volume (mitigated by blocklist)
