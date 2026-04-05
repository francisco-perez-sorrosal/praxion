# Memory Architecture

Praxion's memory system gives every agent persistent, cross-session knowledge about the project -- user preferences, architectural decisions, discovered patterns, gotchas, and a chronological record of what happened. It operates as a dual-layer store with automatic enforcement, designed to work as an optional context-enhancer that never blocks the agent pipeline.

## Architecture

```
                        Memory v2.0
  ┌─────────────────────────────────────────────────────┐
  │                                                     │
  │  Layer A: Curated Memories                          │
  │  .ai-state/memory.json                              │
  │  ─────────────────────────                          │
  │  High-signal institutional knowledge.               │
  │  Agents call remember() to store.                   │
  │  Scored, linked, consolidated, soft-deleted.         │
  │  Answers: "What do we know?"                        │
  │                                                     │
  ├─────────────────────────────────────────────────────┤
  │                                                     │
  │  Layer B: Observation Log                           │
  │  .ai-state/observations.jsonl                       │
  │  ────────────────────────────                       │
  │  Append-only event log from tool hooks.             │
  │  Automatic capture, zero LLM cost.                  │
  │  Immutable once written.                            │
  │  Answers: "What happened?"                          │
  │                                                     │
  ├─────────────────────────────────────────────────────┤
  │                                                     │
  │  Enforcement Layer                                  │
  │  ─────────────────                                  │
  │  inject_memory.py    → injects context at start     │
  │                        (SessionStart + SubagentStart)│
  │  memory_gate.py      → blocks Stop without remember │
  │  validate_memory.py  → blocks SubagentStop same way │
  │  remind_memory.py    → warns at commit time         │
  │  capture_memory.py   → captures tool events         │
  │  capture_session.py  → captures lifecycle events    │
  │  promote_learnings.py → warns before cleanup        │
  │  memory-protocol.md  → always-loaded rule           │
  │                                                     │
  └─────────────────────────────────────────────────────┘
```

### Why Two Layers

Memory systems face a fundamental tension: **curated memories are high-signal but sparse** (agents forget to call `remember()`), while **automatic observations are comprehensive but noisy** (every tool call captured). The solution is both layers with clear separation:

- **Curated layer** stores facts, decisions, gotchas, and patterns that agents explicitly chose to persist. These entries have importance scores, types, links, and lifecycle management. They are the project's institutional knowledge.
- **Observation layer** records what happened — which files were written, which tests ran, which decisions were made — without any manual action. Pattern-based extraction classifies events at zero LLM cost. The chronological log enables timeline queries and session narratives.

### Storage Format

**JSON for storage, Markdown for presentation.** The LLM never reads raw JSON. Every LLM-facing path goes through a formatting layer that produces Markdown-KV:

| Consumer | Reads | Format It Sees |
|----------|-------|---------------|
| LLM agents | MCP tools, inject hook | Markdown-KV summaries |
| MCP server | memory.json directly | Structured JSON (parsed, validated) |
| Hooks | memory.json, observations.jsonl | Structured JSON (filtered, formatted) |
| Dream agent | browse_index() → consolidate(actions) | Markdown in, structured actions out |
| Humans | Files in editor, git diff | JSON (2-space indent), JSONL (one line per event) |

This gives programs structured, queryable data while the LLM gets readable Markdown. The dream agent reads summaries via `browse_index()` and writes structured actions via `consolidate()` — actions are validated before execution, preventing schema corruption.

## Data Model

### Curated Entries (memory.json)

Schema v2.0 with 6 categories: `user`, `assistant`, `project`, `relationships`, `tools`, `learnings`.

Each entry has:

