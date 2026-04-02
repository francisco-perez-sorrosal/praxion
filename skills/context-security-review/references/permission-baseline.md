# Agent Permission Baseline

Expected tool permissions, permission modes, and access levels for all Praxion pipeline agents. Use this baseline to detect permission escalation in PRs that modify agent definitions.

Back-link: [Context Security Review Skill](../SKILL.md)

## Baseline Table

| Agent | Tools | Permission Mode | Disallowed Tools | Web Access | Notes |
|-------|-------|-----------------|------------------|------------|-------|
| researcher | Read, Glob, Grep, Bash, WebSearch, WebFetch, Write | default | -- | Yes | Only agent with web access |
| systems-architect | Read, Glob, Grep, Bash, Write, Edit | acceptEdits | -- | No | Full filesystem write |
| implementation-planner | Read, Glob, Grep, Bash, Write, Edit | acceptEdits | -- | No | Full filesystem write |
| implementer | Read, Write, Edit, Glob, Grep, Bash | acceptEdits | -- | No | Full filesystem write |
| test-engineer | Read, Write, Edit, Glob, Grep, Bash | acceptEdits | -- | No | Full filesystem write |
| context-engineer | Read, Glob, Grep, Bash, Write, Edit | acceptEdits | -- | No | Full filesystem write |
| cicd-engineer | Read, Write, Edit, Glob, Grep, Bash | acceptEdits | -- | No | Full filesystem write |
| doc-engineer | Read, Write, Edit, Glob, Grep, Bash | acceptEdits | -- | No | Full filesystem write |
| promethean | Read, Glob, Grep, Bash, Write, Edit, AskUserQuestion | default | -- | No | Can prompt user |
| sentinel | Read, Glob, Grep, Bash, Write | default | Edit | No | Read-heavy, write-only (no edit) |
| verifier | Read, Glob, Grep, Bash, Write | default | Edit | No | Read-heavy, no edit |
| skill-genesis | Read, Glob, Grep, Bash, Write, AskUserQuestion | default | -- | No | Can prompt user |

## Permission Mode Summary

| Mode | Agents | Behavior |
|------|--------|----------|
| `default` | researcher, promethean, sentinel, verifier, skill-genesis | User must approve file modifications |
| `acceptEdits` | systems-architect, implementation-planner, implementer, test-engineer, context-engineer, cicd-engineer, doc-engineer | File writes/edits auto-approved |

## Web Access Summary

| Access Level | Agents |
|-------------|--------|
| Web access (WebSearch, WebFetch) | researcher |
| No web access | All other agents (11 of 12) |

## Special Tools

| Tool | Agents | Purpose |
|------|--------|---------|
| AskUserQuestion | promethean, skill-genesis | Interactive user prompts |
| WebSearch, WebFetch | researcher | External documentation and research |

## Deviation Detection

When reviewing a PR that modifies `agents/*.md`, check for these escalation patterns:

### Critical Escalations (FAIL)

- **New web access**: Any agent gaining `WebSearch` or `WebFetch` (currently only `researcher` has these)
- **Removed disallowed tools**: `sentinel` or `verifier` losing their `Edit` restriction
- **Mode escalation**: An agent changing from `default` to `acceptEdits` without clear justification
- **New unscoped Bash**: Adding `Bash` where the agent previously had no Bash access (all agents currently have Bash, but new agents should be evaluated)

### Suspicious Changes (WARN)

- **New tools added**: Any tool added to an agent's tool list that was not previously present
- **New AskUserQuestion**: An agent gaining interactive prompt capability
- **permissionMode change**: Any change to permission mode, even if seemingly benign
- **New agent definition**: A new agent file added to `agents/` -- verify it follows least-privilege

### Acceptable Changes (PASS)

- **Skill list changes**: Modifying `skills:` in frontmatter (skills are advisory, not permissions)
- **Description updates**: Changing agent description text
- **Hook configuration**: Updating hook registrations (reviewed separately under Hook Compromise)
- **maxTurns changes**: Adjusting turn limits

## How to Use This Baseline

1. **During PR review**: Compare the agent's current frontmatter against this table. Any difference in `tools`, `permissionMode`, or `disallowedTools` is a finding.
2. **During full-scan**: Read all `agents/*.md` files and compare against this table. Report any deviations.
3. **When adding new agents**: Verify the new agent follows least-privilege -- only tools it actually needs, `default` permission mode unless `acceptEdits` is justified, `disallowedTools` for tools it should never use.
4. **Updating this baseline**: When a legitimate permission change is approved, update this table to reflect the new baseline. This file is the source of truth for expected permissions.

## Accepted Design Decisions

These are known deviations from strict least-privilege that have been intentionally accepted:

- **8 of 12 agents use `acceptEdits`**: Required for pipeline efficiency -- these agents need to write code and documents without user confirmation for every file operation.
- **All agents have `Bash` access**: Required for running formatters, linters, git commands, and other development tools. Agent-level Bash scoping is not currently supported by Claude Code; scoping is applied at the command level instead.
- **`researcher` has web access**: Required for its core function of researching external documentation and technologies. Web access is not granted to any other agent.
