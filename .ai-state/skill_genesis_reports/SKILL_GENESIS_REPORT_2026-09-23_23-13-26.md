---
schema_version: 1
report_id: skill-genesis-2026-09-23_23-13-26
generated_at: 2026-09-23T23:13:26Z
task_slug: skill-genesis-2026-09-23
agent_version: skill-genesis@f731fa8e
invocation_args: { since: null, scope: null, sources: ".ai-work/_harvest", batch: "11 of 13", dry_run: false }
review_status: pending
disposition_count: { pending: 6, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-09-23 23:13:26

## Summary

2 learning sources analyzed (process-economy-phase0, process-economy-phase1, each
contributing `LEARNINGS.md` — no `VERIFICATION_REPORT.md`/`CONSULT_*.md` present in either
directory), ~30 discrete learning items extracted, 6 proposals generated, ~24 items
deduplicated or skipped (already captured by finalized ADRs dec-377/dec-378/dec-379, by
harness auto-memory, by this run's earlier batch proposals, or judged too narrow/transient
to formalize). Review status: pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| Queue source: process-economy-phase0 LEARNINGS.md | `.ai-work/_harvest/process-economy-phase0/process-economy-phase0/LEARNINGS.md` | ~15 | Read |
| Queue source: process-economy-phase0 VERIFICATION_REPORT.md | `.ai-work/_harvest/process-economy-phase0/process-economy-phase0/VERIFICATION_REPORT.md` | 0 | Not read (LEARNINGS.md alone yielded sufficient extractable items within turn budget; no oversize flag was set for this batch) |
| Queue source: process-economy-phase1 LEARNINGS.md | `.ai-work/_harvest/process-economy-phase1/process-economy-phase1/LEARNINGS.md` | ~15 | Read |
| Queue source: process-economy-phase1 VERIFICATION_REPORT.md | `.ai-work/_harvest/process-economy-phase1/process-economy-phase1/VERIFICATION_REPORT.md` | 0 | Not read (same rationale) |
| Latest SENTINEL_REPORT_*.md | `.ai-state/sentinel_reports/SENTINEL_REPORT_2026-09-14_07-59-49.md` | 0 | Not read (queue-mode batch scoped to the two listed LEARNINGS.md sources; no sentinel cross-reference needed for this batch's items) |
| Latest IDEA_LEDGER_*.md | `.ai-state/idea_ledgers/IDEA_LEDGER.md` | 0 | Not read (checked filename only; no overlap expected with this batch's implementation-detail learnings) |
| ADRs (recent) | `.ai-state/decisions/DECISIONS_INDEX.md` | 3 matched | Grep-scanned for `simplification`, `observations-wal-leaves-git`, `worktree-guard` — dec-377/dec-378/dec-379 confirmed already finalized, covering the three major decisions recorded in these LEARNINGS.md files |
| Calibration log Retrospective cells | `.ai-state/calibration_log.md` | 0 | Not read (queue mode scoped to listed sources only) |
| Consult fragments | `.ai-work/_harvest/process-economy-phase{0,1}/*/CONSULT_*.md` | 0 | Not found (neither directory listing shows a `CONSULT_*.md` file) |
| Sibling reports (this run) | `.ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_2026-09-23_{22-35-25..23-09-58}.md` | — | Grepped proposal headings across all 10 prior batches — no overlap with process-economy-phase0/phase1 content found |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | PM-1 Reader Audit — mandatory per-reader degrade-vs-edit classification before retiring a widely-consumed artifact | phase1 LEARNINGS §Step 7 Learnings, table | Skill (update: refactoring or software-planning) | Procedural, generalizable checklist with a proven worked example (12-reader table); no existing skill/rule encodes this workflow |
| 2 | `validate_references.py` anchor-slug gotcha — `&`/punctuation in headings collapses to a double-hyphen slug; `<a id>` tags are never consulted | phase1 LEARNINGS §Step 5 Learnings | Skill (update: skill-crafting) | Non-obvious script behavior directly gates every cross-reference the skill's own validator checks; belongs next to the script it documents |
| 3 | Template/rendered-file relative-link mismatch — a `.tmpl` source validates links against its own directory, not the rendered destination; prefer backtick citations over markdown links inside `.tmpl` files | phase1 LEARNINGS §Step 6 Learnings | Skill (update: skill-crafting, same reference as #2) | Same script (`validate_references.py`), same consumer, same file — bundling avoids a second near-duplicate proposal |
| 4 | Hook benchmarking confounds — `git stash` round-trips perturb git-state-reading hooks (git-context relevance scoring); benchmark harnesses touching `$HOME`-writing hooks must sandbox `$HOME` | phase1 LEARNINGS §Step 11 Learnings | Skill (update: hook-crafting) | Two concrete, hard-won measurement gotchas for anyone benchmarking or testing a hook — hook-crafting has a `references/testing-guide.md` that is the natural home |
| 5 | Cross-plugin WAL contamination — multiple plugins (`praxion`, `i-am`) register same-named agents; telemetry queries must filter on the `praxion:` `agent_type` prefix or silently inflate counts | phase1 LEARNINGS §Gotchas, §Step 8 Learnings | Rule (new, narrow) or skill update | Concrete, reusable gotcha for any future WAL/telemetry query script; flagged ambiguous — narrow enough it could also live as a code comment, but the failure mode (silent inflation, already caught once) merits a durable, discoverable note |
| 6 | `measure_token_budget.py`'s governed 9-file set excludes `agents/*.md` — per-agent-file token trims are real (per-spawn preload cost) but invisible to the resident-budget ratchet | phase0 LEARNINGS §Gotchas | Rule (update: `rules/CLAUDE.md` or `rule-crafting` token-budget section) | Directly qualifies a claim already made in the always-loaded token-budget rule; a reader trimming `agents/*.md` for token savings needs to know the ratchet won't move |
| — | Evidence-based frontmatter decision ("prediction is not evidence" — 7-agent `memory:` drop by telemetry, not roadmap prediction) | phase1 LEARNINGS §Decisions Made | Skip | Already fully captured by finalized dec-378 (`Simplification requires a measured cost and an executable guard`); this item is the worked application, not new formalizable knowledge |
| — | `.gitattributes` merge-driver + `merge_driver_observations.py` become inert once WAL leaves git | phase0 LEARNINGS §Technical Debt | Skip | Already covered by finalized dec-377's own Consequences section; a tech-debt row, not a rule/skill candidate |
| — | Step 3 EC08 transcript-scanning design cannot work (system prompt never persisted in transcript JSONL) | phase0 LEARNINGS §Step 3 BLOCKED | Skip | A single negative finding tied to one specific, already-reverted implementation attempt; not a recurring pattern to formalize (the underlying "transcript vs. system-prompt delivery" fact is a Claude Code platform detail, not a Praxion convention) |
| — | WAL query must target the main checkout's absolute path, never a worktree-local copy | phase1 LEARNINGS §Assumptions | Skip | Same lesson `feedback_implementer_cwd_in_worktrees` already generalizes in harness memory; a WAL-specific restatement adds no new formalizable content |
| — | `claude/config/CLAUDE.md.tmpl` vs rendered `~/.claude/CLAUDE.md` — edit the template, never the render | phase1 LEARNINGS §Assumptions | Skip | Already captured in harness memory (`feedback_claude_config_is_generated_from_tmpl.md`) |
| — | `skillOverrides` per-plugin key form (`praxion:<name>` vs bare `<name>`), listing truncation vs. drop semantics | phase1 LEARNINGS §Step 12 disposition | Skip | Already captured in harness memory (`feedback_skill_overrides_setting_is_inert.md`); this item adds an unverified assumption pending next-session confirmation, not settled knowledge |
| — | Deleted-but-still-registered hook breaks Edit/Write for the rest of the session (dev-install worktree) | phase1 LEARNINGS §Gotcha (orchestrator) | Skip | Already captured verbatim in harness memory (`feedback_deleting_registered_hook_breaks_session_tools.md`) |
| — | 12 skill-retirement candidates from a zero-WAL-usage query, with caveats on evidence limits | phase1 LEARNINGS §Technical Debt | Skip | A dispositioned technical-debt/candidate list awaiting a separate user decision, not a reusable pattern — the *methodology* (query zero-usage skills against the WAL before retiring) is folded into Proposal 1's neighboring discipline but the candidate list itself is task-specific output, not durable knowledge |
| — | Remaining ~15 smaller Gotchas/Assumptions/Edge-Case items (Step 8 schema field-naming discrepancy, `tokens_by_agent_type` shape choice, ratchet 30-day-window bug, byte-vs-token ratchet basis, name-based rule dedup identity, two-steps-per-spawn cadence, etc.) | both LEARNINGS.md files, various | Skip | Each is either a one-off implementation judgment call scoped to this pipeline's own code (not reusable beyond it), or overlaps content this run's earlier batches (22-35-25 through 23-09-58) already proposed under `feedback_implementer_turn_cap_two_steps`-class memory and gate-liveness/gate-canaries proposals — no new formalizable surface found on inspection |

## Proposals

### Proposal 1: Reader-Degradation Audit — pre-retirement checklist for widely-consumed artifacts

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-phase1/process-economy-phase1/LEARNINGS.md` §Step 7 Learnings (PM-1 Reader Audit table, 12 readers classified degrade-vs-edit) and its "Files-field gap, surfaced explicitly" follow-up paragraph
- **Description**: A short, reusable checklist for retiring a mechanism, field, or file convention that an unknown number of downstream readers may depend on: (1) enumerate every known reader via targeted grep across `dashboard_app/`, `scripts/`, `hooks/`, `skills/`, `rules/`, `agents/`, `commands/`, `docs/`; (2) for each, prove — not assume — whether it degrades gracefully to absence (cite the specific try/except, optional-field check, or skip-if-missing loop) or requires an edit because it makes an active claim that becomes false; (3) record the table in `LEARNINGS.md` so a future reader can audit the audit. Would live as a new subsection in `skills/refactoring/references/patterns.md` (or `skills/software-planning/references/coordination-details.md`'s Pre-Refactor Sub-Pipeline section, since the pattern's proof obligation mirrors that section's degrade-check spirit).
- **Rationale**: This is procedural expertise with concrete steps and a worked, non-trivial example (12 readers, 2 correctly identified as needing an edit despite not being in the plan's `Files:` field). It directly prevents a documented failure mode — silently leaving a stale "active claim" reader broken while assuming graceful degradation. The pattern is domain-general (any retirement of a field/file/mechanism with unknown fan-out) and distinct from existing refactoring-skill content, which covers mechanical-move verification, not consumer-fanout auditing.
- **Estimated scope**: single reference-file addition (~40–60 lines: the checklist + the degrade-vs-edit worked example, trimmed of task-specific reader names)
- **Overlap check**: `skills/refactoring/references/patterns.md` (no reader-audit content found); `skills/software-planning/references/coordination-details.md` § Pre-Refactor Sub-Pipeline (covers *when* to run a pre-refactor mini-pipeline, not *how* to audit readers — complementary, not overlapping); this run's batch `23-05-46` Proposal 4/6 (`Files:` field syntax discipline, dogfood-step unexecutability) — adjacent but addresses a different failure mode (plan-authoring precision vs. reader-fanout proof)
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/refactoring/references/patterns.md` (new `## Reader-Degradation Audit` section) — context-engineer to confirm placement against `coordination-details.md` as the alternative home

### Proposal 2: skill-crafting — `validate_references.py` anchor-slug and template-link gotchas

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-phase1/process-economy-phase1/LEARNINGS.md` §Step 5 Learnings (anchor-slug gotcha) and §Step 6 Learnings (template relative-link resolution gotcha)
- **Description**: Two gotchas about `skills/skill-crafting/scripts/validate_references.py`'s own resolution logic, both discovered empirically while editing rule/CLAUDE.md prose: (1) anchor slugs are computed purely from heading text via the script's `github_slug()` function — punctuation like `&` collapses to nothing while surrounding spaces still become hyphens, producing a double-hyphen slug (e.g. `interface-designer-shadowing--the-architecture-challenge-loop`); the script never reads a file's own `<a id="...">` tags. (2) The script resolves a relative-path link against the *citing file's own directory in the repo*, not wherever that file is rendered/symlinked to — so a link written inside a `.tmpl` source that would resolve correctly once rendered still fails validation; the established workaround is a backtick-quoted path citation instead of a markdown link for template-internal rule references.
- **Rationale**: Both gotchas gate every future skill/rule cross-reference edit through this exact script and were found only by running the script's own regex logic before committing, not by reading its docstring. Undocumented, they cost a future author the same investigation each time. `validate_references.py` is Step 5 of the skill-crafting workflow (`## Step 5: Validate and Package`) — the natural, already-loaded home.
- **Estimated scope**: SKILL.md gotchas-section addition (~10–15 lines) or a new short section in a skill-crafting reference file if one exists for the validator
- **Overlap check**: `skills/skill-crafting/SKILL.md` § Step 5 (names the script and its modes but not these two resolution behaviors); no existing reference file documents `github_slug()`'s exact algorithm or the template-vs-rendered-path caveat
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/skill-crafting/SKILL.md` (Step 5 section) or a new `skills/skill-crafting/references/validate-references-gotchas.md` if the two gotchas plus future ones warrant their own file

### Proposal 3: hook-crafting — benchmarking confounds (`git stash` state reconstruction, unsandboxed `$HOME`)

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-phase1/process-economy-phase1/LEARNINGS.md` §Step 11 Learnings (`git stash` confound; `$HOME` sandboxing)
- **Description**: Two measurement-methodology gotchas for benchmarking or A/B-testing hooks: (1) using `git stash push`/`pop` to reconstruct a pre-edit command set for timing comparison is not state-neutral when any compared hook reads live git state (e.g. a relevance-scoring hook that ranks by recent commits/working-tree state) — it produces spurious non-identical output that looks like a regression but is a measurement artifact; reconstruct "before" commands as literal strings instead. (2) A hook that writes to `$HOME` (install markers, config renders) must have `$HOME` redirected to a scratch directory for every benchmark run, or the run can trigger real installer side effects against the actual machine.
- **Rationale**: Both are non-obvious, hard-won (discovered via a spurious `diff -r` failure that required a second controlled run to disambiguate from a real regression) and directly reusable by anyone timing or comparing `hooks/*.py` behavior — a recurring activity in this ecosystem's SessionStart-cost work. `hook-crafting/references/testing-guide.md` already exists as the natural home.
- **Estimated scope**: `references/testing-guide.md` addition (~10–15 lines, a "Benchmarking Confounds" subsection)
- **Overlap check**: `skills/hook-crafting/references/testing-guide.md` (content unknown pending context-engineer read; no other reference file names `git stash` or `$HOME` sandboxing per this batch's search)
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/hook-crafting/references/testing-guide.md`

### Proposal 4: Cross-plugin telemetry contamination — WAL queries must filter on the owning plugin's `agent_type` prefix

- **Disposition**: pending
- **Type**: rule (new, narrow) — ambiguous, see rationale
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `.ai-work/_harvest/process-economy-phase1/process-economy-phase1/LEARNINGS.md` §Gotchas ("Multiple plugins... register similarly-named agents") and §Step 8 Learnings (caught 2 `i-am:context-engineer` rows that would have inflated the count)
- **Description**: Any script or agent that queries `.ai-state/observations.jsonl` (or `observations_summary.jsonl`) by `agent_type` name must filter on the owning plugin's prefix (`praxion:`) rather than a bare name match — a differently-plugin-installed agent of the same name (observed: `i-am:context-engineer`) silently contaminates the count. Caught once in this pipeline by inspecting raw rows before trusting an aggregate.
- **Rationale**: This is a declarative constraint ("always prefix-filter WAL agent_type queries") applicable across any future telemetry script — process-economy, skill-genesis usage queries, `project_metrics` collectors — not a one-off implementation detail of this pipeline. Ambiguous placement: narrow enough that a single doc-comment convention in the WAL schema's own description could suffice instead of a standalone rule file; flagged for context-engineer's placement judgment (candidate: a short addition to whichever reference documents the WAL schema, if one exists, rather than a new always-loaded rule).
- **Estimated scope**: single rule file (if standalone) or a 2–3 line addition to an existing WAL-schema-documenting reference
- **Overlap check**: none found — no existing rule or reference documents multi-plugin `agent_type` namespacing for WAL queries
- **Recommended delegation**: context-engineer (placement decision first)
- **Suggested artifact path**: TBD by context-engineer — candidates: `rules/swe/observability-telemetry.md` (new, narrow) or an existing artifact-inventory/coordination-details WAL-schema subsection

### Proposal 5: Token-budget rule caveat — `measure_token_budget.py`'s governed set excludes `agents/*.md`

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-phase0/process-economy-phase0/LEARNINGS.md` §Gotchas (`measure_token_budget.py`'s governed 9-file set)
- **Description**: A one-sentence caveat for the always-loaded token-budget rule (`rules/CLAUDE.md` and/or `rule-crafting`'s Token Budget section): per-agent-file (`agents/*.md`) token trims are real savings for per-spawn preload cost but are invisible to `measure_token_budget.py`'s resident-budget ratchet, which measures only CLAUDE.md files + always-loaded rules (the 9-file governed set on this tree). A future author trimming an agent file for token savings should not expect the ratchet's reported number to move, and should not conclude the trim "did nothing" from an unchanged ratchet reading.
- **Rationale**: This directly qualifies a claim implicitly made by the existing token-budget rule (that the measured figure represents "always-loaded content") without stating the boundary of what's measured — a reader could reasonably but wrongly assume `agents/*.md` counts toward it, since agent files are loaded on every spawn. The caveat is small, declarative, and prevents a specific documented confusion (Merge Gate 1 in the source pipeline had to state this explicitly to preempt exactly this misreading).
- **Estimated scope**: CLAUDE.md/rule edit (1–2 sentences)
- **Overlap check**: `rules/CLAUDE.md` § Token Budget (states the 25,000-token ceiling and measurement script but does not scope what counts as "always-loaded" beyond CLAUDE.md + unconditional rules — this proposal makes that scope explicit, not contradicted)
- **Recommended delegation**: context-engineer (review scope) then implementer or direct edit
- **Suggested artifact path**: `rules/CLAUDE.md` (Token Budget section) — or `skills/rule-crafting/SKILL.md` § Token Budget if the caveat belongs closer to the measurement-methodology discussion instead

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | Reference-file addition to refactoring or software-planning; load `skill-crafting`/`rule-crafting` as needed for placement judgment |
| 2 | context-engineer | Skill update; load `skill-crafting` |
| 3 | context-engineer | Skill update; load `hook-crafting`'s existing testing-guide.md first to confirm no duplication |
| 4 | context-engineer | Placement ambiguous between new rule and existing WAL-schema reference — context-engineer decides before drafting |
| 5 | context-engineer (review) then implementer or direct edit | Small always-loaded-rule edit; token-budget-sensitive, verify with `scripts/measure_token_budget.py` after |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 6 pending proposals.
- After approval, invoke `context-engineer` for skills/rules; the agent will pick up the recommended delegations table.
- This is batch 11 of 13 in a queued harvest sweep over `.ai-work/_harvest/`; remaining batches continue independently — no action needed here beyond this report.
