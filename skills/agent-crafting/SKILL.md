---
name: agent-crafting
description: Creating and configuring agents (subagents) with effective prompts, tool permissions, and lifecycle hooks. Use when building custom agents, designing agent workflows, spawning subagents, delegating tasks via the Task tool, defining subagent_type, or using the /agents command.
compatibility: Claude Code
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
---

# Agent Creator

Guide for building agents -- specialized subprocesses with separate context windows, independent tool permissions, and focused system prompts. The term "subagent" is used interchangeably with "agent" throughout Claude Code documentation.

**Satellite files** (loaded on-demand):

- [references/configuration.md](references/configuration.md) -- detailed field docs, prompt writing guide, prompt template, CLI agents, troubleshooting
- [references/examples.md](references/examples.md) -- complete agent definitions showing distinct patterns (read-only, edit-capable, hooks, memory)
- [../skill-crafting/references/artifact-naming.md](../skill-crafting/references/artifact-naming.md) -- naming conventions for all artifact types

## Creating Agents

**Quick**: Run `/agents` for guided creation (recommended starting point).

**Manual**: Create a markdown file in `.claude/agents/` (project) or `~/.claude/agents/` (personal).

### Agent File Structure

```markdown
---
name: agent-name
description: When this agent should be invoked
tools: tool1, tool2, tool3  # Optional: omit to inherit all
disallowedTools: tool4      # Optional: denylist
model: sonnet               # Optional: sonnet/opus/haiku/inherit (default: inherit)
permissionMode: default     # Optional: default/acceptEdits/dontAsk/bypassPermissions/plan
color: blue                 # Optional: UI background color
skills: skill1, skill2      # Optional: inject skill content at startup
hooks:                       # Optional: lifecycle hooks scoped to this agent
memory: user                 # Optional: persistent memory (user/project/local)
---

Your agent's system prompt goes here.
Define role, expertise, instructions, constraints, and output format.
```

### Configuration Fields Summary

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique identifier, lowercase with hyphens |
| `description` | Yes | When Claude should delegate -- be specific, include "use proactively" for auto-invocation |
| `tools` | No | Allowlist of tools; omit to inherit all |
| `disallowedTools` | No | Denylist; removed from inherited/specified set |
| `model` | No | `inherit` (default), `sonnet`, `opus`, `haiku` |
| `permissionMode` | No | `default` for read-heavy agents, `acceptEdits` for agents that write files |
| `color` | No | UI background color for identification |
| `skills` | No | Skills injected into context (not inherited from parent) |
| `hooks` | No | `PreToolUse`, `PostToolUse`, `Stop` events |
| `memory` | No | `user` (personal prefs), `project` (project-specific), `local` (gitignored). Default to `user` for most agents |

For detailed field documentation, prompt writing guide, and the full prompt template, see [references/configuration.md](references/configuration.md).

## Agent Example

A concise debugger agent showing the key structural elements:

```markdown
---
name: debugger
description: Debugging specialist for errors and test failures. Use proactively when encountering any issues.
tools: Read, Edit, Bash, Grep, Glob
---

You are an expert debugger specializing in root cause analysis.

When invoked:
1. Capture error message and stack trace
2. Identify reproduction steps
3. Isolate the failure location
4. Implement minimal fix
5. Verify solution works

For each issue, provide:
- Root cause explanation
- Evidence supporting the diagnosis
- Specific code fix
- Prevention recommendations

Focus on fixing the underlying issue, not the symptoms.
```

For more complete examples (read-only, edit-capable, hooks, memory), see [references/examples.md](references/examples.md).

### System Prompt Sizing

Keep agent prompts focused. When a prompt grows too long, use the `skills` field to offload domain knowledge:

- **Target**: 50–150 lines for the system prompt body
- **Hard ceiling**: ~300 lines — beyond this, extract domain content into skills (via the `skills` field) or inline it
- **Progressive disclosure**: Use the `skills` field to inject reusable knowledge that the agent needs but that doesn't define its core behavior

**Plugin agent self-containment:** Agents distributed via the plugin system must be self-contained. Reference/satellite files placed next to the agent definition (e.g., `agents/references/`) are NOT accessible when the agent runs in other projects — the sub-agent's `Read` calls resolve relative to the project's working directory, not the plugin cache. This fails silently: the read returns "file not found" but the agent continues without the missing content, producing degraded output with no visible error. If an agent's prompt exceeds the ceiling:
- Use the `skills` field to offload domain knowledge (skills are resolved from the plugin)
- Inline the content directly in the agent prompt (acceptable for agents since they run in their own context window and are not always-loaded)
- Do NOT use satellite/reference files that the agent reads at runtime

