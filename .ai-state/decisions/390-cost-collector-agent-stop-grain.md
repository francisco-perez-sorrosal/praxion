---
id: dec-390
draft_id: dec-draft-c3f0ca68
title: "Cost collector: the agent_stop row is the grain, honest provenance is the only admissible population, and the committed summary gains a slug but no totals"
status: accepted
category: architectural
date: 2026-09-22
summary: "Adds scripts/project_metrics/collectors/cost_collector.py (CostCollector), a Tier-0 read-only collector emitting a `cost` namespace and a `## Cost` report section. Tokens are aggregated at the agent_stop grain keyed by agent_id over a union of per-checkout WALs (plus .1 rotation archives) discovered from git rev-parse --git-common-dir, filtered to usage_source == subagent-transcript; the other three provenance populations are counted by name and never summed. The pipeline slug joins to a tier through calibration_log.md with explicit ambiguous/unknown variants. hooks/capture_session.py's committed summary row gains pipeline_slug additively and nothing else: honest sub-totals were designed and rejected because the fleet-shipped merge driver collapses summary rows by session_id. No aggregate column, no METRICS_LOG.md cell. Guard is a pre-publication provenance invariant that errors with no totals."
tags: [process-economy, roadmap-p3-5, project-metrics, collector, observability, token-accounting, provenance, honest-empty, measurement-instrument, calibration-log, wal]
made_by: agent
agent_type: systems-architect
branch: worktree-process-economy-p3-5
pipeline_tier: standard
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09, REQ-10, REQ-11, REQ-12, REQ-13, REQ-14, REQ-15, REQ-16, REQ-17]
re_affirms: dec-378
affected_files:
  - scripts/project_metrics/collectors/cost_collector.py
  - scripts/project_metrics/runner.py
  - scripts/project_metrics/_report_sections.py
  - scripts/project_metrics/report.py
  - scripts/project_metrics/tests/test_cost_collector.py
  - hooks/capture_session.py
  - hooks/test_capture_session.py
  - docs/metrics/README.md
  - commands/project-metrics.md
  - scripts/CLAUDE.md
  - docs/architecture.md
  - .ai-state/DESIGN.md
---

## Context

The process-economy roadmap's F12 asks whether Standard is worth roughly four times Lightweight. The user
overrode the 2026-10-08 data gate and reframed the deliverable: **build the instrument, not the verdict**
(`.ai-work/process-economy-p3-5/TASK_BRIEF.md`). `/project-metrics` had no cost surface at all, and the two
places token data lives are both hazardous to read naively.

Measured in this repository on 2026-09-22, across five reachable write-ahead logs (47,631 lines, 21.0 MiB,
5,170 `agent_stop` rows → 5,098 distinct `agent_id`s):

- Only **44** rows carry honest per-subagent usage (`usage_source: subagent-transcript`). **286** carry token
  numbers that are the *parent session's cumulative usage* (rows written before commit `23b1bbc5`, which lack
  the `usage_source` key entirely); **4,768** carry no usage at all; **0** carry `parent-transcript`.
