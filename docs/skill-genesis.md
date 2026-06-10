---
diataxis: how-to
audience: developer
---

# Harvesting Learnings with Skill-Genesis

A how-to for the pull-driven skill-genesis flow: when to run `/skill-genesis`, what the report contains, how to disposition proposals via `/skill-genesis-review`, and understanding when artifacts should be formalized from accumulated experience.

## Table of contents

- [Why this guide exists](#why-this-guide-exists)
- [The flow at a glance](#the-flow-at-a-glance)
- [When to run /skill-genesis](#when-to-run-skill-genesis)
- [Quick start — first harvest](#quick-start--first-harvest)
- [Walkthrough — dispositioning a report](#walkthrough--dispositioning-a-report)
- [Understanding maturity, scope, and priority](#understanding-maturity-scope-and-priority)
- [Deferred and refined proposals](#deferred-and-refined-proposals)
- [Memory-disabled projects](#memory-disabled-projects)
- [Troubleshooting](#troubleshooting)
- [How it works under the hood](#how-it-works-under-the-hood)
- [Related](#related)

## Why this guide exists

Skill-genesis previously fired at the end of every pipeline and presented patterns one-by-one via interactive prompts — exactly when a long pipeline had just landed and you were least interested in another decision cycle. The cognitive load landed on top of an already-saturated session.

This guide documents the pull-driven inversion that decouples learning harvest from learning disposition. The harvest (an autonomous background agent pass that writes a permanent report) happens on your command, not the pipeline's. The disposition (approving proposals, refining descriptions, delegating artifact creation) happens separately, whenever you're ready — sometimes minutes later, sometimes days. Compare to the rework-dispatch model: same cognitive-load problem, same architectural fix (defer the decision moment). The merge moment stops being a decision-cycle moment; you decide when to harvest.

## The flow at a glance

Skill-genesis operates as a two-edge loop, temporally decoupled:

**Edge 1 (Harvest):** You invoke `/skill-genesis`. The agent runs autonomously in the background, analyzes accumulated learning sources (LEARNINGS.md, verification reports, sentinel findings, memory entries, decision records), triages them into artifact proposals, and writes a timestamped report to `.ai-state/skill_genesis_reports/`. The agent never blocks and never asks you a question.

**Edge 2 (Disposition):** Later (minutes, hours, or days), when you're ready to decide which proposals matter, you invoke `/skill-genesis-review`. The command auto-discovers the latest unreviewed report, presents every pending proposal in a single batch multi-select, records your disposition (approve / reject / refine / defer) in an append-only log, and surfaces recommended delegations if any proposals were approved.

The key insight: **the harvest is async and always-ready; the decision is sync and always-optional.** You run `/skill-genesis` when you expect signal from accumulated learnings. You run `/skill-genesis-review` when you have the cognitive space to approve artifacts. If neither happens, the report sits durably in `.ai-state/` — nothing is lost, and no merge is blocked.

## When to run /skill-genesis

Run `/skill-genesis` when accumulated learnings are worth harvesting:

- **After a feature pipeline completes** — the planner merged LEARNINGS.md into `.ai-work/` during execution. Skill-genesis extracts patterns worth formalizing.
- **At the end of a working session** — before you merge, harvest the session's patterns so they're captured before cleanup.
- **Periodically** (weekly, monthly) — if your project accumulates `.ai-work/` between formal pipelines, skill-genesis can run standalone to harvest those learnings.
- **With `--since <commit>`** — scope the harvest to recent work when you want a focused set of proposals.

**Do NOT run immediately mid-pipeline** — let the pipeline write LEARNINGS.md first. Mid-pipeline harvests will miss the session's final learnings.

**Do NOT run on a fresh project** — no learnings exist yet. Wait until `.ai-work/` or memory entries have accumulated.

## Quick start — first harvest

**Step 1.** Run the command:

```bash
/skill-genesis
```

You see:

```
Skill-genesis agent spawned in the background.

Expected report: .ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_2026-05-15_14-32-58.md
Run-log:         .ai-state/skill_genesis_reports/SKILL_GENESIS_LOG.md

Once the agent completes, run /skill-genesis-review to disposition the pending proposals.
```

The agent is working in the background. You can close this pane, continue other work, or check progress:

```bash
# Check the agent's phase transitions
cat .ai-work/skill-genesis-<slug>/PROGRESS.md

# Check the run-log to see when harvests completed
cat .ai-state/skill_genesis_reports/SKILL_GENESIS_LOG.md
```

**Step 2.** Once the agent completes (check PROGRESS.md or wait for a phase-final line), the report exists:

```bash
cat .ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_2026-05-15_14-32-58.md
```

The report has:
- A summary (how many sources were analyzed, how many items were extracted, how many proposals were generated)
- A "Learning Sources Consumed" table (which input sources were read)
- A "Triage Results" table (each learning item and why it was proposed or skipped)
- Numbered "Proposals" sections (the meat — each with type, maturity, scope, priority, description, and rationale)
- A "Recommended Delegations" table (where each proposal should go if approved)
- An empty "Disposition Log" (populated by `/skill-genesis-review`)

**Step 3.** Skim the report. No action needed yet — this is just visibility.

## Walkthrough — dispositioning a report

When you're ready to approve, refine, or reject proposals:

**Step 1.** Run:

```bash
/skill-genesis-review
```

The command auto-discovers the most recent unreviewed report and presents a multi-select:

```
Pending proposals from SKILL_GENESIS_REPORT_2026-05-15_14-32-58.md:

☐ Proposal 1: CLI argument parsing (skill, new, P0)
☐ Proposal 2: Environment variable conventions (rule, new, P1)
☐ Proposal 3: Token budgeting pattern (memory, P0)
☐ Proposal 4: Refactor request logging (rule, update, P1)

Select which proposals to disposition (space to toggle, enter to confirm):
```

**Step 2.** Toggle the proposals you want to decide on (you can disposition only a subset; the rest remain pending). Press Enter.

**Step 3.** For each selected proposal, you see a single-select:

```
Proposal 1: CLI argument parsing

What's your disposition?
  approve   — accept the proposal; will be delegated or executed
  reject    — discard the proposal; no action taken
  refine    — keep as pending refinement; adjust scope / name / type first
  defer     — postpone the decision; remains pending for a future pass
```

Choose one. If you choose **refine**, you're asked for a note:

```
Refinement note for Proposal 1:

"Change 'CLI argument parsing' to 'CLI validation layer' — broader scope,
and coordinate with the TUI-design skill's input-handling conventions"
```

**Step 4.** After you disposition all selected proposals, the command updates the report in place:

- Appends rows to the `## Disposition Log` with timestamps and your choices
- Updates the frontmatter `review_status` (pending → partial if some are dispositioned; partial → complete if all are done)
- Updates the `SKILL_GENESIS_LOG.md` run-log row

Then it surfaces approved proposals:

```
Approved delegations:

Proposal 1 — CLI argument parsing (skill, new)
  → Delegate to: context-engineer (create skills/cli-design/references/argument-parsing.md)

Proposal 3 — Token budgeting pattern (memory, P0)
  → Execute directly via remember MCP tool

Spawn delegations now, or defer to a later session?
  spawn now  — invoke context-engineer and execute memory entries immediately
  defer      — print the commands; you'll action them later
```

If you choose **spawn now**, the context-engineer is invoked with the proposal description. If you choose **defer**, you get a command to copy-paste later.

**Step 5.** A final summary:

```
Disposition pass complete.

  Approved:  2 proposal(s)
  Rejected:  1 proposal(s)
  Refined:   0 proposal(s)
  Deferred:  1 proposal(s)
  Remaining: 0 proposal(s) still pending

Report: .ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_2026-05-15_14-32-58.md
Review status: complete
```

## Understanding maturity, scope, and priority

Each proposal in the report is classified on three axes. These help you disposition at speed without reading every rationale in full.

**Maturity** — how cooked is the idea?

| Level | Meaning |
|-------|---------|
| **seedling** | Barely an observation; needs refinement before creating an artifact. Good refine candidates. |
| **sapling** | A coherent pattern with enough evidence to propose; ready for creation. |
| **mature** | A fully-formed, battle-tested pattern with multiple supporting examples. Safe to approve and delegate immediately. |

**Scope** — how much code/docs does the artifact touch?

| Level | Meaning |
|-------|---------|
| **narrow** | Single file, or a local config change. Safe to approve quickly. |
| **medium** | A new skill or rule that spans multiple references, or an update to an existing artifact. Worth reviewing the description. |
| **broad** | Cross-cutting changes (CLAUDE.md edits, wide skill scope, or coordination-protocol changes). These deserve careful consideration. |

**Priority** — when does the user likely want this?

| Level | Meaning |
|-------|---------|
| **P0 (this-cycle)** | Fix a blocker in the current work. Approve immediately. |
| **P1 (next-cycle)** | Improves ongoing workflows; act on in the next feature or maintenance pass. |
| **P2 (someday)** | Nice-to-have; low urgency. Good defer candidates for later triage. |

**Decision rule:** Mature + narrow + P0 → **approve immediately**. Seedling + broad + P2 → **defer or refine**. Everything else lives in the middle — read the description and decide based on context.

## Deferred and refined proposals

Deferred and refined proposals remain in the report as pending:

- **Deferred** proposals have no opinion yet. Re-run `/skill-genesis-review` later, and deferred proposals will re-appear for you to decide.
- **Refined** proposals are pending-refinement — you noted a change needed. Re-run `/skill-genesis-review` later, and they'll re-appear with your refinement note visible, ready to finalize.

This is the idempotency contract: `/skill-genesis-review` is safe to run multiple times on the same report. Only pending and pending-refinement proposals are presented; already-dispositioned ones are skipped.

Example workflow:
1. Run `/skill-genesis-review` and disposition 3 proposals, deferring 2
2. Later, run `/skill-genesis-review` again — only the 2 deferred proposals appear
3. Disposition those 2 — now all 5 are done
4. Run `/skill-genesis-review` a third time on the same report — it exits immediately with a no-op (report is complete)

## Memory-disabled projects

skill-genesis proposes skills, rules, and CLAUDE.md additions; it does not propose cross-session memory entries — the in-house memory subsystem was removed (dec-225). The harvest sources are `LEARNINGS.md`, verification reports, sentinel findings, and ADR patterns.

## Troubleshooting

<details>
<summary>No unreviewed report found</summary>

You've run `/skill-genesis-review` but no report exists yet. Solution: run `/skill-genesis` first to create a harvest report, then wait for it to complete (check PROGRESS.md for phase transitions).

</details>

<details>
<summary>Report seems wrong — proposals don't match my learnings</summary>

The agent's triage decisions live in the report's `## Triage Results` section. Each learning item is listed with the agent's decision (Skill / Rule / Memory / CLAUDE.md / Skip) and rationale. Read that section to understand why a learning was (or wasn't) proposed.

If you disagree with the decision, `/skill-genesis-review` accepts `--refine` — use it to adjust a proposal's description, scope, or type before approving. This captures your correction.

</details>

<details>
<summary>I want to disposition only some proposals</summary>

The multi-select is your friend. Toggle only the proposals you want to decide on. The rest remain pending. Re-run `/skill-genesis-review` later to tackle the others.

</details>

<details>
<summary>Re-running /skill-genesis-review shows the same proposals</summary>

The command appends to the `## Disposition Log` when you disposition proposals. If you re-run and see the same proposals, either:

1. The dispositions weren't persisted to the report file (check that the file is writable and the report path is correct)
2. You're running against a different report (use `--report <path>` to force a specific one)

Try `cat .ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_*.md | grep "review_status"` to check the frontmatter status of all reports.

</details>

<details>
<summary>The agent crashed or didn't write a report</summary>

Check `.ai-work/<slug>/PROGRESS.md` for phase-transition signals. The report is only written if the agent completes all 7 phases. If a phase failed:

- Phase 1–2 (Scope, Source Analysis): typically means no learnings exist. Run `/skill-genesis-review` and you'll see a "nothing to harvest" message.
- Phase 3–4 (Dedup, Triage): unlikely to fail; internal logic error. Check logs.
- Phase 5–7 (Proposals, Delegation, Report): report-writing failed. Check disk space and `.ai-state/skill_genesis_reports/` permissions.

</details>

## How it works under the hood

<details>
<summary>Why two commands instead of one?</summary>

The harvest and disposition have orthogonal lifecycles. Harvest is async and may complete in the background after you've moved on to other work. Disposition is sync — you decide when to interrupt and answer the batch multi-select. Coupling them would reintroduce the cognitive-load problem this design exists to solve.

**Sentinel follows the same pattern.** The agent runs autonomously and writes reports; the user consumes them later via direct reads or by asking Claude to analyze them. There is no `/sentinel-review` command because sentinel's findings are diagnostic (no artifact creation), but the temporal decoupling principle is the same: autonomous report-writing is always-ready; user decision-making is always-optional.

Skill-genesis is the first to add the disposition edge — this is a new pattern that other future harvesters may follow.

</details>

<details>
<summary>Why .ai-state/ instead of .ai-work/?</summary>

Reports go to `.ai-state/` (persistent, committed, per-project) because:

1. **Durability across pipeline cleanup.** `.ai-work/` is gitignored and cleaned up after a pipeline. Reports live longer than that — they accumulate over time, and you may disposition them days later.
2. **Team visibility.** Reports in `.ai-state/` are committed to git and visible to teammates. `.ai-work/` is local and ephemeral.
3. **Precedent.** This matches sentinel's pattern (reports in `.ai-state/sentinel_reports/`), lowering cognitive load.
4. **Separation of concerns.** The `.ai-state/` directory is where canonical project intelligence lives (decisions, specs, deployments, metrics). Skill-genesis reports are project intelligence.

</details>

<details>
<summary>What if I accumulate dozens of pending reports without reviewing them?</summary>

No problem — they're durable and visible. The run-log (`.ai-state/skill_genesis_reports/SKILL_GENESIS_LOG.md`) lists all harvests with their timestamps and review status. You can:

- Review them in any order (use `--report <path>` to pick a specific one)
- Batch-review old ones later when you have time
- Ignore old reports with a clear conscience if you've moved on (the new-harvest always picks the most-recent unreviewed one)

This is the "report accumulation" risk identified in the design; the run-log and "most-recent-first" discovery make the state visible and manageable.

</details>

## Related

- [`agents/skill-genesis.md`](../agents/skill-genesis.md) — the agent definition; describes what sources it reads and how triage works
- [`commands/skill-genesis.md`](../commands/skill-genesis.md) — the `/skill-genesis` command; optional flags for scoping and previewing
- [`commands/skill-genesis-review.md`](../commands/skill-genesis-review.md) — the `/skill-genesis-review` command; detailed disposition behavior and delegation routing
- [`docs/rework-dispatch.md`](rework-dispatch.md) — sibling precedent for the autonomous-then-review pattern; addresses a similar cognitive-load problem in the verifier rework loop
- [`docs/architecture.md` § 10 Pipeline Feedback Loops](architecture.md#10-pipeline-feedback-loops) — architectural rationale for how skill-genesis fits into the larger pipeline graph
