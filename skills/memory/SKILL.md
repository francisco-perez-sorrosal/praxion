---
name: memory
description: >
  MCP-backed persistent memory across sessions: user preferences, assistant
  learnings, project conventions, relationship dynamics. Triggers: remembering
  user preferences, storing project decisions, recalling past interactions,
  managing assistant self-knowledge, loading context at session start;
  cross-session memory, persistent context.
compatibility: Claude Code
---

# Persistent Memory

MCP-backed memory that persists across sessions. The `memory` MCP server handles all storage operations -- this skill defines **when** and **why** to use each tool, not how to manipulate JSON.

**Satellite files** (loaded on-demand):
- [references/schema.md](references/schema.md) -- full JSON schema, category definitions, field constraints

## Three-Layer Enforcement

Memory context is delivered to agents through three complementary mechanisms:

1. **Hook injection (Layer 1)**: The `inject_memory.py` SubagentStart hook reads `.ai-state/memory.json` (with LOCK_SH for concurrent safety) and injects a Markdown-KV summary into every agent's context. Uses importance tiers, agent-type-aware category routing, and a MAX_INJECT_CHARS budget.

2. **Always-loaded rule (Layer 2)**: The `memory-protocol.md` rule provides clear criteria for when to call `remember()` vs. when to skip, including type guidance. Loaded for every agent session.

3. **Validation hook (Layer 3)**: The `validate_memory.py` SubagentStop hook checks whether agents that wrote to LEARNINGS.md also called `remember()`. Warns the parent agent on omission.

4. **Capture hooks**: `capture_memory.py` (PostToolUse) and `capture_session.py` (lifecycle events) write automatic JSONL observations to `.ai-state/observations.jsonl`. `promote_learnings.py` (PreToolUse) warns before LEARNINGS.md cleanup when unpromoted entries exist.

**Implication**: You do NOT need to call `session_start()` or `recall()` to see memory data. It is already in your context. Focus on `remember()` for writing discoveries. Tool and lifecycle events are captured automatically to the observation layer.

## Gotchas

- **Never store secrets, API keys, or tokens in memory.** The memory store is a plain JSON file committed to `.ai-state/` -- visible in version control.
- **Memory categories are not tags** -- each memory belongs to exactly one category.
- **Do not duplicate CLAUDE.md or rule content into memory.** Creates drift when the source is updated but memory is not.
- **`forget()` soft-deletes** -- entry remains with `invalid_at` set and `status=superseded`. Use `hard_delete()` for permanent removal.

## Ontology

Six memory categories, each targeting a distinct knowledge domain:

| Category | Purpose | Examples |
|----------|---------|----------|
| `user` | Personal info, preferences, workflow habits | Name, email, preferred tools, response style |
| `assistant` | Self-identity, patterns, effective approaches | Name, "User prefers concise answers" |
| `project` | Project conventions, architecture decisions, tech stack | "Uses plugin system", "Skills use progressive disclosure" |
| `relationships` | Interaction dynamics, delegation style, collaboration | "Prefers proactive agents", "Values pragmatism" |
| `tools` | Tool preferences, environment setup, configurations | "Uses gh CLI", "Prefers pbcopy for clipboard" |
| `learnings` | Cross-session insights, gotchas, patterns | "Hooks can't live in ~/.claude/hooks/" |

## Available Tools

| Tool | Description |
|------|-------------|
| `remember` | Store or update. Checks for duplicates first. Use `force=True` to bypass. Optional `summary`, `type` (knowledge classification), and `created_by` (provenance) params. |
| `forget` | **Soft-delete**: sets `invalid_at` and status to `superseded`. Entry remains in historical queries. |
| `hard_delete` | Permanent removal with link cleanup and backup. |
| `search` | Multi-term ranked search. `detail="index"` (Markdown summaries, default) or `detail="full"` (complete entries). `include_historical=True` to include soft-deleted. `since` filters by creation time. `type` filters by knowledge type. |
| `browse_index` | Full Markdown-KV summary of all entries grouped by category. Most token-efficient overview. |
| `consolidate` | Execute structured actions (merge, archive, adjust_confidence, update_summary) atomically with backup. JSON actions param. |
| `recall` | Retrieve entries from a category with access tracking. |
| `session_start` | Increment session counter, return summary. Not needed for agents (hook handles this). |
| `reflect` | Lifecycle analysis: stale entries, archival candidates, confidence adjustments. Read-only. |
| `about_me` / `about_us` | Aggregated user or relationship profiles. |
| `connections` | Show outgoing and incoming links for an entry. |
| `add_link` / `remove_link` | Manage unidirectional links between entries. |
| `timeline` | Chronological observation history as compact Markdown. Filter by `since`, `until`, `session_id`, `tool_filter`, `classification`, `limit`. |
| `session_narrative` | Structured session summary: what was done, files touched, decisions made, outcome. Uses most recent session if `session_id` omitted. |