- The committed per-session rollup `.ai-state/observations_summary.jsonl` sums token fields **regardless of
  provenance** (`hooks/capture_session.py::_tokens_by_agent_type` filters only on "at least one field is
  populated"). One committed row consequently records **14,666,970,597 tokens** for a single session — an
  arithmetically impossible figure that no downstream filter can repair.
- A `session_id` is not scoped to a checkout. Session `f24cda13` has three different committed rollups — an
  empty one on main, 404,929,898 tokens in `process-economy-p3-2-adopt`, 430,370,366 in
  `process-economy-p3-6-adopt`.
- `.ai-state/calibration_log.md`'s `Actual Tier` cell is prose-decorated in 38 of 128 rows, but its leading
  alphabetic token lands in the five-tier enum for **128/128**. Five slugs match several rows, and **three of
  those disagree on tier** (`sentinel-fanout-audit`, `process-economy-phase1`, `process-economy-p2-residual`),
  so slug → tier is not a function.

The design question was therefore not arithmetic but representation: what is the unit of cost, and where does
the pipeline identity live.

## Decision

Add **`CostCollector`** (`scripts/project_metrics/collectors/cost_collector.py`), a Tier-0, always-available,
read-only collector registered last in `runner.py::default_registry`. It emits a `cost` namespace at the
metrics-JSON root and a `## Cost` Markdown section. Five clauses:

1. **The grain is the `agent_stop` row keyed by `agent_id`** — not the session, not the summary rollup. Rows
   are read from a union of per-checkout WALs and their `.1` rotation archives, de-duplicated last-in-file /
   first-across-files.
2. **Provenance is a four-variant classification**, partitioning on the *absence* of the `usage_source` key
   rather than on a value: `attributed` (the only admissible one), `parent-sourced`, `pre-attribution`,
   `unparsed`. Non-admissible populations are counted by name and never enter a total. The committed summary's
   provenance-blind rollups are counted separately as `summary-rollup-unattributed`.
3. **Source discovery is anchored on `git rev-parse --path-format=absolute --git-common-dir`**, so the main
   checkout and every sibling worktree of the same repository resolve to the same source set regardless of the
   cwd the collector runs from. Unavailable git degrades to `repo_root` only with a named issue.
4. **`hooks/capture_session.py`'s committed summary row gains `pipeline_slug` and nothing else**, derived by
   the same helper that derives a WAL row's `project`. Honest sub-totals on that row are explicitly *not*
   added.
5. **No verdict, no aggregate column.** The F12 cell renders only when both `Standard` and `Lightweight` have
   attributed rows, always with its sample sizes and basis; otherwise it reads `n/a` with the reason. No column
   joins the frozen aggregate block and no cell joins the append-only `METRICS_LOG.md` (re-affirms `dec-378` on
   the reasoning `dec-388` used for the mutation sensor).

The `dec-378` guard is a **pre-publication provenance invariant** inside the collector: `attributed +
parent-sourced + pre-attribution + unparsed == total_agent_stop_rows` and `sum(per-pipeline attributed) ==
attributed`. A violation returns `status: "error"` with **no totals** and a named issue; a fault-injection test
forces a non-honest row past the classifier and asserts exactly that. Measured cost of the addition: 0.059 s
warm / 0.164 s cold over the full 21.0 MiB corpus, 0 new dependencies, 0 always-loaded tokens.

## Considered Options

### Grain

| Option | Pros | Cons |
|---|---|---|
| **Agent-stop grain keyed by `agent_id` (chosen)** | Measured 0 of 5,098 ids appear in more than one file, so union is safe by construction; within-file repeats do occur (48 per-file honest rows collapse to 44), so dedup is load-bearing; the honesty filter, the tier join and the dedup all key off one row | Machine-local — WALs are gitignored since `dec-377`, so a fresh clone or the weekly CI job reports an honest empty section |
| Session grain over the committed summary | Durable, committed, visible in CI | The rollup is provably inadmissible (14.7 billion tokens in one row) and a session spans checkouts with three different rollups — a session-keyed total must double-count copies or discard data |
| Hybrid: agent grain where a WAL is reachable, summary rollup as fallback | Would fill the CI/fresh-clone hole | Needs a *new* honest summary field that the merge driver discards (below); precedence between two partial sources cannot be decided honestly (rotation truncation vs merge collapse — "pick the bigger" is a guess); doubles the aggregation paths for a benefit that is zero today |

### Summary-row schema

| Option | Pros | Cons |
|---|---|---|
| **`pipeline_slug` only (chosen)** | One line in the hook; no key changes meaning; gives the coverage census its pipeline dimension; zero fleet risk | The durable committed artifact carries no honest cost data |
| `pipeline_slug` + `usage_attribution` honest sub-totals | Would make the committed row a durable cost record readable in CI | `scripts/reconcile_ai_state.py::reconcile_observations_summary` — the merge driver registered in every onboarded project's git config — merges **by `session_id` alone**, keeping the later `ended_at` and discarding the other checkout's row. The sub-totals would look complete and be structurally partial, with no marker. Correcting that means re-keying a fleet-shipped, version-pinned merge driver whose defects are silent and land in committed history |
| No summary change; WAL `project` only | Smallest change | Loses the pipeline dimension of the durable session census; contradicts the brief's S5 |

## Consequences

**Positive**

- Every rendered number is traceable to a row that carries its own provenance marker; the 286-row
  parent-cumulative population cannot reach a total through any code path, and a leak fails loudly.
- The report states how little it stands on (44 attributed rows over 5,098) instead of implying breadth.
- Source-set symmetry means the instrument gives the same answer from main and from any worktree — the property
  a measuring instrument most needs.
- `ambiguous` and `unknown` tier variants keep contested and unjoinable pipelines visible rather than
  fabricating or dropping them.
- Reads are streamed and stdlib-only; the whole pass is sub-1% of a `/project-metrics` run.

**Negative**

- Cost data is machine-local. The weekly `audits.yml` report will render `## Cost` with
  `coverage: 0 attributed / 0 total` and a reason — honest, but empty. Durable per-pipeline cost history needs
  the merge driver re-keyed on `(session_id, pipeline_slug)` first; that is named as the follow-up, not
  attempted here.
- Rotation past `.1` destroys history permanently.
- The collector reads outside `repo_root` (sibling worktrees) and over a file that grows during the run, so the
  collector protocol's byte-identical-output contract does not hold for it. Mitigated, not eliminated, by
  publishing every source path/kind/mtime in the payload — the precedent `CoverageCollector` set with
  `coverage_artifact_mtime`.
- The dashboard's collector strip iterates `tool_availability`, so a new "cost" chip appears. Additive and
  benign, but a visible change.

## Disconfirmation

**Falsifier.** *Name the component.* `scripts/project_metrics/collectors/cost_collector.py` (`CostCollector`) is a
new member of the `Scripts` artifact family and a new member of the metrics runner's frozen collector registry;
the responsibility "decide which token rows are admissible" moves from nowhere (no component held it — the
committed rollup summed everything it found) to that collector's classifier, and "publish per-pipeline token
cost" moves from nobody to the metrics report. That is what makes this `architectural` rather than `behavioral`.
It adds **no** `DESIGN.md` §3a structural row and no LikeC4 element — the collector lives inside the existing
`Project metrics command` capability and the filesystem-scanned `Scripts` catalog, the same disposition taken for
the ADR-checkpoint and mutation-sensor scripts.

*Falsify the decision itself.* Find one `agent_id` present in two source files with differing usage, or one pipeline whose
attributed total at the agent grain is provably lower than a *correct* session-grain total over the same
corpus. Either finding invalidates the grain. For the summary clause: show a git merge in which two branches
both carry a summary row for one `session_id` and **both survive** — that would refute the collapse and make
the rejected `usage_attribution` option viable immediately.

**Steelmanned runner-up.** The hybrid (agent grain with the committed summary as a durable fallback, backed by
honest sub-totals on the summary row) is the design this decision declines, and its case is genuinely strong:
`dec-377` moved the raw WAL out of git *specifically* so a compact committed rollup would carry history to a
fresh clone, and this decision then refuses to use that rollup for the one metric the pipeline is about. The
result is an instrument that, in the one execution environment the project runs automatically and weekly
(`.github/workflows/audits.yml`), reports nothing at all — arguably the worst place for an instrument to be
silent. The counter is narrow and factual: the merge driver collapses per-checkout rows by `session_id`, so the
durable number would be structurally incomplete and unmarked, and a knowingly-lossy committed figure is worse
than a stated absence. The absence is *reported* (`summary-rollup-unattributed` in the coverage census), which
keeps the gap visible and fixable rather than papered over.

**Reversal trigger.** Re-key `reconcile_observations_summary` on `(session_id, pipeline_slug)`. The moment that
lands, add `usage_attribution` to the summary row and re-open the grain decision in favour of the hybrid —
the fallback becomes trustworthy and the CI hole closes. A second, independent trigger: if the cost figure
begins to vary meaningfully between consecutive reports on the same repository, revisit the no-aggregate-column
clause.
