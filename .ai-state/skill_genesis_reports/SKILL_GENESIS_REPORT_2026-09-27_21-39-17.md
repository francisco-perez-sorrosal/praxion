---
schema_version: 1
report_id: skill-genesis-2026-09-27_21-39-17
generated_at: 2026-09-28T04:39:17Z
task_slug: skill-genesis-2026-09-28
agent_version: skill-genesis@f5988784
invocation_args: { since: null, scope: null, sources: "/Users/fperez/dev/praxion/.claude/worktrees/remove-chub/.ai-work", batch: "1 of 1", dry_run: false }
review_status: pending
disposition_count: { pending: 5, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-09-27 21:39:17

## Summary

2 learning sources (queue mode, `remove-chub` and `remove-chub-land` pipeline
directories) analyzed. 13 discrete learning items extracted across LEARNINGS.md,
rework fragments (`LEARNINGS_rw1.md`, `LEARNINGS_rw2.md`), and VERIFICATION_REPORT.md
headings. 8 items deduplicated against user memory (rerere/updateRefs traps,
worktree-guard command-text heuristics, consumer-check-includes-llm-readers +
its WebFetch capability corollary) or against `.ai-state/TECH_DEBT_LEDGER.md`
(td-287 CODE_FENCE_RE indentation bug, td-288 spawn_count.py slug-tracking gap).
5 proposals generated, all pending. Review status: pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| Queue source: remove-chub | `.../remove-chub/LEARNINGS.md` | 8 | Read |
| Queue source: remove-chub | `.../remove-chub/LEARNINGS_rw1.md`, `LEARNINGS_rw2.md` | 3 | Read (fragments postdate LEARNINGS.md, unmerged) |
| Queue source: remove-chub | `.../remove-chub/VERIFICATION_REPORT.md` | 0 new (headings only, cross-checked against LEARNINGS) | Sampled (headings) |
| Queue source: remove-chub-land | `.../remove-chub-land/LEARNINGS.md` | 8 | Read |
| Queue source: remove-chub-land | `.../remove-chub-land/VERIFICATION_REPORT.md` | 0 new (headings only, cross-checked against LEARNINGS) | Sampled (headings) |
| Queue source: remove-chub-land | `.../remove-chub-land/LEARNINGS_implementer.md`, `LEARNINGS_test-engineer.md` | 0 new (already folded into LEARNINGS.md per its own preamble) | Read |
| Latest SENTINEL_REPORT_*.md | `.ai-state/sentinel_reports/` | — | Not consulted (queue-mode batch scoped to the two named directories) |
| Latest IDEA_LEDGER_*.md | `.ai-state/idea_ledgers/` | — | Not consulted (no ledger directory found) |
| ADRs (recent) | `.ai-state/decisions/` | — | Not needed — no learning item overlapped an existing decision category |
| TECH_DEBT_LEDGER.md (dedup check) | `.ai-state/TECH_DEBT_LEDGER.md` | 2 matched (td-287, td-288) | Read — excluded per invocation instructions |
| User memory (dedup check) | `~/.claude/projects/-Users-fperez-dev-praxion/memory/` | 3 matched (rerere/updateRefs, worktree-guard heuristics, consumer-check) | Read — excluded per invocation instructions |
| Consult fragments | `CONSULT_*.md` | 0 | Not found in either source directory |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | Global `rerere.enabled`/`rebase.updateRefs` traps during simulated + real rebases | remove-chub-land LEARNINGS.md | Skip (duplicate) | Already captured in memory `feedback_rebase_rerere_updaterefs_traps.md` with full recovery steps |
| 2 | Worktree isolation refuses HOME overrides, "eval" in text, heredocs naming git, compound git forms | remove-chub-land LEARNINGS.md | Skip (duplicate) | Already captured in memory `feedback_worktree_guard_command_text_heuristics.md` |
| 3 | JSON-key consumer check must include prose readers; WebFetch capability gap on 6/7 agents | remove-chub LEARNINGS.md + rw2 | Skip (duplicate) | Already captured in memory `feedback_consumer_check_includes_llm_readers.md`, including the WebFetch/permission-baseline corollary |
| 4 | `CODE_FENCE_RE` misses indented fences in `validate_references.py` | remove-chub-land VERIFICATION_REPORT.md | Skip (tracked) | Already tracked as td-287 |
| 5 | `spawn_count.py` tallies by worktree, not task slug — split-slug remedy invisible | remove-chub-land LEARNINGS.md | Skip (tracked) | Already tracked as td-288 |
| 6 | Generated files (`rules/_manifest.yaml`) re-conflict at every commit touching a rule during rebase; end-state `merge-tree` prediction hides this | remove-chub-land LEARNINGS.md | Rule (update) | Declarative gotcha about rebase mechanics affecting a repeatable pipeline procedure (pipeline worktree lifecycle) |
| 7 | A hook rewrites `token_budget_baseline.json` at tool boundaries; `rebase --continue` refuses the unstaged change — must reset every stop | remove-chub-land LEARNINGS.md | Rule (update) | Same class as #6 — bundle into one "rebase over generated-file churn" addition |
| 8 | Per-file `git patch-id --stable` (base→backup vs main→HEAD) proves which patches a rebase left byte-identical, skipping unneeded light-review | remove-chub-land LEARNINGS.md | Skill (update) | Procedural technique with a clear trigger and payoff — belongs in the pipeline-worktree-lifecycle procedure, not a bare constraint |
| 9 | When main independently "fixes" the same line differently in a rebase conflict, check *why* before overriding (CI's own validator forced main's form) | remove-chub-land LEARNINGS.md | Skip (too narrow) | Single-instance judgment call already explained by td-287; not yet a recurring pattern independent of that bug |
| 10 | Fixing a command's behavior (run → print) invalidates every doc describing its effect, including ordering advice; only pointed-to sites got fixed | remove-chub-land VERIFICATION_REPORT.md (Edge cases) | Skip (too narrow / seedling) | Single occurrence; general "grep for behavior-description sites on a behavior change" is closer to existing doc-engineer trigger conventions than a new formalizable unit — flag for a future harvest if it recurs |
| 11 | Planner coverage gap: a `SYSTEMS_PLAN.md` disposition row had no owning step in any step's `Files:` — orchestrator caught it only by manual cross-check during execution | remove-chub LEARNINGS.md | Rule (update) | Declarative checklist addition for planner/orchestrator handoff — recurring risk class (disposition rows silently unassigned), not procedural narrative |
| 12 | Split large commit-sequence plan items (10-25 files) into 2-5 disjoint-file parallel steps, committed as one union preserving the architect's original commit message, to fit the implementer's ~80-turn/2-step budget | remove-chub LEARNINGS.md | Skill (update) | Procedural pattern with clear trigger (large commit-sequence item vs. turn budget) and payoff — extends the existing spawn-budget/batched-improvements guidance |
| 13 | `mutation_sensor.py` v1 is Python-only and flat-layout-only; when a mutation-tagged step targets shell scripts, the correct disposition is `Mutation: unavailable` (verbatim tool refusal), never a fabricated survivor count or a synthetic Python shim | remove-chub rw2 | Rule (update) / Skill (update) | Declarative convention (what to write when the tool cannot run) with a narrow procedural payoff — routed to testing-strategy's existing mutation-sensor documentation |

## Proposals

### Proposal 1: Rebase-over-generated-files gotcha in pipeline-worktree-lifecycle

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: sapling
- **Scope**: medium
- **Priority**: P1
- **Source(s)**: remove-chub-land `LEARNINGS.md` § Gotchas — "A generated file (`rules/_manifest.yaml`) re-conflicts at *every* commit that touches a rule; the end-state `merge-tree` prediction hides these. Budget a regenerate per stop." and "A hook rewrites today's `token_budget_baseline.json` row in place at tool boundaries; `rebase --continue` refuses the unstaged change. The continue script must reset it (and park the WAL summary tail) on every stop."
- **Description**: Add a declarative gotcha to the pipeline-worktree-lifecycle content (`skills/software-planning/references/agent-pipeline-details.md#pipeline-worktree-lifecycle`, or the coordination-details.md pointer section) naming the class of generated/hook-rewritten files (`rules/_manifest.yaml`, `token_budget_baseline.json`, and any future regenerate-on-edit artifact) that re-conflict at every touching commit during a rebase, and that a whole-range `merge-tree --write-tree` end-state prediction will not surface per-commit. State the remedy: regenerate/reset such files at every `rebase --continue` stop, not just at the end.
- **Rationale**: This is a repeatable procedural risk for any future rebase-heavy pipeline stage (worktree merges, rework rebases) that touches rule files or WAL-adjacent state — exactly the kind of file the ecosystem already treats specially (manifest regeneration gate, WAL hooks). Formalizing it prevents re-discovering the same conflict class pipeline after pipeline.
- **Estimated scope**: single rule/reference-file edit (a few lines, table row or bullet)
- **Overlap check**: `feedback_worktree_merge_wal_race.md` (memory) covers a related but distinct WAL race (commit-dirt ordering during ff-merge, not mid-rebase generated-file conflicts) — complementary, not overlapping.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/agent-pipeline-details.md` (pipeline-worktree-lifecycle section)

### Proposal 2: `git patch-id --stable` verification technique in pipeline-worktree-lifecycle

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P1
- **Source(s)**: remove-chub-land `LEARNINGS.md` § Patterns — "Per-file `git patch-id --stable` (base→backup vs main→HEAD) proves which of our patches the rebase left byte-identical. It turned 'did an installer function change?' into a mechanical answer and skipped an unneeded light-review."
- **Description**: Document the `git patch-id --stable` comparison technique (per-file, backup-branch-vs-rewritten-tip) as a verification step in the pipeline-worktree-lifecycle exit procedure, for confirming a rebase left specific patches byte-identical before deciding whether a light-review or re-verification pass is needed.
- **Rationale**: This closes a real decision point — "did the rebase change this file's actual patch, or just its context lines?" — with a mechanical, cheap check instead of a manual diff read or an unnecessary re-review spawn. It is exactly the kind of procedural technique that belongs in a skill (has steps, has a clear trigger, has a payoff) rather than a rule.
- **Estimated scope**: SKILL.md + 1 reference addition (a short subsection, ~10-15 lines)
- **Overlap check**: none found — the pipeline-worktree-lifecycle content has no existing patch-verification technique.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/agent-pipeline-details.md` (pipeline-worktree-lifecycle exit procedure)

### Proposal 3: Disposition-row-to-step cross-check in planner/orchestrator handoff

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: sapling
- **Scope**: medium
- **Priority**: P1
- **Source(s)**: remove-chub `LEARNINGS.md` — "[orchestrator] Planner coverage gap: `skills/upstream-stewardship/SKILL.md` had a SYSTEMS_PLAN disposition row (line 451) but no step owned it in `Files:`; orchestrator applied it in Batch 3. Lesson: cross-check every disposition row against the union of step `Files:` before execution."
- **Description**: Add a declarative checkpoint to the coordination protocol (or the implementation-planner's delegation checklist) requiring that, before execution begins, every disposition row in an architect's plan document (`SYSTEMS_PLAN.md` or equivalent) is matched against the union of every step's `Files:` field — any unassigned row is either given an owning step or explicitly flagged as an orchestrator-applied exception.
- **Rationale**: This is a recurring class of silent gap (a disposition decision made but never wired to an executing step) independent of this specific pipeline — the same failure mode could recur in any plan with a large disposition table (e.g. a removal/migration inventory) and a step-based execution model. A one-line cross-check closes it structurally.
- **Estimated scope**: single rule/checklist-file edit (a few lines)
- **Overlap check**: `rules/swe/swe-agent-coordination-protocol.md` § Delegation Checklists and `coordination-details.md § Delegation Checklists` cover per-agent deliverables but not this specific disposition-row-to-step reconciliation step — no existing coverage found.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/coordination-details.md` (Delegation Checklists section, implementation-planner or orchestrator row)

### Proposal 4: Large commit-sequence step-splitting pattern in spawn-budget guidance

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P1
- **Source(s)**: remove-chub `LEARNINGS.md` — "[implementation-planner] Split large commit-sequence items into parallel steps, committed as one union: `SYSTEMS_PLAN.md`'s 8 suggested commits include several that touch 10-25 files... each is decomposed into 2-5 disjoint-file steps run by concurrent implementer instances, then the orchestrator commits their union with the original single commit message — preserving the architect's approved commit narrative while fitting the implementer's ~80-turn/2-step budget."
- **Description**: Extend the existing "Batched Improvements" / spawn-budget guidance in `coordination-details.md` with this named pattern: when a single architect-proposed commit in a plan touches enough files to exceed an implementer's turn budget, decompose it into disjoint-file parallel steps run by concurrent implementer instances, then have the orchestrator commit their union under the original single commit message — preserving the plan's commit narrative while respecting the per-spawn turn ceiling. Distinguish this from the existing per-file-mechanical-substitution heuristic (3-5 files/step) which does not apply when edits are fully drafted verbatim.
- **Rationale**: This directly extends an existing, already-formalized area (spawn budget + batched improvements) with a specific, reusable resolution for a documented tension (turn budget vs. architect's commit narrative) that will recur in any Standard/Full pipeline with a large SYSTEMS_PLAN commit list.
- **Estimated scope**: SKILL.md/reference addition (~10-15 lines) to an already-existing section
- **Overlap check**: `coordination-details.md § Batched Improvements` (Classify/Pair-spawn/Sequence/Full-suite-gate) and `§ Spawn Budget` cover general independence and budget count, but not this specific "split-and-reunify-under-one-commit-message" technique — complementary, not duplicate.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/coordination-details.md` (Batched Improvements or Spawn Budget section)

### Proposal 5: Mutation-sensor "unavailable" disposition convention

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2
- **Source(s)**: remove-chub `LEARNINGS_rw2.md` — "[implementer] W-11 disposition: record `Mutation: unavailable`, don't attempt a workaround. `mutation_sensor.py` v1 is Python-only and flat-layout-only... Rather than bypass the tool's own safety property (never fabricate a survivor count), recorded the verbatim refusal in `TEST_RESULTS_7mutation.md`... **Alternatives considered**: writing a synthetic Python shim to satisfy the sensor (rejected — changes what's under test); silently omitting the `Mutation:` line (rejected...)."
- **Description**: Add one declarative line to the testing-strategy mutation-sensor documentation: when a `mutation: on` step targets a non-Python or non-flat-layout file the sensor cannot run against, the correct disposition in `TEST_RESULTS_*.md` is `Mutation: unavailable` with the tool's verbatim refusal message — never a fabricated survivor count, and never a synthetic shim written solely to satisfy the sensor.
- **Rationale**: A small but real gap in existing mutation-testing documentation, which currently explains when/why to invoke the sensor but not what to record when the tool correctly refuses. Low priority since it is a narrow addendum to an already-documented feature, but cheap to close and prevents a future implementer from either fabricating a result or writing a scope-creeping test shim.
- **Estimated scope**: single-line addition to an existing reference section
- **Overlap check**: `skills/testing-strategy/references/python-testing.md` § Mutation Sensor (Per-Step) documents invocation, cost, and false-positive exclusions, but not the refusal-disposition convention — no existing coverage found.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/testing-strategy/references/python-testing.md` (Mutation Sensor (Per-Step) section)

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | Rule/reference update; review scope against pipeline-worktree-lifecycle content |
| 2 | context-engineer | Skill reference update; add patch-id verification technique |
| 3 | context-engineer | Rule/checklist update; small, single-section addition |
| 4 | context-engineer | Skill reference update; extends existing spawn-budget section |
| 5 | context-engineer | Rule/reference update; single-line addendum |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 5 pending proposals.
- After approval, invoke `context-engineer` for the reference/rule updates; the agent will pick up the recommended delegations table.
- td-287 and td-288 already carry the two ledger-tracked findings from this batch — no further action needed here.
- Items 9 and 10 (triage table) are recorded as skipped-too-narrow; re-harvest if either recurs across a future pipeline.