### Key Parameters on `remember`

- **`summary`** (str, optional): One-line description (~100 chars). Auto-generated from value if omitted.
- **`importance`** (int, 1-10, default 5): Priority. Gotchas/conventions: 7-8. Patterns: 5-6. Preferences: 3-4.
- **`source_type`** (str, default "session"): `"session"`, `"user-stated"`, `"inferred"`, or `"codebase"`.
- **`confidence`** (float, 0.0-1.0, optional): For assistant self-knowledge; null for factual entries.
- **`tags`**: 2-4 lowercase tags for discoverability.
- **`type`** (str, optional): Knowledge classification -- `"decision"`, `"gotcha"`, `"pattern"`, `"convention"`, `"preference"`, `"correction"`, or `"insight"`.
- **`created_by`** (str, optional): Identifier for the agent or user that created the entry.

See [references/schema.md](references/schema.md) for full field definitions and constraints.

## Observation Layer

The observation layer captures tool and lifecycle events automatically in `.ai-state/observations.jsonl` (JSONL, one event per line). No LLM calls are involved in capture.

- **`capture_memory.py`** (PostToolUse): records tool events with file paths, outcome, and classification. Noisy tools (Read, Glob, Grep, etc.) are blocklisted.
- **`capture_session.py`** (SessionStart, Stop, SubagentStart, SubagentStop): records lifecycle events with session and agent IDs.

Query the observation layer via two MCP tools:

- **`timeline()`**: chronological event history grouped by date, filterable by date range, session, tool, or classification
- **`session_narrative()`**: structured summary of a session -- what was done, files touched, decisions made, outcome

Observations are separate from curated memories. They accumulate without deduplication. The `ObservationStore` handles rotation when the file exceeds 10 MiB.

## Integration with Agent Pipeline

### LEARNINGS.md Bridge

LEARNINGS.md captures valuable insights during pipeline execution. At pipeline end:
- Agents should call `remember()` for discoveries that apply beyond the current task
- The dream agent or skill-genesis can harvest LEARNINGS.md entries into permanent memory
- The `validate_memory.py` hook warns when LEARNINGS.md was written without `remember()` calls

### What to Remember vs. What Stays in LEARNINGS.md Only

| Promote to Memory | Keep in LEARNINGS.md Only |
|-------------------|--------------------------|
| Gotchas that apply beyond this task | Task-specific implementation details |
| Reusable patterns | Temporary workarounds resolved in this task |
| Project conventions not documented elsewhere | Info derivable from code or git history |
| Framework quirks or API drift | Content already in CLAUDE.md or rules |

## Proactive Memory Guidelines

Store memories when you observe:

- **User corrects a preference**: "Actually, I prefer X over Y" --> remember it
- **Repeated patterns**: User consistently uses a tool or workflow --> remember the pattern
- **Explicit requests**: "Remember that I always..." --> remember immediately
- **Project discoveries**: Architecture decisions, naming conventions --> store as project knowledge
- **Debugging insights**: Framework quirks, environment issues --> store as learnings
- **Collaboration feedback**: "That was helpful" or "Don't do that" --> update relationship dynamics

Do NOT store:
- Transient task details
- Information already in CLAUDE.md or rules
- Speculative conclusions from a single interaction
- Sensitive credentials

## Constraints

- Never store secrets, credentials, API keys, or tokens
- Validate category names -- reject unknown categories
- Confidence values: 0.0 to 1.0, or null
- Importance values: clamped to 1-10
