---
name: hook-crafting
description: Creating, testing, and registering Claude Code hooks for automated
  code quality, observability, security gates, and workflow enforcement. Covers hook
  events, registration lifecycle, output patterns, gotchas from production use, and
  installer integration. Use when creating new hooks, debugging hook execution,
  fixing hook registration, choosing between hook types, or understanding why a hook
  is not firing.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
---

# Hook Crafting

Hooks are shell commands, prompts, or agents that Claude Code executes in response to lifecycle events (tool calls, session start, subagent spawn, etc.). They enable automated enforcement that doesn't depend on the LLM remembering to follow rules.

**Satellite files** (loaded on-demand):

- [references/event-reference.md](references/event-reference.md) -- All 24 hook events with input schemas and blocking semantics
- [references/output-patterns.md](references/output-patterns.md) -- JSON output formats: additionalContext, decision, permissionDecision, updatedInput
- [references/registration-guide.md](references/registration-guide.md) -- Where hooks live, how they get loaded, installer integration
- [references/testing-guide.md](references/testing-guide.md) -- Manual testing, debugging, environment setup

**Relationship to built-in skill**: Use `plugin-dev:hook-development` for writing hook scripts (prompt vs command types, security best practices, matcher patterns, bash validation examples). Use this skill for everything around the scripts: registration lifecycle, why hooks don't fire, output patterns (`additionalContext`, `updatedInput`, `decision`), the `if` conditional field, the 15 events the built-in skill doesn't document, known bugs, and installer integration. The built-in skill tells you how to write a hook; this skill tells you how to ship one.

## Gotchas

Hard-won lessons from production use. Read these before writing or debugging hooks.

- **Plugin hooks.json does NOT auto-fire.** Placing `hooks/hooks.json` inside `.claude-plugin/` installs the file into the plugin cache but Claude Code does not execute those hooks (tested v2.1.37, documented in `PLUGIN_SCHEMA_NOTES.md`). Workaround: register hooks in `~/.claude/settings.json` or `.claude/settings.json` with absolute paths. The `hooks.json` file serves as a reference manifest, not an activation mechanism.

- **Async hooks cannot deliver feedback.** A hook with `"async": true` runs in the background — its stdout JSON (including `additionalContext`) may not reach Claude before it moves on. Use sync for any hook that needs to provide feedback, inject context, or block a tool call.

- **Consume all stdin.** Every hook receives JSON on stdin. If the script doesn't read all of stdin, the pipe breaks and Claude Code logs an error. Pattern: `raw = sys.stdin.read()` at the top, even if you don't use the data.

- **Shell profile text corrupts JSON.** If `~/.zshrc` or `~/.bashrc` contains unconditional `echo` or `printf` statements, they inject text before the hook's JSON output. Guard startup text with `[[ $- == *i* ]]` (interactive shell check).

- **`if` field silently fails on non-tool events.** The `if` conditional (`"if": "Bash(git *)"`) only works on tool events (PreToolUse, PostToolUse, PostToolUseFailure, PermissionRequest). Adding `if` to other events (SessionStart, Stop, etc.) prevents the hook from running entirely with no error.

- **`stop_hook_active` prevents infinite loops.** A Stop hook that returns `decision: "block"` creates a self-correcting loop: Claude responds → Stop fires → blocks → Claude continues → Stop fires again. Check `stop_hook_active` in the input JSON — when true, this is the second attempt, and you must exit 0 to let Claude stop.

