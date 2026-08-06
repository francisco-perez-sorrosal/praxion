# Agent Permission Baseline

Expected tool permissions, permission modes, and access levels for all Praxion pipeline agents. Use this baseline to detect permission escalation in PRs that modify agent definitions. Back to [SKILL.md](../SKILL.md).

## Baseline Table

| Agent | Tools | Permission Mode (intended) | Disallowed Tools | Web Access | Notes |
|-------|-------|-----------------|------------------|------------|-------|
| researcher | Read, Glob, Grep, Bash, WebSearch, WebFetch, Write, Edit | default | -- | `WebSearch` + `WebFetch` | The only agent that can *discover* an external URL rather than follow one it was given |
| systems-architect | Read, Glob, Grep, Bash, Write, Edit | acceptEdits | -- | No | Full filesystem write |
| interface-designer | Read, Glob, Grep, Bash, Write, Edit | acceptEdits | -- | No | Peer sub-architect; identical surface to systems-architect, so any divergence between the two rows is itself the finding |
| agentic-transactions-architect | Read, Glob, Grep, Bash, Write, Edit | acceptEdits | -- | No | Peer sub-architect; identical surface to systems-architect. Reasons about payment and brokerage boundaries but holds no credential access — a tool grant that implies live transaction execution is out of baseline |
| discipline-consultant | Read, Glob, Grep, Bash, Write, Edit, Skill | acceptEdits | -- | No | The only agent with `Skill`. It loads a skill chosen by a runtime registry lookup, so the instruction text it executes is selected at spawn time rather than fixed in its definition — review the registry alongside the agent |
| implementation-planner | Read, Glob, Grep, Bash, Write, Edit | acceptEdits | -- | No | Full filesystem write |
| implementer | Read, Write, Edit, Glob, Grep, Bash | acceptEdits | -- | No | Full filesystem write |
| test-engineer | Read, Write, Edit, Glob, Grep, Bash | acceptEdits | -- | No | Full filesystem write |
| context-engineer | Read, Glob, Grep, Bash, Write, Edit | acceptEdits | -- | No | Full filesystem write |
| cicd-engineer | Read, Write, Edit, Glob, Grep, Bash | acceptEdits | -- | No | Full filesystem write |
| doc-engineer | Read, Write, Edit, Glob, Grep, Bash | acceptEdits | -- | No | Full filesystem write |
| promethean | Read, Glob, Grep, Bash, Write, Edit, AskUserQuestion, WebFetch | default | -- | `WebFetch` | Can prompt user. Fetches a named URL but cannot search — a narrower egress grant than researcher's, and the distinction is the point |
| roadmap-cartographer | Read, Glob, Grep, Bash(git:\*), Bash(wc:\*), Bash(grep:\*), Bash(find:\*), Bash(jq:\*), Write, Edit, AskUserQuestion, Task | default | -- | No | Two deviations in one row, pulling opposite ways: the only agent whose `Bash` is **scoped** to an allowlist (tighter than every peer), and the only one holding `Task` (looser — it spawns subagents, whose privileges are their own and are not bounded by this row) |
| sentinel | Read, Glob, Grep, Bash, Write | default | Edit | No | Read-heavy, write-only (no edit) |
| verifier | Read, Glob, Grep, Bash, Write | default | Edit | No | Read-heavy, no edit |
| architect-validator | Read, Glob, Grep, Bash, Write | default | Edit | No | Read-heavy, write-only. Runs as a pre-merge CI gate that exits non-zero, so a tool grant here widens what executes inside CI, not just inside a session |
| skill-genesis | Read, Glob, Grep, Bash, Write | default | Edit | No | Read-heavy, write-only (no edit). Proposes new context artifacts but must not author them — gaining `Edit` or `Write` beyond its report path would let a harvest pass rewrite the ecosystem it harvests |

