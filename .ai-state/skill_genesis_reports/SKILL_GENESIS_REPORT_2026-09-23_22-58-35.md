---
schema_version: 1
report_id: skill-genesis-2026-09-23_22-58-35
generated_at: 2026-09-24T06:00:02Z
task_slug: skill-genesis-2026-09-23
agent_version: skill-genesis@bfebf639
invocation_args: { since: null, scope: null, sources: .ai-work/_harvest, batch: "7 of 13", dry_run: false }
review_status: pending
disposition_count: { pending: 8, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-09-23 22:58:35

## Summary

1 learning source analyzed (`.ai-work/_harvest/process-economy-p3-1`, LEARNINGS.md 1019 lines +
VERIFICATION_REPORT.md 612 lines), 19 candidate items extracted, 8 proposals generated, 11
deduplicated/discarded (already captured by harness agent memory, too narrow/transient, or
overlapping a pending proposal from an earlier batch of this same harvest run). Review status:
pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| Queue source: LEARNINGS.md | `.ai-work/_harvest/process-economy-p3-1/LEARNINGS.md` | 13 | Read |
| Queue source: VERIFICATION_REPORT.md | `.ai-work/_harvest/process-economy-p3-1/VERIFICATION_REPORT.md` (Findings F1–F10 + patterns) | 6 | Read |
| Latest SENTINEL_REPORT_*.md | `.ai-state/sentinel_reports/` | 0 | Not consulted (single-source batch, budget-scoped) |
| Latest IDEA_LEDGER_*.md | `.ai-state/idea_ledgers/IDEA_LEDGER.md` | 0 | Read (no overlap found) |
| ADRs (recent) | `.ai-state/decisions/` | 0 | Not queried (no file-scope match needed; items are cross-cutting conventions) |
| Calibration log Retrospective cells | `.ai-state/calibration_log.md` | 0 | Not consulted (queue-mode source is this run's primary input) |
| Sibling reports of this harvest run | 6 prior `SKILL_GENESIS_REPORT_2026-09-23_*.md` (pending) | — | Read, greped `## Proposals` headings — no overlap with this batch's proposals |
| Harness agent memory | `~/.claude/projects/-Users-fperez-dev-praxion/memory/MEMORY.md` | — | Read — 2 items discarded as already-captured (worktree transcript-dir mangling, `build_doc_manifest` `.claude/` exclusion) |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | Purity refactor relocates the defect to an untested I/O adapter (`readiness()` pure+covered, `dirty_paths()` impure+uncovered) | VERIFICATION_REPORT.md § Process patterns (verifier) | Skill (update, testing-strategy) | Recurring, generalizable testing methodology; explicitly phrased as a "Rule:" by the verifier |
| 2 | `git status --porcelain` column-slicing after `.strip()` corrupts the first line | VERIFICATION_REPORT.md F1 + LEARNINGS.md Step 10 rework | Rule (new or update, coding-style.md) | Declarative, reusable gotcha for any git-porcelain parser; intermittent-by-construction failure mode |
| 3 | ADR H1 headline must be re-titled on decision reversal, not only frontmatter `title:` | VERIFICATION_REPORT.md F7 | Rule (update, adr-conventions.md) | Declarative ADR-authoring constraint, applies across all pipelines |
| 4 | `affected_files` is a discovery index, not a changelog — list new files before modified files | VERIFICATION_REPORT.md F7 | Rule (update, adr-conventions.md) | Declarative ADR-authoring constraint; directly affects `query_adrs.py --paths` discoverability |
| 5 | Ephemeral `.ai-work/<slug>/` paths and dotted milestone ids in shipped code/`--help` output escape `check_id_citation_discipline.py`'s shape set | VERIFICATION_REPORT.md F6 | Rule (update, id-citation-discipline.md) | Extends an existing, explicitly-scoped gap in a rule this repo already maintains |
| 6 | "Zero of everything" (`pass=0 fail=0 skip=0` / collection error) reads green to both `TEST_RESULTS.md` readers | VERIFICATION_REPORT.md F4 + § Process patterns | Rule (update, coding-style.md § Error Handling) | Declarative constraint ("check the total, not just the failure count"); distinct from the pending totalising-check proposals in batch `22:47`/`22:51` (those cover exhaustive-grammar/registry patterns for scanners, not test-result-line classification) |
| 7 | A satisfied `REWORK_MANIFEST.md` must be deleted, not kept "for the audit trail" | VERIFICATION_REPORT.md § Process patterns (verifier) | Rule (update, swe-agent-coordination-protocol.md, Verifier rework loop row) | Declarative coordination-protocol constraint; prevents a resolved manifest from re-triggering a worktree spawn |
| 8 | A widening rule-set (readiness/refusal gates) should union its conditions, not shadow via first-non-empty chain | LEARNINGS.md § Step 10 rework (implementer) | Rule (new candidate, ambiguous placement — software-design-principles vs. coding-style) | Generalizable design heuristic beyond this one gate; flagged ambiguous, context-engineer to place |
| 9 | Half-fixed two-halves finding: append a dated "half X closed, half Y remains" clause instead of closing or leaving the ledger row unchanged | VERIFICATION_REPORT.md § Re-verification patterns | Skip | Narrow to `TECH_DEBT_LEDGER.md` row-editing mechanics already governed by `tech-debt-ledger.md`'s schema; the general principle ("don't lose the surviving half") is implicit in "narrow the row, don't close it" already documented there per the artifact-inventory summary — insufficient novelty to formalize separately |
| 10 | Re-measure file-size ceilings after a rework pass, not only after a feature (td-208's 4th/5th recurrence) | VERIFICATION_REPORT.md § Re-verification patterns | Skip | Restates an already-filed, already-generalized tech-debt observation (td-208); no new mechanism proposed, would duplicate existing ledger row's own point |
| 11 | "Verify a documented limit from the vantage point the doc is read from" (caveat placed away from the instruction it qualifies) | VERIFICATION_REPORT.md F5 + § Process patterns | Skip | Sound but single-instance; below the ≥3-scenario skill bar and too general for a declarative rule line without more recurrence |
| 12 | Worktree-mangled `~/.claude/projects/` transcript directory is invisible to a single `--project-root` invocation | LEARNINGS.md Step 13 | Skip (already captured) | Matches harness memory `context_baseline worktree dir resolution` verbatim in mechanism |
| 13 | `check_doc_manifest_freshness`/`build_doc_manifest.py` excludes `.claude/` by absolute-path check, breaking worktree regeneration | LEARNINGS.md Step 15 | Skip (already captured) | Matches harness memory `build_doc_manifest .claude exclusion` |
| 14 | When splitting a module, check which names tests `monkeypatch` *by module path* before deciding what crosses the seam (the `datetime.now()` clock stayed put) | LEARNINGS.md Step 10 rework (file-size split) | Discipline-gap/Skip | Single-instance refactoring gotcha; close cousin of the pending "mechanical-move verification" proposal already filed in batch `22:39` Proposal 6 — noted as overlap, not re-proposed |
| 15 | `TEST_RESULTS.md` convention: a RED row should name the later step/row that turns it green | VERIFICATION_REPORT.md § Process patterns | Skip | Narrow, single-artifact convention already partially covered by dec-386's shape contract; not enough independent recurrence to warrant a new rule line |
| 16 | Consumer-check pattern for additive WAL `event_type` values: grep every reader for *negation* filters, not just positive-match filters | LEARNINGS.md Step 6 | Skip | Specializes the already-captured "Consumer check includes LLM readers" harness memory to WAL schemas; single instance |
| 17 | `--table` CLI flag accepted but functionally identical to default; documented as non-load-bearing by the implementer itself | LEARNINGS.md Step 13 | Skip | Explicitly flagged non-load-bearing by its own author; no formalization value |
| 18 | AC-7's load-bearing assumption surfaced in three independent places (HANDOFF §3, AC-7 Evidence, ADR `dissent:`) — praised pattern | VERIFICATION_REPORT.md § What went unusually well | Skip | Positive-confirmation instance of the existing Surface Assumptions behavioral-contract tenet; illustrative but not a new rule content |
| 19 | Three always-on `SessionStart` hooks get cancelled (not merely delayed) when they share the empty matcher with a slow `compact`-matcher hook, under interpreter-startup contention at the compaction moment | LEARNINGS.md § AC-7 Evidence — live run | Skip | Filed as `td-219` already; a live-corpus hook-timing observation, not a generalizable authoring rule — correctly stays a tech-debt row, not a skill/rule proposal |

## Proposals

### Proposal 1: testing-strategy — pure-core/impure-adapter split needs its own adapter test

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-p3-1/VERIFICATION_REPORT.md` § Process patterns ("A purity refactor relocates the defect site, and the tests usually do not follow"), F1, and the paired test-engineer learning ("A gate's I/O adapter needs at least one test through the real adapter, not only its pure core")
- **Description**: Add a subsection to `skills/testing-strategy/references/gate-canaries.md` (or a new `references/pure-adapter-split.md`) stating: when a design factors a gate/check into a pure decision function plus an impure I/O adapter (e.g. `readiness()` vs `dirty_paths()`), full test coverage of the pure function proves nothing about the adapter — the adapter must have at least one test exercised against *real* output of the thing it wraps (real `git status --porcelain` output, not a hand-written Python list). Worked example: `compose_handoff.py`'s `readiness()` was 100% covered via literal lists; `dirty_paths()`'s `.strip()`-then-`line[3:]` corruption of the first porcelain line was invisible to every test because none called it.
- **Rationale**: This is exactly the class of "gotcha that breaks the agent's default reasoning" the skill-crafting spec singles out as highest-signal content — a fully green test suite gave false confidence over a real fail-open security-relevant bug (a readiness gate that reported `ready` over a dirty tree). It recurs by construction whenever a purity refactor is applied (a common, encouraged pattern per `software-design-principles`), so the failure mode will recur elsewhere.
- **Estimated scope**: SKILL.md reference update (append to `gate-canaries.md`, currently 43 lines — stays well under the file's implicit size budget)
- **Overlap check**: `skills/testing-strategy/references/gate-canaries.md` covers gate-testing methodology generally but has no existing content on the pure/impure adapter split; no overlap with pending sibling proposals from earlier batches (those cover totalising-scan patterns and RED/GREEN handshake conventions, a different axis)
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/testing-strategy/references/gate-canaries.md`

### Proposal 2: coding-style.md — `git status --porcelain` column-slicing after `.strip()` corrupts the first line

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-p3-1/VERIFICATION_REPORT.md` F1 ("`git_output()` strips the whole output... every porcelain line is `XY path`... the first line loses the path's first character") and LEARNINGS.md § Step 10 rework F1-F3 (root cause + fix: `run_git` raw stdout + `--porcelain -z`)
- **Description**: A short "Git Porcelain Parsing" entry for `rules/swe/coding-style.md`'s Error Handling or a new small subsection: never call a shared `.strip()`-the-whole-output helper before column-slicing `git status --porcelain` lines — the first line's leading status-column space is eaten by an aggregate strip, corrupting only that line (the defect is invisible with 2+ dirty files, since only the first line loses its leading character). Prefer `git status --porcelain -z` (unquoted paths, rename handled as its own record) or slice from raw unstripped stdout.
- **Rationale**: A concrete, high-confidence, declarative gotcha that meets the rule bar (applies across any future git-porcelain-parsing code in this ecosystem, not project-specific) and is intermittent-by-construction — exactly the kind of failure an agent would reproduce with a two-file test fixture and never catch.
- **Estimated scope**: single rule file edit (a few lines added to an existing section)
- **Overlap check**: none — `coding-style.md`'s Error Handling section (line 175) has no git-specific content
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/coding-style.md` (§ Error Handling)

### Proposal 3: adr-conventions.md — re-title the ADR H1 body heading when a decision reverses, not only the frontmatter

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-p3-1/VERIFICATION_REPORT.md` F7 — `dec-387`'s frontmatter `title:` was correctly rewritten after a mid-pipeline decision reversal, but the H1 body heading still headlined the rejected design (a 50% harness-enforced band, a 1 KiB PostCompact restore) — both explicitly rejected
- **Description**: Add one line to `rules/swe/adr-conventions.md` (Agent Writing Protocol or Finalize Protocol section): when a decision under active drafting reverses mid-pipeline, grep and update *both* the frontmatter `title:` and the body's `# <H1>` heading — a draft finalizes to a permanent `dec-NNN` record and whatever the H1 asserts is what the record says forever, independent of the frontmatter.
- **Rationale**: Declarative, applies to every ADR-writing agent (systems-architect, implementation-planner) across every pipeline that amends architecture mid-flight (an explicitly supported, documented workflow per the pre-mortem gate). Cheap to encode, catches a permanent-record defect class.
- **Estimated scope**: single rule file edit (one line/bullet)
- **Overlap check**: none — the existing rule covers frontmatter fields and relation protocols but has no instruction about the body H1 tracking a retitle
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/adr-conventions.md`

### Proposal 4: adr-conventions.md — `affected_files` lists new files before modified files (it is a discovery index, not a changelog)

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-p3-1/VERIFICATION_REPORT.md` F7 — the ADR listed the nine files it *modified* and omitted the six it *created*, including every new component that is the ADR's own justification for `category: architectural`; `scripts/query_adrs.py --paths` matches on `affected_files`, so a future edit to a created-but-unlisted file (e.g. `compose_handoff.py`) would never surface this decision
- **Description**: Add a constraint to `rules/swe/adr-conventions.md`'s frontmatter-fields description for `affected_files`: list newly-created files first, then modified files — `affected_files` is a discovery index consumed by `query_adrs.py --paths` for future changes to those paths, not a diff/changelog of the current commit; omitting a new file breaks discoverability for every future editor of that file, which is precisely the architectural-decision context the field exists to surface.
- **Rationale**: Directly load-bearing for the ADR discovery protocol this rule file already documents (`query_adrs.py --paths` is the *recommended* pre-scan tool); an incomplete `affected_files` silently defeats that recommendation for the newest, most architecturally significant files in a change.
- **Estimated scope**: single rule file edit (a clause added to the `affected_files` row in the Frontmatter table, and to the Agent Writing Protocol pointer)
- **Overlap check**: none — current field description in the rule doesn't specify created-vs-modified ordering
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/adr-conventions.md`

### Proposal 5: id-citation-discipline.md — ephemeral `.ai-work/` paths and dotted milestone ids in shipped code escape the gate's shape set

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-p3-1/VERIFICATION_REPORT.md` F6 — `context_baseline.py` cites `.ai-work/process-economy-p3-1/BASELINE.md` in its module docstring and "the P3.1 baseline" in its argparse `description` (i.e. `--help` output from a script installed onto `PATH`); `check_id_citation_discipline.py` reports clean because it matches only `REQ-`/`AC-`/`DS-`/`Step N`/`dec-draft-` shapes, and neither an `.ai-work/` path nor a dotted milestone id is one of those shapes
- **Description**: Document this as a **known limitation** of `check_id_citation_discipline.py` in `rules/swe/id-citation-discipline.md` (if it doesn't already carry a Known Limitations section — two are already pending from earlier batches of this harvest run, both about worktree-blindness and full-file-scan scope; this is a third, distinct limitation about the *shape set* the scanner matches). State the mitigation: an author writing a durable/shipped script must manually grep for `.ai-work/` and for dotted-milestone-style ids (e.g. `P3.1`, `p3-1`) before commit, since the mechanical gate does not catch this shape.
- **Rationale**: This repo already treats `id-citation-discipline.md`'s known-limitations as a living, incrementally-extended list (two prior batches of this same harvest already proposed additions to it); this is a distinct, concretely-reproduced gap (ephemeral-path + milestone-id shapes, not the worktree-scope or scan-breadth gaps already proposed) worth adding to the same list rather than skipping.
- **Estimated scope**: single rule file edit (append to Known Limitations)
- **Overlap check**: `id-citation-discipline.md` Known Limitations — extends but does not duplicate the two pending limitation-additions from `SKILL_GENESIS_REPORT_2026-09-23_22-35-25.md` Proposal 4 (worktree self-verification) and `SKILL_GENESIS_REPORT_2026-09-23_22-43-59.md` Proposal 6 (full-file-scan, not diff-only) — this is a third, shape-based gap
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/id-citation-discipline.md`

### Proposal 6: coding-style.md — a zero-total test-result line ("pass=0 fail=0 skip=0") is not green

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-p3-1/VERIFICATION_REPORT.md` F4 and § Process patterns ("Zero-of-everything is not green... a pytest collection error renders... as `Result: pass=0 fail=0 skip=0`, and both readers of that shape classify it green... Check the total, not just the failure count")
- **Description**: Add a declarative constraint to `rules/swe/coding-style.md`'s Error Handling section: any parser or gate that classifies a test-run summary as pass/fail must treat a zero total (`pass=0 fail=0 skip=0`, or any all-zero variant) as **not green** — a collection error or empty run renders identically to a clean pass under a "no failures found" classifier, and that ambiguity must be resolved toward suspicion, not success.
- **Rationale**: A concrete, reproducible defect class (confirmed live for two independent readers of the same `TEST_RESULTS.md` shape: the reconciler and `check_test_results_shape.py`) that generalizes past this one pipeline to any future test-summary parser written against the dec-386 shape contract.
- **Estimated scope**: single rule file edit (a bullet under Error Handling)
- **Overlap check**: distinct from the pending totalising-check/exhaustive-grammar proposals in `SKILL_GENESIS_REPORT_2026-09-23_22-47-22.md`/`_22-51-24.md` (those address scanner registries and grammar coverage, not test-result-count classification); no overlap
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/coding-style.md` (§ Error Handling)

### Proposal 7: swe-agent-coordination-protocol.md — a satisfied REWORK_MANIFEST.md must be deleted, not kept for the audit trail

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-p3-1/VERIFICATION_REPORT.md` § Re-verification stage ("A satisfied rework manifest must be deleted, not left as a record. The main agent spawns one worktree per `REWORK_MANIFEST.md` row on sight of the file. Keeping a resolved manifest 'for the audit trail' would dispatch a worktree with nothing to fix; the trail belongs in `VERIFICATION_REPORT.md`, which survives longer anyway.")
- **Description**: Add a one-line constraint to `rules/swe/swe-agent-coordination-protocol.md`'s "Verifier rework loop" pipeline-rule row: once every `td-NNN` row in `REWORK_MANIFEST.md` is confirmed resolved by re-verification, the verifier (or the orchestrator on its behalf) deletes the file rather than retaining it — its presence is itself the trigger for the main agent to spawn a rework worktree, so a resolved-but-undeleted manifest re-fires the loop on nothing.
- **Rationale**: A concrete operational hazard in a mechanism this repo already runs (the rework loop is documented, named, and load-bearing) — an easy, cheap-to-encode fix that prevents a wasted worktree spawn on every future rework cycle.
- **Estimated scope**: single rule file edit (one line in the pipeline-rules table's "Verifier rework loop" row, or its deep-dive in `coordination-details.md`)
- **Overlap check**: none — the current row describes creation of rework worktrees and `REWORK_MANIFEST.md` triggers, but not the teardown/deletion step
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/swe-agent-coordination-protocol.md` (Verifier rework loop row) or `skills/software-planning/references/coordination-details.md`

### Proposal 8: Widening rule-sets should union, not shadow via first-non-empty fallback chain

- **Disposition**: pending
- **Type**: rule (new candidate — ambiguous placement)
- **Maturity**: sapling
- **Scope**: medium
- **Priority**: P2 (someday)
- **Source(s)**: `.ai-work/_harvest/process-economy-p3-1/LEARNINGS.md` § Step 10 Learnings (implementer, rework F1-F3): "The lesson behind the chain being wrong in the first place: a fallback chain answers 'where do I look?' when the real question was 'what must be true?'. First-non-empty quietly makes a *narrower* answer win whenever it exists, which is precisely the wrong direction for a gate — a widening rule set should union, not shadow."
- **Description**: A design heuristic for any future refusal/blocking gate with multiple candidate rule sources (e.g. "declared step files" vs. "every unfinished step's union" vs. "every dirty path"): when the rule's purpose is to *widen* what gets caught (a safety gate), compose candidate sources by union, never by first-non-empty precedence — a narrower answer silently winning defeats the gate's own justification. This generalizes past the one gate (`compose_handoff.py`'s `dirty-step-files`) that surfaced it.
- **Rationale**: A single, well-articulated instance so far (sapling maturity) but the reasoning is crisp and portable: it names a recognizable anti-pattern (fallback-chain-as-implicit-narrowing) distinct from existing SOLID/Balanced-Coupling heuristics already documented. Flagged ambiguous rather than assigned a path because it could live in `software-design-principles` (a design heuristic) or as a coding-style constraint (a gate-authoring rule) — the context-engineer is the authoritative placement expert per the triage decision tree's ambiguous-case guidance.
- **Estimated scope**: single rule file edit, or a short SKILL.md reference addition — depends on placement decision
- **Overlap check**: none found in `skills/software-design-principles/SKILL.md` or `rules/swe/coding-style.md` for this specific pattern (fallback-chain vs. union for widening/safety gates)
- **Recommended delegation**: context-engineer (placement decision first, then draft)
- **Suggested artifact path**: TBD — `skills/software-design-principles/references/*.md` or `rules/swe/coding-style.md`, context-engineer to decide

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | Skill reference update; load `skill-crafting` |
| 2 | context-engineer | Rule update; load `rule-crafting` |
| 3 | context-engineer | Rule update; load `rule-crafting` |
| 4 | context-engineer | Rule update; load `rule-crafting` |
| 5 | context-engineer | Rule update (Known Limitations append); load `rule-crafting`; coordinate with the two pending sibling limitation-additions from earlier batches of this harvest run |
| 6 | context-engineer | Rule update; load `rule-crafting` |
| 7 | context-engineer | Rule update; load `rule-crafting` |
| 8 | context-engineer | Placement decision required first (design-principles vs. coding-style), then draft |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 8 pending proposals.
- Proposals 3, 4, and 5 all touch `rules/swe/adr-conventions.md` / `rules/swe/id-citation-discipline.md`; consider batching them into a single context-engineer delegation alongside the equivalent pending proposals from earlier batches of this same harvest run (`22:35-25`, `22:43-59`) to avoid repeated edits to the same rule files.
- After approval, invoke `context-engineer` for rule/skill updates; the agent will pick up the recommended delegations table.
- This is batch 7 of 13 in a queued harvest — further batches will continue to surface proposals from the remaining parked pipeline directories; do a final consolidated dedup pass across all 13 batch reports before running `/skill-genesis-review`.
