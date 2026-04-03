# Memory Skill

Persistent, structured memory system that tracks user preferences, assistant learnings, project conventions, and relationship dynamics across sessions. Stores data in `.ai-state/memory.json` as a categorized, queryable JSON document with progressive disclosure via Markdown-KV format.

Complements built-in memory (e.g. Claude Code's `MEMORY.md`) with explicit categories, tags, confidence levels, temporal supersession, and structured consolidation. Used via memory MCP in both Claude Code and Cursor.

## When to Use

- Starting a new session (memory context is auto-injected via hook -- no manual action needed)
- Storing user preferences, project conventions, or workflow discoveries via `remember()`
- Browsing the full memory index via `browse_index()`
- Searching across accumulated knowledge via `search()`
- Consolidating overlapping entries via `consolidate()`
- Reviewing memory health via `reflect()`

## Three-Layer Enforcement

Memory is automatically integrated into agent workflows:

1. **Hook injection**: `inject_memory.py` injects Markdown-KV summary into every agent's context at spawn
2. **Always-loaded rule**: `memory-protocol.md` guides when to call `remember()`
3. **Validation hook**: `validate_memory.py` warns when agents write LEARNINGS.md without calling `remember()`

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core reference: ontology, tool table, enforcement, integration, proactive guidelines |
| `references/schema.md` | Full JSON schema v1.3, field constraints, Markdown-KV format, consolidation actions |
| `README.md` | This file -- overview and usage guide |

## Data Model

Schema v1.3 with six categories. Key new fields: `summary` (one-line description), `valid_at`/`invalid_at` (temporal supersession).

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
| `remember` | Store entry with optional `summary` param. Auto-generates summary if omitted. |
| `search` | Multi-term ranked search. `detail="index"` (Markdown) or `detail="full"` (JSON). |
| `forget` | Soft-delete (sets `invalid_at`). Use `hard_delete` for permanent removal. |
| `consolidate` | Execute structured actions (merge, archive, adjust, update) with backup. |
| `reflect` | Lifecycle analysis: stale entries, archival candidates. Read-only. |

## Related Artifacts

- [`/memory` command](../../commands/memory.md) -- slash command that delegates to this skill
- [`memory-protocol.md`](../../rules/swe/memory-protocol.md) -- always-loaded rule for remember guidance
- [`inject_memory.py`](../../.claude-plugin/hooks/inject_memory.py) -- SubagentStart hook for context injection
- [`.ai-state/memory.json`](../../.ai-state/memory.json) -- the persistent data store