- **Exit code 2 has known bugs.** PreToolUse exit code 2 (block) can intermittently cause Claude to stop instead of acting on the error (#24327). It may also fail to block Task tool calls (#26923) and Write/Edit operations (#13744). For critical gates, verify the block actually worked.

- **hooks.json and settings.json drift.** The project maintains two hook configurations: `hooks.json` (declarative reference, uses `${CLAUDE_PLUGIN_ROOT}`) and `settings.json` (runtime-active, absolute paths). Adding a hook to one without updating the other is the most common registration bug. Always update both.

## Registration Lifecycle

Hooks can be defined in 6 locations. They are additive (merged, not overridden):

| Location | Scope | When to Use |
|----------|-------|-------------|
| `~/.claude/settings.json` | All projects | User-wide hooks (formatting, observability) |
| `.claude/settings.json` | This project | Project-specific hooks (committed to git) |
| `.claude/settings.local.json` | This project | Local-only hooks (gitignored) |
| Managed policy | Organization | Org-enforced hooks |
| Plugin `hooks/hooks.json` | Plugin enabled | **Reference only** — does not auto-fire |
| Skill/agent frontmatter | Component lifetime | Scoped to skill activation or agent spawn |

**For Praxion hooks**: Register in `~/.claude/settings.json` via the installer (`install_claude.sh`). Keep `hooks.json` as the declarative manifest. See [references/registration-guide.md](references/registration-guide.md) for the installer integration pattern.

## Hook Types

| Type | Async? | Feedback? | Use When |
|------|--------|-----------|----------|
| `command` | Yes/No | Yes (sync only) | Running scripts, formatters, linters |
| `prompt` | No | Yes | LLM-based validation (style checks, safety) |
| `agent` | No | Yes | Complex multi-step verification (up to 50 tool turns) |
| `http` | Yes/No | Yes (sync only) | Forwarding events to external services |

Prefer `command` for deterministic checks (formatting, linting). Use `prompt` when the check requires LLM judgment. Use `agent` when verification needs to read files or run commands.

## Design Patterns

### Fail-Open

Hooks must never block the agent due to their own bugs. Wrap the entire main function in try/except:

```python
if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # exit 0 — never block
```

### Auto-Fix Then Gate

For code quality hooks: fix what you can automatically, then only block on what's unfixable.

```
1. Run formatter in fix mode (ruff format)
2. Run linter in fix mode (ruff check --fix)
3. Re-stage fixed files (git add)
4. Run checks again — block only if violations remain
```

### Delegating Hook

Keep hook scripts thin — delegate to heavier packages:

```python
result = subprocess.run(
    ["uv", "run", "--project", package_path, "python", "-m", "module", "subcommand"],
    input=raw, capture_output=True, text=True, timeout=25,
)
sys.exit(result.returncode)
```

### Observability (Fire-and-Forget)

Async hooks that POST events to an HTTP API. Never fail, never block:

```python
try:
    urllib.request.urlopen(req, timeout=5)
except Exception:
    pass
```

### Self-Correcting Loop (Stop Hook)

Force Claude to continue working until a condition is met:

```python
data = json.loads(sys.stdin.read())
if data.get("stop_hook_active"):
    sys.exit(0)  # CRITICAL: prevent infinite loop
# ... check conditions ...
if not conditions_met:
    print(json.dumps({"decision": "block", "reason": "Tests not run"}))
    sys.exit(2)
```

## Quick Reference: Events

24 events, grouped by phase. See [references/event-reference.md](references/event-reference.md) for full schemas.

**Before tool execution** (can block): PreToolUse, PermissionRequest
**After tool execution** (cannot block): PostToolUse, PostToolUseFailure
**Session lifecycle**: SessionStart, Stop, StopFailure, PreCompact, PostCompact
**Subagent lifecycle**: SubagentStart, SubagentStop
**Task lifecycle** (can block): TaskCreated, TaskCompleted
**User interaction**: UserPromptSubmit, Notification, Elicitation, ElicitationResult
**Environment**: ConfigChange, CwdChanged, FileChanged, InstructionsLoaded
**Worktree**: WorktreeCreate, WorktreeRemove
**Team**: TeammateIdle

## Sync vs Async Decision

| Need | Use |
|------|-----|
| Block a tool call or commit | Sync (`"async": false`) |
| Inject context via `additionalContext` | Sync |
| Return `decision: "block"` | Sync |
| Fire-and-forget logging/observability | Async (`"async": true`) |
| Auto-format silently (no feedback) | Either — async avoids latency |

**Key rule**: If the hook's value depends on Claude seeing its output, it must be sync.
