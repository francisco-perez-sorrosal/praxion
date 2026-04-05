# Hook Exit Code Semantics

How Claude Code interprets hook exit codes, what each code means, and which events support blocking.

## Exit Codes

| Code | Meaning | Stdout | Stderr | Use For |
|------|---------|--------|--------|---------|
| **0** | Allow / pass | JSON `hookSpecificOutput` is processed | Shown in verbose mode | Injection, permission decisions, non-blocking info |
| **2** | Block / deny | **Ignored** completely | Fed back to agent as error message | Enforcement gates (memory, code quality, permissions) |
| **1** | Hook error | Ignored | Shown as error | Never use intentionally — indicates a bug |

**Critical rule**: On exit 2, stdout is discarded. A hook that needs to both block AND inject context cannot do both. Choose one approach per hook.

## Event Support Matrix

### Events that support exit 2 (blocking)

| Event | Exit 2 Effect |
|-------|---------------|
| `PreToolUse` | Blocks the tool call — agent must adjust |
| `Stop` | Prevents session end — agent continues |
| `SubagentStop` | Prevents subagent completion |
| `PermissionRequest` | Denies the permission |
| `UserPromptSubmit` | Blocks prompt processing, erases prompt |
| `TaskCreated` | Rolls back task creation |
| `TaskCompleted` | Prevents task completion marking |
| `ConfigChange` | Blocks config change (except `policy_settings`) |
| `Elicitation` | Denies the elicitation |
| `ElicitationResult` | Blocks the response |
| `WorktreeCreate` | Fails worktree creation |
| `TeammateIdle` | Prevents teammate from going idle |

### Events that do NOT support exit 2

| Event | Exit 2 Behavior |
|-------|-----------------|
| `PostToolUse` | Shows stderr as error but does NOT undo the tool call |
| `PostToolUseFailure` | Same — informational only |
| `PreCompact` | Cannot prevent compaction |
| `SessionStart` | Cannot prevent session start |
| `SubagentStart` | Cannot prevent subagent spawn |
| `Notification` | Informational only |
| `SessionEnd` | Informational only |
| `PermissionDenied` | Post-fact notification |
| `CwdChanged` | Informational only |
| `FileChanged` | Informational only |
| `PostCompact` | Informational only |
| `WorktreeRemove` | Informational only |
| `InstructionsLoaded` | Informational only |

## JSON Output Format (Exit 0 Only)

### Inject context into agent

```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "Context text injected into the conversation"
  }
}
```

**Supported events for `additionalContext`**: PostToolUse, PostToolUseFailure, SessionStart, UserPromptSubmit, SubagentStart, Notification, PreToolUse (exit 0 only).

### Block a tool call via JSON (alternative to exit 2)

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Explanation shown to agent"
  }
}
```

When multiple PreToolUse hooks return decisions, precedence is: **deny > defer > ask > allow**.

## Known Issues and History

| Version | Fix/Issue |
|---------|-----------|
| v2.1.90 | Fixed: PreToolUse hooks with JSON stdout + exit 2 now correctly block |
| v2.1.92 | Fixed: PreToolUse/PostToolUse hook file paths are now absolute |
| #34600 (open) | Stop hooks with exit 2 display as "Stop hook error" instead of "Stop hook blocked" |
| #10412 (closed) | Plugin-installed hooks had exit 2 failures — addressed in subsequent releases |

## Design Patterns

### Enforcement gate (blocks until condition met)

```python
# Exit 2 + stderr — blocks the action
if violation_detected:
    print("You must fix X before proceeding", file=sys.stderr)
    sys.exit(2)
# Exit 0 — allow the action (implicit)
```

### Context injection (adds info to agent context)

```python
# Exit 0 + stdout JSON — injects context
output = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": "Injected knowledge..."
    }
}
print(json.dumps(output))
# Exit 0 implicit
```

### Fail-open wrapper

```python
if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # fail-open: never block on internal errors
```

All enforcement hooks should be fail-open — an unhandled exception exits 0 (allows the action) rather than exit 2 (blocks). This prevents hook bugs from freezing the agent.
