# Plugin Configuration

Plugin infrastructure for the `i-am` Claude Code plugin. Contains the manifest, hooks, and schema documentation.

## Key Files

- `plugin.json` — Plugin manifest defining MCP servers, skills, commands, and agents
- `hooks/hooks.json` — Hook registration (event → script mappings)
- `hooks/*.py` — Hook implementation scripts (Python)
- `PLUGIN_SCHEMA_NOTES.md` — Schema documentation for plugin.json

## Registration Patterns

| Component | Registration in plugin.json | Discovery |
|---|---|---|
| Skills | Directory glob: `"./skills/"` | Automatic |
| Commands | Directory glob: `"./commands/"` | Automatic |
| Agents | Explicit file paths (no globs) | Manual — update array |
| MCP servers | Named entries with command + args | Manual |

## Hooks

Hooks are Python scripts triggered by Claude Code events (SessionStart, Stop, PreToolUse, PostToolUse, PreCompact). They use `${CLAUDE_PLUGIN_ROOT}` for portable paths. Hooks are deterministic enforcement — unlike CLAUDE.md which is advisory guidance.

**Single authority**: All hooks are registered in `hooks/hooks.json` and auto-loaded by Claude Code via the plugin system. Do NOT register hooks in `~/.claude/settings.json` — that causes double-firing and path portability issues. The installer (`install_claude.sh`) no longer writes hooks to settings.json.

Load the `hook-crafting` skill before creating or modifying hooks.

### Hook Exit Code Semantics

| Exit Code | Effect | Stdout | Stderr |
|-----------|--------|--------|--------|
| **0** | Allow the action | JSON `hookSpecificOutput` is processed (`additionalContext`, `permissionDecision`) | Shown to user in verbose mode |
| **2** | Block the action | **Ignored** — stdout JSON is NOT processed on exit 2 | Fed back to the agent as the error/block message |

**Events supporting exit 2 (blocking)**: PreToolUse, Stop, SubagentStop, PermissionRequest, UserPromptSubmit, TaskCreated, TaskCompleted, ConfigChange, Elicitation, ElicitationResult, WorktreeCreate, TeammateIdle.

**Events that do NOT support exit 2**: PostToolUse, PreCompact, SessionStart, SubagentStart, Notification, and others — these are informational only.

**Design rule**: Never mix approaches in one hook. A blocking hook uses exit 2 + stderr only. An injecting hook uses exit 0 + stdout JSON only.

**Known issue**: Stop hooks via plugins may display as "Stop hook error" instead of "Stop hook blocked" (#34600, open). PreToolUse exit 2 was fixed in v2.1.90.
