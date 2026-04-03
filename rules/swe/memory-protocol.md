## Memory Protocol

Memory context is injected automatically at agent start via hook. You do NOT need to call `session_start()` or `recall()` — the data is already visible in your context as "Memory Context (auto-injected)".

### When to Remember

Call `remember()` when you discover something that applies beyond the current task:

- A gotcha that future agents working in this area should know
- A pattern that worked well and should be reused
- A project convention or constraint not documented elsewhere
- A tool behavior, framework quirk, or API drift
- An architectural insight or trade-off rationale (alongside ADR creation)

### When NOT to Remember

Do NOT call `remember()` for:

- Task-specific implementation details (they belong in LEARNINGS.md only)
- Information derivable from code, git history, or existing documentation
- Temporary workarounds that will be resolved in this task
- Content already captured in CLAUDE.md, rules, or skills

### How to Remember

```
remember(category, key, value, tags, importance, summary)
```

- **category**: `learnings` for gotchas/patterns, `project` for conventions/decisions
- **summary**: One-line description (~100 chars) — this is what agents see in the index
- **importance**: Gotchas and conventions: 7-8. Patterns: 5-6. Preferences: 3-4
- **tags**: 2-4 lowercase tags for discoverability

### After Completing Your Task

Before reporting completion, ask yourself: "Did I discover anything that future agents should know?" If yes, call `remember()`. If no, proceed.
