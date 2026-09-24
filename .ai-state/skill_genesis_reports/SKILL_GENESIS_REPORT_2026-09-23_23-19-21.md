---
schema_version: 1
report_id: skill-genesis-2026-09-23_23-19-21
generated_at: 2026-09-23T23:19:21Z
task_slug: skill-genesis-2026-09-23
agent_version: skill-genesis@f731fa8e
invocation_args: { since: null, scope: null, sources: .ai-work/_harvest, batch: "13 of 13", dry_run: false }
review_status: pending
disposition_count: { pending: 2, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-09-23 23:19:21

## Summary

1 queued source analyzed (`sidecar-placement`, oversize — sampled by section since it was already fully mined by an earlier report). 5 candidate items extracted from the delta not covered by the prior report (`SKILL_GENESIS_REPORT_2026-09-04_15-12-10.md`, which already dispositioned 14 items into 6 proposals from this same task). 2 proposals generated, 3 items deduplicated or judged too narrow. Review status: pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| Prior report on this source | `.ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_2026-09-04_15-12-10.md` | — | Read fully — establishes the already-covered baseline (14 items, 6 proposals) |
| Memory file for this source | `project_sidecar_placement_spike.md` | — | Read — confirms merge/debt-remediation history, no new extractable learning beyond what's already in memory |
| LEARNINGS.md (queued source) | `.ai-work/_harvest/sidecar-placement/sidecar-placement/LEARNINGS.md` | 4 | Sampled by heading (3130 lines, oversize) — read only the tail section not covered by the prior report's 15:12 cutoff: "Batch 21 — verifier round (orchestrator, 2026-09-04)" (lines 3125-3130). All earlier sections (lines 1-3124) were already fully mined by the prior report; not re-read. |
| VERIFICATION_REPORT.md | `.ai-work/_harvest/sidecar-placement/sidecar-placement/VERIFICATION_REPORT.md` | 3 | Sampled by heading (378 lines) — read `## Behavioral Contract Findings` (169-181), `## Architecture Doc Validation` (182-231), `## Test Coverage` (232-253), `## Recommendations (prioritized)` (309-316). Skipped: `## Verdict`, `## Scope`, `## Acceptance Criteria`, `## Spec Conformance`, `## Convention Compliance`, `## Security Review`, `## Specialist Design Review`, `## Context Artifact Completeness`, `## Ledger Rows Filed`, `## Re-verification` — no gotcha/pattern/decision headings in those sections beyond what the prior report or the sampled sections already surfaced. |
| CONSULT_data-structure-specialist.md | `.ai-work/_harvest/sidecar-placement/sidecar-placement/CONSULT_data-structure-specialist.md` | 0 | Not sampled — `VERIFICATION_REPORT.md § Specialist Design Review` confirms every challenge already carries a disposition captured elsewhere; no independent read needed |
| ARCH_WT_RULING.md | `.ai-work/_harvest/sidecar-placement/sidecar-placement/ARCH_WT_RULING.md` | 0 | Not re-sampled — prior report already extracted its §15 finding (Proposal 1 of the prior report) |
| Latest SENTINEL_REPORT_*.md | `.ai-state/sentinel_reports/` | — | Not re-checked this batch (no new sentinel run since the prior report on this source) |
| Latest IDEA_LEDGER_*.md | `.ai-state/idea_ledgers/` | — | Not checked (queue-mode source-scoped harvest; out of scope per prior report's own note) |
| Sibling reports of this run (12 earlier batches, 2026-09-23) | `.ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_2026-09-23_22-35-25.md` … `_23-16-24.md` | 0 | Grepped for `sidecar` across all 12 — zero hits, no overlap to dedupe against |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | `resolve_placement()` called directly inside a writer (`refresh_claude_blocks.py`) treated every non-`SidecarOwned` variant as "in-repo," routing a write to the team's tracked file when the mount was actually missing — a permissive fallback where the contract needed a fail-closed `require_writable_placement()` call instead | VERIFICATION_REPORT.md § Architecture Doc Validation / Behavioral Contract Findings (`td-160`, `[UNSURFACED-ASSUMPTION]` V-3) | Skill (update) | Generalizable design gotcha distinct from `data-structure-design`'s existing "invariant with no named enforcer" entry — this is specifically about a *reader-shaped* resolver being called from a *writer* context, silently degrading a fail-closed contract into a fail-open one. See Proposal 1. |
| 2 | A test suite's verdict can flip between a clean `git archive` extraction and the live working tree, depending only on whether an untracked file (the observations WAL) is present — three tests in this task swapped PASS/FAIL this way and none carried a ledger row, because "pre-existing" was treated as a disposition when it isn't | LEARNINGS.md "Batch 21 — verifier round" (line 3130); VERIFICATION_REPORT.md § Test Coverage V-6 (`td-162`) | Skill (update) | Extends `testing-strategy`'s existing "Flaky tests from shared mutable state" gotcha with a distinct trigger (untracked working-tree state, not in-process state) and a distinct symptom (green on dev machine / red in CI or the reverse). See Proposal 2. |
| 3 | A post-rename grep swept out every line containing the string `recipes` to skip an unrelated meaning, but one file's mount reference shared a line with a `recipes` mention and was hidden until a human read the file — "a filter that drops whole lines by a keyword is not a classifier" | LEARNINGS.md "Batch 21 — verifier round" (line 3127) | Skip | Real gotcha, but overlaps the shape already held in this agent's own persistent memory (`feedback_pattern_match_is_not_corpus_evidence.md` — "never trust a truncated/keyword-based match for a corpus claim; re-derive with a real parser"). The specific mechanism (line-level exclusion vs. truncated diagnostic) differs, but the corrective instinct is identical and no existing skill/rule has an obvious single-occurrence home distinct from that already-captured lesson. Below the bar for a new proposal; noted here for visibility. |
| 4 | "Numbers in prose rot fastest" — three stale counts (`fourteen modules`, `545-line entry point`, `every module under 800`) were true at plan time and false at delivery; recommended remedy is pairing a number with the command that produces it, or dropping the number | LEARNINGS.md "Batch 21 — verifier round" (line 3129); VERIFICATION_REPORT.md § Architecture Doc Validation V-5 | Skip (already captured) | `skills/doc-management/SKILL.md § Gotchas` already carries "Trusting counts in prose without filesystem verification... Always count against the filesystem" — same lesson, same remedy shape. The "pair with the producing command" phrasing is a minor refinement, not a gap; doesn't clear the deletion test for a separate edit. |
| 5 | Two `[UNSURFACED-ASSUMPTION]` findings shared a shape: "a green gate implies the rule it gates is satisfied" (V-1) and "an unresolvable placement state defaults to the most permissive branch (in-repo) instead of failing closed" (V-3) | VERIFICATION_REPORT.md § Behavioral Contract Findings | Skip | Single-task instance of a general behavioral-contract self-test category already covered abstractly by `rules/swe/agent-behavioral-contract.md`'s "Surface Assumptions" behavior and the verifier's own `[UNSURFACED-ASSUMPTION]` tag definition; the concrete V-3 instance is the same fact already promoted to Proposal 1 above (the writer-fallback item), so recording it separately would double-count one learning. |

## Discipline-Gap Signals

No signal recorded this pass. No learning item in the sampled sections named a decision that would have benefited from a specialist voice the consultant registry does not carry; the one `discipline-consultant` engagement in this task (`data-structure-specialist`) was already noted as registry-working-as-designed in the prior report on this source.

## Proposals

### Proposal 1: data-structure-design Gotchas — a permissive resolver called from a writer is a fail-open leak

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/sidecar-placement/sidecar-placement/VERIFICATION_REPORT.md` § Architecture Doc Validation / Behavioral Contract Findings (`td-160`, finding V-3); re-verification section confirms the fix shape (`require_writable_placement()`)
- **Description**: Add a Gotchas entry to `skills/data-structure-design/SKILL.md`: when a codebase splits a reader-shaped resolver (returns a best-effort classification, permissive on the unknown case) from a writer-shaped contract (must fail closed on the unknown case), calling the reader's resolver directly inside writer code silently inherits its permissive default. The concrete instance: `resolve_placement()` treated every non-owned variant as "in-repo," so a missing mount routed a write to the team's tracked file instead of refusing. The fix pattern is a distinct, explicitly-named writer-side entry point (`require_writable_placement()`) that fails closed on exactly the cases the reader treats permissively — not a shared function with an implicit assumption about which caller it serves.
- **Rationale**: This is a specific, evidence-backed instance of a design smell not currently named in `data-structure-design`'s Gotchas (which has "an invariant with no named enforcer is not an invariant" — adjacent but not the same failure: here the invariant *is* named and enforced, just by the wrong-shaped function). The reader/writer split for resolvers is a reusable pattern across any codebase with a permissive-classification helper reused in a should-be-strict context.
- **Estimated scope**: SKILL.md Gotchas section, ~4-5 lines
- **Overlap check**: `skills/data-structure-design/SKILL.md § Gotchas` exists (4 entries checked); closest is "an invariant with no named enforcer is not an invariant" — related but distinct failure mode (missing enforcer vs. wrong-shaped enforcer reused across a fail-open/fail-closed boundary). No rule currently covers this.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/data-structure-design/SKILL.md` (Gotchas section)

### Proposal 2: testing-strategy Gotchas — test verdict flips between clean extraction and dirty working tree

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/sidecar-placement/sidecar-placement/LEARNINGS.md` "Batch 21 — verifier round" (line 3130); `VERIFICATION_REPORT.md § Test Coverage` finding V-6 (`td-162`)
- **Description**: Add a Gotchas entry to `skills/testing-strategy/SKILL.md`: some tests' pass/fail verdict depends on whether an *untracked* working-tree artifact (e.g., an observations WAL file, a stray build output) is present — not on any in-process shared state. Three tests in this task swapped verdicts between a clean `git archive` extraction and the live working tree, and were left undispositioned because "pre-existing" was treated as a resolution when it is only an observation. The remedy: any test whose result changes between a clean checkout and the dirty working tree is a distinct class from ordinary flakiness and needs its own ledger row (not silent "pre-existing" bookkeeping) — verify suite-green claims from a clean extraction, not just a scoped in-place run.
- **Rationale**: Extends the existing "Flaky tests from shared mutable state" gotcha with a genuinely distinct trigger (filesystem/VCS dirtiness, not process-level shared state) and a genuinely distinct symptom (green on the developer's machine, red in CI, or the reverse) — the exact failure class `TEST_BASELINE.md`'s own "verifier note" in this task was written to guard against. Recurs as a named category (not a one-off) in the source's own framing ("the class matters beyond these three").
- **Estimated scope**: SKILL.md Gotchas section, ~4-5 lines
- **Overlap check**: `skills/testing-strategy/SKILL.md § Gotchas` exists (6 entries checked, including "Flaky tests from shared mutable state" — adjacent but scoped to in-process state, not working-tree dirtiness). No rule currently covers this; related to this agent's own memory item `feedback_ci_equivalent_test_invocation.md` (CI-equivalent invocation) but that memory addresses *how* to invoke the suite, not *why* a clean-vs-dirty tree changes individual test verdicts — complementary, not duplicate.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/testing-strategy/SKILL.md` (Gotchas section)

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | Skill update; load `skill-crafting` for the Gotchas-section pattern |
| 2 | context-engineer | Skill update; short, single-entry addition alongside the existing flaky-test gotcha |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 2 pending proposals.
- After approval, invoke `context-engineer` for the two skill Gotchas additions; the agent will pick up the recommended delegations table.
- This closes the `sidecar-placement` source out of the harvest queue — the prior report (2026-09-04) plus this batch have now mined every section of `LEARNINGS.md` and `VERIFICATION_REPORT.md`; no further `/skill-genesis` pass over this source is expected to surface new material unless the task directory changes.
