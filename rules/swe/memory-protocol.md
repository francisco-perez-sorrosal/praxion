---
codex:
  portability: claude_only
core: false
load: always_on
install: hook-deliver
---

## Memory Protocol

This protocol applies only when the memory MCP server is available and the project hasn't disabled it. Skip all memory operations — `remember()`, `recall()`, `search()`, `browse_index()`, any memory tool, even if callable — and offer no memory advice, when either holds:

- Memory tools are absent from your context (MCP server not loaded), or
- A SessionStart/SubagentStart notice sets `PRAXION_DISABLE_MEMORY_MCP=1` — the project has opted out of memory persistence.

Memory context is injected at agent start via hook (visible as "Memory Context (auto-injected)"), so don't call `session_start()` or `recall()`. It replaces `browse_index` for most uses — call `browse_index` only for the full index or `include_historical`.

### When to Remember

You MUST call `remember()` when you discover something that applies beyond the current task; the memory gate hook blocks session completion if significant work happened with zero `remember()` calls.

Call `remember()` for:

- A gotcha that future agents working in this area should know
- A pattern that worked well and should be reused
- A project convention or constraint not documented elsewhere
- A tool behavior, framework quirk, or API drift
- An architectural insight or trade-off rationale (alongside ADR creation)
- A user correction or preference expressed during the session
- A debugging insight that took effort to discover

The `remember()` signature is in `### How to Remember` below; treat each trigger above as warranting a call.

### When NOT to Remember

Do NOT call `remember()` for:

- Task-specific implementation details (they belong in LEARNINGS.md only)
- Information derivable from code, git history, or existing documentation
- Temporary workarounds that will be resolved in this task
- Content already captured in CLAUDE.md, rules, or skills

When in doubt, remember. A low-importance memory (3-4) is better than a lost insight. The memory system handles deduplication.

### How to Remember

```python
remember(category, key, value, tags, importance, summary, type)
```

- **category**: `learnings` for gotchas/patterns, `project` for conventions/decisions
- **key**: Kebab-case topic slug. Never include dates — `updated_at` tracks freshness. Use descriptive topics: `memory-gate-phase-aware-fix`, not `memory-gate-fix-2026-04-05`
- **summary**: One-line description (~100 chars) -- this is what agents see in the index
- **importance**: Gotchas and conventions: 7-8. Patterns: 5-6. Preferences: 3-4
- **tags**: 2-4 lowercase tags for discoverability
- **type**: When the knowledge kind is clear, set `type` to one of: `decision`, `gotcha`, `pattern`, `convention`, `preference`, `correction`, `insight`

### Tag Vocabulary

Use these standard tags for consistent discoverability:

- `decision` -- architectural or implementation decision
- `gotcha` -- non-obvious failure point
- `pattern` -- reusable approach
- `convention` -- project standard
- `api-drift` -- external API version change
- `bugfix` -- bug diagnosis and solution
- `preference` -- user preference
- `correction` -- user-corrected behavior

### Conflict Resolution

Two memory systems coexist: Claude Code's auto-memory (`~/.claude/.../memory/`) and Praxion's memory-mcp (`.ai-state/memory.json`). When they conflict:

- **Praxion memory wins** -- it has timestamps (`created_at`, `updated_at`) and is the actively curated project store. Claude Code's auto-memory has no per-entry timestamps.
- **More recent wins** -- check `updated_at` on the Praxion entry. The most recently updated fact is the current truth.
- **If still ambiguous** -- verify against the code or git history. Memory is a hint, not truth.

### Before Completing Your Task

Before finishing, evaluate whether you discovered anything future agents should know — the memory gate hook blocks sessions with significant work and zero `remember()` calls. If you genuinely have nothing to persist, the gate lets you through on the second attempt; but the default is to remember, not skip.