**End-user-facing prompt design:** This skill covers agent-loop plumbing and system-prompt role/boundary wiring. For end-user-facing prompt design (few-shot patterns, chain-of-thought, structured output via Pydantic/Zod, prompt versioning, injection hardening), consult the [`llm-prompt-engineering`](../llm-prompt-engineering/SKILL.md) skill.

## Agent Location Hierarchy

Higher priority wins when names collide:

| Priority | Location | Scope |
|----------|----------|-------|
| 1 (Highest) | `--agents` CLI flag | Current session only |
| 2 | `.claude/agents/` | Current project |
| 3 | `~/.claude/agents/` | All projects |
| 4 (Lowest) | Plugin `agents/` | Where plugin is enabled |

**Best practice**: Use project-level agents (`.claude/agents/`) for team collaboration. For CLI-defined ephemeral agents, see [references/configuration.md](references/configuration.md).

## Constraints and Runtime Behavior

- **Agents cannot spawn agents.** Do not include `Task` in tools. Chain agents from the main conversation instead.
- **System prompt isolation.** Agents receive only their markdown body + basic env details, not the full Claude Code system prompt. They do **not** inherit:
  - Skills from the parent context (must be listed in the `skills` field)
  - Rules (`~/.claude/rules/` content is not injected into sub-agents)
  - Parent CLAUDE.md content (project or user-level)
  - Memory settings (must be set via the `memory` field)
  - Parent's conversation history or context
- **Session loading.** Agents load at session start. Manually added files need a restart or `/agents`.
- **Foreground**: Blocks main conversation; permission prompts pass through.
- **Background**: Runs concurrently; permissions pre-approved; press **Ctrl+B** to background a running agent.
- **Disabling agents**: `claude --disallowedTools "Task(my-agent)"` or add to `deny` array in settings.
- **Transcripts** persist at `~/.claude/projects/{project}/{sessionId}/subagents/agent-{agentId}.jsonl`.

## Anti-Patterns

| Anti-Pattern | Fix |
|-------------|-----|
| Overly broad agent ("General purpose helper for all tasks") | Focus on a single domain ("Security vulnerability scanner for authentication code") |
| Vague description ("Use when needed") | Specific triggers ("Use proactively after modifying authentication or authorization code") |
| No output format ("Just tell me what's wrong") | Structured output ("Organize findings by severity: Critical/High/Medium with code examples") |
| Kitchen sink agent (all tools, all tasks) | Specialized agent (read-only tools, focused on analysis) |
| Listing all tools individually when full access is fine | Omit `tools` field to inherit all |
| Reference files for plugin agents (file unreachable in other projects) | Use `skills` field or inline content |

## Integration with Other Features

### Agents + Skills

- Skills provide broad capabilities in the main context
- Agents delegate specific workflows to a separate context window
- Use the `skills` field to inject skill content into an agent
- Agents do **not** inherit skills from the parent -- list them explicitly
- For creating or modifying skills that agents consume, see the `skill-crafting` skill

```yaml
---
name: code-reviewer
description: Reviews Python code for quality, design, and correctness
skills: python, refactoring
tools: Read, Glob, Grep
---
```

### Agents + Slash Commands

- Commands are user-invoked; agents are automatic or explicitly delegated
- Commands can reference or trigger agents
- Use commands for repeatable user actions, agents for delegated workflows

### Agents + Hooks

- Define hooks in agent frontmatter for scoped lifecycle control (`PreToolUse`, `PostToolUse`, `Stop`)
- Configure project-level hooks via `SubagentStart`/`SubagentStop` events in `settings.json`

## Development Workflow

1. **Generate**: Run `/agents` to scaffold an initial agent definition
2. **Test**: Invoke with real scenarios, observe behavior and output quality
3. **Refine**: Adjust prompt, restrict tools, add examples and constraints
4. **Version control**: Commit agent files in `.claude/agents/`
5. **Iterate**: Gather team feedback, update prompts, add edge cases

## Deployment Checklist

- [ ] Single, clear responsibility
- [ ] Descriptive name matching purpose
- [ ] Specific description with trigger words
- [ ] Detailed system prompt with steps, checklist, output format, constraints
- [ ] Appropriate tools granted (or inherited)
- [ ] Correct model selected
- [ ] Tested with real scenarios
- [ ] Version controlled in git

## Quick Reference

### Minimal Template

```markdown
---
name: agent-name
description: Specific description of when to use this agent
---

You are [role] specializing in [domain].

When invoked:
1. [Step 1]
2. [Step 2]
3. [Step 3]

Checklist:
- [Item 1]
- [Item 2]

Output format:
[How to structure output]

Constraints:
- [Constraint 1]
- [Constraint 2]
```

### Common Tool Sets

```yaml
# Read-only
tools: Read, Grep, Glob, Bash

# Development
tools: Read, Edit, Grep, Glob, Bash, Write

# Full access -- omit tools field
```