| Field | Purpose |
|-------|---------|
| `value` | The memory content |
| `summary` | One-line description (~100 chars) for index browsing |
| `type` | Knowledge kind: decision, gotcha, pattern, convention, preference, correction, insight |
| `importance` | 1-10 priority (drives injection filtering) |
| `created_by` | Agent type or "user" that created the entry |
| `source` | Full provenance: type, detail, agent_type, agent_id, session_id |
| `valid_at` / `invalid_at` | Temporal supersession (soft delete) |
| `tags` | 2-4 lowercase tags for discoverability |
| `links` | Unidirectional relations: supersedes, elaborates, contradicts, related-to, depends-on |
| `access_count` / `last_accessed` | Usage tracking for lifecycle analysis |

### Observations (observations.jsonl)

Append-only JSONL, one line per event. Each observation has:

| Field | Purpose |
|-------|---------|
| `timestamp` | ISO 8601 UTC |
| `session_id` | Originating session |
| `agent_type` / `agent_id` | Which agent produced this event |
| `project` | Project identifier (from cwd) |
| `event_type` | `tool_use`, `session_start`, `session_stop`, `agent_start`, `agent_stop` |
| `tool_name` | Which tool was called (for tool_use events) |
| `file_paths` | Files involved |
| `outcome` | `success` or `failure` |
| `classification` | `implementation`, `test`, `decision`, `commit`, `documentation`, `configuration`, `command` |

Observations are **immutable** — once written, never modified or deleted. The observation log is the ground truth of what happened. Rotation at a configurable threshold (default 10MB) keeps the active file bounded.

## MCP Tools

18 tools registered on the Memory MCP server:

### Curated Layer Tools

| Tool | Description |
|------|-------------|
| `remember` | Store or update with dedup check. Params: `summary`, `type`, `created_by`, `importance`. |
| `search` | Multi-term ranked search. `detail="index"` (Markdown summaries) or `"full"`. Filters: `since`, `type`, `include_historical`. |
| `browse_index` | Full Markdown-KV summary of all active entries, grouped by category. |
| `forget` | Soft-delete: sets `invalid_at`, status becomes `superseded`. |
| `hard_delete` | Permanent removal with link cleanup. |
| `consolidate` | Execute structured actions (merge, archive, adjust_confidence, update_summary) atomically. |
| `recall` | Retrieve entries with access tracking. |
| `reflect` | Read-only lifecycle analysis: stale entries, archival candidates, confidence adjustments. |
| `session_start` | Increment session counter, return summary. |
| `status` | Category counts, total entries, schema version, file size. |
| `about_me` / `about_us` | Aggregated user or relationship profiles. |
| `export_memories` | Full export as Markdown or JSON. |
| `connections` / `add_link` / `remove_link` | Link management. |

### Observation Layer Tools

| Tool | Description |
|------|-------------|
| `timeline` | Chronological Markdown of observations. Filter by date range, session, tool, classification. |
| `session_narrative` | Structured session summary: what was done, files touched, decisions made, outcome. |

## Enforcement: How Agents Use Memory

Memory integration relies on three complementary mechanisms — not on agents "remembering" to call tools.

### Layer 1: Context Injection (inject_memory.py)

A **synchronous** hook registered at both **SessionStart** and **SubagentStart** that reads `memory.json` (with LOCK_SH for concurrency safety), formats active entries as Markdown-KV, and injects them into the agent's context via `additionalContext`. Every agent — including the main agent — sees memory data automatically from the first turn without calling any tool. The hook detects the event type from the payload and sets `hookEventName` accordingly.

**Scaling strategy** for large stores:

| Entry Count | Behavior |
|-------------|----------|
| < 50 | All entries injected |
| 50-200 | Importance >= 7 always; 4-6 if budget allows; 1-3 search-only |
| 200+ | Same tiers + BM25 pre-filter (deferred) |

**Agent-type-aware routing**: Different agents see different category priorities. An implementer sees `learnings` first (gotchas to avoid); an architect sees `project` first (prior decisions).

### Layer 2: Protocol Rule (memory-protocol.md)

An always-loaded rule that guides agents on when to call `remember()`:

- **Remember**: Cross-task gotchas, reusable patterns, project conventions, framework quirks
- **Don't remember**: Task-specific details, info derivable from code/git, temporary workarounds
- Includes a standard tag vocabulary for consistent discoverability

