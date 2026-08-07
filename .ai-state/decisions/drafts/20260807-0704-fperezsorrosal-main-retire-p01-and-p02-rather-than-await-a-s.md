---
id: dec-draft-71566337
title: Retire P01 and P02 rather than await a substrate that cannot answer them
status: proposed
category: behavioral
date: 2026-08-07
summary: Retire sentinel checks P01 (delegation depth) and P02 (delegation-result pairing) permanently; re-specify P03 and P04 against the observations.jsonl WAL; scope the P-dimension preamble to the checks that actually read an event stream.
tags: [sentinel, pipeline-discipline, gate-liveness, chronograph, observations-jsonl, retirement, scope-fidelity]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: standard
affected_files:
  - agents/sentinel.md
  - .ai-state/observations.jsonl
re_affirms: dec-248
---

## Context

The sentinel's Pipeline Discipline dimension declared "Requires Task Chronograph data. Skip with a note when unavailable." The 2026-08-06 audit was the first run to execute that dimension with the Chronograph MCP tools actually in hand — the sentinel's own grant (`Read, Glob, Grep, Bash, Write`) has never included them, so the orchestrator ran them instead. Two facts emerged:

- `get_pipeline_status` returns **only the current session**. It returned exactly the five agents then in flight, all at depth 1, all `running`.
- `get_agent_events` returns `[]` for every past agent type queried.

So P01–P05 as specified could never observe a *historical* violation. They always measure an in-flight session, which is trivially clean — a false all-clear presented as a PASS. This is a **specification** defect, not a data gap, and no amount of populated substrate would fix it.

A tempting remedy was to mark the checks blocked-on-substrate and name the producer that would unblock them. Examining what each check actually asserts showed that reasoning is wrong for two of them.

## Decision

**Retire P01 and P02.** Both carry a do-not-re-add note in the catalog.

- **P01 (no delegation chains exceeding depth 2).** Even if the WAL emitted a parent edge, it would read **depth 1 forever**: agents cannot spawn agents in this architecture, so every subagent's parent is the orchestrator. What P01 actually means — the orchestrator's *recommendation* chain across a conversation, where one agent's output suggests spawning another — is unobservable by any hook, because it exists in the orchestrator's reasoning rather than in the event stream. The invariant is real and keeps its genuine enforcement point: `swe-agent-coordination-protocol.md § Delegation Depth`, with explicit user confirmation required at depth 3+.
- **P02 (every `delegation` has a matching `result`).** The `delegation`/`result` event pair it reads was never emitted by any producer — the consumer was wired to a producer that does not exist. Its only WAL-expressible reading is *"every agent that started also stopped"*, which **is P03**. Its document-level reading is already covered by the completion handshake. Two rows asserting one thing, one of them permanently unrunnable, is worse than one row that runs.

**Re-specify P03 against `.ai-state/observations.jsonl`** — the durable WAL `dec-248` designates — pairing on `agent_id`. Pairing on `agent_type` is named in the row as the trap: a sibling agent's stop would satisfy another's start. Two boundaries are excluded as non-findings rather than left to a future reader to rediscover: in-flight agents legitimately have a start with no stop, and a stop whose start predates the WAL's first record is front-truncation, reported INFO and never WARN.

**Re-specify P04** to judge tool and path surface from `tool_use` records grouped by `agent_id` against each agent's declared `tools:` grant, with its bound stated in the row: surface, never semantics.

**Scope the preamble.** It now names the real substrate, states the Chronograph problem as a specification defect, and requires every skip to say which of three states applies — `substrate absent` / `reader unreachable` / `substrate carries no history`. A skip citing the first when the truth is the third is what concealed this for as long as it lasted.

## Considered Options

### A. Mark P01/P02 blocked-on-substrate, naming the producer that would unblock them

- **Pro**: preserves the stated intent; costs nothing today; leaves a clear path.
- **Con**: dishonest for P01, whose answer would be a constant regardless of substrate, and redundant for P02, whose only expressible form already exists as P03. It would leave two rows that a future maintainer might "fix" by building an emitter that still could not make them bite.

### B. Build the emitter (parent/delegation edges in the WAL), then keep all five

- **Pro**: the most complete substrate.
- **Con**: buys nothing for P01 (depth 1 forever) and duplicates P03 for P02. Real cost, no detection gained.

### C. Retire P01/P02, re-specify P03/P04, scope the preamble (chosen)

- **Pro**: every surviving row runs against a substrate that exists and can disagree with it. Per `gate-liveness.md`, "a correct gate nobody calls and a deleted one catch the same number of defects, and only one of them misleads a reader."
- **Con**: the dimension no longer *appears* to cover delegation depth, so a reader must follow the pointer to the coordination protocol to find where that invariant lives. Mitigated by naming that location in the retirement note.

## Consequences

**Positive.** Every remaining P check reads a substrate that exists and carries history. P03 became answerable only because the same session's emitter fix made `agent_stop` reliably carry `agent_id` and `agent_type` (with provenance in a new `agent_type_source` field) — the repair and the re-specification are causally linked, not merely adjacent.

**Negative.** Retiring a check is not free: if agents ever *can* spawn agents, P01's question returns and the retirement must be re-opened rather than silently outlived. The do-not-re-add note names that condition so a future reader can tell a superseded question from a returning one.

**Neutral but load-bearing.** A scope-fidelity fix surfaced that this decision did not anticipate: **P05 was never an event check at all.** Its substrate is `.ai-work/` handoff documents, and the Chronograph preamble had been gating it — and P06–P08 — on a substrate none of them read. The preamble is now scoped to P03–P04 only. That mis-gating is exactly the failure this decision is about, found one layer down while fixing it.

## Prior Decision

This **re-affirms `dec-248`** without superseding it. `dec-248` designated `observations.jsonl` as the recovery WAL and demoted claim-based state to a verified cache; this decision applies that same designation to the Pipeline Discipline dimension, which had been reading a different, historyless surface. `dec-248` remains `accepted`; nothing in it is contradicted. A future supersession would need evidence that a session-scoped telemetry surface can answer questions the durable WAL cannot.
