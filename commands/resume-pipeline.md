---
description: "Reconcile a pipeline's WIP.md against ground truth (git + tests + the observations.jsonl WAL) and auto-recover truncated steps — auto-mark verified-complete work, auto-resume partial work, surface the ambiguous — leaving a full audit trail on every action."
allowed-tools: [Read, Edit, Glob, Grep, Bash(reconcile_pipeline_state.py:*), Bash(python3:*), Bash(git:*), Agent]
argument-hint: "<task-slug> [--dry-run] [--base-ref <ref>]"
disable-model-invocation: true
---

## Help

```
/resume-pipeline — recover a pipeline whose agents may have truncated mid-work

USAGE
  /resume-pipeline <task-slug> [options]

  Runs reconcile_pipeline_state.py to classify every WIP.md step against ground
  truth, then acts per verdict: auto-mark verified-complete steps, auto-resume
  partial/in-flight steps (scoped to the unfinished remainder), and surface
  `unknown`, `blocked` and `attempts-exhausted` steps to you. Every automatic action is recorded in five places
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
  2   one or more `unknown`, `blocked` or `attempts-exhausted` steps, or an `Attempts:` line naming no step, surfaced for your decision
  3   reconcile error (no WIP.md for the slug, bad slug, plugin-cache path)
```

## Arguments

`$ARGUMENTS` holds the invocation. Parse it as: the first non-flag token is the **task slug**
(required), plus the optional `--dry-run` and `--base-ref <ref>` documented above.

- **Non-empty** — the slug names the pipeline to reconcile: `<worktree_root>/.ai-work/<slug>/`.
  Both flags apply to the pass as a whole, not to individual steps — `--dry-run` suppresses every
  action across every step, and `--base-ref` is the diff base for every step's Tier-1 evidence.
  Never mix the modes: a partially-applied dry run is worse than either.
- **Empty (no slug)** — do not guess and do not run the reconciler. Recovering the wrong pipeline
  writes to five audit surfaces under a slug the user never named. List the slugs under
  `<worktree_root>/.ai-work/` that have a `WIP.md`, ask for one, and exit 3.

## Why this exists

A subagent hard-truncated at its context ceiling can finish real work but die
before flipping its `WIP.md` checkbox — or leave a stale `[COMPLETE]` claim. The
checkbox is a Tier-3 agent-authored claim and cannot be trusted. This command
re-derives the truth from the two strata that do not lie — **Tier 1** (codebase +
`git diff` + `TEST_RESULTS.md`, the arbiter) and **Tier 2** (the harness WAL
`.ai-state/observations.jsonl`, a localization hint) — and repairs the pipeline
position. It restores *position*, not *correctness sign-off*; the verifier remains
the behavioral gate.

A `HANDOFF.md` left by a previous window is **Tier-3 evidence**, the same stratum as
the `WIP.md` checkbox: useful orientation, never an authority. Where it disagrees with
a Tier-1 verdict the verdict wins, and the disagreement is **reported in the resume
summary** — never silently overridden in either direction. That one rule is what keeps
a convenience document from becoming a correctness hazard.

## Procedure

1. **Read the handoff, if there is one (orientation only).** Parse the slug out of
   `$ARGUMENTS` per **Arguments** above; `worktree_root = git rev-parse --show-toplevel`.
   If `<worktree_root>/.ai-work/<slug>/HANDOFF.md` exists, read it before anything else:
   its Preflight and Next action sections orient you, and its **Operating constraints
   from the user** and **Corrections in force** sections are standing instructions that
   apply from this point on. If its header carries `readiness: overridden`, the handoff
   was composed over a non-quiescent tree — say so in the resume summary and treat its
   State section as unverified until the reconcile below re-derives it from ground truth.
   If there is no handoff, continue; the reconciler never needed one.
2. **Resolve the slug and roots.** The slug's pipeline lives at
   `<worktree_root>/.ai-work/<slug>/`; the remaining flags parse per **Arguments** above.
3. **Reconcile (read-only).** Run the reconciler. It is installed on `PATH` by
   `install_claude.sh` (linked into `~/.local/bin/`); in the Praxion self-host
   checkout, use `python3 scripts/reconcile_pipeline_state.py` instead:
   ```
   reconcile_pipeline_state.py <slug> \
     --repo-root <worktree_root> --worktree-root <worktree_root> \
     [--base-ref <ref>] --json
   ```
   This mutates nothing (the reconciler is side-effect-free). Parse the verdict
   array. Each verdict carries `step`, `wip_claim`, `verdict`, `needs_mark`,
   `tier1`, `tier2`, `evidence`, `resume_scope` and `decided_by` (`check`, `fallback`
   or `none`: what decided it), plus `outcome_source` (when a declared check decided)
   and `attempt` (when `WIP.md` records a fresh-attempt count for the step). When an `Attempts:` line names
   no step, the array is unchanged: the lines go to stderr, one per line, and the exit status is 2.
