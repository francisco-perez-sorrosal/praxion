---
description: Run skill-genesis as an on-demand autonomous learning harvest. Writes a timestamped report to .ai-state/skill_genesis_reports/. Disposition later via /skill-genesis-review.
argument-hint: "[--since <commit>] [--scope <area>] [--dry-run]"
allowed-tools: [Read, Glob, Grep, Bash(git:*), Task]
disable-model-invocation: true
---

Spawn the `skill-genesis` agent in the background to harvest learnings from the current project state. The agent runs autonomously, writes a timestamped report to `.ai-state/skill_genesis_reports/`, and appends a row to the sibling `SKILL_GENESIS_LOG.md`. Once the agent completes, run `/skill-genesis-review` to disposition the pending proposals.

## Flags

| Flag | Description |
|------|-------------|
| `--since <commit>` | Scope the harvest to learning sources newer than the given commit. Passes the commit reference to the agent so it focuses triage on recent changes. |
| `--scope <area>` | Narrow the harvest to a specific area (e.g., `agents`, `rules/swe`, `dashboard_app`). Useful when a long pipeline touched a focused surface and you want targeted proposals. |
| `--dry-run` | Preview which learning sources would be harvested without spawning the agent. Lists detected sources (LEARNINGS.md, VERIFICATION_REPORT.md, SENTINEL_REPORT, IDEA_LEDGER, recent ADRs) and exits. |

## Process

### 1. Parse arguments

Parse `$ARGUMENTS` for the three optional flags:

```
--since <commit>      Sets the harvest commit boundary (passed to agent as `since`)
--scope <area>        Sets the harvest area filter (passed to agent as `scope`)
--dry-run             Preview mode: list sources; do not spawn agent
```

### 2. Generate task slug

When invoked inside an active pipeline (a `.ai-work/<slug>/` directory exists with a
`WIP.md`), inherit the parent pipeline's slug. Otherwise derive a standalone slug:

```
skill-genesis-YYYY-MM-DD
```

Append `_2`, `_3`, … on collision (if `.ai-work/skill-genesis-YYYY-MM-DD/` already exists).

### 3. Pre-flight — detect learning sources

Scan for harvestable sources. Exit with a "nothing new to harvest" message if none found.

Sources to detect:

- Any `.ai-work/*/LEARNINGS.md` (non-empty)
- Any `.ai-work/*/VERIFICATION_REPORT.md`
- Any `.ai-state/sentinel_reports/SENTINEL_REPORT_*.md` newer than the most recent
  `SKILL_GENESIS_REPORT_*.md` in `.ai-state/skill_genesis_reports/`
- Any `.ai-state/idea_ledgers/IDEA_LEDGER_*.md`
- Any recent `.ai-state/decisions/*.md` (ADRs created since the last harvest)

When `--since <commit>` is provided, apply it as an additional filter (prefer sources
modified after that commit).

**`--dry-run` exit point**: when `--dry-run` is set, print the list of detected sources
(or the "nothing new" message) and exit without spawning the agent.

### 4. Delegate to the skill-genesis agent in background mode

Invoke the `skill-genesis` agent via the `Task` tool. The agent runs with `background: true`,
so this command returns to the user immediately after spawning.

Pass in the task prompt:

```
Task slug: <slug>
Invocation args:
  since: <commit or null>
  scope: <area or null>
  dry_run: false
Write the report to: .ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_<YYYY-MM-DD_HH-MM-SS>.md
```

### 5. Surface the expected report path and next step

After spawning, print:

```
skill-genesis agent spawned in the background.

Expected report: .ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_<YYYY-MM-DD_HH-MM-SS>.md
Run-log:         .ai-state/skill_genesis_reports/SKILL_GENESIS_LOG.md

Once the agent completes, run /skill-genesis-review to disposition the pending proposals.
```

The agent also appends phase-transition signals to `.ai-work/<slug>/PROGRESS.md` as it runs —
check that file to track progress.
