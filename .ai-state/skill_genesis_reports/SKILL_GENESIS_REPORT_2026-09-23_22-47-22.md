---
schema_version: 1
report_id: skill-genesis-2026-09-23_22-47-22
generated_at: 2026-09-23T22:47:22Z
task_slug: skill-genesis-2026-09-23
agent_version: skill-genesis@unknown
invocation_args: { since: null, scope: null, sources: ".ai-work/_harvest", batch: "4 of 13", dry_run: false }
review_status: pending
disposition_count: { pending: 5, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-09-23 22:47:22

## Summary

1 learning source (`process-economy-p2-10`) analyzed. ~14 discrete learning items extracted from `LEARNINGS.md` (full read) and `VERIFICATION_REPORT.md` (targeted sections: Tech Debt, Recommendations, Calibration Verdict). 5 proposals generated after deduplication against existing rules/skills and against this run's three earlier batch reports; 9 items discarded (already covered by an existing artifact, or too narrow/transient). Review status: pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| Queue source: LEARNINGS.md | `.ai-work/_harvest/process-economy-p2-10/LEARNINGS.md` | 11 | Read (full) |
| Queue source: VERIFICATION_REPORT.md | `.ai-work/_harvest/process-economy-p2-10/VERIFICATION_REPORT.md` | 3 | Sampled (sections read: Tech Debt, Recommendations, Calibration Verdict; skipped: Gate Re-Runs, Acceptance Criteria, Spec Conformance, Convention Compliance, ADR Review, Security Review, Architecture Documentation, Test Coverage, Context Artifact Completeness — these are per-pipeline verification detail, not generalizable pattern candidates) |
| Latest SENTINEL_REPORT_*.md | `.ai-state/sentinel_reports/` | 0 | Not consulted (batch scope; no signal of new ecosystem pattern beyond what LEARNINGS/VERIFICATION already surfaced) |
| Latest IDEA_LEDGER_*.md | `.ai-state/idea_ledgers/IDEA_LEDGER.md` | 0 | Present, not needed (no proposal collided with an ideation item) |
| ADRs (recent) | `.ai-state/decisions/` | 0 | Not queried (no item required file-scoped ADR cross-check) |
| Calibration log Retrospective cells | `.ai-state/calibration_log.md` | 0 | Not read this batch (source directory scope is the single queue entry) |
| Consult fragments | `.ai-work/_harvest/process-economy-p2-10/CONSULT_*.md` | 0 | Not found |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | Pre-commit refuses to run with its own config unstaged — `.pre-commit-config.yaml` changes must land first when a batch touches it | LEARNINGS.md:357 | Rule (update) | Declarative git-workflow constraint, not covered by `git-conventions.md`; applies whenever a pipeline batch edits the hook config itself |
| 2 | Regenerated tracked files bake in the generator's cwd (worktree path) — `install_codex.sh --compat-only` → `AGENTS.md`; `measure_token_budget.py` reads `~/.claude/CLAUDE.md` through a symlink into MAIN, invisible from a worktree; `check_design_checkpoint.py` state is worktree-local until merge | LEARNINGS.md:180-197, 356 + Orchestrator section:354,356 | Rule (update) | Recurring pattern (3 distinct regeneration/measurement instances in one pipeline) not covered by `coordination-details.md`'s worktree-lifecycle section; a declarative "regenerate/measure from main at merge, never from a worktree" constraint |
| 3 | Calibration Verdict judged from spawn economy + light-review closure signal (0 cap-outs, all light-review FAILs closed without re-plan) rather than raw file count against the tier band | VERIFICATION_REPORT.md — Calibration Verdict | Skill (update) | `calibration-procedure.md` documents the file-count/behavior-count proxy but not this evidentiary pattern for *judging a completed run's* calibration correctness — procedural depth for a specific skill section |
| 4 | Import convention split by directory: `tests/*.py` importing `scripts/*.py` modules uses `sys.path.insert` + plain import (`# noqa: E402`); `scripts/test_*.py` siblings use `importlib.util.spec_from_file_location` against absolute paths | LEARNINGS.md:273-276, 310-314 | Rule (update) | Declarative project convention not stated in `coding-style.md`; narrow scope (one repo's two coexisting import idioms) but concrete and reusable at every new cross-directory test module |
| 5 | Integration-checkpoint pattern for interdependent live-corpus test assertions inside a fully-parallel step batch — defer specific assertions' greenness to a dedicated integration checkpoint step rather than serializing the whole batch | LEARNINGS.md:49-58 | Skill (update) | Extends `coordination-details.md`'s existing BDD/TDD "Integration checkpoint" concept (currently scoped to test+impl pairs) to the case where *live-corpus* assertions depend on sibling consumer-rewrite steps landing — same mechanism, undocumented variant |
| 6 | BC05 definition-shape predicate: declared-limits table for a regex-based totalising check, proven via a *planted copy* rather than live allowlist entries (which can vacuously score 0) | LEARNINGS.md:229-244 | Skip (overlap) | Overlaps `SKILL_GENESIS_REPORT_2026-09-23_22-43-59.md` Proposal 1 ("gate-canaries.md — non-vacuity proof methodology", pending) — this item is additional supporting evidence for that pending proposal, not a new one; noted here for the reviewer to fold in when dispositioning that proposal |
| 7 | `Step <n>` is a forbidden literal in `scripts/**` (not exempt); mid-pipeline markers in code must describe the condition, never the step number | LEARNINGS.md:224-228 | Skip (covered) | Already fully covered by `rules/swe/id-citation-discipline.md` (`Step N` pattern + `scripts/` explicitly non-exempt) |
| 8 | `.ai-state/DESIGN.md` checkpoint advances by one ADR at a time; "not applicable" and "folded in" both advance the mark; folding a not-yet-judged ADR is forbidden | LEARNINGS.md:17 | Skip (covered) | Already fully and precisely covered by `skills/software-planning/references/architecture-documentation.md` § Checkpoint |
| 9 | Traceability.yml omission — planner must name the merged-traceability artifact explicitly at Standard tier | VERIFICATION_REPORT.md — Recommendations #1, LEARNINGS.md:362 | Skip (covered) | `coordination-details.md` § Delegation Checklists already instructs exactly this ("Initialize `.ai-work/<task-slug>/traceability.yml`; give every step... an explicit owner..."); this pipeline's miss is a compliance gap, not a documentation gap |
| 10 | `extract_summary` lacked an HTML-comment branch, corrupting the Codex-facing rule `summary`; fixed in Step 10b (5-line addition) | LEARNINGS.md:15, 260-267, 320-326 | Skip (resolved) | Bug already fixed in the same pipeline; no residual gotcha to formalize (rule bodies with fences remain forbidden per `rule-crafting`'s existing Self-Containment Constraint) |
| 11 | `sync_canonical_blocks.py --write` has no per-block selection flag — processes every registered block in one pass | LEARNINGS.md:94-97 | Skip (too narrow) | Single-script operational quirk with no cross-context reuse beyond this one pipeline's step-sequencing choice |
| 12 | `check_behavioral_contract.py` kept as one 667-line file rather than split, because five sentinel/Triangle mechanisms key on the single script name (one-family-one-script) | LEARNINGS.md:245-250 | Skip (too narrow) | Restates an existing, already-documented Praxion convention (one family = one script) applied to a specific file; not a new pattern |
| 13 | `docs/rules-taxonomy.md`'s core-rule token table was stale by up to 65%; no script reads/validates it | LEARNINGS.md:36, 333-345 | Skip (transient) | One-off staleness fix already applied in this pipeline (Step 14); not a recurring gotcha to formalize (the token-budget measurement-history note in `rule-crafting`'s REFERENCE already covers the "measure, don't restate" discipline) |
| 14 | `count_tokens(text, api_key)` takes the key as a positional second argument — one-arg call raises `TypeError` | LEARNINGS.md:39 | Skip (too narrow) | Single-function signature gotcha, not independently actionable as an artifact (would need a broader "measure_token_budget usage" context to be worth a rule line) |

## Discipline-Gap Signals

_(none recorded this batch — no decision surfaced a "needed a specialist voice here" signal)_

## Proposals

### Proposal 1: git-conventions.md — pre-commit config-first ordering

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1
- **Source(s)**: `.ai-work/_harvest/process-economy-p2-10/LEARNINGS.md:357` ("Pre-commit refuses to run with its own config unstaged — the Step 11 group had to land before any other commit. Order config changes first when a batch touches `.pre-commit-config.yaml`.")
- **Description**: Add a bullet to `rules/swe/vcs/git-conventions.md` stating that `pre-commit` refuses to run at all when its own config file has unstaged changes, so any batch of commits that touches `.pre-commit-config.yaml` must land that commit first, before any other commit in the same batch depends on the hooks it defines.
- **Rationale**: This is a hard mechanical constraint on commit ordering that silently blocks an entire commit batch if violated (pre-commit errors out rather than degrading gracefully). It sits naturally beside the file's existing pre-commit-stash gotcha (same domain: pre-commit's interaction with a dirty/reordered tree) but names a distinct failure mode. P1 because it recurs on every pipeline batch that edits hook config, which is common when adding a new gate (e.g., BC05 in this same pipeline).
- **Estimated scope**: single rule file (one bullet, ~2-3 lines)
- **Overlap check**: `rules/swe/vcs/git-conventions.md` already documents the pre-commit stash/restore non-idempotency gotcha (adjacent domain, distinct failure mode — no direct overlap)
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/vcs/git-conventions.md`

### Proposal 2: coordination-details.md — regenerated tracked files bake the generator's cwd; regenerate/measure from main at merge

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P1
- **Source(s)**: `.ai-work/_harvest/process-economy-p2-10/LEARNINGS.md:180-197` (AGENTS.md regeneration bakes worktree path), `LEARNINGS.md:356` ("The budget instrument reads `~/.claude/CLAUDE.md` through its symlink into MAIN... Do not regenerate the live global file from a worktree"), `LEARNINGS.md:354` (`install_codex.sh --compat-only` baked worktree cwd into tracked `AGENTS.md`, → td-206)
- **Description**: Add a declarative constraint to `skills/software-planning/references/coordination-details.md`'s worktree-lifecycle section: any script that regenerates a tracked, committed file from a template or renders global config (`install_codex.sh --compat-only`, `render_claude_md.py`, `measure_token_budget.py`'s read of `~/.claude/CLAUDE.md`) bakes in the invoking process's cwd or reads through a symlink resolved at invocation time. When run from a pipeline worktree, the regenerated artifact or measurement is worktree-scoped and must be re-run from the main checkout at merge time to produce the canonical, mergeable result.
- **Rationale**: This bit the same pipeline three separate times (AGENTS.md content, token-budget measurement, and implicitly the DESIGN.md checkpoint state) — a genuine recurring pattern, not a one-off. The existing worktree-lifecycle documentation covers `.ai-state/` write reconciliation but has no guidance for cwd-sensitive regeneration/measurement scripts, which is a distinct failure class (wrong *content*, not a merge conflict). P1 because self-hosting pipelines (Praxion working on itself) hit this whenever a worktree-based Standard/Full pipeline touches a regenerated surface.
- **Estimated scope**: single rule file (one new subsection, ~10-15 lines) — could alternatively land as a new bullet under the existing `.ai-state/` reconciliation cross-reference
- **Overlap check**: `skills/software-planning/references/coordination-details.md` § pipeline-worktree-lifecycle covers `.ai-state/` write reconciliation; `agent-intermediate-documents.md` covers `.ai-work/`/`.ai-state/` lifecycle but not cwd-baking; no existing artifact states this constraint
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/coordination-details.md`

### Proposal 3: calibration-procedure.md — evidentiary basis for judging a completed run's calibration

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2
- **Source(s)**: `.ai-work/_harvest/process-economy-p2-10/VERIFICATION_REPORT.md` § Calibration Verdict ("Evidence, judged independently of the plan's own framing... the spawn economy: 8 implementer spawns with 0 cap-outs at maxTurns 100... The 3 light-reviews are the decisive datum: they caught 2 FAIL + 10 WARN... and every one was closed by the orchestrator without a single re-plan or mid-task re-tier event. Under-calibration would have shown as those FAILs reaching this report; over-calibration would have shown as spawns idling on ceremony or a cap-out")
- **Description**: Add a short section to `skills/spec-driven-development/references/calibration-procedure.md` describing the evidentiary signals a verifier (or a retrospective reader) should use to judge whether a *completed* pipeline's tier selection was correct, distinct from the intake-time file-count/behavior-count proxy the skill already documents: spawn cap-out rate (over-calibration signal if agents idle/cap without cause), rework-closure volume and whether closures required re-planning or mid-task re-tiering (under-calibration signal if fixes needed a re-plan), and light-review FAIL/WARN counts as a proxy for how much undetected error the process would have shipped without the extra process weight.
- **Rationale**: `calibration-procedure.md` currently documents only the intake-time signal-scoring procedure (Phase 1/2 file-count proxy). It has no guidance for the retrospective judgment a verifier performs at hand-back — a distinct but related use of "calibration" that this pipeline's verifier executed well and explained clearly, worth capturing as a reusable evaluation pattern. P2: valuable but not urgent — the verifier produced a correct verdict without this guidance, so the gap is a documentation improvement, not a live defect.
- **Estimated scope**: SKILL.md + 1 reference (single reference file addition, ~15-20 lines)
- **Overlap check**: `calibration-procedure.md` (intake-time signal scoring — adjacent, no overlap on the retrospective-judgment content); `swe-agent-coordination-protocol.md`'s tier table (describes tiers, not retrospective judgment)
- **Recommended delegation**: context-engineer (review scope) then implementer (content)
- **Suggested artifact path**: `skills/spec-driven-development/references/calibration-procedure.md`

### Proposal 4: coding-style.md — directory-scoped import convention for cross-directory test modules

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2
- **Source(s)**: `.ai-work/_harvest/process-economy-p2-10/LEARNINGS.md:273-276` ("Import pattern copied verbatim from `scripts/test_export_codex_rules_bridge.py`: `importlib.util.spec_from_file_location`... since `codex/config/` is not a package"), `LEARNINGS.md:310-314` ("Import convention for `tests/*.py` importing `scripts/*.py` modules: followed `tests/test_criteria_spec_eval.py`'s pattern (`sys.path.insert`... `# noqa: E402`)... The two conventions coexist by directory... used whichever the destination directory already established")
- **Description**: Add a short table/note to `rules/swe/coding-style.md` (or the relevant path-scoped Python rule) recording the two coexisting, directory-determined import idioms for a test module importing a non-package script module in this repo: `scripts/test_*.py` siblings use `importlib.util.spec_from_file_location` against the absolute module path; `tests/*.py` modules importing `scripts/*.py` use `sys.path.insert(0, str(SCRIPTS_DIR))` + a plain `import` with `# noqa: E402`. State explicitly that the convention is chosen by destination directory, not personal preference.
- **Rationale**: This is exactly the kind of non-obvious, repo-specific convention that a new test file gets wrong by default (Python offers several valid ways to import a non-package module, and picking the wrong one for the destination directory creates inconsistency an agent won't self-correct without being told). Declarative, applies whenever a new test imports a `scripts/*.py` module. P2 because it's low-frequency (new cross-directory test imports are not a common operation) but cheap to encode and prevents silent inconsistency accumulation.
- **Estimated scope**: single rule file (one table row or short paragraph, ~5 lines)
- **Overlap check**: `rules/swe/coding-style.md` has no existing import-convention guidance for this specific cross-directory case; none found
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/coding-style.md`

### Proposal 5: coordination-details.md — integration checkpoint for interdependent live-corpus assertions in a parallel batch

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2
- **Source(s)**: `.ai-work/_harvest/process-economy-p2-10/LEARNINGS.md:49-58` ("Step 3's live-corpus BC05 assertions... cannot go green until every consumer-rewrite step (4, 5, 7, 8) has also landed... I resolved this by explicitly deferring those specific assertions' greenness to a new Step 12 integration checkpoint rather than forcing Steps 4/5/7/8 to sequence before Step 3 (which would have serialized an otherwise fully parallel batch for no reason)")
- **Description**: Extend `coordination-details.md`'s existing "Integration checkpoint" concept (currently documented only for the test+implementation paired-step case) with the variant this pipeline used: when a gate-writing step's live-corpus assertions depend on sibling consumer-rewrite steps in the *same* parallel batch, defer only those specific assertions' greenness to a dedicated integration-checkpoint step at the end of the batch, rather than serializing the whole group. Name the trade-off explicitly (if the reasoning is wrong, the plan collapses to a strict sequence, costing one round-trip of parallelism) so a planner can make the same call deliberately.
- **Rationale**: This is a reusable planning technique for a specific, recognizable situation (a totalising/corpus-wide gate step whose assertions span files touched by sibling steps) that the existing documentation doesn't cover — it currently only describes the narrower test/impl-pair case. Capturing it prevents a future planner from either serializing unnecessarily or shipping a step with assertions that can't go green until sibling steps land, without an explicit deferred-checkpoint plan. P2: a real technique, applicable narrowly (only to corpus-wide gate steps in parallel batches).
- **Estimated scope**: single reference file (one paragraph addition to the existing "Integration checkpoint" subsection)
- **Overlap check**: `coordination-details.md` § BDD/TDD Execution → "Integration checkpoint" (partial overlap — same mechanism name, narrower existing scope; this proposal extends rather than duplicates)
- **Recommended delegation**: context-engineer (review scope) then implementer (content)
- **Suggested artifact path**: `skills/software-planning/references/coordination-details.md`

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | Rule update; load rule-crafting |
| 2 | context-engineer | Rule update; load rule-crafting; recurring worktree-regeneration pattern |
| 3 | context-engineer then implementer | Skill reference update; validate placement before content |
| 4 | context-engineer | Rule update; load rule-crafting |
| 5 | context-engineer then implementer | Skill reference update; extends existing Integration Checkpoint subsection |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 5 pending proposals (batch 4 of 13; other batches' reports also pending).
- When dispositioning `SKILL_GENESIS_REPORT_2026-09-23_22-43-59.md` Proposal 1 (gate-canaries.md non-vacuity proof methodology), fold in this report's Triage item 6 (BC05's planted-copy proof for allowlist entries) as additional supporting evidence.
- After approval, invoke `context-engineer` for the rule/skill updates; the agent will pick up the recommended delegations table.
- This is batch 4 of 13 in the queue-mode harvest of `.ai-work/_harvest/` — continue with remaining batches before a consolidated review.
