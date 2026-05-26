# Hook Registration Guide

How hooks get from source files to active execution. Back to [SKILL.md](../SKILL.md).

## Contents

- [Auto-Discovery Model](#auto-discovery-model)
- [Configuration Format](#configuration-format)
- [Single Registration Authority](#single-registration-authority)
- [Plugin Cache Mechanics](#plugin-cache-mechanics)
- [Hook Configuration Fields](#hook-configuration-fields)
- [Merging Behavior](#merging-behavior)
- [Verifying Registration](#verifying-registration)
- [Checklist: Adding a New Hook](#checklist-adding-a-new-hook)

## Auto-Discovery Model

Plugin hooks placed at `<repo-root>/hooks/hooks.json` are auto-discovered by Claude Code when the plugin is installed. The `hooks.json` file is the single source of truth for plugin hooks — scripts referenced there execute automatically. Do NOT duplicate hooks into `~/.claude/settings.json`, as that causes double-firing and path portability issues.

## Configuration Format

### settings.json (user/project)

Events directly under the `hooks` key:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/hook.py",
            "timeout": 10,
            "async": true
          }
        ]
      }
    ]
  }
}
```

### hooks.json (plugin)

Wrapped in a `hooks` object, uses `${CLAUDE_PLUGIN_ROOT}`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/hook.py",
            "timeout": 10,
            "async": true
          }
        ]
      }
    ]
  }
}
```

**`${CLAUDE_PLUGIN_ROOT}`** resolves to the plugin's cache root (e.g., `~/.claude/plugins/cache/bit-agora/i-am/0.0.1/`), NOT to `.claude-plugin/`. Reference scripts as `${CLAUDE_PLUGIN_ROOT}/hooks/script.py`.

## Single Registration Authority

Praxion uses a single hook configuration:

- **`hooks/hooks.json`** at the repo root — uses `${CLAUDE_PLUGIN_ROOT}` paths. Auto-discovered by Claude Code.

**When adding a new hook:**
1. Add the script to `hooks/`
2. Register it in `hooks/hooks.json`

That's it. No installer step needed — Claude Code discovers `hooks.json` automatically.

## Plugin Cache Mechanics

When a plugin is installed, Claude Code copies the plugin directory into `~/.claude/plugins/cache/<publisher>/<name>/<version>/`. The `${CLAUDE_PLUGIN_ROOT}` variable resolves to this cache path at runtime. Hook scripts referenced from `hooks.json` execute from the cached copy, ensuring consistent paths across machines.

## Hook Configuration Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `type` | Yes | — | `command`, `prompt`, `agent`, or `http` |
| `command` | Yes (command) | — | Shell command to execute |
| `matcher` | No | `""` (all) | Tool name filter at the group level |
| `if` | No | — | Tool + argument filter (v2.1.85+, tool events only) |
| `timeout` | No | 600s (cmd), 30s (prompt), 60s (agent) | Max execution time in seconds |
| `async` | No | false | Run without blocking (command type only) |
| `once` | No | false | Run only on first matching event per session |
| `statusMessage` | No | — | Message shown in status bar while hook runs |

## Merging Behavior

Hooks from all sources are additive:
- User settings + project settings + plugin hooks all run
- Multiple hooks on the same event run in parallel
- Identical hook commands are deduplicated automatically
- No priority/override mechanism — all hooks fire

## Verifying Registration

```bash
# Check what hooks are registered at user level
grep -A5 "format_python\|check_code_quality" ~/.claude/settings.json

# In Claude Code session
/hooks  # Read-only browser showing all active hooks

# Debug mode — shows hook execution logs
claude --debug
```

## Checklist: Adding a New Hook

1. Write the hook script in `hooks/`
2. Test manually: `echo '{"tool_name":"Bash","tool_input":{"command":"git status"}}' | python3 hooks/hook.py`
3. Add to `hooks/hooks.json` with `${CLAUDE_PLUGIN_ROOT}` paths
4. Reinstall the plugin (so the cache updates)
5. Verify: start a Claude session — check `claude --debug` output if it doesn't fire