4. **Act per verdict** (skip all actions under `--dry-run` — print the plan instead):

   | Verdict | Action |
   |---|---|
   | `verified-complete`, `needs_mark: true` | **Auto-mark**: record the step as complete in the `WIP.md` claim source it came from (checkbox `- [x]` / `[COMPLETE]`, status-table cell, or `[x]` heading marker) and annotate it (see Audit trail). The work is proven done by ground truth; the dying agent just never recorded it. |
   | `verified-complete`, `needs_mark: false` | No action — checkbox already correct. |
   | `mismatch` / `partial@<pt>` / `in-flight` | **Auto-resume**: re-spawn the step's agent (the assignee in the step row) scoped to `resume_scope` only, citing the Tier-1 evidence of what is already done. See "Auto-resume contract". A step whose `Attempts:` line names a request the ledger has not recorded belongs to the driver: run `step_loop.py next <slug>`, never a fresh spawn. Inside the loop the step-loop driver writes the `Attempts:` line ahead, commits a verified step and records the return; outside the loop the orchestrator does. |
   | `unknown` | **Surface, do not act.** Report the step + its evidence to the user and stop on that step. |
   | `blocked` | **Surface, do not act — never auto-mark, never auto-resume.** The step is otherwise done but is tagged `mutation: on` and its results carry no usable `Mutation:` reading. Report the step, the reason in `evidence`, and the two ways out: restore the sensor (environment, network) and re-run it, or amend the plan to drop the tag with a recorded reason. Stop on that step. |
   | `attempts-exhausted` | **Surface, do not act — never auto-mark, never auto-resume.** The step used its fresh attempts without verified completion; another automatic attempt is exactly what the verdict forbids. Report the step, its `evidence` (it carries the underlying verdict and the replan request when `WIP.md` records one) and ask the user to replan, fix or take over. Stop on that step. |
   | `pending` | No action — a not-started step is normal. |

5. **Write the audit trail** for every auto-action (Audit trail, below).
6. **Summarize** to the user: counts per verdict, every auto-mark and auto-resume
   with its evidence, every `unknown` needing a decision, every `attempts-exhausted` step with
   its replan request, and every `blocked` step with its
   reason and the two ways out. Name every point where
   the handoff read in step 1 disagreed with a verdict, stating that the verdict won.
   Point to `RECOVERY_LOG.md` for the full record.

## Auto-resume contract (clobber-safety)

The guard against re-spawning over verified work is structural:

- A `verified-complete` step is **never** a resume target — only `mismatch`,
  `partial`, and `in-flight`. An `attempts-exhausted` step is not one either, whatever
  verdict it would otherwise have had: it already had its fresh attempts. A `blocked` step is not one either: its files are done, and
  re-running the agent cannot produce a sensor reading the environment withholds. For the same
  reason a `blocked` verdict carries an empty `resume_scope` (no file is unfinished; `tier1`
  lists the changed files and the reason lives in `evidence`), unlike the non-empty
  scope of the verdicts above. Do not read "blocked" here as the subagent `[BLOCKED]` marker:
  this is the reconciler's verdict for a step awaiting a mutation reading.
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

**Exit 3 — no slug given:**
```
Cannot resume: no task slug. Pipelines with a WIP.md under this worktree:
  <slug>  (<N> steps, last modified <date>)
To fix: re-run as /resume-pipeline <task-slug>.
```

**Exit 2 — blocked step surfaced:**
```
<N> step(s) are done but tagged `mutation: on` with no usable mutation reading
(verdict: blocked) and were NOT marked complete:
  <Step N>: <evidence>
To fix: restore the sensor (environment, network) and re-run it so the step's results
carry a `Mutation:` line, or amend the plan to drop the tag with a recorded reason.
```

**Exit 2 — attempts exhausted:**
```
<N> step(s) used their fresh attempts without verified completion
(verdict: attempts-exhausted) and were NOT resumed or marked:
  <Step N>: <evidence, including the replan request when one is recorded>
To fix: replan the step, fix its cause, or take it over by hand.
```

**Exit 2 — ambiguous steps surfaced:**
```
<N> step(s) could not be verified from ground truth (verdict: unknown) and were
NOT auto-recovered:
  <Step N>: <evidence>
To fix: inspect the step, then mark it complete by hand or re-run the work.
Unknown = the reconciler refuses to guess; ground truth was inconclusive.
```
