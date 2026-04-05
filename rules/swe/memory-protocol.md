## Memory Protocol

This protocol applies only when the memory MCP server is available. If memory tools are not present in your context, skip all memory operations.

Memory context is injected automatically at agent start via hook. You do NOT need to call `session_start()` or `recall()` -- the data is already visible in your context as "Memory Context (auto-injected)". Injected context replaces `browse_index` for most use cases -- use `browse_index` only when you need the full index or `include_historical`.

### When to Remember

You MUST call `remember()` when you discover something that applies beyond the current task. The memory gate hook will block session completion if significant work was done without any `remember()` calls.

Call `remember()` for:

- A gotcha that future agents working in this area should know
- A pattern that worked well and should be reused
- A project convention or constraint not documented elsewhere
- A tool behavior, framework quirk, or API drift
- An architectural insight or trade-off rationale (alongside ADR creation)
- A user correction or preference expressed during the session
- A debugging insight that took effort to discover

**Examples of memories that should have been created:**

- After discovering that async hooks silently drop `additionalContext` at SubagentStop: `remember("learnings", "async-hooks-drop-context", "...", tags=["gotcha", "hooks"], importance=8, type="gotcha")`
- After a pipeline run reveals that worktree isolation prevents agent coordination issues: `remember("project", "worktree-isolation-pattern", "...", tags=["pattern", "pipeline"], importance=6, type="pattern")`
- After the user corrects an approach: `remember("learnings", "user-prefers-X", "...", tags=["preference", "correction"], importance=7, type="correction")`

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

You MUST evaluate whether you discovered anything that future agents should know. This is enforced by the memory gate hook -- sessions with significant work and zero `remember()` calls will be blocked from completing. If you genuinely have nothing to persist, that's fine -- the gate will let you through on the second attempt. But the default should be to remember, not to skip.
