---
id: dec-048
title: Observation/span correlation via OpenInference `session.id` + W3C trace-context
status: accepted
category: architectural
date: 2026-04-16
summary: Elevate `trace_id`/`span_id`/`parent_span_id` to top-level fields on Observation; rename chronograph `praxion.session_id` to OpenInference `session.id` on every span; extract W3C traceparent from MCP `params._meta` at memory-mcp tool handlers; forward via hook `additionalContext`; three-phase rollout with empty-string defaults
tags: [observability, otel, openinference, correlation, schema-break, memory-mcp, chronograph]
made_by: agent
agent_type: systems-architect
pipeline_tier: full
affected_files:
  - memory-mcp/src/memory_mcp/schema.py
  - memory-mcp/src/memory_mcp/correlation.py
  - memory-mcp/src/memory_mcp/server.py
  - task-chronograph-mcp/src/task_chronograph_mcp/otel_relay.py
  - hooks/capture_observations.py
---

## Context

Observations (captured by hooks into `observations.jsonl`) and spans (captured by chronograph into OTel/Phoenix) both carry `session_id`, allowing session-level correlation. But there is no span-level or trace-level correlation: a `remember()` call recorded in observations cannot be linked back to the specific MCP tool span that produced it, and chronograph spans do not all carry the canonical OpenInference `session.id` attribute. RESEARCH_FINDINGS_correlation.md enumerated four primitives (session.id everywhere, trace_id+span_id on observations, `params._meta.traceparent` extraction, OTel MCP semconv field names). User confirmed breaking schema changes are acceptable.

## Decision

Adopt all four primitives from RESEARCH_FINDINGS_correlation.md: `session.id` on every chronograph span, `trace_id`+`span_id` on observations, MCP `params._meta.traceparent` extraction at memory-mcp tool handlers, and the OTel MCP semconv field names. Rename all `praxion.session_id` to the OpenInference canonical `session.id` (breaking-allowed per user). Accept a schema break on `observations.jsonl`: new fields added, no migration of historical entries. Query model: extend `query()` with trace filters; no new MCP tool.

**Objection registered on audit-open-question #3**: the researcher's open question on "should observation writes move from hooks into memory-mcp tool handlers?" — answered **no**, keep observations hook-only per dec-009 and dec-010. Moving observation writes to memory-mcp would revisit two ADRs and change the "zero-LLM, hook-captured" invariant. Instead, enrich the hook payload at capture time by having the hook read the MCP request envelope or forward extracted IDs via `additionalContext`. This keeps dec-009/dec-010 intact.

**Identifier scheme** (finalized):

| Field | Where it lives | Value format | Source |
|---|---|---|---|
| **`session.id`** (OpenInference canonical) | Every chronograph span attribute + every observation row's top-level field | Claude Code's `payload["session_id"]` | Hook payload |
| **`trace_id`** | Observation row top-level field; chronograph spans inherit from OTel context | 32-char lowercase hex (W3C) | Extracted from MCP `params._meta.traceparent` OR empty string when unavailable |
| **`span_id`** | Observation row top-level field; chronograph spans inherit from OTel context | 16-char lowercase hex (W3C) | Extracted from MCP `params._meta.traceparent` OR empty string when unavailable |
| **`parent_span_id`** (optional) | Observation row top-level field | 16-char lowercase hex | Optional; populated when traceparent is parent-context |
| **`mcp.session.id`** (OTel semconv, additive) | Chronograph tool spans; observations optional | MCP-level UUID | Captured from MCP protocol when available; ignored when not |
| **`jsonrpc.request.id`** (OTel semconv, additive) | Chronograph tool spans; observations optional | Per-request | Captured from MCP protocol |

**Top-level fields, not metadata.** Storing `trace_id` and `span_id` as top-level columns of `observations.jsonl` matches the log-correlation industry pattern (Datadog, OpenTelemetry log SDKs). Putting them under `metadata: {}` hides them from quick grep and from simple query filters. Breaking-allowed per user. **Deviation from research**: research's Primitive 2 example used `metadata:` dict; this ADR elevates to top-level.

**Propagation mechanism** — three-phase rollout:

