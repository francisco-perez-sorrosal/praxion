---
id: dec-draft-03f65506
title: affected_files hygiene enforces at creation time as a non-blocking warning; query-side filtering is rejected
status: proposed
category: implementation
date: 2026-08-31
summary: 'Staged ADR files whose affected_files name an absent path emit a non-blocking pre-commit warning; sentinel DH02 remains the continuous backstop; query_adrs.py never filters on path liveness because that would suppress the decisions most needing repair.'
tags: [adr, affected-files, hygiene, pre-commit, sentinel, retrieval, decay]
made_by: agent
agent_type: systems-architect
branch: worktree-adr-living-view
pipeline_tier: standard
affected_files:
  - scripts/check_adr_frontmatter_promotion.py
  - .pre-commit-config.yaml
  - scripts/adr_health.py
  - scripts/query_adrs.py
---

## Context

`dec-347` made `affected_files` load-bearing: it is the retrieval key for "which decisions govern the files I am about to touch". The still-current audit reported two false-positive classes degrading it — (a) non-path entries (`REQ-*` ids, `dec-NNN` cross-refs) stuffed into the field in 8 of 30 sampled records, and (b) decay created after a remediation pass, reappearing immediately.

**Class (a) does not exist.** A direct measurement over all 347 finalized records — 342 carrying `affected_files`, 1,589 entries total — found **zero** non-path entries. The audit's examples resolve to *adjacent* fields: `dec-028`'s `dec-093` is a `re_affirmed_by` value, `dec-041`'s `REQ-TC-*` are `affected_reqs` values. Both are correct uses of their own fields. Objection registered against that finding rather than building a validator for a defect the corpus does not have.

**Class (b) is real and measured**: 113 of 1,589 entries (7.1%) do not resolve on disk. `scripts/adr_health.py` already detects and classifies every one of them (`renamed`, `removed-by-self`, `lazy-artifact`, `vanished`, …) and sentinel DH02 already reports the repairable classes. Detection is solved. The gap is **cadence** — repair happens in campaigns, and decay resumes the day after one ends.

## Decision

Enforce at **creation time**, advisory. Extend the existing pre-commit ADR block (already filtered to `^\.ai-state/decisions/.*\.md$`) so a staged ADR file whose `affected_files` names a path absent from the working tree emits a **non-blocking warning** naming the path, together with the removal-decision exemption text. The commit succeeds.

Sentinel DH02 remains unchanged as the continuous backstop. No new sentinel check. No validator for non-path entries.

**Query-side filtering is rejected outright.** Suppressing a record because one of its `affected_files` no longer resolves would reduce recall on precisely the decisions most in need of repair: a decision whose file was *renamed* still governs the new file, and hiding it is the worst available outcome.

**Why non-blocking.** A decision whose *action* was deleting the listed files legitimately names absent paths — `adr_health` counts 57 such `removed-by-self` records corpus-wide, every one a decision working exactly as decided. A blocking gate would fail on those and, at authoring time, the removal is in the same commit as the record, so the two cases are not cheaply separable. A warning catches typos at the cheapest moment without punishing correct authorship.

## Considered Options

### A — Sentinel only (status quo)
Pros: zero new code. Cons: repair stays campaign-driven; decay reappears immediately after each pass.

### B — Creation-time non-blocking warning + sentinel backstop (chosen)
Pros: catches decay at authoring, the cheapest moment; zero backlog obligation; no false-positive cost because it never blocks; reuses an existing hook and file filter. Cons: warnings can be ignored.

### C — Creation-time blocking gate
Pros: decay cannot enter the corpus. Cons: fails on removal decisions, which are the corpus's single largest absent-path class and are correct.

### D — Query-tool-side filtering
Pros: retrieval output contains only live paths. Cons: inverts the intent — hides exactly the records whose paths need repair; a renamed file's governing decision disappears from the query that would surface it.

## Consequences

Positive: the continuous half of `affected_files` hygiene is closed with an additive change to an existing hook. The measurement disproving class (a) is recorded, so no future pass rebuilds a validator for it.

Negative: warnings are ignorable, so this narrows rather than eliminates the decay window. The 113 currently-unresolved entries are not addressed by this decision — they remain DH02's disposition queue, and this decision deliberately does not schedule a campaign to clear them.
