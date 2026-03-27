# Hook Event Reference

All 24 Claude Code hook events with input schemas and blocking semantics.

## Common Input Fields

Every event receives these fields on stdin:

```json
{
  "session_id": "string",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/working/directory",
  "permission_mode": "default|plan|acceptEdits|auto|dontAsk|bypassPermissions",
  "hook_event_name": "EventName",
  "agent_id": "optional — present in subagent context",
  "agent_type": "optional — e.g. i-am:researcher"
}
```

## Events by Category

### Before Tool Execution

| Event | Can Block | Extra Input | Use For |
|-------|-----------|-------------|---------|
| **PreToolUse** | Yes (exit 2) | `tool_name`, `tool_input` | Security gates, quality gates, input modification |
| **PermissionRequest** | Yes | `tool_name`, `tool_input` | Auto-approve/deny permissions, custom permission logic |

**PreToolUse matchers**: Match by tool name — `Bash`, `Write`, `Edit`, `Read`, `Glob`, `Grep`, `WebSearch`, `WebFetch`, `Agent`, `Task`, `NotebookEdit`, `mcp__<server>__<tool>`.

**PreToolUse `if` field**: Filters by tool name AND arguments. `"if": "Bash(git *)"` only fires for git commands. `"if": "Edit(*.py)"` only for Python edits. Requires v2.1.85+. Only works on tool events.

**PreToolUse output** (exit 0):
```json
{
  "updatedInput": { "command": "modified command" },
  "additionalContext": "Text injected into Claude's context"
}
```

**PermissionRequest output** (exit 0):
```json
{
  "decision": {
    "behavior": "allow|deny",
    "updatedPermissions": [{"tool": "Bash", "permission": "allow|deny"}]
  }
}
```

### After Tool Execution

| Event | Can Block | Extra Input | Use For |
|-------|-----------|-------------|---------|
| **PostToolUse** | No | `tool_name`, `tool_input`, `tool_response` | Auto-formatting, logging, context injection |
| **PostToolUseFailure** | No | `tool_name`, `tool_input`, `error` | Error tracking, retry logic hints |

**PostToolUse `tool_response`** includes `exit_code` for Bash, `content` for Write, etc.

**PostToolUse output** (exit 0):
```json
{
  "additionalContext": "Text Claude sees in its context"
}
```

### Session Lifecycle

| Event | Can Block | Extra Input | Use For |
|-------|-----------|-------------|---------|
| **SessionStart** | No | `source`: startup/resume/clear/compact | Environment setup, context injection |
| **Stop** | Yes (exit 2) | `reason`, `stop_hook_active` | Completion enforcement, checklist gates |
| **StopFailure** | No | `reason` | Cleanup after failed stop |
| **PreCompact** | No | — | State snapshot before context compression |
| **PostCompact** | No | — | State restoration after compression |

**Stop** — `stop_hook_active` is `true` on the second invocation (after a block). Always check this to prevent infinite loops.

### Subagent Lifecycle

| Event | Can Block | Extra Input | Use For |
|-------|-----------|-------------|---------|
| **SubagentStart** | No | `agent_type`, `agent_id` | Observability, agent tracking |
| **SubagentStop** | Yes (exit 2) | `agent_type`, `agent_id`, `agent_transcript_path` | Post-agent validation |

### Task Lifecycle

| Event | Can Block | Extra Input | Use For |
|-------|-----------|-------------|---------|
| **TaskCreated** | Yes | Task metadata | Task validation, resource limits |
| **TaskCompleted** | Yes | Task metadata, result | Result validation |

### User Interaction

| Event | Can Block | Extra Input | Use For |
|-------|-----------|-------------|---------|
| **UserPromptSubmit** | Yes (exit 2) | `prompt` | Input validation, prompt augmentation |
| **Notification** | No | Notification type in matcher | Desktop alerts, sound notifications |
| **Elicitation** | Yes | Elicitation details | Custom approval flows |
| **ElicitationResult** | Yes | User response | Response validation |

**UserPromptSubmit output** (exit 0):
```json
{
  "additionalContext": "Context injected alongside the user's prompt"
}
```

### Environment

| Event | Can Block | Extra Input | Use For |
|-------|-----------|-------------|---------|
| **ConfigChange** | Yes | Changed config details | Config validation |
| **CwdChanged** | No | New working directory | Project detection, env switching |
| **FileChanged** | No | Changed file basename in matcher | File watching, auto-reload |
| **InstructionsLoaded** | No | Loaded instructions | Instruction augmentation |

**FileChanged matchers**: Match by filename — `"matcher": "package.json"` fires when package.json changes.

### Worktree

| Event | Can Block | Extra Input | Use For |
|-------|-----------|-------------|---------|
| **WorktreeCreate** | Yes | Worktree details | Worktree validation |
| **WorktreeRemove** | No | Worktree details | Cleanup |

### Team

| Event | Can Block | Extra Input | Use For |
|-------|-----------|-------------|---------|
| **TeammateIdle** | Yes | Teammate details | Task reassignment |

## Exit Code Semantics

| Code | Meaning | Stdout Parsed? | Stderr |
|------|---------|----------------|--------|
| **0** | Success | Yes — JSON output processed | Shown in verbose mode |
| **2** | Block | No — JSON ignored | Fed to Claude as error context |
| **Other** | Non-blocking error | No | Shown in verbose mode only |

## Known Bugs

| Issue | Behavior | Workaround |
|-------|----------|------------|
| #24327 | PreToolUse exit 2 causes Claude to stop instead of acting on feedback | May be version-dependent; test with current version |
| #26923 | PreToolUse exit 2 does not block Task tool calls | Agent launches despite block |
| #13744 | PreToolUse exit 2 doesn't block Write/Edit | Historical; verify with current version |
| #37210 | `permissionDecision: "deny"` ignored for Edit | Permission bypass on Edit tool |