- **Phase A** (implement now): add `session.id` (OpenInference name) as an explicit attribute on every chronograph span — not just session root. Extend `Observation` dataclass with top-level `trace_id`, `span_id`, `parent_span_id` fields — emit empty strings when unknown. Rename `praxion.session_id` → `session.id` everywhere in chronograph's OTel attributes. Keep `praxion.project_name`, `praxion.agent_id`, `praxion.task_slug`. `praxion.session_id` is the only field being superseded.
- **Phase B** (implement now): add a `parse_traceparent()` helper to memory-mcp (pure stdlib, 55-char regex). `remember()` and `recall()` tool handlers read `params._meta.traceparent` from the MCP request envelope; parse; pass extracted IDs to the hook via `additionalContext`. Hooks (`capture_memory.py`) read `additionalContext.trace_id`/`span_id` if present; populate observation row fields; empty string otherwise.
- **Phase C** (future — upstream watch): when Claude Code's MCP client gains `params._meta.traceparent` injection (tracked via modelcontextprotocol issue #246), coverage improves to include all MCP tool calls. No schema change needed — fields already present since Phase A.

**Schema changes** (breaking): `Observation` dataclass gains top-level `trace_id: str = ""`, `span_id: str = ""`, `parent_span_id: str = ""`. `ObservationStore.query()` gains `trace_id: str | None = None` parameter (field-equality filter; append-only JSONL; full-scan is fine for current size). Chronograph span attributes: rename `praxion.session_id` → `session.id` on all spans; additionally add `session.id` to tool spans (currently absent); additionally set `mcp.session.id` and `jsonrpc.request.id` when available.

**Migration for existing data**: no migration — historical `observations.jsonl` entries lose the `trace_id`/`span_id` fields silently (they read as empty strings via `dict.get("trace_id", "")`). Backfilling from `session_id` would synthesize trace IDs that don't correspond to real OTel spans — this is the `correlation_id` anti-pattern.

**Query model**: extend `ObservationStore.query()` with `trace_id` filter. Secondary `find_by_trace(trace_id)` MCP tool deferred (trivial to add once the core field exists). Phoenix-side: no changes — Phoenix already filters by `session.id` via the Sessions UI.

**`agent_id` parity**: use `session_id` (not `__main_agent__`) for the main agent in chronograph, matching the hook convention. Closes the last parity gap.

**Project-identity reconciliation**: keep `project` on observations, keep `praxion.project_name` on chronograph spans for now — conceptually the same but syntactically divergent; renaming would touch many chronograph call sites for marginal gain.

**`praxion.session_id` deprecation**: one-shot rename per user (breaking allowed). ADR dec-009 was reviewed and does not name `praxion.session_id`; no supersession clause is needed.

## Considered Options

### Option 1 — Synthetic `correlation_id`

Rejected per research Axis 1 option C (fabricated IDs create false correlations).

### Option 2 — session_id-only (coarse)

Rejected as insufficient for "which trace produced this `remember()`" query; user explicitly asked for that capability.

### Option 3 — Move observation writes into memory-mcp tool handlers

Rejected; revisits dec-009/dec-010 invariants ("zero-LLM, hook-captured").

### Option 4 — Sidecar MCP proxy that injects traceparent

Rejected as out-of-scope for this phase (complexity cost, new component). Phase C of the rollout plan assumes upstream Claude Code eventually injects it; meanwhile, `additionalContext` forwarding works for memory-mcp's own spans.

### Option 5 — Top-level trace fields + `session.id` rename + traceparent extraction (chosen)

Enables the user-requested trace↔memory join; aligns with 2026 OTel MCP semconv; no new infrastructure; ~60 bytes/row overhead.

## Consequences

**Positive**: enables the user-requested trace↔memory join; aligns with 2026 OTel MCP semconv; no new infrastructure; ~60 bytes/row overhead. Phase A alone delivers ~80% of the value (session-level join).

**Negative**: breaking schema change on `observations.jsonl` (mitigated — user confirmed); historical data is lossy on the new fields; `praxion.session_id` rename touches 5 call sites.

**Risk**: MCP spec PR #414 may see field-name churn before 1.0. Mitigated by using the published convention names (`session.id`, `mcp.session.id`, `jsonrpc.request.id`) and by the fact that none of these are on the critical path — empty strings degrade gracefully.
