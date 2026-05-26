# Hook Crafting Skill

Skill for creating, registering, and debugging Claude Code hooks — deterministic lifecycle enforcement that doesn't depend on the LLM following instructions. Compatible with Claude Code.

## When to Use

- Creating a new hook (PreToolUse, PostToolUse, SessionStart, Stop, or any other event)
- Debugging why a hook is not firing or is producing unexpected output
- Fixing hook registration or double-firing issues
- Choosing between hook types (command, prompt, agent, http, mcp_tool)
- Understanding hook output patterns (additionalContext, decision, updatedInput)
- Integrating hooks into the Praxion installer (`hooks/hooks.json`)

## Activation

The skill activates automatically when Claude detects tasks related to:

- Writing or modifying hook scripts
- Debugging hook execution or registration
- Choosing hook events or output formats
- Questions about `hooks.json`, `settings.json` hook config, or installer integration

Trigger explicitly by referencing "hook-crafting" or asking about Claude Code hooks.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core: hook-vs-rule decision, gotchas, registration lifecycle, hook types, design patterns, event quick reference |
| `references/event-reference.md` | All hook events with input schemas, blocking semantics, and known bugs |
| `references/output-patterns.md` | JSON output formats: additionalContext, decision, permissionDecision, updatedInput |
| `references/registration-guide.md` | Where hooks live, auto-discovery model, configuration format |
| `references/testing-guide.md` | Manual testing, debugging, environment setup |

## Quick Start

```python
# Minimal PreToolUse hook (block Write to /etc)
import json, sys

data = json.loads(sys.stdin.read())
tool = data.get("tool_name", "")
tool_input = data.get("tool_input", {})

if tool == "Write" and tool_input.get("file_path", "").startswith("/etc"):
    print(json.dumps({"decision": "block", "reason": "Writes to /etc are not permitted"}))
    sys.exit(2)
# Exit 0 = allow
```

Register in `hooks/hooks.json`:

```json
{
  "hooks": {
    "PreToolUse": [{"type": "command", "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/guard.py"}]
  }
}
```

## Testing

```bash
# Pipe a sample event to test a hook script manually
echo '{"tool_name":"Write","tool_input":{"file_path":"/etc/test"}}' | python3 hooks/guard.py
```

See `references/testing-guide.md` for the full manual testing workflow.

## Related Skills

- [`rule-crafting`](../rule-crafting/SKILL.md) — when a rule (not a hook) is the right level of enforcement
- [`skill-crafting`](../skill-crafting/SKILL.md) — skill frontmatter `hooks:` field for lifecycle hooks scoped to a skill
- [`agent-crafting`](../agent-crafting/SKILL.md) — agent frontmatter `hooks:` field for hooks scoped to an agent
