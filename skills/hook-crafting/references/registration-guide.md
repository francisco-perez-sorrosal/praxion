# Hook Registration Guide

How hooks get from source files to active execution, including installer integration.

## The Registration Problem

Claude Code hooks must be registered in a settings file to execute. The most common bug is writing a hook script, adding it to `hooks.json`, and assuming it will fire. It won't — `hooks.json` is a reference manifest, not an activation mechanism.

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
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/.claude-plugin/hooks/hook.py",
            "timeout": 10,
            "async": true
          }
        ]
      }
    ]
  }
}
```

**`${CLAUDE_PLUGIN_ROOT}`** resolves to the plugin's cache root (e.g., `~/.claude/plugins/cache/bit-agora/i-am/0.0.1/`), NOT to `.claude-plugin/`. Reference scripts as `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/hooks/script.py`.

## The Dual-Registration Pattern

Praxion maintains two hook configurations that must stay in sync:

1. **`hooks.json`** — declarative manifest with `${CLAUDE_PLUGIN_ROOT}` paths. Documents what hooks are available. Does NOT auto-fire.
2. **`~/.claude/settings.json`** — runtime-active hooks with absolute paths. Written by the installer. This is what actually executes.

**When adding a new hook:**
1. Add the script to `.claude-plugin/hooks/`
2. Register it in `hooks.json` (reference)
3. Update the installer to register it in `settings.json` (activation)

Missing step 3 is why hooks silently fail to fire.

## Installer Integration

The Praxion installer (`install_claude.sh`) uses an inline Python script to write hooks into `~/.claude/settings.json`:

```python
def hook(script, matcher="", timeout=10, is_async=True):
    return {
        "matcher": matcher,
        "hooks": [{
            "type": "command",
            "command": f"python3 {hooks_dir}/{script}",
            "timeout": timeout,
            "async": is_async,
        }],
    }

settings["hooks"] = {
    "SubagentStart": [hook("send_event.py")],
    "SubagentStop": [hook("send_event.py")],
    "PostToolUse": [
        hook("send_event.py", "Write|Edit"),
        hook("format_python.py", "Write|Edit"),
    ],
    "PreToolUse": [{
        "matcher": "Bash",
        "hooks": [{
            "type": "command",
            "command": f"python3 {hooks_dir}/check_code_quality.py",
            "timeout": 30,
            "async": False,
        }],
    }],
}
```

**Key patterns:**
- Uses absolute paths (`{hooks_dir}/script.py`), not `${CLAUDE_PLUGIN_ROOT}`
- Overwrites the entire `hooks` section — existing hooks are replaced
- Async for observability hooks, sync for quality gates

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

1. Write the hook script in `.claude-plugin/hooks/`
2. Test manually: `echo '{"tool_name":"Bash","tool_input":{"command":"git status"}}' | python3 hook.py`
3. Add to `hooks.json` (reference, with `${CLAUDE_PLUGIN_ROOT}` paths)
4. Add to installer's `prompt_hooks_install()` (activation, with absolute paths)
5. Run `./install.sh code` and choose Install hooks
6. Verify: `grep hook_name ~/.claude/settings.json`
7. Test in a Claude session — check `claude --debug` output if it doesn't fire
