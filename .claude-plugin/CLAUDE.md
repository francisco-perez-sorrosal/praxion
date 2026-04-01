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

Load the `hook-crafting` skill before creating or modifying hooks.