### Layer 3: Enforcement Gates

Three hooks form a chain of enforcement checkpoints:

- **memory_gate.py** (Stop, sync): Blocks session end if the main agent did significant work without calling `remember()`. Scans the transcript for edit/search/delegation patterns. Passes through on retry to prevent infinite loops.
- **validate_memory.py** (SubagentStop, sync): Same logic for subagents. Exempt agents (sentinel, Explore, doc-engineer, Plan) pass through automatically.
- **remind_memory.py** (PreToolUse/Bash, sync, commit-gated): Non-blocking warning at commit time if significant work was done without `remember()`. Closes the gap between SubagentStop and Stop — the commit is a natural "done with work phase" checkpoint.

### Layer 4: Automatic Capture

- **capture_memory.py** (PostToolUse, async): Extracts structured observations from tool events using pattern matching. Classifies by tool name and file paths. Blocklist excludes low-value tools (Read, Glob, Grep).
- **capture_session.py** (lifecycle, async): Captures session start/stop and agent start/stop events for timeline continuity.
- **promote_learnings.py** (PreToolUse, sync): Warns before `.ai-work/` cleanup when LEARNINGS.md files have unpromoted content.

## Agent Integration

Every agent in the pipeline benefits from memory at different points:

```
Session/Agent Start
  ↓
  inject_memory.py fires → agent receives curated Markdown-KV context
  ↓                        (SessionStart for main agent, SubagentStart for subagents)
Agent executes its primary task
  ↓
  capture_memory.py fires on each tool call → observations accumulate
  ↓
Agent discovers a cross-session insight
  ↓
  Agent calls remember() → curated entry stored with provenance
  ↓
Agent commits work
  ↓
  remind_memory.py fires → warns if remember() not called (main agent, commit-gated)
  ↓
Agent completes
  ↓
  memory_gate.py / validate_memory.py fires → blocks if significant work without remember()
  ↓
  capture_session.py fires → agent_stop event recorded
```

At pipeline end, the `promote_learnings.py` hook warns before cleanup if LEARNINGS.md has unpromoted entries.

### What Different Agents Remember

| Agent | Typical Memories | Category |
|-------|-----------------|----------|
| Researcher | API constraints, resolved uncertainties | `learnings` |
| Systems-Architect | Trade-off decisions, architectural constraints | `project` |
| Implementer | Framework quirks, API drift, reusable patterns | `learnings` |
| Test-Engineer | Testing patterns, framework behaviors | `learnings` |
| Verifier | Recurring quality patterns | `learnings` |
| Sentinel | Ecosystem health trends | `project` |

## Concurrency Model

### Curated Layer

- **Writes** (remember, forget, consolidate): LOCK_EX on `memory.lock` → read → mutate → temp file → `os.replace()` atomic swap → release
- **Hook reads** (inject_memory.py): LOCK_SH on `memory.lock` → read → release. Shared lock allows concurrent readers but blocks during exclusive writes.

### Observation Layer

- **Writes** (capture_memory.py, capture_session.py): LOCK_EX on `observations.lock` → append single JSONL line → flush → release. Each append holds the lock for <1ms.
- **Reads** (timeline, session_narrative): No locking. JSONL readers tolerate a partial last line (skip it). Append-only guarantees completed lines are never modified.

## Temporal Consistency

Default queries return only active knowledge. Superseded entries never leak into agent context unless explicitly requested.

| Query Path | Behavior |
|------------|----------|
| `search()`, `browse_index()` | Excludes entries with `invalid_at` set, unless `include_historical=True` |
| `inject_memory.py` hook | Always excludes superseded entries (no historical flag) |
| `timeline()`, `session_narrative()` | Shows all observations (immutable, no soft-delete on observations) |

## Graceful Degradation

Memory is an **optional context-enhancer**. Praxion works without it.

