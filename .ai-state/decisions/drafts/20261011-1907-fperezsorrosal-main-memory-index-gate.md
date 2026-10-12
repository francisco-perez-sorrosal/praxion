---
id: dec-draft-b26172ec
title: A PreToolUse gate keeps memory indexes to short pointers, backed by an audit command
status: proposed
category: architectural
date: 2026-10-11
summary: "New hooks/guard_memory_index.py (PreToolUse Write|Edit) refuses a write to a Claude Code memory index (a project's auto-memory MEMORY.md or an agent-memory MEMORY.md) that would add a line over 150 characters, add content that is not a pointer, or grow the index past the harness load limit; existing debt never blocks a write. New scripts/check_memory_index.py holds the rules and audits whole indexes (too-long, not-a-pointer, dangling, duplicate, unindexed, over/near load limit). The live praxion-* agent indexes were shortened without loss (verifier 5,241 -> 2,920 tokens per spawn)."
tags: [memory, auto-memory, agent-memory, hooks, gate, startup-context, token-budget, convention]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - hooks/guard_memory_index.py
  - hooks/test_guard_memory_index.py
  - hooks/hooks.json
  - scripts/check_memory_index.py
  - scripts/test_check_memory_index.py
  - scripts/CLAUDE.md
  - skills/context-security-review/references/hook-safety-contract.md
  - README_DEV.md
affected_reqs: []
supersedes: null
superseded_by: null
re_affirms: null
re_affirmed_by: null
retired_by: null
---

## Context

Claude Code loads a memory index (`MEMORY.md`) into the start of every session, and an agent's own index (agents declaring `memory:`) into every spawn of that agent, up to the first 200 lines or 25 KB. Topic files load only when read. The harness tells the model to keep each entry a one-line pointer, but nothing holds it there. Measured on 2026-10-11:

- Praxion's own project index had grown into a status log: 19.3 KB, lines up to 1,225 characters, about 8.7K tokens per session and per spawn, weeks from the point where entries stop loading. It was shortened by hand to 12.2 KB with no entry dropped.
- The `praxion-verifier` agent index was 19.1 KB, with 73 of 75 lines over 150 characters: 5,241 tokens in every verifier spawn, in every project.
- 33 of the 36 indexes on the machine had at least one line over 150 characters.

A convention written down as a memory entry or a rule is advisory, and the research behind the startup-context diet found that advisory and on-demand guidance fails at the trigger. The trigger here is exact and deterministic: a Write or Edit to an index.

## Decision

1. **`hooks/guard_memory_index.py`, PreToolUse on `Write|Edit`, synchronous.** For a project auto-memory index under the Claude config directory (`$CLAUDE_CONFIG_DIR` or `~/.claude`) or any `agent-memory/<agent>/MEMORY.md`, it computes the text the pending write would leave and denies the write when the write *adds* a line over 150 characters, adds a line that is neither a pointer, a heading nor blank, or grows the index past the load limit. The denial reason states the convention and the offending lines. Lines already in the index never block, so an index carrying old debt still accepts a conforming entry. Every other path returns before the rules are imported. Fail-open.
2. **`scripts/check_memory_index.py` holds the rules and audits whole indexes**: `too-long`, `not-a-pointer`, `dangling`, `duplicate`, `unindexed` (a topic file no line links, which is a dropped entry), `over-load-limit` (fail) and `near-load-limit` (warn), for the current project's index, every index (`--all`), or given paths. It is executable, so the installer puts it on `PATH` for managed projects.
3. **The live Praxion agent indexes were brought inside the convention without loss**: 84 lines across `praxion-verifier`, `praxion-discipline-consultant`, `praxion-implementer` and `praxion-interface-designer`, every title and link unchanged and every original line kept verbatim in its topic file.

## Considered Options

### PreToolUse gate on the added lines, plus an audit command (chosen)

Pros: the bad line never lands; the agent learns the convention at the moment it applies; old debt never blocks unrelated work; works in every project and for every agent with the plugin installed. Cons: one Python start-up on every Write or Edit; a write made through Bash bypasses it.

### The convention alone (a memory entry, a rule, or CLAUDE.md text)

Rejected: the harness already states the one-line convention and the indexes drifted anyway; an always-loaded rule would add tokens to fix a token problem.

### PostToolUse feedback

Never denies a tool call, so its failure mode is gentler. Rejected: the bad line lands first and costs a second edit; a deny before the write is cheaper for the agent.

### A SessionStart audit

Rejected: it adds work and possibly text to every session start, and reports one session late.

### Narrow the hook with an `if` permission pattern

Would avoid a Python start-up on most writes. Rejected: the pattern's path semantics for files outside the project are uncertain, and a pattern that parses but misses a path (a relocated config directory) leaves the gate silently dead.

## Consequences

- New over-long or content lines cannot reach an index through Write or Edit, in Praxion or any managed project, once the plugin is released.
- Each verifier spawn starts 2,321 tokens lighter (3,292 on the current model's tokenizer).
- Writes through Bash, and indexes in a custom auto-memory directory, bypass the gate; the audit still sees their result.
- The 150-character ceiling is the harness's own guidance turned into a constant; tune `MAX_LINE_CHARS` if it bites.
- Not acted on: indexes of other projects on this machine, and the `i-am-*` agent memories left by Praxion's retired plugin namespace, which today's `praxion-*` agents never load.

## Disconfirmation

- **Falsifier:** an audit after the release finds new over-long lines written by Write or Edit, or transcripts show agents denied repeatedly without converging on a conforming line.
- **Steelmanned runner-up:** PostToolUse feedback never blocks a tool call, so a misjudged rule costs a nudge rather than a refusal. It loses because the refusal carries the fix and the bad line never lands.
- **Reversal trigger:** Claude Code enforces index entry length itself, or denials appear in a meaningful share of memory writes, which would mean the threshold or the grammar is wrong.
