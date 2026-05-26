# Agent Configuration Reference

Detailed documentation for all frontmatter fields, prompt writing, and troubleshooting. Back to [SKILL.md](../SKILL.md).

## Contents

- [Configuration Fields](#configuration-fields) -- required and optional frontmatter
- [Writing Effective Agent Prompts](#writing-effective-agent-prompts) -- principles, examples, template
- [CLI-Defined Agents](#cli-defined-agents) -- ephemeral session-only agents
- [Troubleshooting](#troubleshooting) -- activation, errors, performance, permissions

## Configuration Fields

### Required Fields

**name** (required)

- Unique identifier
- Lowercase with hyphens
- Examples: `code-reviewer`, `security-analyzer`, `performance-optimizer`

**description** (required)

- Natural language description of when to invoke
- Claude uses this for automatic delegation
- Be specific and action-oriented
- Include "use proactively" or "MUST BE USED" for automatic invocation

```yaml
# Good descriptions
description: Expert code review specialist. Use proactively after writing or modifying code to ensure quality and security.
description: Debugging specialist for errors and test failures. MUST BE USED when encountering any errors or unexpected behavior.

# Bad descriptions
description: Helps with code
description: Use when needed
```

### Optional Fields

**tools**

- Comma-separated list of allowed tools (allowlist)
- Omit field to inherit all tools from main conversation (including MCP tools)
- Restrict for security or focus

Common tool sets:

```yaml
# Read-only exploration
tools: Read, Grep, Glob, Bash

# Development work
tools: Read, Edit, Bash, Grep, Glob, Write

# Full access -- omit field entirely
```

**disallowedTools**

- Denylist complement to `tools`
- Tools listed here are removed from the inherited or specified set
- Useful when you want most tools but need to exclude a few

```yaml
# Allow everything except file modification
disallowedTools: Write, Edit
```

**model**

- `inherit`: Use main conversation model (default when omitted)
- `sonnet`: Balanced capability and speed
- `opus`: Most capable, for complex reasoning
- `haiku`: Fastest, for quick searches

The frontmatter `model:` declares a **capability floor** — the minimum tier this agent can safely run on. The orchestrator may route up via the Agent tool's per-spawn `model:` parameter, never below the floor. The authoritative tier table for Praxion subagents lives in `rules/swe/agent-model-routing.md`.

**permissionMode**

- `default`: Standard permission prompts
- `acceptEdits`: Auto-accept file edits
- `dontAsk`: Auto-deny permission prompts (explicitly allowed tools still work)
- `bypassPermissions`: Skip all permission checks (use with caution)
- `plan`: Plan mode (read-only exploration)

If the parent uses `bypassPermissions`, it takes precedence and cannot be overridden.

**color**

- UI background color shown when the agent is running
- Helps visually identify which agent is active

**skills**

- Comma-separated skill names to inject at startup
- Full skill content is injected into the agent's context, not just made available
- Agents do **not** inherit skills from the parent conversation -- list them explicitly
- Example: `skills: python, refactoring`

**hooks**

- Lifecycle hooks scoped to this agent's execution
- Supported events: `PreToolUse`, `PostToolUse`, `Stop`
- Cleaned up automatically when the agent finishes

```yaml
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./scripts/validate-command.sh"
  PostToolUse:
    - matcher: "Edit|Write"
      hooks:
        - type: command
          command: "./scripts/run-linter.sh"
```

**memory**

- Persistent memory directory for cross-session learning
- Scopes:
  - `user`: `~/.claude/agent-memory/<name>/` -- learnings across all projects
  - `project`: `.claude/agent-memory/<name>/` -- project-specific, shareable via git
  - `local`: `.claude/agent-memory-local/<name>/` -- project-specific, not in git
- When enabled, first 200 lines of `MEMORY.md` from the memory directory are injected into the system prompt
- Read, Write, and Edit tools are automatically enabled

```yaml
memory: user  # recommended default
```

## Writing Effective Agent Prompts

### Core Principles

**Be specific about role and expertise:**

```markdown
You are a senior security engineer specializing in web application security.
Focus on OWASP Top 10 vulnerabilities, authentication flaws, and data exposure.
```

**Include clear instructions:**

```markdown
When invoked:
1. Read the modified files using git diff
2. Identify security-critical code paths
3. Check for common vulnerabilities
4. Verify input validation and sanitization
5. Report findings with severity levels
```

**Provide analysis checklists:**

```markdown
Security Review Checklist:
- SQL injection vulnerabilities
- Cross-site scripting (XSS)
- Authentication and authorization flaws
- Sensitive data exposure
- Security misconfiguration
```

**Define output format:**

```markdown
Provide findings organized by severity:

**Critical** (must fix immediately):
- [Specific issue with code location]
- [Recommended fix]

**High** (fix before deployment):
- [Issue and location]
- [Fix recommendation]

**Medium** (should address):
- [Issue and location]
- [Improvement suggestion]
```

**Set constraints and boundaries:**

```markdown
Constraints:
- Only flag actual security issues, not style preferences
- Provide specific code examples for fixes
- Consider both security and maintainability
- Do not suggest changes that break functionality
```

### Prompt Template

```markdown
---
name: [agent-name]
description: [When to use this agent -- be specific]
tools: [Optional: specific tools]
model: [Optional: sonnet/opus/haiku/inherit]
---

# Role and Expertise

You are a [specific role] specializing in [domain/expertise].
Focus on [primary responsibilities].

# When Invoked

When activated:
1. [First step]
2. [Second step]
3. [Third step]

# Analysis Framework

[Checklist or framework for analysis]:
- [Criterion 1]
- [Criterion 2]
- [Criterion 3]

# Output Format

Provide [type of output] organized by [structure]:

**[Category 1]**: [What goes here]
**[Category 2]**: [What goes here]

# Constraints

- [Constraint 1]
- [Constraint 2]
- [Constraint 3]
```

## CLI-Defined Agents

Session-only agents defined via the `--agents` CLI flag (not saved to disk):

```bash
claude --agents '{
  "code-reviewer": {
    "description": "Expert code reviewer. Use proactively after code changes.",
    "prompt": "You are a senior code reviewer...",
    "tools": ["Read", "Grep", "Glob", "Bash"],
    "model": "sonnet"
  }
}'
```

## Troubleshooting

### Agent Not Being Used

**Problem**: Agent doesn't activate automatically.

**Solutions**:

- Make description more specific
- Add "use proactively" or "MUST BE USED"
- Match user terminology
- Test with explicit invocation first
- Check file location and naming

### Agent Has Errors

**Problem**: Agent fails or behaves unexpectedly.

**Solutions**:

- Verify YAML frontmatter syntax (no tabs, proper `---` delimiters)
- Check tool names are correct
- Use `/agents` interface for validation
- Test in isolation before team rollout
- Review prompt for clarity

### Agent Performance Issues

**Problem**: Agent is slow or gives poor results.

**Solutions**:

- Simplify and focus the prompt
- Add specific examples
- Restrict tools to necessary ones
- Consider different model
- Break into multiple focused agents

### Permission Problems

**Problem**: Agent blocked by permissions or has too much access.

**Solutions**:

- Set appropriate `permissionMode`
- Restrict `tools` to minimum needed
- Use plan mode for read-only analysis
- Test permission flow
