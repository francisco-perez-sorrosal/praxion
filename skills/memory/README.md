# Memory Skill

Persistent, structured memory system that tracks user preferences, assistant learnings, project conventions, and relationship dynamics across sessions. Dual-layer architecture: curated memories in `.ai-state/memory.json` (JSON) and automatic observations in `.ai-state/observations.jsonl` (JSONL). Progressive disclosure via Markdown-KV format.

Complements built-in memory (e.g. Claude Code's `MEMORY.md`) with explicit categories, knowledge types, tags, confidence levels, temporal supersession, structured consolidation, chronological timelines, and session narratives. Used via memory MCP in both Claude Code and Cursor.

## When to Use

- Starting a new session (memory context is auto-injected via hook -- no manual action needed)
- Storing user preferences, project conventions, or workflow discoveries via `remember()`
- Browsing the full memory index via `browse_index()`
- Searching across accumulated knowledge via `search()`
- Consolidating overlapping entries via `consolidate()`
- Reviewing memory health via `reflect()`

## Activation

Auto-triggered by phrases like "remember", "recall", "cross-session memory", "persistent
context", or "session start". Also activates when managing user preferences, project
conventions, or assistant self-knowledge. Requires the `memory` MCP server to be present
in the session; in Praxion, this is conditionally enabled (disabled when
`PRAXION_DISABLE_MEMORY_MCP=1`).

## Enforcement and Capture

Memory is automatically integrated into agent workflows:

1. **Hook injection**: `inject_memory.py` injects Markdown-KV summary into every agent's context at spawn (LOCK_SH reads, importance tiers, agent-type-aware routing)
2. **Always-loaded rule**: `memory-protocol.md` guides when to call `remember()` with type guidance
3. **Validation hook**: `validate_memory.py` warns when agents write LEARNINGS.md without calling `remember()`
4. **Capture hooks**: `capture_memory.py` (PostToolUse) and `capture_session.py` (lifecycle events) write automatic JSONL observations
5. **Promotion hook**: `promote_learnings.py` warns before LEARNINGS.md cleanup when unpromoted entries exist

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core reference: ontology, tool table, enforcement, observation layer, integration, proactive guidelines |
| `references/schema.md` | Full JSON schema v2.0, field constraints, Observation schema, Markdown-KV format, consolidation actions |
| `README.md` | This file -- overview and usage guide |

## Data Model

Schema v2.0 with six categories. Key fields: `summary` (one-line description), `valid_at`/`invalid_at` (temporal supersession), `type` (knowledge classification), `created_by` (provenance), enriched `source` with `agent_type`, `agent_id`, and `session_id`.

| Category | Tracks |
|----------|--------|
| `user` | Personal info, preferences, workflow habits |
| `assistant` | Self-knowledge about patterns, effective approaches |
| `project` | Conventions, architecture decisions, tech stack |
| `relationships` | Interaction dynamics, delegation style, trust |
| `tools` | Tool preferences, environment setup, CLI shortcuts |
| `learnings` | Cross-session insights, gotchas, debugging solutions |

## Key Tools

| Tool | Description |
|------|-------------|
| `browse_index` | Full Markdown-KV summary of all entries. Most token-efficient view. |
| `remember` | Store entry with `summary`, `type`, and `created_by` params. Auto-generates summary if omitted. |
| `search` | Multi-term ranked search. `detail="index"` (Markdown) or `detail="full"` (JSON). Filter by `since` and `type`. |
| `forget` | Soft-delete (sets `invalid_at`). Use `hard_delete` for permanent removal. |
| `consolidate` | Execute structured actions (merge, archive, adjust, update) with backup. |
| `reflect` | Lifecycle analysis: stale entries, archival candidates. Read-only. |
| `timeline` | Chronological observation history. Filter by date range, session, tool, classification. |
| `session_narrative` | Structured session summary: what was done, files touched, decisions, outcome. |

## Related Artifacts

- [`/cajalogic` command](../../commands/cajalogic.md) -- slash command that delegates to this skill
- [`memory-protocol.md`](../../rules/swe/memory-protocol.md) -- always-loaded rule for remember guidance
- [`inject_memory.py`](../../hooks/inject_memory.py) -- SubagentStart hook for context injection
- `.ai-state/memory.json` -- the persistent data store (created on first write; not committed)
