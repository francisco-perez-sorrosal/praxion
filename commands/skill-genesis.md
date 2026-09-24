---
description: Run skill-genesis as an on-demand autonomous learning harvest. Writes a timestamped report to .ai-state/skill_genesis_reports/. Disposition later via /skill-genesis-review.
argument-hint: "[--since <commit>] [--scope <area>] [--sources <dir>] [--cap <bytes>] [--dry-run]"
allowed-tools: [Read, Glob, Grep, Bash(git:*), Bash(python3:*), Task]
disable-model-invocation: true
---

Spawn the `skill-genesis` agent in the background to harvest learnings from the current project state. The agent runs autonomously, writes a timestamped report to `.ai-state/skill_genesis_reports/`, and appends a row to the sibling `SKILL_GENESIS_LOG.md`. Once the agent completes, run `/skill-genesis-review` to disposition the pending proposals.

Two harvest modes, chosen by what is on disk:

- **Pipeline mode** — the live `.ai-work/<slug>/` directories at the top level. One spawn.
- **Queue mode** — a harvest queue (`.ai-work/_harvest/` by default, or `--sources <dir>`) holding one parked pipeline directory per sub-directory, sometimes one level deeper when a worktree's whole `.ai-work/` tree was copied in. The queue is enumerated and batched by `scripts/list_harvest_sources.py`; one spawn per batch, in sequence.

## Flags

| Flag | Description |
|------|-------------|
| `--since <commit>` | Scope the harvest to learning sources newer than the given commit. Passes the commit reference to the agent so it focuses triage on recent changes. |
| `--scope <area>` | Narrow the harvest to a specific area (e.g., `agents`, `rules/swe`, `dashboard_app`). Useful when a long pipeline touched a focused surface and you want targeted proposals. |
| `--sources <dir>` | Harvest queue directory for queue mode. Defaults to `.ai-work/_harvest/` when that directory exists; pass explicitly to harvest another queue. A source is any directory at depth ≤ 2 under it holding `LEARNINGS.md`, `VERIFICATION_REPORT.md` or a `CONSULT_*.md` fragment. |
| `--cap <bytes>` | Queue mode only: maximum source bytes per spawn (default 200,000 ≈ 50k tokens). A single source over the cap becomes its own batch, flagged oversize, and the agent samples it by section. |
| `--dry-run` | Preview which learning sources would be harvested without spawning the agent. In queue mode this prints the enumeration script's table — per source: bytes, whether a prior report already cites it, whether a memory file names its slug — and the batch plan. In pipeline mode it lists the detected sources (LEARNINGS.md, VERIFICATION_REPORT.md, SENTINEL_REPORT, IDEA_LEDGER, recent ADRs). |

## Process

### 1. Parse arguments

Parse `$ARGUMENTS` for the five optional flags:

```
--since <commit>      Sets the harvest commit boundary (passed to agent as `since`)
--scope <area>        Sets the harvest area filter (passed to agent as `scope`)
--sources <dir>       Queue directory (default .ai-work/_harvest/ when present)
--cap <bytes>         Queue mode batch cap (default 200000)
--dry-run             Preview mode: list sources and batches; do not spawn agent
```

### 2. Generate task slug

When invoked inside an active pipeline (a `.ai-work/<slug>/` directory exists with a
`WIP.md`), inherit the parent pipeline's slug. Otherwise derive a standalone slug:

```
skill-genesis-YYYY-MM-DD
```

Append `_2`, `_3`, … on collision (if `.ai-work/skill-genesis-YYYY-MM-DD/` already exists).

### 3. Pre-flight — detect learning sources

**Queue mode** applies when `--sources <dir>` is given or `.ai-work/_harvest/` exists. Run
the enumeration script from the repository root and read its output whole:

```
python3 scripts/list_harvest_sources.py [--sources <dir>] [--cap <bytes>] --memory-dir <harness memory directory>
```

The harness memory directory is the path the system prompt announces for this project's
memory; pass it so the `memory` marker can be computed, omit it when unknown (the marker is
then withheld as `n/a`, never reported as `no`). The script exits `2` with
`no harvest sources` when the queue is missing or empty — fall through to pipeline mode.

Read the two markers for what they are: `prior-report: yes` means an existing
`SKILL_GENESIS_REPORT_*.md` already cites that source; `memory: yes` means a memory file names
its slug. Neither says *everything* in the source was captured, so flagged sources are still
harvested — the agent reads them for deduplication and extracts only what the cited artifact
lacks.

**Pipeline mode** applies otherwise. Scan for harvestable sources and exit with a "nothing new
to harvest" message if none are found:

- Any `.ai-work/*/LEARNINGS.md` (non-empty)
- Any `.ai-work/*/VERIFICATION_REPORT.md`
- Any `.ai-state/sentinel_reports/SENTINEL_REPORT_*.md` newer than the most recent
  `SKILL_GENESIS_REPORT_*.md` in `.ai-state/skill_genesis_reports/`
- Any `.ai-state/idea_ledgers/IDEA_LEDGER_*.md`
- Any recent `.ai-state/decisions/*.md` (ADRs created since the last harvest)

When `--since <commit>` is provided, apply it as an additional filter (prefer sources
modified after that commit).

**`--dry-run` exit point**: when `--dry-run` is set, print the enumeration (the script's table
and batch plan in queue mode; the detected-source list or the "nothing new" message in
pipeline mode) and exit without spawning the agent.

### 4. Delegate to the skill-genesis agent in background mode

Invoke the `skill-genesis` agent via the `Task` tool. The agent runs with `background: true`,
so this command returns to the user immediately after spawning.

**Pipeline mode** — one spawn. Pass in the task prompt:

```
Task slug: <slug>
Invocation args:
  since: <commit or null>
  scope: <area or null>
  sources: null
  batch: null
  dry_run: false
Write the report to: .ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_<YYYY-MM-DD_HH-MM-SS>.md
```

**Queue mode** — one spawn per batch from the script's plan, **in sequence**: spawn the next
batch only when the previous batch's completion notification has arrived. Sequencing keeps
the second-resolution report filenames distinct and lets each batch's deduplication see the
reports its predecessors wrote in this run. Pass in the task prompt:

```
Task slug: <slug>
Invocation args:
  since: <commit or null>
  scope: <area or null>
  sources: <queue dir>
  batch: <i> of <N>
  dry_run: false
Sources (read each listed directory's LEARNINGS.md, VERIFICATION_REPORT.md and CONSULT_*.md in place of `.ai-work/<slug>/`):
  - <queue dir>/<rel>  (<bytes> bytes; prior-report: yes|no; memory: yes|no|n/a)
  - ...
Oversize: <yes — sample by section | no>
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

In queue mode add the batch position (`batch <i> of <N>; <N − i> to follow`) and, after the
last batch completes, the list of reports this run produced. `/skill-genesis-review` walks
pending reports newest-first, one per pass.

Track progress via the run-log above or the background task's own output — the agent no
longer maintains a separate `PROGRESS.md` phase-transition log.
