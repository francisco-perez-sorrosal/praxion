# Hook Event Reference

Claude Code hook events with input schemas and blocking semantics. The event surface keeps growing — cross-check the live [hooks reference](https://code.claude.com/docs/en/hooks) for additions. Back to [SKILL.md](../SKILL.md).

## Contents

- [Common Input Fields](#common-input-fields)
- [Events by Category](#events-by-category)
- [Exit Code Semantics](#exit-code-semantics)
- [Exec Form vs Shell Form](#exec-form-vs-shell-form)
- [Known Bugs](#known-bugs)

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
| **PermissionDenied** | No | `tool_name`, denied permission | React to an auto-mode permission denial (logging, hints) |

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
| **PostToolBatch** | Yes (exit 2) | resolved parallel tool-call batch | Validate/gate a parallel tool batch as a unit |

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
| **Setup** | Yes | `source`: init/maintenance | First-run / maintenance setup steps |
| **SessionStart** | No | `source`: startup/resume/clear/compact | Environment setup, context injection |
| **SessionEnd** | No | `reason`: clear/resume/logout/… | Cleanup, logging on session end |
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
| **UserPromptExpansion** | Yes (exit 2) | expanded slash-command/skill text | Inspect or gate slash-command expansion |
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

> **Exit 0 with no output means "no decision, proceed normally" — NOT "approve."** To actually block you must `exit 2` (or emit JSON `decision: "block"` / `permissionDecision: "deny"`). A hook that silently `exit 0`s is a no-op, not an approval gate. CLI tools default error text to **stdout**; redirect to stderr (`>&2`) on a block, since only stderr is fed back to Claude.

## Exec Form vs Shell Form

A handler with an `args` array runs **exec form** — no shell, no string interpolation, so no injection risk. Prefer it with `${...}` path placeholders. Omitting `args` (a bare `command` string) runs **shell form** — full shell features, but you own the quoting/escaping. Use exec form for anything touching untrusted input.

## Known Bugs
<!-- last-verified: 2026-08-05 -->

Re-verify before relying on these — hook bugs get fixed (and regress) across Claude Code releases.

**No open hook defects are currently tracked here.** All four issues this table previously
carried are closed. They are kept below with their dispositions rather than deleted, because
"we checked and it's fixed" is different information from "we never looked" — and because one
of them was never a bug at all.

| Issue | Behavior | Disposition (verified 2026-08-05) |
|-------|----------|-----------------------------------|
| #24327 | PreToolUse exit 2 makes Claude go idle instead of acting on stderr feedback | **Closed 2026-02-22** (completed). Root cause was a race condition when **parallel** hooks fire — not a version or model correlation. Reporter's workaround: wrap multiple hooks so they fire once |
| #26923 | PreToolUse exit 2 does not block Agent/Task tool calls | **Closed 2026-04-18** (completed) — **fixed in v2.1.90**. PreToolUse hooks exiting 2 with JSON on stdout now correctly block the tool call, including the Task tool |
| #13744 | PreToolUse exit 2 doesn't block Write/Edit | **Closed 2025-12-15** as a duplicate of #3514, itself closed `not_planned` (2026-02-28). Not an open tracked defect |
| #37210 | `permissionDecision: "deny"` ignored for Edit | **Closed 2026-03-21** (not planned) — **never a Claude Code bug**. The reporter's hook exited 2, and JSON output is only processed on exit 0, so the decision was discarded. Promoted to a correctness rule in [SKILL.md § Gotchas](../SKILL.md#gotchas) |

The #24327 lesson is worth keeping even though the issue closed: **parallel hooks on the same
event can race.** If several hooks are registered for one event and behavior is intermittent,
collapse them behind a single dispatching hook before assuming a platform defect.
