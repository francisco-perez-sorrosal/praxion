---
schema_version: 1
report_id: skill-genesis-2026-09-23_22-55-14
generated_at: 2026-09-23T22:55:14Z
task_slug: skill-genesis-2026-09-23
agent_version: skill-genesis@unknown
invocation_args: { since: null, scope: null, sources: .ai-work/_harvest, batch: "6 of 13", dry_run: false }
review_status: pending
disposition_count: { pending: 5, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-09-23 22:55:14

## Summary

1 queue source analyzed (`process-economy-p2-wrap`). Its `LEARNINGS.md` (881 lines) is byte-identical
to `process-economy-p2-residual/LEARNINGS.md` through line 845 (already harvested by this run's
earlier batches) with 36 net-new tail lines; its `VERIFICATION_REPORT.md` is a byte-for-byte
duplicate of `process-economy-p2-residual/VERIFICATION_REPORT.md` (already harvested). The genuinely
new artifact is `LIGHT_REVIEW_wrap.md` — a fresh light-review of the 7-commit `main..HEAD` diff,
carrying 2 FAIL + 5 WARN findings none of the prior batches could have seen. 7 learning items
extracted from the new material, 5 survived triage as proposals (5 rule updates), 2 discarded as
either too narrow or already implied by pending sibling proposals. Review status: pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| Queue source: LEARNINGS.md | `.ai-work/_harvest/process-economy-p2-wrap/process-economy-p2-wrap/LEARNINGS.md` | 0 net-new | Read — lines 1–845 identical to `process-economy-p2-residual/LEARNINGS.md` (already harvested); lines 846–881 (Batch G, AC/T extensions, PW-6 retirement decision) read and triaged, no surviving items — see Triage rows 6–7 |
| Queue source: VERIFICATION_REPORT.md | `.ai-work/_harvest/process-economy-p2-wrap/process-economy-p2-wrap/VERIFICATION_REPORT.md` | 0 | Read — byte-identical (531/531 lines, `diff` empty) to `process-economy-p2-residual/VERIFICATION_REPORT.md`, already harvested by an earlier batch of this run |
| Queue source: LIGHT_REVIEW_wrap.md | `.ai-work/_harvest/process-economy-p2-wrap/process-economy-p2-wrap/LIGHT_REVIEW_wrap.md` | 7 | Read in full — genuinely new artifact (light-review of the 7-commit diff, not present in the `p2-residual` source) |
| Queue source: HANDOFF_PHASE2_PHASE3.md | `.ai-work/_harvest/process-economy-p2-wrap/process-economy-p2-wrap/HANDOFF_PHASE2_PHASE3.md` | 0 | Not read — byte-identical file size/date to the `p2-residual` copy (14,949 B), skipped as duplicate |
| Queue source: COST_LEDGER_WRAP.md | `.ai-work/_harvest/process-economy-p2-wrap/process-economy-p2-wrap/COST_LEDGER_WRAP.md` | 0 | Read — cost/spawn ledger only, no extractable learning items |
| Latest SENTINEL_REPORT_*.md | `.ai-state/sentinel_reports/` | — | Not read (out of scope for this batch — no new sentinel-relevant signal in the new material) |
| Latest IDEA_LEDGER_*.md | `.ai-state/idea_ledgers/` | — | Not read (queue-mode batch; dedup handled via sibling-report scan below) |
| ADRs | `.ai-state/decisions/` | 0 matched | Pre-scanned by keyword (`adr-conventions`, `frontmatter`) — no existing ADR duplicates the F2 YAML-quoting finding |
| Sibling reports of this run | `.ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_2026-09-23_{22-35-25,22-39-30,22-43-59,22-47-22,22-51-24}.md` | — | Grepped `## Proposals` headings for overlap — confirmed the VERIFICATION_REPORT.md F-1 finding (declared-limit/severity mismatch) is already Proposal 1 of the `22-51-24` batch; excluded from this batch's triage |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | F1 — `--table` renderer omits `bound`, but the Phase-3 preamble mandates reproducing it verbatim for all 55 family rows | `LIGHT_REVIEW_wrap.md` § F1 | Rule (update) | Generalizable anti-pattern: a digest/summary rendering mode silently drops a field a downstream instruction promises to reproduce, forcing either fabrication or a protocol violation to recover it |
| 2 | F2 — unquoted YAML `summary:` plain scalar containing `: ` breaks frontmatter parsing; the reciprocity check silently `withheld`s the broken record and reports 0 findings (false-clean); no frontmatter-parse gate covers `.ai-state/decisions/drafts/` | `LIGHT_REVIEW_wrap.md` § F2 | Rule (update) | Recurring authoring risk (two independent authors hit the same defect class in one review) with a real consequence (a false-clean reciprocity gate) and a concrete coverage gap |
| 3 | F3 — the digest carries severity counts but drops `withheld` entirely, making "N clean" indistinguishable from "N clean, M suppressed" | `LIGHT_REVIEW_wrap.md` § F3 | Rule (update) | Same family as item 1 (digest-completeness), distinct failure mode (a whole envelope key missing, not one field) and distinct remedy (surface suppression, not verbatim reproduction) — kept as its own entry |
| 4 | F4 — a `fullmatch` regex whose verdict-map capture is the terminal `.*?` group accepts arbitrary trailing content (duplicate Spec pointer, misplaced Conditional clause) because nothing bounds what follows `; ` | `LIGHT_REVIEW_wrap.md` § F4 | Rule (update) | General regex/grammar-design pitfall distinct from the two prior batches' greedy-regex and cross-directory-import findings — a terminal capture group provides no trailing-content boundary |
| 5 | F5 — a runner `continue`s past a crashed family, silently dropping its rows from the digest with exit code 0; the preamble never names `runner_errors`/family `status` as something to check | `LIGHT_REVIEW_wrap.md` § F5 | Skip | Narrow, single-script instance of the same "digest completeness" class as items 1/3; folding a third variant into the same rule row would blur rather than sharpen it — noted here rather than proposed separately |
| 6 | F6 — the dispatch table's `Rows` column is a fourth un-bound corner outside the existing rows↔registry↔script Triangle | `LIGHT_REVIEW_wrap.md` § F6 | Skip | Too narrow/transient — a specific gap in one project's own Triangle test, not a portable pattern beyond "know every corner of your own totalising invariant," which the Triangle pattern itself (already proposed in an earlier batch of this run) already communicates |
| 7 | Batch G / AC-T extensions / PW-6 retirement decision (tail lines 846–881) | `LEARNINGS.md` lines 846–881 | Skip | Batch G and the AC/T extensions restate the already-proposed per-family dispatch-cost dynamic with new numbers, no new mechanism; the PW-6 retirement decision ("absence of evidence is grounds to instrument, not delete") is a one-off project decision, not a reusable pattern |

## Proposals

### Proposal 1: gate-liveness.md — digest/summary render modes must carry every field a downstream instruction promises to reproduce

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-p2-wrap/process-economy-p2-wrap/LIGHT_REVIEW_wrap.md` § F1
- **Description**: Add an anti-pattern row to `rules/swe/gate-liveness.md`: when a runner/aggregator offers two output modes (a full per-entity envelope and a compact digest/table), and an instruction elsewhere (an agent prompt, a preamble, a protocol doc) tells the caller to invoke the *compact* mode and reproduce a specific field from it verbatim, verify the compact mode's schema actually includes that field before shipping the instruction — it is not safe to assume the digest is a strict superset of the full envelope's fields. The worked example: `run_check_families.py --table` renders `Check | Family | FAIL | WARN | INFO | Skipped | Examined | Sample entity` with no `bound` column, while `agents/sentinel.md`'s Phase-3 preamble instructs "reproduce `bound` verbatim as the PASS statement" after a single mandated `--table` call — making the instruction unexecutable for all 55 rows it governs without either fabricating the PASS text or silently running the forbidden second (`--json`) call.
- **Rationale**: This is the same class of self-contradiction `gate-liveness.md`'s existing anti-pattern table already targets (scope fidelity between an instruction and what its named mechanism actually delivers), but no existing row addresses the specific "digest mode drops a field the caller is told to reproduce" shape. It is a general risk anywhere a project builds a cheaper "table"/"summary" view alongside a richer `--json`/full mode and later writes prose instructing agents to prefer the cheap view.
- **Estimated scope**: single rule file, one new anti-pattern table row + one short worked-example sentence (~6-8 lines)
- **Overlap check**: `gate-liveness.md`'s anti-pattern table covers self-contradicting grep, consumer-with-no-producer, happy-path-only canary, convention-at-two-textual-sites, advisory-value-with-no-named-consumer, and (per this run's `22-51-24` batch, pending) severity/declared-limit mismatch — none address digest-vs-full-envelope field coverage
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/gate-liveness.md`

### Proposal 2: adr-conventions.md — quote or block-scalar any YAML frontmatter value containing `: `

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P0 (this-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-p2-wrap/process-economy-p2-wrap/LIGHT_REVIEW_wrap.md` § F2
- **Description**: Add a line to `rules/swe/adr-conventions.md`'s Frontmatter section: a YAML plain scalar (unquoted string value) that contains a bare colon-followed-by-space (`: `) is invalid YAML — PyYAML raises `mapping values are not allowed here`. ADR `summary:` values are the highest-risk field (long, prose-like, often quoting code with `` `Family: `...`; ... ` `` shapes). Require quoting (`summary: "..."`) or a block scalar (`summary: |` / `summary: >`) whenever the value contains `: `. Also record the concrete consequence observed: `scripts/check_adr_reciprocity.py --json` does not fail loudly on an unparseable draft — it silently adds the file to its `withheld` list and reports `findings: []`, producing a **false-clean** result for exactly the record under review, and no frontmatter-parse gate currently covers `.ai-state/decisions/drafts/` (only finalized ADRs, if at all).
- **Rationale**: Two independent authors hit this exact defect class within one review (the reviewer's own first probe fixture, and the actual ADR under review) — a strong signal this is a systemic authoring risk, not a one-off typo. The downstream consequence is worse than a normal syntax error: it degrades a reciprocity *gate* into reporting a clean result while silently excluding the one record it was asked to verify, which is the same class of guard-failing-open risk the ADR/reciprocity machinery exists to prevent.
- **Estimated scope**: single rule file, one new bullet in the Frontmatter subsection (~5-6 lines); a companion coverage gap (extend `check_frontmatter_parses.py` or an equivalent gate to `.ai-state/decisions/drafts/`) is out of scope for this proposal and should be raised separately to the context-engineer/implementer as a follow-up fix, not folded into the rule text
- **Overlap check**: grepped `adr-conventions.md` for "quote"/"scalar"/"colon" — no existing guidance on YAML scalar escaping in frontmatter values
- **Recommended delegation**: context-engineer (rule text) — the coverage-gap fix (`check_frontmatter_parses.py` scope) is a separate implementer follow-up, not part of this rule proposal
- **Suggested artifact path**: `rules/swe/adr-conventions.md`

### Proposal 3: gate-liveness.md — a digest must surface suppressed (`withheld`) findings, not just severity counts

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-p2-wrap/process-economy-p2-wrap/LIGHT_REVIEW_wrap.md` § F3
- **Description**: Extend the same anti-pattern table (or the new row from Proposal 1, if the context-engineer judges them close enough to merge) with the distinct failure mode where a digest carries `fail/warn/info/skipped/examined/bound` but omits `withheld` (suppressed-finding) entries entirely. The consequence differs from Proposal 1: it is not that one instruction becomes unexecutable, it is that "N checks clean" becomes indistinguishable from "N checks clean, M findings suppressed" — silently defeating any check whose own PASS semantics explicitly depend on reading `withheld` (the source's worked example: `AC13`'s own bound string reads "clean means … read withheld before reading zero findings", which the digest makes impossible to honor).
- **Rationale**: A genuinely distinct remedy from Proposal 1 (surface a whole omitted key vs. reproduce one present-but-missing field) and a distinct trigger condition (only bites when a family's own PASS semantics reference `withheld`) — worth a separate row so a future author searching "what must a digest never drop" finds both entries rather than one merged, less-specific one.
- **Estimated scope**: single rule file, one new anti-pattern table row (~5-6 lines)
- **Overlap check**: none beyond the shared theme with Proposal 1 (same rule file, adjacent but distinct row) — flagged for the context-engineer to decide merge-vs-separate at drafting time
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/gate-liveness.md`

### Proposal 4: gate-canaries.md — a terminal free-form capture group in a `fullmatch` grammar has no trailing-content boundary

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-p2-wrap/process-economy-p2-wrap/LIGHT_REVIEW_wrap.md` § F4
- **Description**: Add a subsection to `skills/testing-strategy/references/gate-canaries.md`: when a row/record grammar's final field is matched by a lazy free-form group (e.g. `(?P<verdict>.*?)\s*` under `fullmatch`), nothing after that group's own terminator can ever fail the pattern on *shape* — only a downstream budget/length check can catch trailing content. Probe table from the source: a **leading** misplaced clause is correctly rejected, but the same clause **trailing** the verdict is silently accepted, along with a trailing duplicate of another field. If the parse-don't-strip property is meant to hold ("verdict map only, nothing else"), the fix is a negative lookahead for every other field's own leading marker (e.g. `(?!.*Conditional on )(?!.*Spec \+ golden bad-cases:)`) placed before the terminal group, not reliance on the budget check to catch shape violations after the fact.
- **Rationale**: A directly reusable regex-design gotcha for any grammar with a free-form terminal field (common in row-based DSLs like this project's own sentinel-row contract) — distinct from this run's earlier-batch findings on greedy `MULTILINE+DOTALL` misattribution and cross-directory import idioms, and general enough to apply beyond this specific script.
- **Estimated scope**: single skill reference file, ~10-12 line new subsection with the probe table as a worked example
- **Overlap check**: grepped `gate-canaries.md` for "terminal"/"lookahead"/"trailing" — no existing coverage of this specific pitfall
- **Recommended delegation**: context-engineer (review scope) then implementer (content)
- **Suggested artifact path**: `skills/testing-strategy/references/gate-canaries.md`

### Proposal 5: gate-canaries.md — re-verify a synthetic probe fixture against the real artifact before trusting its result

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `.ai-work/_harvest/process-economy-p2-wrap/process-economy-p2-wrap/LIGHT_REVIEW_wrap.md` § Property (a)
- **Description**: A short note for `skills/testing-strategy/references/gate-canaries.md`'s mutation-probing guidance: the reviewer's first run of the F4 probe table produced false failures because the synthetic test text omitted the real dispatch table the pattern depends on; only after embedding the live dispatch table did the probe results become trustworthy. State the discipline explicitly: a mutation probe against a hand-written synthetic fixture is only as good as that fixture's fidelity to the real artifact's structure — re-run once against the live corpus/file before reporting a probe's PASS/FAIL, not just against the synthetic case.
- **Rationale**: Low-priority but genuinely reusable meta-discipline for anyone writing mutation probes for a gate/canary — the failure mode (false probe failures from an incomplete fixture) is easy to mistake for a real bug and costs a debugging detour if not named explicitly.
- **Estimated scope**: single skill reference file, 3-4 line addition to existing mutation-probing guidance (if present) or a new short callout
- **Overlap check**: none found — `gate-canaries.md`'s mutation-probing content (if any) does not currently address fixture fidelity
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/testing-strategy/references/gate-canaries.md`

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | Rule update; load rule-crafting |
| 2 | context-engineer | Rule update; load rule-crafting; note the separate implementer follow-up for the `check_frontmatter_parses.py` coverage gap is NOT part of this proposal |
| 3 | context-engineer | Rule update; decide merge-vs-separate against Proposal 1 at drafting time |
| 4 | context-engineer then implementer | Skill reference update; context-engineer scopes, implementer drafts the worked-example subsection |
| 5 | context-engineer | Small skill reference addition; low priority, bundle with Proposal 4 if convenient |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 5 pending proposals.
- After approval, invoke `context-engineer` for the `gate-liveness.md`, `adr-conventions.md`, and `gate-canaries.md` updates; the agent will pick up the recommended delegations table.
- Separately from this harvest: consider raising the `check_frontmatter_parses.py` coverage gap noted in Proposal 2 (does not scan `.ai-state/decisions/drafts/`) as a direct implementer fix — it is a code change, not a rule proposal, and falls outside skill-genesis's scope.
