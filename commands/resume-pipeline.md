---
description: "Reconcile a pipeline's WIP.md against ground truth (git + tests + the observations.jsonl WAL) and auto-recover truncated steps — auto-mark verified-complete work, auto-resume partial work, surface the ambiguous — leaving a full audit trail on every action."
allowed-tools: [Read, Edit, Glob, Grep, Bash(reconcile_pipeline_state.py:*), Bash(python3:*), Bash(git:*), Agent]
argument-hint: "<task-slug> [--dry-run] [--base-ref <ref>]"
---

## Help

```
/resume-pipeline — recover a pipeline whose agents may have truncated mid-work

USAGE
  /resume-pipeline <task-slug> [options]

  Runs reconcile_pipeline_state.py to classify every WIP.md step against ground
  truth, then acts per verdict: auto-mark verified-complete steps, auto-resume
  partial/in-flight steps (scoped to the unfinished remainder), and surface
  `unknown` steps to you. Every automatic action is recorded in five places
  (see "Audit trail") — recovery is never silent.

EXAMPLES
  /resume-pipeline auth-flow
  /resume-pipeline auth-flow --dry-run            # classify + show the plan, act on nothing
  /resume-pipeline auth-flow --base-ref main      # diff against the pipeline base

OPTIONS
  --base-ref <ref>   git ref the pipeline branched from (improves change detection
                     for committed work; default: working-tree + HEAD diff)
  --dry-run          reconcile and print the recovery plan; take no action
  --help, -h         show this help

EXIT CODES
  0   nothing to recover (all steps verified-complete or pending) / dry-run done
  1   recovery actions taken (auto-mark and/or auto-resume)
  2   one or more `unknown` steps surfaced for your decision
  3   reconcile error (no WIP.md for the slug, bad slug, plugin-cache path)
```

## Why this exists

A subagent hard-truncated at its context ceiling can finish real work but die
before flipping its `WIP.md` checkbox — or leave a stale `[COMPLETE]` claim. The
checkbox is a Tier-3 agent-authored claim and cannot be trusted. This command
re-derives the truth from the two strata that do not lie — **Tier 1** (codebase +
`git diff` + `TEST_RESULTS.md`, the arbiter) and **Tier 2** (the harness WAL
`.ai-state/observations.jsonl`, a localization hint) — and repairs the pipeline
position. It restores *position*, not *correctness sign-off*; the verifier remains
the behavioral gate.

## Procedure

1. **Resolve roots.** `worktree_root = git rev-parse --show-toplevel`. The slug's
   pipeline lives at `<worktree_root>/.ai-work/<slug>/`.
2. **Reconcile (read-only).** Run the reconciler. It is installed on `PATH` by
   `install_claude.sh` (linked into `~/.local/bin/`); in the Praxion self-host
   checkout, use `python3 scripts/reconcile_pipeline_state.py` instead:
   ```
   reconcile_pipeline_state.py <slug> \
     --repo-root <worktree_root> --worktree-root <worktree_root> \
     [--base-ref <ref>] --json
   ```
   This mutates nothing (the reconciler is side-effect-free). Parse the verdict
   array. Each verdict carries `step`, `wip_claim`, `verdict`, `needs_mark`,
   `tier1`, `tier2`, `evidence`, `resume_scope`.
3. **Act per verdict** (skip all actions under `--dry-run` — print the plan instead):

   | Verdict | Action |
   |---|---|
   | `verified-complete`, `needs_mark: true` | **Auto-mark**: flip the step's `WIP.md` checkbox to `- [x]` / `[COMPLETE]` and annotate it (see Audit trail). The work is proven done by ground truth; the dying agent just never recorded it. |
   | `verified-complete`, `needs_mark: false` | No action — checkbox already correct. |
   | `mismatch` / `partial@<pt>` / `in-flight` | **Auto-resume**: re-spawn the step's agent (the assignee in the step row) scoped to `resume_scope` only, citing the Tier-1 evidence of what is already done. See "Auto-resume contract". |
   | `unknown` | **Surface, do not act.** Report the step + its evidence to the user and stop on that step. |
   | `pending` | No action — a not-started step is normal. |

4. **Write the audit trail** for every auto-action (Audit trail, below).
5. **Summarize** to the user: counts per verdict, every auto-mark and auto-resume
   with its evidence, and every `unknown` needing a decision. Point to
   `RECOVERY_LOG.md` for the full record.

## Auto-resume contract (clobber-safety)

The guard against re-spawning over verified work is structural:

- A `verified-complete` step is **never** a resume target — only `mismatch`,
  `partial`, and `in-flight`.
- The re-spawn is scoped to `resume_scope` (the files Tier-1 shows still
  *unchanged*), and the brief explicitly lists what git shows already done so the
  agent does not redo it.
- The verdict that authorizes a resume is recomputed from git ground truth at
  resume time — so a step that became complete since the last run will not resume.
- While Sonnet is quota-limited, re-spawn the step's agent on Opus (per the model
  routing override). If the assignee agent is unavailable, fall back to surfacing
  the step as if `unknown`.

## Audit trail (five surfaces — recovery is never silent)

Every auto-mark and auto-resume writes ALL of:

1. **`.ai-work/<slug>/RECOVERY_LOG.md`** (append-only ledger) — one entry:
   ```
   ## <ISO-8601 timestamp> — <Step N> — <auto-mark | auto-resume>
   - Verdict: <verdict> — <evidence>
   - Detected stop-point: <tier2.last_write> (agent <tier2.correlated_agent_ids>, agent_stop=<tier2.agent_stop_seen>)
   - Tier-1 evidence: changed=<tier1.files_changed>; unchanged=<tier1.files_unchanged>; tests=<tier1.tests>
   - Action: <what was done>  | Resume scope: <resume_scope>
   ```
2. **`WIP.md` inline annotation** on the touched step: append
   ` **[AUTO-RECOVERED <timestamp>]**` plus a half-sentence (`verified via git+tests`
   or `resumed: <files>`).
3. **`LEARNINGS.md` `### Recovery Events`** — a one-line `**[resume-pipeline]**`
   entry (create the section if absent) so it flows into the archived feature record.
4. **Real-time user notice** — an in-conversation line per action:
   `⚠ <Step N> <agent> truncated at <stop-point> → <auto-action> (evidence: <…>)`.
5. **Synthetic WAL event** — append one line to `.ai-state/observations.jsonl`
   (fcntl-safe append; one compact JSON object) so recovery is queryable in the
   chronograph/Phoenix pipeline:
   `{"event_type":"recovery","timestamp":"<iso>","project":"<name>","summary":"<Step N>: <action>","file_paths":<resume_scope>,"outcome":"success","classification":"recovery"}`

A recovery is **incomplete** unless all five surfaces are written — this is the
guarantee that "automatic" never means "silent or unaccountable".

## --dry-run mode

Run the reconcile, print the per-step verdicts and the recovery plan (what would
be auto-marked / auto-resumed / surfaced), and exit 0 without touching any file,
spawning any agent, or writing any audit surface.

## Error grammar

**Exit 3 — no pipeline for the slug:**
```
Cannot resume: no WIP.md at .ai-work/<slug>/WIP.md under this worktree.
To fix: confirm the task slug, or run from the worktree holding the pipeline.
```

**Exit 2 — ambiguous steps surfaced:**
```
<N> step(s) could not be verified from ground truth (verdict: unknown) and were
NOT auto-recovered:
  <Step N>: <evidence>
To fix: inspect the step, then mark it complete by hand or re-run the work.
Unknown = the reconciler refuses to guess; ground truth was inconclusive.
```
