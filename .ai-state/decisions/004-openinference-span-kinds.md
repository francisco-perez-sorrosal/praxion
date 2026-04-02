---
id: dec-004
title: "CHAIN span kind for session root, AGENT for pipeline agents"
status: accepted
category: architectural
date: "2026-03-31"
summary: "Use OpenInference CHAIN for orchestration/session root and AGENT for reasoning blocks in Phoenix traces"
tags: [observability, otel, openinference, phoenix]
made_by: agent
agent_type: systems-architect
affected_files: ["task-chronograph-mcp/src/task_chronograph_mcp/otel_relay.py"]
affected_reqs: ["REQ-01", "REQ-04"]
---

## Context

OpenInference defines span kinds for categorizing trace spans in Phoenix. The session root span and pipeline agent spans needed appropriate kind assignments for correct Phoenix UI rendering.

## Decision

Use CHAIN span kind for the session root (orchestration/linking) and AGENT for individual pipeline agents (reasoning blocks). Phoenix renders both with appropriate UI treatment.

## Considered Options

### Option 1: AGENT for root

Use AGENT span kind for the session root span.

- (-) Conflates orchestration with reasoning
- (-) Phoenix UI treats AGENT spans as reasoning blocks, which is misleading for a session container

### Option 2: Custom SESSION kind

Define a custom span kind not in the OpenInference spec.

- (-) Not in the OpenInference specification
- (-) Phoenix may not recognize or render it correctly

### Option 3: CHAIN for root, AGENT for agents (selected)

CHAIN is semantically correct for orchestration/linking spans.

- (+) Semantically accurate: CHAIN represents orchestration, AGENT represents reasoning
- (+) Phoenix renders both with appropriate visual treatment
- (+) Follows the OpenInference specification as intended

## Consequences

### Positive

- Correct semantic representation in trace data
- Phoenix UI displays session structure clearly

### Negative

- Must maintain awareness of OpenInference span kind semantics when adding new span types
