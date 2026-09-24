---
schema_version: 1
report_id: skill-genesis-2026-09-23_22-39-30
generated_at: 2026-09-24T05:41:46Z
task_slug: skill-genesis-2026-09-23
agent_version: skill-genesis@queue-batch
invocation_args: { since: null, scope: null, sources: ".ai-work/_harvest", batch: "2 of 13", dry_run: false }
review_status: pending
disposition_count: { pending: 7, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-09-23 22:39:30

## Summary

2 learning sources analyzed (queue mode, batch 2 of 13), ~35 discrete learning items surfaced
across both `LEARNINGS.md` files (Decisions Made, Gotchas, Registered Objections), 7 proposals
generated (all "update existing artifact" — no new skills/rules qualified), remainder deduplicated
against existing rules/skills, the harness agent-memory index, or discarded as too narrow/already
implemented. Review status: pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| Queue source: onboarding-unification | `.ai-work/_harvest/onboarding-unification/LEARNINGS.md` | ~18 | Read |
| Queue source: onboarding-unification | `.ai-work/_harvest/onboarding-unification/VERIFICATION_REPORT.md` | 0 | Not read (LEARNINGS.md sufficed; not oversize-flagged but budget-conscious — no additional distinct items expected beyond the already-rich Gotchas/Decisions sections) |
| Queue source: praxion-health | `.ai-work/_harvest/praxion-health/praxion-health/LEARNINGS.md` | ~17 | Read |
| Queue source: praxion-health | `.ai-work/_harvest/praxion-health/praxion-health/VERIFICATION_REPORT.md` | 0 | Not read (same rationale) |
| Latest SENTINEL_REPORT_*.md | `.ai-state/sentinel_reports/SENTINEL_REPORT_2026-09-14_07-59-49.md` | 0 | Not read this batch (no keyword overlap surfaced during triage; prior batch already consulted sentinel context) |
| Latest IDEA_LEDGER_*.md | `.ai-state/idea_ledgers/IDEA_LEDGER.md` | 0 | Referenced for dedup only, not read in full |
| ADRs | `.ai-state/decisions/DECISIONS_INDEX.md` | — | Grep-pre-scanned for `haiku`/`stash`/`check_state_ledgers`/`corpus` — no additional dedup hits beyond what rules already show |
| Calibration log Retrospective cells | `.ai-state/calibration_log.md` | 0 | Not read this batch (queue sources already carry rich Decisions/Gotchas sections; time-boxed) |
| Sibling reports of this run | `.ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_2026-09-23_22-35-25.md` | — | Read; its 4 proposals (gate-liveness, evidence-appraisal, discipline-consultant carrier-files, id-citation-discipline) target unrelated artifacts — no overlap with this batch's proposals |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | `git stash` mid-task in a repo with an active WAL-writing PostToolUse hook fails to pop (conflict on `observations.jsonl`); recover via `git checkout stash@{N} -- <files>`, never force-resolve the WAL file | praxion-health LEARNINGS.md:124 | Rule (update) | `git-conventions.md` already bans bare stash in *multi-agent* worktrees with an `apply`-not-`pop` remedy; this is a narrower single-agent A/B-testing variant with a distinct recovery technique (`stash@{N}` + `checkout --`) worth folding into the same section |
| 2 | Two plan steps with disjoint *files* can still race if both scope pytest to the same `parallel_safe: false` topology group — file-disjointness ≠ test-execution disjointness | praxion-health LEARNINGS.md:~65 (planner "Wave sequencing") | Skill (update) | `test-topology.md` documents `parallel_safe` from the runner's perspective; it lacks the planner-facing consumption gotcha that two waves must be sequenced even when their edited files don't overlap |
| 3 | `pytestmark = [pytest.mark.xfail(strict=False, ...)]` at module level + an explicit removal instruction recorded in `WIP.md`, so a RED-first paired test-engineer step hands off cleanly to the implementer without silently masking a later regression via `XPASS` | onboarding-unification LEARNINGS.md:51 | Skill (update) | Not covered by `testing-strategy` skill's TDD guidance; a reusable paired-step handshake pattern |
| 4 | Anchor characterization/structural tests on stable structural markers (e.g. a specific `### Sub-step N.M` heading) rather than exact prose/heading text the implementer is still free to choose | onboarding-unification LEARNINGS.md:52 | Skill (update) | Bundled with item 3 — same paired-step section of `testing-strategy` |
| 5 | Acceptance criteria must be scoped to the step/pass; a corpus-wide invariant (spanning every file in a category) belongs in a sentinel check, not a step's `Done when` block | praxion-health LEARNINGS.md:431 (verifier disposition) | Skill (update) | Grepped `spec-driven-development` and `software-planning` references for "corpus invariant" / AC-scoping guidance — no hit; the planner nearly failed verification by writing a corpus-wide AC into one step |
| 6 | Codex model-tier adapter was coupled to the routing rule's volatile `Alias` column and broke on a routine alias pin change; re-keyed to the stable `Tier` column instead (dec-draft-41df8a7a) | praxion-health LEARNINGS.md (Decisions Made) | Skill (update) | A concrete, dated case study of Balanced Coupling's strength/volatility heuristic — bind consumers to the stable semantic column, not the label most likely to change. `software-design-principles` skill currently has no adapter/export example |
| 7 | Python regex extracting a markdown section via `re.MULTILINE` `^`/`$` anchors combined with a DOTALL-greedy `.*` walks past the *first* qualifying heading and re-anchors on whichever heading precedes the *last* keyword occurrence in the remainder of the document — fix with anchor-then-slice (`re.search` for the heading line under `MULTILINE` only, then slice to the next `\n##\s` or EOF) | onboarding-unification LEARNINGS.md:89 | Rule (update) | Grepped for `DOTALL`/`anchor-then-slice` across skills+rules — no hit. This repo has many scripts parsing markdown sections by heading (`sync_canonical_blocks.py`, test files cited in the source, etc.); a recurring regex footgun worth a coding-style gotcha |
| 8 | Mechanical ~2,500-line move verified byte-for-byte via `sed -n '<range>p'` extraction (not manual Read/Write transcription) plus a heading-set diff (`## §Phase N`, `### Sub-step N.M`) across source vs destination files | onboarding-unification LEARNINGS.md:61 | Skill (update) | `refactoring` skill's "Verify Re-Wiring and Clean Up" step lacks this concrete large-scale-move verification technique |
| 9 | "Duplicated in N arms" is not the same as "applies to all arms" — hoisting a guard extracted from 3-of-5 switch arms above all 5 silently changes behavior for the other 2 (which handled the null case differently); the hoist is only safe below the arms it wasn't derived from | praxion-health LEARNINGS.md:409 (implementer Step 22) | Skill (update) | Bundled with item 8 — same `refactoring` skill gotcha section, general extraction-safety caution |
| 10 | `.ai-state/doc_manifest.yaml` must regenerate from the canonical checkout, never a worktree (excludes `.claude/` by absolute path) | onboarding-unification LEARNINGS.md:44 | Skip | Already captured verbatim in harness agent-memory (`feedback_build_doc_manifest_claude_exclusion.md`) |
| 11 | Verifier is a ledger writer but didn't run `check_state_ledgers.py` before returning; candidate self-test line for `agents/verifier.md` | praxion-health LEARNINGS.md:435 | Skip | Targets an agent prompt file directly, not a skill/rule/CLAUDE.md; also substantively covered by harness memory `feedback_ledger_writers_run_check_state_ledgers.md` |
| 12 | `dashboard_app/` has no linter/formatter config; style matched to siblings by hand | praxion-health LEARNINGS.md:423 | Skip | Single-project fact about a specific package's tooling gaps, not reusable knowledge |
| 13 | dashboard vitest full-suite parallel-worker contention intermittently exceeds a 5s default timeout on a heavy-import test; bumped to 45s per-file rather than touching shared config; flagged `--no-file-parallelism` as the real CI fix if flakiness recurs | praxion-health LEARNINGS.md:369 | Skip (too narrow/environment-specific — single sandbox's CPU contention characteristic, not a general testing pattern; flagged for the orchestrator already, not for formalization) | — |
| 14 | `RECONSTRUCTED:`/`UNSEALED:` consult-cost provenance labelling convention; G6 vacuity exemption for NONE tombstones; seal-witness monotone-restore predicate | praxion-health LEARNINGS.md (Decisions Made) | Skip | Praxion-internal fitness-gate mechanism, not reusable outside this project's own `CONSULT_*` ledger family |
| 15 | AC12 bidirectional traceability deliberately left unadopted; dashboard `/overview` landing not adopted | praxion-health LEARNINGS.md (Decisions Made) | Skip | Project-specific ADR outcomes, not reusable knowledge |
| 16 | `--profile`/`--with`/`--without` capability resolution is a flat static default table, bash layer does no block-level classification; phase-id-verbatim + capability-vocabulary split (dec-340..346) | onboarding-unification LEARNINGS.md | Skip | Praxion's own onboarding architecture decisions, not generalizable patterns |
| 17 | `seed-pipeline.md` scope-gap objections (flagged, not fixed, across three separate steps) | onboarding-unification LEARNINGS.md:71,73,91 | Skip | Project-specific residual-duplication tracking, already flagged for the planner inline; not a formalizable pattern |
| 18 | Doc-engineer omitted from every parallel group, verified against the architect's own Planner Handoff table | praxion-health LEARNINGS.md | Skip | Already-encoded planner behavior (consult upstream table before assigning doc steps); no new rule needed |
| 19 | Project Principles threaded by id-citation rather than restated per step | praxion-health LEARNINGS.md | Skip | Single-instance application of the already-established Simplicity First / DRY principle; not a new pattern |
| 20 | `--backfill` on `check_state_ledgers.py` is a blunt instrument that also repairs unrelated pre-existing drift; flag it explicitly in the commit message rather than let it pass as an unexplained diff | onboarding-unification LEARNINGS.md:126 | Skip | Narrow tooling-usage caveat, single occurrence; not yet a recurring pattern (sapling at most, insufficient maturity) |
| 21 | Self-referencing `resolved-by` commit SHA is a chicken-and-egg problem; solve with a small honestly-labeled follow-up commit, never amend | onboarding-unification LEARNINGS.md:125 | Skip | Single-instance tooling caveat already implied by the "never amend" git convention; not distinct enough to warrant its own rule line |

## Discipline-Gap Signals

None recorded this batch — no learning item surfaced a recurring "we needed a specialist voice here" signal.

## Proposals

### Proposal 1: git-conventions.md — WAL-hook stash-pop conflict recovery

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: praxion-health `LEARNINGS.md` line 124 ("`git stash` mid-task inside a shared multi-agent worktree is dangerous — a concurrent WAL hook can make `stash pop` un-poppable")
- **Description**: Add a bullet (or extend the existing stash bullet) in `rules/swe/vcs/git-conventions.md` documenting that a repo with an active WAL-writing `PostToolUse` hook (this repo's `.ai-state/observations.jsonl` rewrite-on-every-tool-call) makes `git stash pop` fail on *any* concurrent tool activity, not just multi-agent worktrees — including a single agent doing solo A/B testing. Recovery: `git checkout stash@{N} -- <your files>` restores exactly the intended files without touching the conflicting WAL file; the stash entry survives for later inspection/drop.
- **Rationale**: The existing rule (line 22 of `git-conventions.md`) already bans bare stash in multi-agent worktrees with an `apply`-not-`pop` remedy — this is the same root failure mode (WAL hook noise) surfacing in a different scenario (solo A/B testing, not concurrent agents) with a different, more targeted recovery technique. Folding it in prevents the next agent from re-discovering the same trap via a full stash-pop failure.
- **Estimated scope**: single rule file, one bullet addition (~3-4 lines)
- **Overlap check**: `rules/swe/vcs/git-conventions.md` line 22 (partial — covers the multi-agent case, not the WAL-hook-specific single-agent case); harness memory has a related-but-distinct `feedback_precommit_stash_wipes_tree_with_subagents.md` (commit-time auto-stash, not manual mid-task stash)
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/vcs/git-conventions.md`

### Proposal 2: test-topology.md — file-disjointness ≠ test-execution disjointness

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: praxion-health `LEARNINGS.md` (implementation-planner "Wave sequencing keeps W6 and W10b in separate waves despite disjoint files")
- **Description**: Add a planner-facing consumption gotcha to `skills/testing-strategy/references/test-topology.md` (near the `parallel_safe Semantics` section): two plan steps whose *edited files* are disjoint can still race if both scope their pytest invocation to the same `parallel_safe: false` topology group via a shared expensive fixture. The architect's file-disjointness note is not a substitute for checking topology-group overlap; sequence the waves when groups collide even if files don't.
- **Rationale**: The current doc documents `parallel_safe` correctly from the *runner's* perspective (isolated invocation, no worker mixing) but the planner-level failure mode — mistaking file-disjointness for safety — is not spelled out, and this exact mistake nearly happened in the praxion-health pipeline. A one-paragraph addition closes a real gap between the doc's current audience (runner authors) and its other audience (implementation-planner writing wave assignments).
- **Estimated scope**: single reference file, one subsection addition (~10-15 lines)
- **Overlap check**: `skills/testing-strategy/references/test-topology.md` (exists, partial — covers the mechanism, not this specific planner gotcha); `skills/testing-strategy/references/python-testing.md`, `rust-testing.md` (language leaves, not the planning-layer nuance)
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/testing-strategy/references/test-topology.md`

### Proposal 3: testing-strategy — RED-GREEN paired-step handshake conventions

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: onboarding-unification `LEARNINGS.md` lines 51-52 (test-engineer Steps 11 & 13 learnings)
- **Description**: Add two paired-step conventions to `testing-strategy`'s TDD/RED-GREEN guidance: (1) module-level `pytestmark = [pytest.mark.xfail(strict=False, reason=...)]` for a RED-first file the implementer will later turn GREEN, paired with an explicit removal instruction recorded in `WIP.md` as a handshake — `strict=False` never blocks the suite while genuinely RED, but leaving the marker in place post-implementation would silently mask a real regression (an `xfail` that "passes" reports `XPASS`, not a hard failure). (2) Anchor structural/characterization tests on stable structural markers (e.g. a specific `### Sub-step N.M` heading, an existing precedent like `test_onboard_ci_autofix_install.py`'s anchor) rather than exact prose or heading text the paired implementer is still free to choose — the behavioral contract under test is content/count, not wording.
- **Rationale**: Both are concrete, reusable conventions for the test-engineer/implementer paired-step pattern that recurs across every Standard/Full pipeline; neither is currently documented, so each test-engineer re-derives them independently.
- **Estimated scope**: single reference file (or SKILL.md body if the TDD section is there), one subsection addition (~15-20 lines)
- **Overlap check**: `skills/testing-strategy/SKILL.md`, `skills/testing-strategy/references/gate-canaries.md` (canary self-test heuristic — different, already-covered content; no overlap with the xfail-handshake or anchor-stability points)
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/testing-strategy/SKILL.md` or a new/existing reference under `skills/testing-strategy/references/`

### Proposal 4: spec-driven-development / software-planning — acceptance-criteria scoping

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P0 (this-cycle)
- **Source(s)**: praxion-health `LEARNINGS.md` line 431 (orchestrator verification disposition — "acceptance criteria must be scoped to the pass; a corpus invariant belongs to a sentinel check, not a step done-when")
- **Description**: Add explicit guidance to the acceptance-criteria authoring section of `spec-driven-development` (or `software-planning`'s three-document model reference): a step's `Done when` / acceptance criteria must be scoped to that step's own files/behavior, never to a corpus-wide invariant spanning every file in a category (e.g. "every `.c4` element has X" when the step only touches one file). Corpus-wide invariants belong in a `sentinel` DL0x-style check, which runs independently of any single step and doesn't gate a step's own completion on unrelated pre-existing corpus state.
- **Rationale**: This exact mistake caused a verifier FAIL (AC-13 clause 2) in the praxion-health pipeline — the planner wrote a corpus-wide `affected_files` invariant into one step's acceptance criteria, which no single step could satisfy, and it had to be dispositioned as a deferred tech-debt row rather than a real defect. This is a recurring class of planner error (mistaking "this property should hold everywhere" for "this step must make it hold everywhere") worth a durable guardrail at P0 given it produces false-negative verification failures.
- **Estimated scope**: single reference file, one guidance paragraph + one worked contrast example (~15-20 lines)
- **Overlap check**: grepped `spec-driven-development` and `software-planning` references for "corpus invariant" / AC-scoping language — no existing coverage found
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/spec-driven-development/SKILL.md` or `skills/spec-driven-development/references/` (acceptance-criteria authoring section)

### Proposal 5: software-design-principles — Balanced Coupling case study (stable column vs. volatile alias)

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: praxion-health `LEARNINGS.md` Decisions Made — "Codex model adapter keys on the routing rule's Tier column (dec-draft-41df8a7a)"
- **Description**: Add a concrete, dated case study to `software-design-principles`'s Balanced Coupling section: a Codex export adapter was originally keyed on the routing rule's `Alias` column (`opus`/`sonnet`/`haiku`), which the rule's own documented principles already flagged as unstable (aliases silently track the newest model generation) — a routine alias pin change (`claude-haiku-4-5`) broke eight tests. The fix re-keys the adapter to the rule's stable semantic column (`Tier`: `H`/`M`/`L`) and forbids the adapter from containing any alias literal at all, per the strength/distance/volatility heuristic: bind a consumer to the most stable column that carries the semantic content it needs, not to whichever column happens to be convenient today.
- **Rationale**: This is a clean, verifiable instance of the skill's own core heuristic (documented in a finalized ADR with a concrete before/after and eight-test breakage as evidence) — worth citing as a worked example the way the skill already does for SOLID heuristics, since abstract principle + concrete instance together outperform either alone.
- **Estimated scope**: single skill body or reference file, one example addition (~10 lines)
- **Overlap check**: `skills/software-design-principles/SKILL.md` (Balanced Coupling section exists; no adapter/export example currently present, per the rule's own §Principles #3 alias-instability note already cross-referenced from `rules/swe/agent-model-routing.md`)
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-design-principles/SKILL.md`

### Proposal 6: refactoring skill — mechanical-move verification + partial-duplication hoist guard

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: onboarding-unification `LEARNINGS.md` line 61 (Step 1/3-6/6b implementer, ~2,500-line mechanical move); praxion-health `LEARNINGS.md` line 409 (implementer Step 22, hoisted null-guard)
- **Description**: Add two items to `refactoring`'s "Verify Re-Wiring and Clean Up" step / Gotchas section. (1) **Verification technique for large mechanical moves**: use `sed -n '<range>p'` line-range extraction (not manual Read/Write transcription) to guarantee byte-for-byte fidelity, then verify with a heading-set diff (or equivalent structural-marker diff) between source and destination — a concrete, repeatable technique for moves too large to eyeball. (2) **Partial-duplication hoist guard**: "duplicated in N of M arms" is not the same as "applies to all M arms" — before hoisting a guard/check extracted from a subset of branches above all branches, verify each excluded branch's existing behavior at that point; a guard derived from 3-of-5 switch arms silently changed behavior for the other 2 when naively hoisted to the top.
- **Rationale**: Both are concrete, repeatable techniques/cautions observed in two independent pipelines (large-scale move fidelity; extraction safety), currently absent from the skill's existing verification and gotchas guidance.
- **Estimated scope**: single skill body, two additions to existing sections (~15-20 lines total)
- **Overlap check**: `skills/refactoring/SKILL.md` §"4. Verify Re-Wiring and Clean Up" and §"Gotchas" exist but do not cover either technique
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/refactoring/SKILL.md`

### Proposal 7: coding-style.md — MULTILINE+DOTALL greedy regex section-extraction pitfall

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: onboarding-unification `LEARNINGS.md` line 89 (implementer Batch C — "Fixed a mechanical regex bug in three Step-11/13 test files")
- **Description**: Add a gotcha bullet to `rules/swe/coding-style.md` (Python section, near Input Validation or a new "Regex" sub-bullet): a Python regex extracting a markdown section by combining `re.MULTILINE`'s `^`/`$` line anchors with a DOTALL-greedy `.*` (`r"^##\s*.*Gate.*$.*?(?=\n##\s|\Z)"` style) walks past the *first* qualifying heading once DOTALL makes `.` match newlines — the greedy prefix re-anchors on whichever heading precedes the *last* keyword occurrence anywhere in the remainder of the document, silently producing a too-early, too-large section extract as soon as the target document grows past a single keyword mention. Fix: anchor-then-slice — `re.search` for the heading line under `MULTILINE` only (no DOTALL), then slice the text to the next `\n##\s` boundary or EOF.
- **Rationale**: This is a subtle, non-obvious regex footgun (the bug was invisible until the document grew past one keyword mention, and reproduced identically in three separate test files written independently in this pipeline) that recurs anywhere a script parses markdown by heading — this repo has many such scripts (`sync_canonical_blocks.py`, `check_architecture_projection.py`, and multiple test-file section extractors cited in the source). A one-time gotcha note prevents re-deriving the same bug the next time someone writes a markdown-section-extraction regex.
- **Estimated scope**: single rule file, one gotcha bullet with a worked before/after example (~8-10 lines)
- **Overlap check**: grepped for `DOTALL`/`anchor-then-slice` across `skills/` and `rules/` — no existing coverage
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/coding-style.md`

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | Rule update (`git-conventions.md`); load `rule-crafting` |
| 2 | context-engineer | Skill reference update (`test-topology.md`); load `skill-crafting` |
| 3 | context-engineer | Skill update (`testing-strategy`); load `skill-crafting` |
| 4 | context-engineer | Skill update (`spec-driven-development`); load `skill-crafting`; P0 — recommend prioritizing, caused a real verifier FAIL |
| 5 | context-engineer | Skill update (`software-design-principles`); load `skill-crafting` |
| 6 | context-engineer | Skill update (`refactoring`); load `skill-crafting` |
| 7 | context-engineer | Rule update (`coding-style.md`); load `rule-crafting` |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 7 pending proposals (this batch) alongside the earlier batch's 4.
- Prioritize Proposal 4 (acceptance-criteria scoping) — it traces directly to a verifier FAIL in a completed pipeline.
- After approval, invoke `context-engineer` for the skill/rule updates; the agent will pick up the recommended delegations table.
- Continue queue-mode harvesting through the remaining batches (3–13) before a final consolidated `/skill-genesis-review` pass.
