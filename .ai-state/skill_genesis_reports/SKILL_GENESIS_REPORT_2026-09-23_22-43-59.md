---
schema_version: 1
report_id: skill-genesis-2026-09-23_22-43-59
generated_at: 2026-09-24T05:45:59Z
task_slug: skill-genesis-2026-09-23
agent_version: skill-genesis@f731fa8e
invocation_args: { since: null, scope: null, sources: ".ai-work/_harvest", batch: "3 of 13", dry_run: false }
review_status: pending
disposition_count: { pending: 6, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-09-23 22:43:59

## Summary

1 learning source analyzed (`process-economy-p2-1` pipeline, LEARNINGS.md + VERIFICATION_REPORT.md),
~13 discrete learning items extracted, 6 proposals generated, 7 items deduplicated or discarded
(3 already covered by `rules/swe/vcs/git-conventions.md`'s stash-apply-not-pop convention, 1 already
covered by `skills/software-planning/references/adr-authoring-protocols.md`'s corpus/recent baseline
text, 1 a one-off bugfix with no generalizable knowledge, 2 too narrow/transient to formalize). Review
status: pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| Queue source | `.ai-work/_harvest/process-economy-p2-1/process-economy-p2-1/LEARNINGS.md` | 10 | Read (full, 907 lines) |
| Queue source | `.ai-work/_harvest/process-economy-p2-1/process-economy-p2-1/VERIFICATION_REPORT.md` | 3 | Read (headings scanned; FAIL/WARN sections read in full) |
| Latest SENTINEL_REPORT_*.md | `.ai-state/sentinel_reports/` | 0 | Not read (batch scope; queue-mode reads LEARNINGS/VERIFICATION/CONSULT only) |
| Latest IDEA_LEDGER_*.md | `.ai-state/idea_ledgers/` | 0 | Not read (batch scope) |
| ADRs (recent) | `.ai-state/decisions/` | 0 | Not queried — no learning item required ADR-scope disambiguation |
| Calibration log Retrospective cells | `.ai-state/calibration_log.md` | 0 | Not read (batch scope) |
| Consult fragments | `.ai-work/_harvest/process-economy-p2-1/process-economy-p2-1/CONSULT_*.md` | 0 | Not found |
| Sibling reports (this run) | `SKILL_GENESIS_REPORT_2026-09-23_22-35-25.md`, `SKILL_GENESIS_REPORT_2026-09-23_22-39-30.md` | — | Read (grepped `## Proposals` headings for overlap) |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | Non-vacuity proof methodology (revert-fix→confirm red→restore→confirm green; single-file `git stash` scoping; `__pycache__` staleness trap during manual revert) | LEARNINGS Step 0, Step 4c, Rework Rows 1–4 (recurs 5+ times) | Skill (update) | `gate-canaries.md` covers what a canary is, not how to *prove* it isn't vacuous — this recurring technique fills that gap |
| 2 | Regex canary gotchas: non-greedy `.+?` is not a length bound (needs explicit `{m,n}`); escaped metacharacters (`\+`) look identical to operator form under a naive char-class scan | LEARNINGS Rework Row 2, rw-9a9c268a | Skill (update) | Concrete, non-obvious canary-authoring failure mode; grep confirms zero existing coverage |
| 3 | RISKY auto-signal gap: none of the three existing predicates (Uncertainty Flag < 7, one-way-door, `tier: H`) fires on "this step is the first application of a contract that will govern N later rows" | VERIFICATION_REPORT WARN-7 | Rule/skill (update) | Verification report explicitly recommends a fourth predicate; the gap it names directly caused FAIL-2 to survive two reworks |
| 4 | `review: force` substitution adequacy must be judged by blast-radius coverage, not presence — a substitute scoped to the step's *declared* work-kind can be blind to what actually shipped in the diff | VERIFICATION_REPORT WARN-6 | Skill (update) | Same file as #3, different seam (verifier-side assessment vs. planner-side predicate); worth a distinct addition |
| 5 | Cross-directory sibling import guard (e.g. `hooks/` imported into a `scripts/` module invoked via bare `python3`) must ship in the *same* implementation step, not deferred — `check_gate_liveness.py --json` is cheap and catches it immediately | LEARNINGS Step 8a Rework | Rule (update) | `gate-liveness.md` already describes the ambient-import check mechanically but not this authoring-time discipline |
| 6 | `ruff`'s PT017 flags `assert <substring> in str(exc)` inside a `try/except AssertionError` block even when the file's whole canary style deliberately avoids `pytest.raises`; fix is `if ... not in ...: raise AssertionError(...) from exc` | LEARNINGS Rework Row 2 | Skill (update) | Narrow but concrete lint/style interaction; folded into the same `gate-canaries.md` file as #1/#2 rather than a 7th proposal |
| 7 | Never a bare `git stash`/`git stash pop`; restore via SHA, not `pop` | LEARNINGS Step 8a Rework, rw-cc29858a | Skip (duplicate) | Already fully covered by `rules/swe/vcs/git-conventions.md` lines 22–23, including the exact tag/SHA/drop pattern |
| 8 | `adr_health.py` DH05 threshold used `"corpus"` share instead of `"recent"` share, contradicting its own cited spec | LEARNINGS Rework Row 2 | Skip (duplicate) | The correct baseline (corpus 72%/227/317, recent 84%/50) is already documented in `skills/software-planning/references/adr-authoring-protocols.md:191-195`; this was a one-off code bug against an already-correct spec, not a knowledge gap |
| 9 | Quote-balance discipline vs. word-boundary discipline are orthogonal fixes for orthogonal failure modes (Rework Row 2) | LEARNINGS | Skip | Restates general debugging wisdom (isolate independent failure modes) already covered by the Methodology's Verify phase; too case-specific to generalize further |
| 10 | Simplification chosen over a fourth regex patch when precision kept opening new holes (rw-9a9c268a) | LEARNINGS | Skip | Restates Root Causes Over Workarounds / Simplicity First, already canonical in `~/.claude/CLAUDE.md` and the behavioral contract; no new mechanism to encode |
| 11 | Row-id mismatch between task prompt and `REWORK_MANIFEST_2.md` resolved by file/content match, not by trusting the id verbatim | LEARNINGS Rework Row 2 | Skip | One-off dispatch-hygiene incident; not a recurring pattern absent further evidence |
| 12 | `dec-378` totalizing-check discipline: prefer scanning the built regex source for any unbounded operator over listing named slots (which the docstring got wrong twice) | LEARNINGS rw-9a9c268a | Skip (folds into #2) | Same underlying lesson as item #2 (regex-bound canary discipline); not a separate mechanism worth its own proposal |
| 13 | `id-citation-discipline.py`'s blocking hook scans full staged file content, not just the diff, so unrelated pre-existing citations in a touched file can trip it | LEARNINGS Step 7 | Skip (overlaps pending proposal) | `SKILL_GENESIS_REPORT_2026-09-23_22-35-25.md` Proposal 4 already proposes a worktree-scoping addition to `rules/swe/id-citation-discipline.md`; this is a second known-limitation for the same rule file — noted here rather than opening a competing pending proposal, to be folded in at disposition time |

## Discipline-Gap Signals

None recorded — no recurring "we needed a specialist voice" signal surfaced in this source.

## Proposals

### Proposal 1: gate-canaries.md — non-vacuity proof methodology

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-p2-1/process-economy-p2-1/LEARNINGS.md` §§ Step 0, Step 4c, Rework Row 1 (`rw-cc29858a`), Rework Row 2 (`rw-93883de7`), Rework Row 4 (`rw-a629c016`)
- **Description**: Add a "How to prove a canary isn't vacuous" subsection to `skills/testing-strategy/references/gate-canaries.md`, covering the revert-fix→confirm-red→restore→confirm-green technique (full-function-body swap via script, never hand-edit, to avoid syntactically-broken intermediate states); the single-file `git stash push -u -- <file>` scoping variant for isolating a production fix from an already-updated test file without risking the shared stash stack; and the `__pycache__` staleness trap when a file is edited twice within the same wall-clock second during manual revert-and-restore (symptom: canary still fails against a byte-identical restored file; fix: `rm -rf <pkg>/__pycache__` before re-running).
- **Rationale**: This exact technique recurs five separate times across one 907-line LEARNINGS.md (Step 0, Step 4c, and three of four rework rows), each time independently re-derived rather than referenced — a clear sapling-to-mature signal that it belongs in the shared skill rather than being rediscovered per pipeline. `gate-canaries.md` currently defines what a canary is and how coverage is enforced, but has no guidance on proving a specific canary is not itself vacuous (asserts the right thing for the right reason).
- **Estimated scope**: SKILL.md unaffected; one new subsection (~25-35 lines) in `skills/testing-strategy/references/gate-canaries.md`
- **Overlap check**: none — grepped `skills/testing-strategy/` for "vacuity"/"vacuous"/"probe", zero hits
- **Recommended delegation**: context-engineer (review scope) then implementer (content)
- **Suggested artifact path**: `skills/testing-strategy/references/gate-canaries.md`

### Proposal 2: gate-canaries.md — regex and lint gotchas for hand-written canaries

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-p2-1/process-economy-p2-1/LEARNINGS.md` §§ Rework Row 2 (`rw-93883de7`), rw-9a9c268a
- **Description**: Add a short "Regex-based canary gotchas" bullet list to `gate-canaries.md`: (1) a non-greedy quantifier (`.+?`) is a search-order hint, not a length bound — it backtracks past arbitrary padding to find a closing anchor; the only real bound is an explicit `{m,n}` cap, and the cap should be derived from the live corpus's max observed width plus margin, not a round number; (2) escaped metacharacters (`\+`, `\*`) look identical to their operator form under a naive character-class scan (`[*+]`) — exclude a preceding backslash; (3) `ruff`'s PT017 flags an `assert <x> in str(exc)` inside a bare `try/except AssertionError` block even in files that deliberately avoid `pytest.raises` for style-uniformity reasons — the lint-clean equivalent is `if <x> not in str(exc): raise AssertionError(...) from exc`.
- **Rationale**: All three items were independently discovered while writing/reworking the same canary file (`tests/test_sentinel_row_contract.py`) and are the class of non-obvious failure the skill-crafting spec calls "highest-signal content" — none is derivable from the agent's default reasoning about regex or pytest conventions.
- **Estimated scope**: SKILL.md unaffected; ~10-15 line addition to `skills/testing-strategy/references/gate-canaries.md` (may combine with Proposal 1's new subsection at drafting time — context-engineer's call)
- **Overlap check**: none — grepped `rules/` and `skills/*/SKILL.md` + `skills/*/references/*.md` for "quantifier"/"greedy"/"PT017"/"pytest.raises", zero relevant hits
- **Recommended delegation**: context-engineer (review scope) then implementer (content)
- **Suggested artifact path**: `skills/testing-strategy/references/gate-canaries.md`

### Proposal 3: intra-step-review.md — fourth RISKY auto-signal (first application of a new contract)

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P0 (this-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-p2-1/process-economy-p2-1/VERIFICATION_REPORT.md` § WARN-7
- **Description**: Add a fourth row to `skills/software-planning/references/intra-step-review.md`'s auto-signals table: a step that establishes a contract/shape that N later steps will conform to (e.g., "the first extraction step defining the row-contract parser") should trigger RISKY review even when its own declared work-kind (e.g., "prose relocation") looks low-risk in isolation. Cross-reference `decomposition-guide.md § Step Risk Tagging` for where the planner assigns this at plan-authoring time.
- **Rationale**: The verification report traces a real, shipped defect (FAIL-2, an unbounded-growth regex contract that survived two reworks) directly to this predicate gap — the step that introduced the contract was correctly exempted from review under all three existing auto-signals (Uncertainty Flag ≥ 7, not one-way-door, not `tier: H`), because none of them measures blast radius across future steps. The verification report itself recommends this exact fix ("Recommend a `first-application-of-a-new-contract` predicate alongside the existing three"). P0 because the gap is confirmed to have caused a shipped, multi-round-rework defect in this very pipeline.
- **Estimated scope**: single reference-file update (~1 table row + 1-2 sentences of trigger criteria)
- **Overlap check**: `intra-step-review.md`'s Auto-signals table currently has exactly 3 rows (Uncertainty Flag < 7, one-way-door, `tier: H`); verified by direct read — no existing predicate covers blast-radius-to-future-steps
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/intra-step-review.md`

### Proposal 4: intra-step-review.md — substitution-adequacy assessment for `review: force`/`review: off` deviations

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-p2-1/process-economy-p2-1/VERIFICATION_REPORT.md` § WARN-6
- **Description**: Add guidance to `intra-step-review.md` (or the verifier's checkpoint procedure it feeds) that when a step names a mechanical substitute for a skipped intra-step review, the substitute's adequacy must be judged by what it could and could not have caught relative to the *actual diff that shipped* — not merely whether a rationale was recorded, and not only against the step's *declared* work-kind. Worked contrast from this pipeline: one substitute (`check_agent_prompt_size.py --json`) fully covered its named risk; a second (a `grep -c` + fitness-green + one pin check) addressed only the declared one-way-door and was blind-by-construction to a contract-conformance defect (FAIL-1) that a direct row-vs-script diff read would have caught.
- **Rationale**: Names a concrete assessment failure mode distinct from Proposal 3 (planner-side predicate gap) — this is a verifier-side judgment call about how to evaluate a recorded substitution, worth capturing so future verifiers don't accept "a rationale exists" as sufficient.
- **Estimated scope**: single reference-file update (~1 short subsection, ~10 lines)
- **Overlap check**: `intra-step-review.md`'s Planner Override section documents *how* to record a substitution but not how a downstream reviewer should judge its adequacy — no existing coverage found
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/intra-step-review.md`

### Proposal 5: gate-liveness.md — cross-directory sibling import guard must ship in the same step

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `.ai-work/_harvest/process-economy-p2-1/process-economy-p2-1/LEARNINGS.md` § Step 8a Rework Learnings
- **Description**: Add a line to `rules/swe/gate-liveness.md` (or a canonical location it points to) stating: when a plan requires importing from a directory outside `scripts/` (e.g. `hooks/`) into a script invoked via bare `python3` in an agent/command file, the `try/except ImportError → sys.exit(<remedy>)` guard must land in the same implementation step/commit that introduces the import — not deferred as a follow-up — because `check_gate_liveness.py --json` is cheap to run before considering any such step done and catches the omission immediately.
- **Rationale**: Concrete, reproducible defect class (a mandated cross-directory import created exactly the `ambient-import` finding the plan had already named the mitigation for, but the mitigation wasn't applied until a rework). `gate-liveness.md` already documents the ambient-import *check* mechanically but not this authoring-time discipline for avoiding the finding in the first place.
- **Estimated scope**: single rule file (~3-5 line addition)
- **Overlap check**: `gate-liveness.md` mentions the ambient-import check's existence but not this same-step-guard discipline — verified by grep
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/gate-liveness.md`

### Proposal 6: id-citation-discipline.md — second known-limitation (full-file scan, not diff-only)

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `.ai-work/_harvest/process-economy-p2-1/process-economy-p2-1/LEARNINGS.md` § Step 7
- **Description**: Add a second known-limitation note to `rules/swe/id-citation-discipline.md`: `check_id_citation_discipline.py` (invoked via `commit_gate.sh`) scans the **full content** of any staged file, not just the diff — so an unrelated, pre-existing `Step N`/`REQ-NN` citation elsewhere in a file being touched for an unrelated reason will block the commit, even though the citation predates the current change.
- **Rationale**: A second, independent gotcha about the same rule file, discovered in this pipeline's Step 7 commit (blocked twice on pre-existing docstring citations in a file otherwise unrelated to the fix). Distinct mechanism from the worktree-scoping known-limitation already pending in `SKILL_GENESIS_REPORT_2026-09-23_22-35-25.md` Proposal 4 (that one is about self-verification returning a vacuous "0 files scanned" inside a worktree; this one is about full-file vs. diff-only scanning scope) — recorded as its own proposal so the two can be reconciled or merged into one rule update at disposition time rather than one silently dropping the other.
- **Estimated scope**: single rule file (~4-line known-limitation addition); likely to be merged with the sibling pending proposal's edit at disposition/context-engineer time
- **Overlap check**: `SKILL_GENESIS_REPORT_2026-09-23_22-35-25.md` Proposal 4 (pending) targets the same file with a different known-limitation; flagged for reconciliation, not treated as a full duplicate since the failure modes are mechanically distinct
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/id-citation-discipline.md`

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer (review scope) then implementer (content) | Skill reference-file update; load `skill-crafting`; may combine with Proposal 2's addition into one subsection |
| 2 | context-engineer (review scope) then implementer (content) | Skill reference-file update; load `skill-crafting`; small, self-contained gotcha list |
| 3 | context-engineer | Reference-file update to `intra-step-review.md`; load `skill-crafting`; P0 — a confirmed shipped defect traces to this gap |
| 4 | context-engineer | Reference-file update to `intra-step-review.md`; can be drafted alongside Proposal 3 in the same pass |
| 5 | context-engineer | Rule update; load `rule-crafting`; small addition |
| 6 | context-engineer | Rule update; load `rule-crafting`; reconcile with the sibling pending proposal in `SKILL_GENESIS_REPORT_2026-09-23_22-35-25.md` before drafting |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 6 pending proposals (note Proposal 6 overlaps a proposal already pending from an earlier batch — reconcile at review time).
- After approval, invoke `context-engineer` for the skill/rule updates; the agent will pick up the recommended delegations table.
- Proposals 1 and 2 target the same file (`gate-canaries.md`) and may be worth combining into a single context-engineer pass; likewise Proposals 3 and 4 (`intra-step-review.md`).