- Missing `memory.json` → hooks silently do nothing, MCP tools return empty results
- Missing `observations.jsonl` → capture hooks create it on first write, query tools return empty
- Unregistered memory MCP → agents don't have memory tools, no errors
- Missing `.ai-state/` → hooks check for existence, auto-create on first write
- All hooks exit 0 unconditionally — a broken memory system never blocks an agent

## Project Isolation

Memory is **per-project**. Praxion is installed once globally; memory data lives in each project's `.ai-state/` directory.

- MCP server: `MEMORY_FILE=.ai-state/memory.json` (relative to cwd)
- Observation JSONL: `.ai-state/observations.jsonl` (relative to cwd)
- All hooks resolve paths from `cwd` in the hook payload — never hardcoded
- Lock files: `.ai-state/memory.lock`, `.ai-state/observations.lock` (gitignored)
- Cross-project memory is out of scope — each project has its own independent store

## Segregation Boundary

The memory system is designed for future extraction as a standalone project.

**Extractable unit:**

- `memory-mcp/` — self-contained Python package with own `pyproject.toml`, source, and tests
- Five hooks in `.claude-plugin/hooks/` (`inject_memory.py`, `validate_memory.py`, `capture_memory.py`, `capture_session.py`, `promote_learnings.py`)
- `skills/memory/` — memory skill documentation

**Integration seam** (stays with Praxion):

- `plugin.json` MCP server registration
- `hooks.json` event wiring
- `rules/swe/memory-protocol.md` (Praxion-specific protocol guidance)

**Design constraints:**

- Memory hooks import nothing from other Praxion hooks
- Memory hooks import nothing from the `memory_mcp` package (they read JSON directly)
- The memory skill does not depend on other Praxion skills
- `memory-mcp/` maintains its own independent `pyproject.toml`

## Comparison with Other Systems

| Capability | Praxion Memory v2.0 | claude-mem | Claude Code Native | Mem0 | Graphiti |
|-----------|-------------------|-----------|-------------------|------|---------|
| **Data model** | Typed JSON entries + JSONL observations | SQLite observations | Markdown files | Vector embeddings | Temporal property graph |
| **Storage** | JSON + JSONL (git-committed) | SQLite + ChromaDB (local) | Markdown (machine-local) | Qdrant + SQLite | Neo4j / KuzuDB |
| **Capture** | Automatic via hooks (zero LLM cost) + manual remember() | Automatic via hooks (LLM call per event) | Manual by Claude during session | Automatic LLM extraction | Automatic entity extraction |
| **Search** | Multi-signal keyword + LLM reads Markdown index | ChromaDB vector + FTS5 | LLM reads MEMORY.md directly | Vector similarity | Hybrid (BM25 + vector + graph) |
| **Progressive disclosure** | 3 layers: inject → browse_index → recall | 3 layers: index → timeline → full | 2 layers: MEMORY.md → topic files | Single layer | Single layer |
| **Consolidation** | Structured actions (merge, archive, adjust) + dream agent | None (manual SQL cleanup) | AutoDream 4-phase background | Auto-consolidate (similarity > 0.85) | Async enrichment pipeline |
| **Importance scoring** | 1-10 scale, drives injection filtering | None (recency only) | None | None | None |
| **Temporal awareness** | Soft delete (valid_at/invalid_at) + timeline | Timestamps only | File modification timestamps | Created/updated timestamps | Bitemporal (event + ingestion time) |
| **Multi-agent support** | Full: hook injection for all agents, type-aware routing | None (single agent) | None (single agent) | None | group_id tenant isolation |
| **Dependencies** | Python stdlib + MCP | SQLite + ChromaDB + Bun + Node.js | None (file-based) | Qdrant + optional Neo4j | Neo4j / KuzuDB |
| **Git-committed** | Yes | No | No (machine-local) | No | No |
| **Reliability** | 329 tests, atomic writes, graceful degradation | 115 GitHub issues, 72% summary failure rate | Mature (built into Claude) | Beta MCP integration | Active development |
| **Cost per event** | Zero (pattern extraction) | LLM API call per tool use | Zero | LLM API call per interaction | LLM API call per episode |
