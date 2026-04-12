---
id: dec-026
title: Derive session_count from observations.jsonl instead of a counter in memory.json
status: accepted
category: implementation
date: 2026-04-12
summary: metrics() computes session count by counting distinct session_id in observations.jsonl; schema.session_count field deprecated, not schema-bumped
tags: [memory, metrics, observations, implementation, drift-fix]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - memory-mcp/src/memory_mcp/observations.py
  - memory-mcp/src/memory_mcp/metrics.py
  - memory-mcp/src/memory_mcp/server.py
---

## Context

`memory.json` has carried a `session_count` header field since the v2.0 schema landed. The field was intended to track the total number of distinct sessions that ever invoked the memory MCP server. In practice, the field is only incremented from `Store.session_start()`, and `session_start()` is called exclusively from tests. The SubagentStart hook does not call it (deliberately — `rules/swe/memory-protocol.md:5` states "you do NOT need to call `session_start()`"). The result: the counter in a live `memory.json` reads `10` while the true session count (derived by scanning `observations.jsonl` for distinct `session_id` values) is ~59. The metrics table at `memory-mcp/src/memory_mcp/metrics.py:334` reads the stale counter and reports the drift to every user who invokes the `metrics()` MCP tool.

Three viable paths exist to close the drift, with different trade-offs between code surface, runtime cost, and schema impact.

## Decision

Adopt option (c): compute `session_count` on demand by counting distinct `session_id` values in `observations.jsonl`. The counter in the `memory.json` schema header is left in place (to preserve backward compatibility and avoid a schema bump) but is no longer read by `metrics()`; it is flagged as deprecated in accompanying documentation (`memory-mcp/CLAUDE.md`, `rules/swe/memory-protocol.md`).

Specific implementation:

- Add a new method `ObservationStore.count_sessions() -> int` at `memory-mcp/src/memory_mcp/observations.py`. The method streams the active `observations.jsonl` file, JSON-decodes each line, skips malformed lines and lines missing `session_id`, and returns the count of the distinct-session-id set. Missing or empty files return `0`. The read path does not take `LOCK_EX` (distinct from the write path).
- `memory-mcp/src/memory_mcp/server.py` — the `metrics()` tool implementation sets `stats["session_count"] = _get_obs_store().count_sessions()` before building the response, falling back to the stored counter if the observations store is not configured.
- `memory-mcp/src/memory_mcp/metrics.py:334` — no change. The formatter already reads `data.get('session_count', '?')`; it now receives the derived count from the caller.
- Schema header field retained. No v2.0 → v2.1 bump. Documentation updated to describe the field as deprecated.

## Considered Options

### Option (a) — Wire `inject_memory.py` to call `session_start()`

Make the SubagentStart hook call `session_start()` so the counter gets incremented at real session boundaries.

**Pros:**
- Tracks session counts at the right boundary (actual session start).
- Uses existing counter infrastructure.

**Cons:**
- Adds an MCP call inside a synchronous hook that currently has no MCP dependency — increases latency on every session start and expands the hook's failure surface.
- Contradicts `rules/swe/memory-protocol.md:5` ("you do NOT need to call `session_start()`") — would require updating the rule and every agent that learned from it.
- Couples hook correctness to memory-server availability; a memory-server outage now causes session-start failures.

### Option (b) — Remove the `session_count` field and its consumers

Delete the field from the schema header; delete the metric line from `metrics.py`.

**Pros:**
- Mechanical; eliminates drift by eliminating the artifact.
- Smallest code surface change.

**Cons:**
- Destroys a useful UX signal (the metrics tool currently lets users gauge memory activity by session count).
- Requires a v2.0 → v2.1 schema bump or a documented "legacy field ignored" policy.
- `session_start()` signature must remain (tests still use it); removing only the counter while keeping the method creates a different kind of inconsistency.

### Option (c) — Derive from observations (chosen)

Count distinct `session_id` values in `observations.jsonl` on demand.

**Pros:**
- Honest — no drift possible; the reported number equals the ground truth.
- No synchronous-hook cost — the computation happens only when the user invokes `metrics()`.
- Uses existing infrastructure (`observations.jsonl` already ships `session_id` on every record; rotation is in place and will be activated in a later ROADMAP phase).
- No schema bump required.
- `session_start()` remains available for tests that need it.

**Cons:**
- O(N) file scan on every `metrics()` call (N = number of observations in the active file). Current file is ~1.9 MB; the scan completes in milliseconds. Bounded by rotation once active.
- Slightly more code than option (b) — a new method on `ObservationStore` plus wiring in `server.py`.
- The `session_count` field in the schema header becomes a dead field that future readers may wonder about; mitigated by the doc updates to `memory-mcp/CLAUDE.md` and `rules/swe/memory-protocol.md`.

## Consequences

**Positive:**

- `metrics()` reports the true session count; drift is structurally impossible.
- No new hook dependencies; no synchronous memory-MCP calls added to the hook path.
- Backward compatible — existing `memory.json` files keep their schema; no v2.0 → v2.1 migration required.
- Read path is lock-free, preserving the existing pattern where `LOCK_EX` guards writes only.

**Negative:**

- Every `metrics()` invocation streams the observations file. Within current rotation bounds this is fast, but if rotation is misconfigured the scan could grow unboundedly.
- The `session_count` field in `memory.json` is now dead schema weight. Future hygiene sprints may want to revisit this.

**Operational:**

- `memory-mcp/CLAUDE.md` documents that `session_count` is derived from observations.
- `rules/swe/memory-protocol.md` describes the derivation (for agents reasoning about memory metrics).
- `test_observations.py` gets test cases covering missing file, empty file, distinct sessions, duplicate session IDs, missing `session_id` field, and malformed JSONL lines — each returning the expected count.
- `test_metrics.py` gets an end-to-end assertion that the `metrics()` tool returns the derived count.
