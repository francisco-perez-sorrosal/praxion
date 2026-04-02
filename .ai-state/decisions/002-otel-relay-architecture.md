---
id: dec-002
title: "Chronograph as OTel relay for hook telemetry"
status: accepted
category: architectural
date: "2026-03-31"
summary: "Hooks POST events to chronograph which creates OTel spans and exports to Phoenix via OTLP HTTP"
tags: [observability, otel, chronograph, phoenix]
made_by: agent
agent_type: systems-architect
affected_files: ["task-chronograph-mcp/src/task_chronograph_mcp/otel_relay.py", "task-chronograph-mcp/src/task_chronograph_mcp/server.py"]
affected_reqs: ["REQ-10", "REQ-15"]
---

## Context

Hook scripts need to emit telemetry data for agent pipeline observability. The question was how hooks should get their trace data into Phoenix (the trace UI). Hooks are stdlib-only Python scripts with strict latency requirements (<100ms).

## Decision

Chronograph acts as an OTel relay: hooks POST events to chronograph's HTTP endpoint, which creates properly structured OTel spans and exports them to Phoenix via OTLP HTTP. No direct hook-to-Phoenix export.

## Considered Options

### Option 1: Direct export from hooks

Hooks import the OTel SDK and export spans directly to Phoenix.

- (-) Requires OTel SDK in hooks, breaking the stdlib-only constraint
- (-) Adds latency to hook execution
- (-) Hooks lack the agent state context needed for correct span hierarchy

### Option 2: OTel Collector infrastructure

Deploy an OTel Collector as an intermediate layer.

- (-) Unnecessary infrastructure for a single-developer tool
- (-) Additional deployment and configuration burden

### Option 3: Chronograph as relay (selected)

Chronograph already has full agent state for correct span hierarchy.

- (+) Hook scripts stay stdlib-only with <100ms execution
- (+) Chronograph has the agent state needed for proper span parent-child relationships
- (+) No additional infrastructure beyond what already exists
- (-) Chronograph becomes a dependency for observability

## Consequences

### Positive

- Hook scripts remain simple and fast
- Span hierarchy is correct because chronograph knows the full agent tree
- No OTel Collector infrastructure needed

### Negative

- Chronograph must be running for telemetry to flow
- Chronograph gains additional responsibility beyond task tracking
