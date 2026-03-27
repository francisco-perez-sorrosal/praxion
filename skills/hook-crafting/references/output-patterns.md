# Hook Output Patterns

JSON output formats for hook scripts. Output goes to stdout (exit 0) or stderr (exit 2).

## additionalContext

Injects text into Claude's conversation context. The most useful feedback mechanism for PostToolUse hooks.

```json
{"additionalContext": "[hook-name] ruff formatted foo.py (12 lines changed)"}
```

**Supported events**: PostToolUse, PostToolUseFailure, SessionStart, UserPromptSubmit, SubagentStart, Notification, PreToolUse (exit 0 only).

**Requirements**:
- Hook must exit 0 (JSON is not parsed for exit 2)
- Hook must be sync (`"async": false`) — async hooks may not deliver context before Claude moves on
- Output must be valid JSON on stdout

**Structured form** (official docs):
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "Text for Claude"
  }
}
```

**Simplified form** (works in practice):
```json
{"additionalContext": "Text for Claude"}
```

## decision: "block"

Forces Claude to reconsider or continue working. Used in Stop and SubagentStop hooks.

```json
{"decision": "block", "reason": "Tests have not been run yet"}
```

**Requirements**:
- Hook must exit 2 (not 0) for the block to take effect on PreToolUse
- For Stop hooks: output to stderr, exit 2
- Always check `stop_hook_active` to prevent infinite loops

**PreToolUse blocking** (exit 2 + stderr):
```python
print("Quality gate failed: unformatted code", file=sys.stderr)
sys.exit(2)
```

Claude receives the stderr text as error context and acts on it.

## updatedInput

Modifies tool arguments before execution. PreToolUse only.

```json
{
  "updatedInput": {
    "command": "git commit --no-gpg-sign -m 'message'"
  }
}
```

**Use cases**:
- Add `--dry-run` flags to destructive commands
- Redact secrets from commands before logging
- Inject environment variables

**Requirements**: Exit 0. The modified input replaces the original tool call arguments.

## permissionDecision

Auto-approve or deny permission requests. PermissionRequest only.

```json
{
  "decision": {
    "behavior": "allow"
  }
}
```

With session-wide permission update:
```json
{
  "decision": {
    "behavior": "allow",
    "updatedPermissions": [
      {"tool": "Bash(npm *)", "permission": "allow"}
    ]
  }
}
```

**Known issue**: `"behavior": "deny"` may be ignored for Edit tool (#37210).

## Combining Output Fields

Multiple fields can be returned in a single JSON object:

```json
{
  "additionalContext": "Added --dry-run flag for safety",
  "updatedInput": {
    "command": "terraform apply --dry-run"
  }
}
```

## Error Output (exit 2)

When a hook exits 2, stdout JSON is ignored. Only stderr reaches Claude:

```python
# For PreToolUse gates:
print("Blocked: dangerous command detected", file=sys.stderr)
sys.exit(2)

# For Stop gates:
print(json.dumps({"decision": "block", "reason": "Checklist incomplete"}), file=sys.stderr)
sys.exit(2)
```

## Python Template

```python
#!/usr/bin/env python3
"""Hook template with output patterns."""
import json
import sys

def main():
    raw = sys.stdin.read()  # Always consume all stdin
    data = json.loads(raw)

    # ... hook logic ...

    # Provide feedback (sync hooks only)
    print(json.dumps({"additionalContext": "[my-hook] result message"}))

    # Or block (PreToolUse/Stop only)
    # print("Blocked: reason", file=sys.stderr)
    # sys.exit(2)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # fail-open
```
