---
schema_version: 1
report_id: skill-genesis-2026-09-23_22-35-25
generated_at: 2026-09-24T05:37:15Z
task_slug: skill-genesis-2026-09-23
agent_version: skill-genesis@a32004c7
invocation_args: { since: null, scope: null, sources: .ai-work/_harvest, batch: "1 of 13", dry_run: false }
review_status: pending
disposition_count: { pending: 4, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-09-23 22:35:25

## Summary

3 queued harvest sources analyzed (`beauty-dimensions`, `data-structures-pillar`, `rust-first-class` — all under `.ai-work/_harvest/data-structures-pillar/`), all three already-merged pipelines whose LEARNINGS.md/VERIFICATION_REPORT.md/CONSULT fragments were read in full (none oversize). ~14 discrete learning items extracted; most implementation-specific content (skill bodies, hook code, ADRs) is already landed in the codebase and was discarded as non-actionable. 5 proposals survived triage — all process/coordination-protocol patterns that generalize beyond the originating tasks, including one recurring-twice signal (three-site philosophy drift) worth cross-batch attention in later batches of this queue. Review status: pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| Queue source: beauty-dimensions LEARNINGS.md | `.ai-work/_harvest/data-structures-pillar/beauty-dimensions/LEARNINGS.md` | 5 | Read |
| Queue source: data-structures-pillar LEARNINGS.md | `.ai-work/_harvest/data-structures-pillar/data-structures-pillar/LEARNINGS.md` | 4 | Read |
| Queue source: rust-first-class LEARNINGS.md | `.ai-work/_harvest/data-structures-pillar/rust-first-class/LEARNINGS.md` | 5 | Read |
| Queue source: rust-first-class VERIFICATION_REPORT.md | `.ai-work/_harvest/data-structures-pillar/rust-first-class/VERIFICATION_REPORT.md` | 0 | Not read (F1 finding already resolved per LEARNINGS's Step-4 rework note; no new pattern beyond what LEARNINGS captured) |
| Queue source: rust-first-class CONSULT_evidence-appraiser.md | `.ai-work/_harvest/data-structures-pillar/rust-first-class/CONSULT_evidence-appraiser.md` | 0 | Not read (the one generalizable finding from this consult — carrier-file tracking — is already captured via the LEARNINGS.md Step-4 rework entry; reading the 42KB fragment for marginal additional yield was not turn-budget-justified this batch) |
| Latest SENTINEL_REPORT_*.md | `.ai-state/sentinel_reports/` | — | Not found / not consulted this batch (queue mode prioritizes listed sources) |
| Latest IDEA_LEDGER_*.md | `.ai-state/idea_ledgers/IDEA_LEDGER.md` | 0 | Read — no overlapping prior proposals |
| ADRs (recent) | `.ai-state/decisions/` | 0 matched | Pre-scanned via grep on "three sites", "carrier file" — no matches |
| Sibling reports of this harvest run | `.ai-state/skill_genesis_reports/` | 0 | None yet pending in this queue run (batch 1 of 13, first report) |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | Three-site philosophy drift: `claude/config/CLAUDE.md.tmpl`, `codex/config/AGENTS.md.tmpl`, root `AGENTS.md` must update together; Balanced Coupling was found absent from the Codex mirror by TWO independent tasks in this batch | beauty-dimensions LEARNINGS (Tech Debt), data-structures-pillar LEARNINGS (Gotchas) | Rule (update) | Declarative, cross-context convention; gate-liveness.md already states the general "two+ sites" anti-pattern abstractly — this is a concrete, twice-confirmed instance worth naming explicitly so the abstract row stops being reproven per task |
| 2 | Internal "N mechanisms converge" claims must be checked for entailment, not just counted — a convergence label survives only if each leg can independently be false while the others hold | rust-first-class LEARNINGS (Gotchas) | Skill (update) | Extends `evidence-appraisal`'s existing "independent traditions must converge" principle from *imported* claims to *self-generated* reasoning chains — same discipline, uncovered corner |
| 3 | An evidence marker naming an absent source is unsatisfiable by construction; a prescription's source scope is part of the claim (check the source's own scope floor before importing into a generator) | rust-first-class LEARNINGS (Gotchas) | Skill (update) | Same evidence-appraisal extension as #2 — two related heuristics for self-authored/generated evidentiary claims, batched into the same proposal |
| 4 | A consult disposition governing a *claim* (not a *file*) needs a "carrier files" field recorded at disposition time — the verifier caught a stale pre-disposition framing surviving in a sibling file that wasn't `review: force`-tagged because only the originally-cited file was | rust-first-class LEARNINGS (Step 4, self-flagged generalization) | Rule/Skill (update) | Coordination-details.md's discipline-consultant disposition protocol records adopted/rejected/escalated but has no field for "which files carry this claim" — the source itself proposes the fix ("a one-line 'carrier files: X, Y' field... set at disposition time") |
| 5 | `scripts/check_id_citation_discipline.py` cannot self-verify its own target files when run from inside the worktree that owns them (`/.claude/worktrees/` path-fragment exclusion checks absolute path, not repo-relative) | rust-first-class LEARNINGS (Step 3) | Rule (update) | Declarative known-limitation note; prevents a future agent from trusting a vacuous "0 violations" self-check inside a worktree session |
| 6 | "Audit-first refresher" pattern: for "engrave X we already partially have" tasks, an internal COVERED/PARTIAL/ABSENT coverage audit must precede external research | beauty-dimensions LEARNINGS (Patterns) | Skip (this batch) | Genuinely reusable but narrower single-task evidence than #1/#4; no existing skill section found to extend cleanly (spec-driven-development/software-planning checked, no hit) — defer to a later batch to see if it recurs before proposing a new section |
| 7 | "Dormant-mechanism delivery" pattern: landing a new cross-cutting feature as the first live instance of an already-built-but-unused mechanism is a reusable "two birds" shape | beauty-dimensions LEARNINGS (Patterns) | Skip (this batch) | Single-instance observation; interesting but not yet a recurring pattern across ≥2 sources — recorded here for a future batch to pick up if it recurs |
| 8 | Principle→skill→rule-anchor→discipline-row four-layer embedding is a reusable template for adding any new philosophy pillar at near-zero always-loaded cost | data-structures-pillar LEARNINGS (Patterns) | Skip (this batch) | Overlaps #6/#7 as a "process pattern" family; same single-instance-so-far reasoning — batching all three into one proposal risked diluting the two strongest (#1, #4) with weaker single-instance material |
| 9 | `software-design-principles` skill lacks frontmatter injection into any agent's `skills:` list, despite the enforcement-surface convention | beauty-dimensions + data-structures-pillar LEARNINGS (both explicitly declined-as-out-of-scope) | Skip | Explicitly a "not fixed here, candidate for follow-up" tech-debt note by the source agents themselves, not a knowledge-formalization candidate — belongs in `TECH_DEBT_LEDGER.md`, not a skill/rule proposal |
| 10 | Quote-attribution drift in the philosophy canon (Dijkstra/Hoare, Perlis/Hickey, Cunningham, Matz, Postel/RFC 9413) | beauty-dimensions LEARNINGS (Gotchas) | Skip | Content-specific to the canon already shipped; not a reusable process pattern |
| 11 | `_lang_tools.staged_files()` / `_find_ruff()` dedup, Rust edition resolution via `tomllib`, registry-invariant test parametrization, and other rust-first-class implementation gotchas (Steps 1–4) | rust-first-class LEARNINGS | Skip | Fully implemented, narrow to the shipped `hooks/_lang_tools.py` — no generalizable pattern beyond what already lives in the code and its docstrings |
| 12 | Ruff-pin-drift resolved via `uv run ruff --version` once to materialize `.venv` | rust-first-class LEARNINGS (Step 1) | Skip (deduped) | Already captured in harness memory (`feedback_ruff_version_skew_precommit.md`) |
| 13 | `scope_matches()` silently iterates characters when passed a bare string instead of a list | beauty-dimensions LEARNINGS (Gotchas) | Skip | Code-level API-signature gotcha already fixed in the shipped `principles.yaml` loader; narrow, non-recurring |
| 14 | Twelve contested Rust practices ship as per-project ADR prompts, never enforced defaults; two evidence regimes (disagreement vs. no-tier-1/2-source) for weakly-grounded guidance | rust-first-class LEARNINGS (Decisions) | Skip | Already fully implemented as shipped `rust-development` skill content; the "regime" taxonomy is task-scoped decision rationale (ADR material), not a reusable cross-task pattern |

## Discipline-Gap Signals

None recorded this batch — the one discipline convened (`evidence-appraiser` in rust-first-class) matched an existing registry entry and its dialogue produced a normal disposition, not a "we needed a voice the registry doesn't carry" signal.

## Proposals

### Proposal 1: Gate-liveness three-site philosophy-drift example

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/data-structures-pillar/beauty-dimensions/LEARNINGS.md § Technical Debt`; `.ai-work/_harvest/data-structures-pillar/data-structures-pillar/LEARNINGS.md § Gotchas`
- **Description**: Add a named example row (or extend the existing example) in `rules/swe/gate-liveness.md`'s two-site anti-pattern table naming the specific triple `claude/config/CLAUDE.md.tmpl` / `codex/config/AGENTS.md.tmpl` / root `AGENTS.md` as a confirmed-twice-drifted site set for philosophy-pillar content, alongside the existing discipline-consultant three-site example.
- **Rationale**: Two independent, unrelated pipeline tasks in the same harvest batch each rediscovered that the Codex mirror lags the Claude template for philosophy principles (Balanced Coupling was missing from the Codex site, caught and left unfixed both times). The general "two+ sites" principle already exists in `gate-liveness.md`; what's missing is that this *specific* site-set isn't named, so each new philosophy-pillar task re-derives the same gotcha from scratch instead of getting warned by the rule.
- **Estimated scope**: single rule file (add ~3-line table row/example)
- **Overlap check**: `rules/swe/gate-liveness.md` line 47 already states the abstract "two+ sites" anti-pattern with the discipline-consultant example — this proposal extends that row's example list, not a new row/rule.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/gate-liveness.md`

### Proposal 2: Evidence-appraisal — internal convergence-claim and absent-source-marker heuristics

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/data-structures-pillar/rust-first-class/LEARNINGS.md § Gotchas Discovered` (lines ~127-143)
- **Description**: Add a short subsection to `skills/evidence-appraisal/` extending its "independent traditions must converge" discipline from *imported* claims to *self-generated* reasoning: (a) a "N mechanisms converge" claim survives only if each leg can independently be false while the others hold (checked against entailment, not just count); (b) an evidence-strength marker that names an absent source is unsatisfiable by construction — the satisfiable form is a fixed-literal statement of absence a verifier can grep for; (c) a prescription's source scope is part of the claim — check the source's own applicability floor (e.g., LOC range, project size) before importing a recommendation into a generator/scaffolding artifact consumed at a different scale.
- **Rationale**: These three heuristics were independently discovered mid-pipeline (not pre-existing skill content) and directly generalize the skill's existing single-source-is-one-source discipline to a blind spot — self-authored convergence claims and generator/template authoring — that the current SKILL.md and `claim-provenance.md` reference don't cover.
- **Estimated scope**: SKILL.md + possible small addition to `references/claim-provenance.md`
- **Overlap check**: `skills/evidence-appraisal/SKILL.md` lines 31/46/58 cover external-source convergence only; no existing coverage of internally-derived convergence claims or generator-scope-import found via grep.
- **Recommended delegation**: context-engineer (review scope) then implementer (content)
- **Suggested artifact path**: `skills/evidence-appraisal/SKILL.md`, `skills/evidence-appraisal/references/claim-provenance.md`

### Proposal 3: Discipline-consultant disposition — carrier-files field

- **Disposition**: pending
- **Type**: rule (update) / skill (update)
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P0 (this-cycle)
- **Source(s)**: `.ai-work/_harvest/data-structures-pillar/rust-first-class/LEARNINGS.md` (unheaded entry after Step 4, "A consult correction must be grepped across ALL sibling files...")
- **Description**: Add a "carrier files" field to the discipline-consultant disposition record described in `coordination-details.md § Discipline-Consultant Dialogue Protocol` — at disposition time (not discovery time), the convener records every file carrying the dispositioned claim's distinctive phrasing (via a repo-wide grep for that phrasing), and downstream `review: force` tagging is scoped to that full carrier set, not just the file the challenge happened to quote from.
- **Rationale**: This is a self-flagged generalization already written out in the source LEARNINGS.md by the implementer who fixed the actual F1 verifier finding: a dispositioned correction was applied correctly to the cited file but survived near-verbatim in a sibling file nobody tagged for content-fidelity review, and was only caught by the verifier after shipping. The fix the source proposes ("a one-line 'carrier files: X, Y' field... set at disposition time rather than discovered at verification time") is concrete and ready to draft; P0 because this is a process gap that will silently recur on every future multi-file consult disposition until fixed.
- **Estimated scope**: single rule file update, or a small section addition to `skills/software-planning/references/coordination-details.md § Discipline-Consultant Dialogue Protocol` — context-engineer to decide correct placement (rule vs. skill reference) since the protocol currently lives in a skill reference, not a rule.
- **Overlap check**: `coordination-details.md` lines ~283-307 cover disposition vocabulary and durable-record requirements but have no carrier-file tracking field.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/coordination-details.md`

### Proposal 4: id-citation-discipline — worktree self-verification limitation

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/data-structures-pillar/rust-first-class/LEARNINGS.md § Step 3 Learnings`
- **Description**: Add a known-limitation note to `rules/swe/id-citation-discipline.md`: `scripts/check_id_citation_discipline.py`'s `EXCLUDED_PATH_FRAGMENTS` excludes any absolute path containing `/.claude/worktrees/` to avoid double-scanning a sibling worktree from the main checkout — but this means running the checker *from inside* a worktree session against its own files always reports "0 files scanned" regardless of `--repo-root`, since the exclusion checks the absolute path, not the repo-relative one. A future agent inside a worktree must verify by inspection, not by trusting a vacuous pass.
- **Rationale**: Concrete, reproducible tooling gotcha discovered mid-pipeline; the exact failure mode (silent vacuous pass, not an error) is exactly the class of non-obvious footgun the rule-crafting guidance prioritizes ("gotchas are the highest-signal content"), and it will recur for every future worktree-scoped pipeline task that tries to self-verify id-citation compliance.
- **Estimated scope**: single rule file (add ~4-line known-limitation note)
- **Overlap check**: `rules/swe/id-citation-discipline.md` has no mention of worktree behavior (grep confirmed zero hits).
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/id-citation-discipline.md`

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | Rule update; load `rule-crafting`; extend existing table row, not a new rule |
| 2 | context-engineer (review scope) then implementer (content) | Skill update; load `skill-crafting`; touches SKILL.md + one reference file |
| 3 | context-engineer | Placement decision (rule vs. skill-reference) needed first, since the protocol lives in `coordination-details.md` today; P0 |
| 4 | context-engineer | Rule update; load `rule-crafting`; small, self-contained addition |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 4 pending proposals.
- After approval, invoke `context-engineer` for the rule/skill updates; the agent will pick up the recommended delegations table.
- Two learning items (audit-first refresher pattern, dormant-mechanism delivery pattern — Triage #6/#7/#8) were single-instance this batch and deliberately skipped; if a later batch in this 13-batch queue surfaces the same pattern again, promote it to a proposal then.
- Proposal 1's three-site drift signal is itself evidence the harvest queue should watch for: if batch 2+ resurfaces the same Codex-mirror-drift gotcha a third time, consider escalating from a rule-table example to a mechanical sentinel/DL0x check.
