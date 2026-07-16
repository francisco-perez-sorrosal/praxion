---
id: dec-225
title: Remove the in-house curated-memory subsystem (blank slate for sandbook)
status: accepted
category: architectural
date: 2026-06-10
summary: Delete Praxion's curated-memory engine (memory.json, the Memory MCP server, the enforcement gate, the memory-protocol rule) while preserving observability and ADR injection, leaving a clean seam for the external `sandbook` memory package
tags: [memory, removal, observability, sandbook, architecture, hooks]
made_by: user
pipeline_tier: full
supersedes: dec-009
affected_files:
  - memory-mcp/
  - hooks/inject_memory.py
  - hooks/memory_gate.py
  - hooks/validate_memory.py
  - hooks/remind_memory.py
  - hooks/inject_decisions.py
  - hooks/_hook_utils.py
  - scripts/merge_driver_memory.py
  - rules/swe/memory-protocol.md
  - skills/memory/
  - commands/cajalogic.md
  - commands/save-changes.md
  - .claude-plugin/plugin.json
  - .gitattributes
re_affirmed_by:
  - dec-237
---

## Context

Praxion shipped an in-house curated-memory subsystem — a dual-layer design
(dec-009): a curated `memory.json` store with `remember`/`recall`/`forget`
tools exposed by a dedicated `memory-mcp/` MCP server, a blocking enforcement
gate that forced `remember()` calls on substantive sessions, an always-loaded
`memory-protocol` rule, and supporting hooks, merge driver, skill, and
commands. Praxion itself ran with this subsystem **disabled**
(`PRAXION_DISABLE_MEMORY_MCP=1`); the machinery existed primarily to be
shipped into managed projects.

Maintaining a memory engine is not Praxion's purpose. A separate, purpose-built
memory package — `sandbook` — provides a categorically more capable engine
(five-tier memory, vector + graph retrieval, background consolidation, a
deterministic eval suite) and ships non-MCP consumption surfaces (an embedded
library and an HTTP `/v1` client) plus a single per-project memory-directory
knob. The decision is to **offload memory to sandbook** and remove the in-house
subsystem first, leaving a clean integration seam.

Two subsystems were entangled with curated memory and must be preserved:
**observability** (`observations.jsonl` + the `capture_*` hooks + the
`observations-jsonl` merge driver) was defined as "layer B" of the dual-layer
memory in dec-009 but is in fact a distinct, independently-toggled concern; and
**ADR context injection**, which was bundled inside `inject_memory.py` and
gated behind the memory kill-switch.

## Decision

Remove the curated-memory subsystem from Praxion and from what onboarding ships
to managed projects, while preserving observability and ADR injection:

- **Extract** ADR-context injection into a standalone, memory-independent
  `hooks/inject_decisions.py` (its own `PRAXION_DISABLE_DECISION_INJECTION`
  toggle) before deleting `inject_memory.py`. ADR injection now fires
  regardless of any memory backend.
- **Delete** `memory-mcp/`, the gate hooks (`memory_gate`, `validate_memory`,
  `remind_memory`), `scripts/merge_driver_memory.py`, `rules/swe/
  memory-protocol.md`, `skills/memory/`, `commands/cajalogic.md`, and
  `commands/save-changes.md`.
- **Strip** `hooks/_hook_utils.py` to `is_disabled` + `DISABLE_OBSERVABILITY`;
  unwire the memory hook/MCP/merge-driver registrations from `hooks.json`,
  `plugin.json`, `.gitattributes`, the install scripts, the Cursor template,
  and the Codex bridge; drop the memory phases from onboarding and the memory
  source/proposal-type from skill-genesis.
- **Preserve** observability in full, and document a "memory backend: none"
  state pending sandbook integration.

## Considered Options

### Keep the in-house subsystem, integrate sandbook alongside
Rejected: two memory systems is strictly worse — duplicated maintenance,
conflicting `remember()` surfaces, and a larger always-loaded footprint. The
in-house engine is the weaker of the two and not Praxion's core competency.

### Remove memory and observability together as one "dual-layer" unit
Rejected: observability is independently toggled (`PRAXION_DISABLE_OBSERVABILITY`),
has its own merge driver, and is the only layer Praxion actually runs. It feeds
metrics and the dashboard. Deleting it would regress live functionality for no
benefit.

### Remove now, behind a pinned sandbook reference (chosen)
Sandbook is pre-1.0 (alpha, not yet on PyPI). Removing the in-house subsystem
now — decoupled from sandbook integration — keeps Praxion's codebase clean and
lets sandbook land later behind a pinned git ref once its API settles.

## Consequences

**Positive.** ~25 fewer files and a deleted MCP server to maintain; the
always-loaded `memory-protocol` rule is gone (reclaimed SessionStart tokens);
observability and ADR injection are now cleanly separated single-purpose
concerns; a documented seam exists for sandbook.

**Negative / accepted.** The persistent half of the Learning Loop is dormant
until sandbook integrates — `LEARNINGS.md` (ephemeral, in-pipeline) remains,
but cross-session memory pauses. skill-genesis loses memory as a harvest
source (it retains LEARNINGS.md, verification reports, sentinel findings, and
ADR patterns). The memory-MCP-sourced span correlation (dec-048) no longer
fires, so observation `trace_id`/`span_id` fields default to empty until a new
tool populates `additionalContext`. Already-onboarded managed projects retain
dangling memory merge-driver registrations until a follow-up cleanup command;
that retro-cleanup is deliberately out of scope here.

## Prior Decision

Supersedes **dec-009** (Dual-layer memory architecture): the curated layer is
removed; the observations layer survives, reframed as a standalone observability
concern rather than "memory layer B". Also obsoletes **dec-025** (memory hygiene
rules R1–R7) and **dec-039** (shared `EXEMPT_AGENTS` for the memory gate), both
of which governed now-deleted machinery. **dec-060** (`/clean-auto-memory`) is
unaffected — it manages Claude Code's *native* `~/.claude` auto-memory, a
separate system that is preserved. A future ADR will record the sandbook
integration that restores cross-session memory.
