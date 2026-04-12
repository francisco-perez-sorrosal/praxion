---
id: dec-012
title: "Deterministic command hook for duplication detection, LLM judgment reserved for verifier"
status: accepted
category: architectural
date: "2026-04-04"
summary: "PostToolUse hook uses command type (AST/heuristic) for intra-file detection; prompt type (LLM-judged) reserved for verifier's cross-module analysis"
tags: [code-quality, duplication, hooks, performance]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - hooks/detect_duplication.py
  - agents/verifier.md
---

## Context

The duplication prevention system needs both real-time detection (at edit time) and deep analysis (cross-module semantic duplication). Claude Code hooks support two types: `command` (runs a script, deterministic) and `prompt` (LLM-judged, adds API cost). The question was where to place the LLM judgment boundary.

## Decision

Use a `command` type hook for real-time PostToolUse detection (Python script with AST analysis for intra-file structural duplication). Reserve LLM-judged semantic analysis for the verifier agent's Phase 4 Convention Compliance, which already uses LLM judgment to assess changed files against coding conventions.

## Considered Options

### Option 1: command hook + verifier LLM judgment (chosen)

**Pros:** Zero API cost per edit. Fast (~200ms). Deterministic. No hallucination risk. Proven pattern (`format_python.py`). LLM judgment applied at the right scope (verifier reads multiple files).

**Cons:** Hook misses semantic duplication. Detection split across two components.

### Option 2: prompt hook for all detection

**Pros:** Can catch semantic duplication in real-time.

**Cons:** API cost per Write/Edit. 5-10s latency per edit. Cannot see sibling files. Hallucination risk for false positives.

### Option 3: command hook only, no LLM judgment

**Pros:** Simplest. No LLM cost.

**Cons:** Cannot catch semantic duplication. No cross-module analysis.

## Consequences

**Positive:**
- Real-time detection adds zero API cost
- Hook latency (~200ms) negligible compared to LLM turn time
- Deterministic findings reduce false positive fatigue
- LLM judgment applied where it has most context (verifier reads multiple files)

**Negative:**
- Semantic duplication within a single file may be missed by the hook
- Direct tier has no LLM-judged duplication analysis
