---
schema_version: 1
report_id: skill-genesis-2026-09-23_23-16-24
generated_at: 2026-09-23T23:16:24Z
task_slug: skill-genesis-2026-09-23
agent_version: skill-genesis@f731fa8e
invocation_args: { since: null, scope: null, sources: ".ai-work/_harvest", batch: "12 of 13", dry_run: false }
review_status: pending
disposition_count: { pending: 6, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-09-23 23:16:24

## Summary

1 learning source (`.ai-work/_harvest/sentinel-phase-b/`, LEARNINGS.md 424 lines + VERIFICATION_REPORT.md 523 lines)
analyzed. ~16 discrete learning items extracted from the sentinel-check-family-envelope pipeline (implementer
fragments A1–C2 plus verifier patterns). After deduplication against existing skills/rules and this run's 11 prior
batch reports, 6 proposals generated; 10 items skipped (too narrow/transient, or fully subsumed by the sentinel's own
existing docstrings/tests). Review status: pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| Queue source: LEARNINGS.md | `.ai-work/_harvest/sentinel-phase-b/LEARNINGS.md` | 13 | Read |
| Queue source: VERIFICATION_REPORT.md | `.ai-work/_harvest/sentinel-phase-b/VERIFICATION_REPORT.md` | 4 (Behavioral Contract Findings + Patterns section overlaps LEARNINGS.md fragment C2) | Read (headings scanned; body read via LEARNINGS.md fragment C2's duplicated verifier patterns) |
| Latest SENTINEL_REPORT_*.md | `.ai-state/sentinel_reports/` | 0 | Not consulted (batch scope is narrow and time-boxed; LEARNINGS.md already carries the sentinel pipeline's own findings) |
| Latest IDEA_LEDGER_*.md | `.ai-state/idea_ledgers/` | 0 | Not consulted this batch (queue-mode volume favors per-source extraction; no candidate item required ledger cross-check) |
| ADRs | `.ai-state/decisions/` | 1 grep pass | Grepped for "family envelope"/"additive"/"superset" — no matching ADR |
| Calibration log Retrospective cells | `.ai-state/calibration_log.md` | 0 | Not consulted (queue-mode batch; source directory carries its own decisions/learnings sections) |
| Sibling reports (this run, batches 1–11) | `.ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_2026-09-23_{22-35-25..23-13-26}.md` | grep dedup pass | Read via grep for overlapping keywords (family envelope, mutation probe, consumer enumeration, worktree guard, commit granularity) — one adjacent-but-distinct match (mutation-probe fixture fidelity, batch `22-55-14`) |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | A shared list key read by two consumers with different classification semantics is not safely additive, even though dict keys are (list membership is reclassified, not just extended) | LEARNINGS.md A1 light-review §145 | Rule/Skill | Declarative software-design gotcha, applies beyond this codebase — Skill (update) |
| 2 | Mutation probes need adversarial noise inside the *selected/winning* file, not just a bigger sibling/parent file, or file-selection alone masks the mutant | LEARNINGS.md C1 §399 | Skill (update) | Extends existing `gate-canaries.md` mutation-probing content (complementary to a prior batch's fixture-fidelity proposal, not a duplicate of it) |
| 3 | Consumer enumeration scoped to code greps is blind to prose consumers in `commands/`/`agents/` files — a fix must reach the LLM-facing prose, not just key names | LEARNINGS.md verifier Patterns §418–420 | Skip | Already captured in the harvester's own memory (`feedback_consumer_check_includes_llm_readers.md`) from a near-identical prior incident — no new artifact warranted, the existing memory + prior corrective behavior already covers this |
| 4 | A provenance/attribution marker ("which source did this come from") must be returned by the chooser function, not re-derived beside it by re-calling the same selector and inferring by equality | LEARNINGS.md verifier Patterns §422 | Rule/Skill | General software-design principle (avoid re-deriving a decision that was already computed) — Skill (update) |
| 5 | `git ls-files`-based test corpora silently return an empty corpus (not an error) against an uncommitted `tmp_path` fixture — a sibling failure mode to the existing "Fixtures Under Gitignored Paths" gotcha, via a different mechanism (uncommitted vs gitignored) | LEARNINGS.md A7 §205–213 | Rule (update) | Extends `testing-conventions.md`'s existing fixture-fidelity section with a second false-green mechanism |
| 6 | Commit granularity should follow atomicity units, not plan steps 1:1 — when splitting a multi-step spawn's steps into separate commits would leave the test suite RED between commits, the systems-architect-mandated atomicity wins over 1-step-per-commit | LEARNINGS.md implementation-planner Decisions §93 | Rule (update) | Sharpens the existing "each step fits in a single commit" / "leave the system in a working state" invariants with an explicit tie-break rule |
| 7 | Worktree Bash guard refuses a `for` loop over script names computed at runtime and a heredoc-written helper script; workaround is Write-tool-to-`tmp/` then plain `uv run python tmp/<x>.py` | LEARNINGS.md gotchas §81–83 | Skip | The two prior worktree-guard command-text heuristics memories are marked RETIRED (v0.30.0, dec-379); this pipeline's worktree predates or bypassed that retirement, and re-proposing guard-workaround content risks encoding stale friction into a rule right as the mechanism it describes is being removed — not durable enough to formalize |
| 8 | `run_check_families.py` reads a fixed six-key envelope by key lookup (never a closed schema), so scripts can add family keys beside existing `--json` keys without a wrapper component | LEARNINGS.md systems-architect Decisions §7–15 | Skip | Sentinel-internal architectural decision, already recorded in the pipeline's own ADR (`dec-draft-34af7f36`) per `adr-conventions.md`'s "who writes ADRs" — no separate skill/rule warranted, it is Praxion-internal implementation detail, not a portable pattern |
| 9 | Severity, not just finding presence, must carry a "never FAIL" guarantee — gate on `severity` at the aggregator (`CheckAggregate.bump()`), not on early-returning an empty findings list | LEARNINGS.md A6 §186 | Skip | Sentinel-specific mechanics (ties to `run_check_families.aggregate_family`'s internal bump logic); too narrow to generalize beyond this one aggregator |
| 10 | `T02`'s "ceiling" must read the frozen ratchet baseline (no side effects) rather than call a stateful `ratchet()` function from inside a per-sweep read-only check | LEARNINGS.md A6 §184 | Skip | Narrow, single-script gotcha; the general principle (a read-only check must not trigger a write side effect) is already implicit in existing coding-style conventions, not novel enough to formalize separately |
| 11 | The `_delegated_gates` regex scans all of `agents/sentinel.md` prose (not just table rows) for script citations, so deleting a script's only prose citation silently drops it from canary-coverage scope | LEARNINGS.md gotchas §77–80 | Skip | Sentinel-internal mechanic, narrow scope (one regex, one file) |
| 12 | A Lane-A scoped-green test run cannot see the check-registration triangle failing, because the triangle only binds *registered* scripts — an unregistered script can pass its own canary while later failing once registered | LEARNINGS.md orchestrator gotcha §113–119 | Skip | Narrow to this pipeline's specific triangle/registry mechanism; the underlying principle (a scoped test run can miss a cross-cutting invariant that only a later, wider registration step exposes) is a specific instance of "scoped tests give false confidence about global invariants" already covered by `ci-equivalent-test-invocation` memory and testing-conventions guidance |
| 13 | Concurrent Lane A/B land in a shared worktree can surface a disk/tracker lag — a downstream file already contains an upstream step's edits before `WIP.md` marks that step done | LEARNINGS.md B1 §238–253 | Skip | Emergent property of this specific parallel-lane worktree topology; transient, not a reusable pattern beyond "re-run the full suite before declaring green in a shared worktree," which is already covered by CI-equivalent-invocation guidance |
| 14 | `--class`-style CLI filters applied in `main()` narrow the output arrays but leave the envelope's own summary counts unfiltered, producing a self-contradicting payload | VERIFICATION_REPORT.md R-2 / LEARNINGS.md verifier Patterns §424 | Skip | Sentinel-internal (`adr_health.py --class`); the general principle ("a filter downstream of a summary computation reaches only one of several views of the same data") is a specific case of Item 4's "don't re-derive, return from source" family — folded into Proposal 4's rationale rather than proposed separately |
| 15 | The `EXTRACTED_CHECKS` registry should be extended with only the missing entries, not re-appended wholesale, to keep an append-only registry free of duplicates | LEARNINGS.md B1 §233–236 | Skip | Narrow, single-registry mechanic |
| 16 | AC14's advisory severity ("never FAIL") maps to the existing `"warn"` vocabulary rather than inventing a bespoke string, matching the codebase's existing severity taxonomy | LEARNINGS.md A3 §176 | Skip | Sentinel-internal naming convention; not a generalizable pattern |

## Proposals

### Proposal 1: Shared collection contracts are per-consumer, not additive-by-default

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/sentinel-phase-b/LEARNINGS.md` fragment A1 "Light-review revision (F1 + F2)" (lines ~145)
- **Description**: Add a gotcha/heuristic to `software-design-principles` (or its `data-structure-design` sibling): when two independent consumers read the same collection-typed field (a shared `findings[]`-style list), adding dict *keys* to individual items is additive-safe, but changing which items land in the shared *list* is not — any consumer that buckets/classifies list membership (e.g. `groupby(item["kind"])`) will silently reclassify entries that a second consumer only ever intended for its own read path. The fix pattern is to split by *consumer*, not to widen the shared key's dict shape further — introduce a second, consumer-scoped key (as this pipeline did: `decay_findings` for the legacy reader, `findings` for the family aggregator) the moment one consumer's read semantics would misinterpret entries meant only for the other.
- **Rationale**: This is a specific, previously-unnamed corollary of the "additive change" heuristic that generalizes well beyond this codebase — anywhere multiple readers share one collection-typed contract field (event logs, findings lists, envelope payloads). It was caught only via a **verifier light-review round**, meaning the author's own dict-superset reasoning ("keys are additive, so this is safe") was plausible enough to survive implementation and self-review; a named heuristic would catch it earlier next time.
- **Estimated scope**: SKILL.md + 1 reference file update (add a subsection, ~15-20 lines, to an existing data-contract/interface-design reference)
- **Overlap check**: `software-design-principles` SKILL.md discusses coupling/cohesion generally but has no existing content on collection-typed contract fields specifically; `data-structure-design` skill covers "parse at the boundary" but not this multi-consumer-collection nuance. No direct overlap found.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-design-principles/references/` (new subsection in an existing coupling/interfaces reference, name TBD by context-engineer) or `skills/data-structure-design/SKILL.md` (context-engineer's call — both are plausible homes)

### Proposal 2: Mutation probes need adversarial noise inside the winning selection, not just a bigger context

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `.ai-work/_harvest/sentinel-phase-b/LEARNINGS.md` fragment C1 (lines ~399)
- **Description**: Add a short callout to `skills/testing-strategy/references/gate-canaries.md`'s mutation-probing guidance: a mutation probe that only tests "does file selection prefer the right file" will pass identically whether or not the per-line equality/tag-filtering logic inside the selected file is correct, if the selected file's own fixture content is entirely clean (no noise line the mutant could wrongly admit or exclude). The probe fixture must plant at least one adversarial (noise) line *inside the winning file itself* so the mutated logic's contribution is observable independent of file-selection.
- **Rationale**: A prior batch of this same harvest run (`SKILL_GENESIS_REPORT_2026-09-23_22-55-14.md` Proposal, targeting the same file) already proposes a related-but-distinct fixture-fidelity lesson (synthetic fixtures must mirror the real artifact's structure). This item is complementary — file-selection vs. in-file noise — not a duplicate; recommend bundling both into the same reference-file edit at drafting time to avoid two near-simultaneous small PRs to one file.
- **Estimated scope**: single skill reference file, 3-5 line addition
- **Overlap check**: `SKILL_GENESIS_REPORT_2026-09-23_22-55-14.md` Proposal (fixture-fidelity-to-real-artifact) targets the same file with adjacent but non-overlapping content — flag for joint drafting, not merge into one proposal (distinct enough to disposition independently)
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/testing-strategy/references/gate-canaries.md`

### Proposal 3: Return provenance from the chooser; never re-derive a decision beside it

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/sentinel-phase-b/LEARNINGS.md` verifier Patterns (lines ~422, ~424 — the `--class` filter contradiction is the same family)
- **Description**: Add a gotcha to `software-design-principles` naming this failure mode: when a function selects among N options (a file, a branch, a source) and a downstream site needs to know *which* option was selected, the selection must be returned as a value from the chooser — never re-derived by a second site re-calling the same selector and inferring the outcome by equality/comparison. The bug is invisible under N=2 (the re-derivation and the original selection happen to agree) and becomes silently wrong the moment a third option is added, because the tests that pinned the two-outcome behavior still pass. The `--class`-filter-narrows-only-some-views case is the same root defect one level up: a value computed once (the full-corpus summary) and a value computed downstream (the filtered array) diverge because the filter was applied *after* the summary rather than *before or alongside* it — "attribution" and "filtering" are both instances of "a derived view forgets to stay in sync with the value it was derived from."
- **Rationale**: This is a durable, cross-domain code-review heuristic (a specific instance of "don't compute the same thing twice" applied to selection/attribution logic) surfaced independently twice in the same verification pass — strong signal it recurs and is easy to introduce even under review.
- **Estimated scope**: SKILL.md + reference file, ~10-15 line addition (gotcha + one worked before/after example)
- **Overlap check**: `software-design-principles` covers coupling/SOLID generally; no existing content names this specific "re-derive vs. return" chooser pattern. No overlap found.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-design-principles/SKILL.md` or a references file therein (context-engineer's call)

### Proposal 4: git-corpus test fixtures need a committed tree, or scripts using `git ls-files` fail closed to an empty, silently-green corpus

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/sentinel-phase-b/LEARNINGS.md` fragment A7 (lines ~205-213)
- **Description**: Extend `rules/swe/testing-conventions.md § Fixtures Under Gitignored Paths` (or the sibling section it lives in) with a second, mechanically distinct false-green case: a fixture built under `tmp_path` without `git init` + `git add` + `git commit` causes any script that shells out to `git ls-files` to hit a caught `CalledProcessError`/exit-128 and silently return an empty corpus — the test then "passes" without ever exercising the code paths it meant to cover, via a different mechanism than the gitignore case (uncommitted, not gitignored) but with an identical symptom (silent false green). Name the mitigation pattern: a `_git_commit_tree`-style test helper that `git init`s, adds, and commits the fixture tree before invoking the script under test.
- **Rationale**: The existing gitignored-paths rule already establishes this exact class of bug matters enough to document; this is the second occurrence of the same symptom via a different root cause, meeting the bar for formalizing a general "test fixtures for git-shelling scripts must be inside a committed tree" convention rather than leaving it implicit per-script.
- **Estimated scope**: single rule file, ~5-8 line addition to an existing section (not a new section)
- **Overlap check**: `rules/swe/testing-conventions.md § Fixtures Under Gitignored Paths` — directly related, this proposal extends rather than duplicates it
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/testing-conventions.md`

### Proposal 5: Commit granularity follows atomicity units; explicit atomicity mandates override 1-step-per-commit

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/sentinel-phase-b/LEARNINGS.md` implementation-planner Decisions (lines ~93)
- **Description**: Sharpen `swe-agent-coordination-protocol.md`'s implicit "each step fits in a single commit, leave the system working" guidance with an explicit tie-break: when a systems-architect-mandated atomicity requirement (e.g. "register a check id and delete its exemption in one commit") conflicts with the default 1-step-per-commit convention, atomicity wins — splitting the steps into separate commits would land a genuinely RED intermediate state, which the known-good-increment invariant forbids more strongly than the 1-step-per-commit convention requires. Name the decision rule explicitly (as this pipeline's implementation-planner had to derive it ad hoc for 4 of 13 spawns) so future planners don't re-derive it from first principles each time.
- **Rationale**: A recurring planning judgment call, made correctly here but only after explicit reasoning in `LEARNINGS.md` — worth promoting to an explicit rule clause so it is available to the planner without re-deriving it, and so a reviewer has a named rule to check the plan against.
- **Estimated scope**: single rule file, ~5 line addition (one clause + one-sentence example) to `swe-agent-coordination-protocol.md` or the linked `coordination-details.md#delegation-checklists`
- **Overlap check**: `swe-agent-coordination-protocol.md`'s "BDD/TDD execution" row states "paired implementation + test steps; concurrent on disjoint file sets; tests run until green" but does not address commit-boundary tie-breaking against atomicity mandates. No direct overlap.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/swe-agent-coordination-protocol.md` (or `skills/software-planning/references/coordination-details.md` if the context-engineer judges it too procedural/detailed for the always-loaded rule)

### Discipline-Gap Signals

No discipline-gap signal was identified in this batch's sources. The sentinel-phase-b pipeline's decisions (family-envelope shape, severity vocabulary, registry extension) were all resolved by the systems-architect/implementation-planner/implementer roster without a missing-specialist-voice pattern emerging.

_(This entry is informational, not a numbered proposal — omitted from the proposal count.)_

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | Skill update; load skill-crafting; decide home (software-design-principles vs. data-structure-design) |
| 2 | context-engineer | Skill update; bundle drafting with the adjacent Proposal from `SKILL_GENESIS_REPORT_2026-09-23_22-55-14.md` targeting the same file |
| 3 | context-engineer | Skill update; load skill-crafting |
| 4 | context-engineer | Rule update; load rule-crafting |
| 5 | context-engineer | Rule update; load rule-crafting; decide rule vs. coordination-details.md reference placement |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 5 pending proposals (plus the informational discipline-gap entry, which requires no action).
- After approval, invoke `context-engineer` for skills/rules; the agent will pick up the recommended delegations table.
- When drafting Proposal 2, cross-reference the adjacent mutation-probe proposal in `SKILL_GENESIS_REPORT_2026-09-23_22-55-14.md` to avoid two near-simultaneous edits to `gate-canaries.md`.
- This is batch 12 of 13 in the queued harvest — the final batch's report should also dedupe against this one.