> **Not machine-enforced.** Praxion's agents ship as plugin subagents (`.claude-plugin/plugin.json`), and Claude Code ignores the `permissionMode` frontmatter field for plugin subagents. The field was removed from `agents/*.md` (see `td-072`); this column records the *intended* posture for review purposes. Enforcement of what an agent can touch comes from `tools` / `disallowedTools`, which are honoured.

## Permission Mode Summary

| Mode | Behavior |
|------|----------|
| `default` | User must approve file modifications |
| `acceptEdits` | File writes/edits auto-approved |

## Special Tools

Tools that are not part of the read-write baseline every agent shares. Each is a distinct
capability class, and a PR adding one is a finding on those grounds alone.

| Tool | Capability class | Why it matters at review |
|------|------------------|--------------------------|
| `WebSearch` | Network egress, agent-chosen destination | The agent selects where to reach. Strictly broader than `WebFetch`: it can reach a host nobody named. |
| `WebFetch` | Network egress, caller-named destination | Egress bounded to a URL already in context. Both tools are egress, so treat the pair as one surface — but do not read a `WebFetch` grant as licence for `WebSearch`. |
| `AskUserQuestion` | Interactive prompt | The agent can put text in front of the user and act on the reply — a social-engineering surface, not just a UX affordance. |
| `Skill` | Runtime instruction loading | Pulls another artifact's instructions into the agent mid-run. What the agent executes is no longer fully determined by its own definition. |
| `Task` | Subagent spawn | Delegation. The spawned agent's permissions are its own, so this grant is not bounded by the granting row — audit it as a hole in the boundary, not as one more tool. |

**Read the roster from the Baseline Table, not from here.** The mode, web access, and special
tools of any given agent are columns above; restating them as name lists in these summaries is
what let five agents go missing and three rows go stale without either being visible.

## Deviation Detection

When reviewing a PR that modifies `agents/*.md`, check for these escalation patterns:

### Critical Escalations (FAIL)

- **New web access**: Any agent gaining `WebSearch` or `WebFetch` beyond what its Web Access column already grants. `WebFetch` → `WebSearch` is an escalation on the same row, not a lateral move
- **Removed disallowed tools**: Any agent losing an entry from its Disallowed Tools column — in practice, one of the read-heavy agents gaining `Edit`
- **Mode escalation**: An agent changing from `default` to `acceptEdits` without clear justification
- **Bash widening**: Adding `Bash` where the agent previously had none, or replacing a scoped `Bash(...)` allowlist with bare `Bash` — the second is easy to read as a formatting cleanup
- **New delegation**: An agent gaining `Task`. It escapes this table: the spawned agent's tools are its own

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

1. **During PR review**: Compare the agent's current frontmatter against this table. Any difference in `tools` or `disallowedTools` is a finding. `permissionMode` is no longer declared in agent frontmatter -- its **presence** is a finding (see `td-072`), not its absence.
2. **During full-scan**: Read all `agents/*.md` files and compare against this table. Report any deviations.
3. **When adding new agents**: Verify the new agent follows least-privilege -- only tools it actually needs, `default` permission mode unless `acceptEdits` is justified, `disallowedTools` for tools it should never use.
4. **Updating this baseline**: When a legitimate permission change is approved, update this table to reflect the new baseline. This file is the source of truth for expected permissions.

## Accepted Design Decisions

These are known deviations from strict least-privilege that have been intentionally accepted:

- **Most agents use `acceptEdits`**: Required for pipeline efficiency -- these agents need to write code and documents without user confirmation for every file operation. The read-heavy agents are the exception and stay on `default`.
- **Every agent has `Bash` access**: Required for running formatters, linters, git commands, and other development tools. Most hold it unscoped; `roadmap-cartographer` demonstrates that a per-agent allowlist is expressible, so an unscoped grant on a *new* agent is a choice to justify rather than the only option.
- **Web access is granted twice, at two widths**: `researcher` needs `WebSearch` for its core function of researching external documentation; `promethean` holds `WebFetch` alone, which reaches a URL already in context but discovers nothing. No other agent has egress.
