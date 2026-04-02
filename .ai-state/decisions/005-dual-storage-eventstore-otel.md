---
id: dec-005
title: "Dual storage: EventStore for real-time MCP + OTel/Phoenix for persistence"
status: accepted
category: architectural
date: "2026-03-31"
summary: "Maintain both in-memory EventStore for MCP queries and OTel/Phoenix for persistent traces in parallel"
tags: [observability, storage, chronograph, phoenix]
made_by: agent
agent_type: systems-architect
affected_files: ["task-chronograph-mcp/src/task_chronograph_mcp/server.py", "task-chronograph-mcp/src/task_chronograph_mcp/otel_relay.py"]
affected_reqs: ["REQ-10", "REQ-14"]
---

## Context

MCP tools need fast in-memory reads for real-time agent queries (task status, current pipeline state). Phoenix provides persistent trace storage and a visualization UI. The question was whether to use one storage system for both purposes or maintain two.

## Decision

Dual storage: EventStore (in-memory) for real-time MCP queries and OTel/Phoenix for persistent traces. Both are maintained in parallel with independent failure domains.

## Considered Options

### Option 1: OTel/Phoenix only

Route all queries through Phoenix's API.

- (+) Single source of truth
- (-) MCP queries require network calls to Phoenix
- (-) Phoenix dependency for core MCP functionality
- (-) Higher latency for real-time queries

### Option 2: EventStore only

Keep only the in-memory store, skip Phoenix integration.

- (+) Simplest architecture
- (-) No persistence across chronograph restarts
- (-) No visualization UI for trace exploration

### Option 3: Dual storage (selected)

Both stores maintained in parallel.

- (+) MCP tools get fast in-memory reads without network dependency
- (+) Phoenix provides persistence and rich trace UI
- (+) Independent failure domains: Phoenix going down does not affect MCP tools
- (-) Two stores to keep consistent
- (-) Additional code complexity for dual-write path

## Consequences

### Positive

- Real-time MCP queries are fast and do not depend on Phoenix availability
- Full trace persistence and visualization via Phoenix

### Negative

- Dual-write path must be maintained
- Potential for inconsistency if one write path fails
