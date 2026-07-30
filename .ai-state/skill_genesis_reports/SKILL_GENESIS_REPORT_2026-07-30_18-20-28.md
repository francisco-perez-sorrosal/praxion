---
schema_version: 1
report_id: skill-genesis-2026-07-30_18-20-28
generated_at: 2026-07-30T18:20:28Z
task_slug: multidisciplinary-identities
agent_version: skill-genesis@b6477a5
invocation_args: { since: null, scope: null, dry_run: false }
review_status: pending
disposition_count: { pending: 5, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-07-30 18:20:28

## Summary

6 learning sources analyzed (LEARNINGS.md, VERIFICATION_REPORT.md, two CONSULT artifacts, the latest
SENTINEL_REPORT, and the calibration log's recent Retrospective cells), ~20 discrete learning items
extracted, 5 proposals generated, ~15 items deduplicated or discarded (project-specific ADR content,
narrow one-off line-budget arithmetic, items already fully captured by existing rules). No
discipline-gap signals found — this is the first exercise of that triage leaf and the sources
contain no recurring "we needed discipline X" pattern. Review status: pending.

This run is the last chance to harvest `.ai-work/multidisciplinary-identities/` prose before its
deletion; the directory's `LEARNINGS.md`, `VERIFICATION_REPORT.md`, and `CONSULT_*.md` fragments were
read in full.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| LEARNINGS.md (current task) | `.ai-work/multidisciplinary-identities/LEARNINGS.md` | 9 | Read |
| VERIFICATION_REPORT.md (current task) | `.ai-work/multidisciplinary-identities/VERIFICATION_REPORT.md` | 6 | Read |
| CONSULT_statistician.md | `.ai-work/multidisciplinary-identities/CONSULT_statistician.md` | 1 (domain content, not process-generalizable — used for context only) | Read |
| CONSULT_SMOKE_TEST.md | `.ai-work/multidisciplinary-identities/CONSULT_SMOKE_TEST.md` | 1 | Read |
| Latest SENTINEL_REPORT_*.md | `.ai-state/sentinel_reports/SENTINEL_REPORT_2026-07-30_11-03-40.md` | 3 (independent confirmation of two verifier findings + T02 self-audit) | Read |
| calibration_log.md Retrospective cells | `.ai-state/calibration_log.md` (last 3 dense rows) | 0 net-new (reinforces patterns already extracted elsewhere; no new item cleared the "note after em-dash" bar beyond restating known findings) | Read |
| Latest IDEA_LEDGER_*.md | `.ai-state/idea_ledgers/IDEA_LEDGER.md` | 0 (consulted for dedup only — no overlapping proposal found) | Read |
| ADRs (recent, dec-298–dec-304) | `.ai-state/decisions/` | 0 (project-specific decisions, not process-generalizable) | Read (index-level) |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | Four checker/gate scripts each computed a narrower actual scope than the scope they claim/are documented to cover (`finalize_adrs.py` allowlist gap; `check_id_citation_discipline.py` missing `I-N` id shape; `check_release_staleness.py` ignoring `scripts/`; sentinel `T02`'s dispatch command vs. the budget rule's defined scope) — each reports PASS/green while silently under-looking | LEARNINGS §Tech Debt, VERIFICATION_REPORT F-03/W-04, SENTINEL_REPORT td-068 | **Rule (update)** | Declarative, cross-context (applies to any deterministic gate), 4 independent occurrences confirmed by 3 separate agents (verifier, sentinel, orchestrator) in one day — well past the "recurs, not formalize-worthy yet" bar |
| 2 | A specification that lives at two textual sites (a canonical table row + a dispatch/prose paragraph, or a canonical count + a duplicate count elsewhere) drifts when only one site is updated — sentinel `P07` row/dispatch asymmetry, `BC03`'s hardcoded agent count, the prior "Available Agents table row asymmetry" (already in memory) | LEARNINGS §Edge Cases (BC03), VERIFICATION_REPORT F-02 | **Rule (update, related to #1 but distinct mechanism)** | Declarative, recurring (3rd confirmed instance across sessions per persistent memory), but the failure mechanism (duplicated source of truth) is mechanically different from #1 (narrowed computed scope) — flagged as sibling, not merged |
| 3 | Fitness/extensibility tests for not-yet-existing artifacts can land early via a pure-function/canary split (assert on synthetic strings first, extend to real file-scanning assertions once the real artifact lands) | LEARNINGS §Decisions Made (implementation-planner, Step 3/5) | **Skill (update)** | Procedural, reusable staging technique; the `gate-liveness.md` rule already points at `testing-strategy/references/gate-canaries.md` for canary authoring, but that reference does not yet cover the *before-the-artifact-exists* staging pattern — natural extension point, not a duplicate |
| 4 | Before treating a live agent spawn/smoke-test as proof of shipped (plugin-distributed) behavior in a self-hosting repo, verify the installed plugin copy is byte-identical to the repo HEAD the agent would resolve against in a managed project — otherwise a spawn proves self-hosting, not the shipped path, and a `[BLOCKED]` or a PASS is equally void | CONSULT_SMOKE_TEST.md § Step 0 — Gate | **Skill (update) / Rule (new), ambiguous** | Reusable dogfooding-verification technique, but narrow to self-hosting plugin repos (a Praxion-specific condition, not universal) — flagged as ambiguous placement; best assessment is a short addition to a `claude-ecosystem`-adjacent skill or agent-evals reference rather than an always-loaded rule |
| 5 | A quantitative acceptance criterion (e.g., a numeric cost/rate bound) discharged by structural argument alone, with no actual measurement taken, is a distinct and recurring quality defect — flagged twice independently in one day (AC15/W-01 in the verification report, and the same failure mode the feature's own statistician consultant flagged hours earlier against the Wave-2 gate) | VERIFICATION_REPORT §1 AC15, §3 W-01; CONSULT_statistician.md CH-02/CH-04 | **Rule (new) / Skill (update), ambiguous** | Declarative in spirit ("a criterion written as a measurement must be discharged by a measurement, or explicitly demoted to qualitative") but currently has no home — `spec-driven-development` skill's acceptance-criteria authoring section doesn't address it; could also live as a verifier checklist addition |
| 6 | ADR-level decisions (peer-sub-architect ruling, model-routing policy, dialogue rounds, ledger ownership, Wave-1 scope) | LEARNINGS §Decisions Made | Skip | Already captured as finalized ADRs (dec-298–dec-304); ADR conventions rule already governs discovery/dedup — no further formalization needed |
| 7 | Line-budget arithmetic for zero-growth edits ("a new `###` heading costs a minimum of 3 lines"; heading-rename-for-coherence at net +0) | LEARNINGS §Step 11 Learnings | Skip | Too narrow/transient — a one-off costing exercise for a specific line-budget constraint, not a recurring cross-context pattern |
| 8 | Project-local discipline registry overlay gap (open architecture question) | LEARNINGS §Open Architecture Question | Skip | Architectural gap already recorded with a sketched path in `LEARNINGS.md` and flagged for a future systems-architect pass; not a skill-genesis-shaped artifact (no procedural/declarative knowledge to extract beyond what's already written) |
| 9 | `traceability.yml` shipped empty; no test-engineer fragment ever produced | VERIFICATION_REPORT F-01 | Skip | Already filed as `td-066`; `id-citation-discipline.md` + the traceability-file convention already govern this — a single-occurrence process slip, not a new pattern (contrast with item 1's 4 independent occurrences) |
| 10 | Discipline-gap signals (recurring "we needed discipline X but had none" pattern) | All sources | Skip (no signal found) | First exercise of this triage leaf; no source contains a recurring gap signal. Recorded in § Discipline-Gap Signals below as an explicit empty result, not silently omitted |

## Discipline-Gap Signals

No discipline-gap signals found in this harvest. This is the first exercise of the fourth triage leaf
(added to this agent's own definition minutes before this run). Checked explicitly against every source:
the statistician consult (`CONSULT_statistician.md`) is itself evidence the one currently-rostered
discipline fired correctly on a matching claim — it is not a signal of a *missing* discipline. The
verification report's W-03 (REQ-18 clause 2 unimplemented — the mechanism for *recording* a recurring
gap signal doesn't exist yet) is a note about tooling absence, not itself a gap signal. No source
names a recurring decision-at-stake that the current one-discipline roster (or the Tier-1/Tier-2 routes)
failed to cover. Per this agent's constraint, no discipline is proposed and no registry row is drafted —
this section exists to make the absence visible, not to fill it.

## Proposals

### Proposal 1: Gate Liveness — Scope Fidelity (5th clause)

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: mature
- **Scope**: broad
- **Priority**: P0 (this-cycle)
- **Source(s)**: `.ai-work/multidisciplinary-identities/LEARNINGS.md` (BC03 hardcoded-count edge case); `.ai-work/multidisciplinary-identities/VERIFICATION_REPORT.md` F-03, W-04; `.ai-state/sentinel_reports/SENTINEL_REPORT_2026-07-30_11-03-40.md` (td-068 independent reproduction + "measurement-instrument problem" framing); user-supplied fourth instance (`check_release_staleness.py` ignoring `scripts/`)
- **Description**: Add a fifth clause to `rules/swe/gate-liveness.md`'s "The four clauses" section — **Scope Fidelity**: a gate's actual computed input set (the literal glob, allowlist, or regex it evaluates) must be checked against the scope it is documented or claimed to cover, independently of whether it fires correctly on the inputs it does examine. The existing four clauses (substance-over-structure, named-producer, no-self-contradiction, pair-with-verification-path) all assume the gate is looking at the right set of things; none currently requires proving that. Add a self-test line: "Did I diff the gate's *documented* scope against its *actual* computed scope — not just confirm it fires within the scope it already computes?"
- **Rationale**: Four independent, confirmed occurrences surfaced in a single 24-hour window across three different verifying agents (verifier, sentinel, orchestrator): `finalize_adrs.py`'s allowlist silently skipped newly-eligible files (fixed same-day, `1b136c7`); `check_id_citation_discipline.py` detects only `REQ-`/`AC-`/`Step N`/`dec-draft-` shapes and missed the `I-N` (plan-local interface id) leak in F-03; `check_release_staleness.py` ignores `scripts/` though scripts ship via git hooks (user-supplied); sentinel's own `T02` dispatch command computes a materially different (and self-inconsistent) file set than the budget rule it measures, independently reproduced by the sentinel itself as "the highest-leverage fix this cycle." This is one generalizable failure mode — a CODE-kind gate whose claimed and actual scopes have diverged — not four unrelated bugs; the shared mechanism (silent under-coverage that still returns green) is exactly what `gate-liveness.md` already exists to name for other failure shapes, so this is the natural home rather than a new rule file. P0 because a fifth occurrence is plausible before the next audit and the fix is cheap (one clause + one self-test line).
- **Estimated scope**: single rule file (add ~10–15 lines to `rules/swe/gate-liveness.md`)
- **Overlap check**: `rules/swe/gate-liveness.md` (direct extension, not a duplicate — the four existing clauses address different failure shapes); `rules/swe/id-citation-discipline.md` (a downstream *instance* of this pattern, not itself the fix)
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/gate-liveness.md`

### Proposal 2: Paired-Contract Site Synchronization

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: sapling
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/multidisciplinary-identities/LEARNINGS.md` § Edge Cases (`BC03` hardcoded count-of-13/14 agents, "the single most easily-missed insertion point in this change set"); `.ai-work/multidisciplinary-identities/VERIFICATION_REPORT.md` F-02 (sentinel `P07` row updated, Pass-1 dispatch paragraph not); persistent memory's already-recorded "Available Agents table row asymmetry" (a third confirmed instance across sessions, not sourced from this pipeline directly but named as the same shape by the verifier itself)
- **Description**: A short addition (likely to `gate-liveness.md` as a named sub-pattern, or a standalone declarative note) capturing: when one piece of knowledge is encoded at two textual sites (a canonical table row + a prose dispatch paragraph; a canonical count + a duplicated count elsewhere), updating only one site is a silent drift that a check reading only the canonical site cannot catch. The remedy is either a single source of truth with the second site deriving from it, or an explicit cross-reference note at both sites naming the other.
- **Rationale**: Confirmed a third time in one day (`BC03`'s count, `P07`'s dispatch/row split, plus the pre-existing memory of the Available-Agents-table asymmetry) — past the "pattern recurs but not formalized" bar. Distinct mechanism from Proposal 1 (duplicated specification vs. narrowed computed scope), so kept as a sibling rather than folded in, though both belong under the same rule file for discoverability. P1 rather than P0 because each known instance was caught and fixed the same day it was introduced — the cost of the gap is currently low, unlike Proposal 1's silent-for-months T02 drift.
- **Estimated scope**: single rule file (add ~5–10 lines, likely as a sub-bullet of the same gate-liveness.md edit as Proposal 1, or its own short section)
- **Overlap check**: `rules/swe/gate-liveness.md` (sibling addition); `rules/swe/agent-behavioral-contract.md` (adjacent but not the same — this is a structural/documentation-sync issue, not a behavioral-contract violation)
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/gate-liveness.md`

### Proposal 3: Testing-Strategy — Canary-Before-Artifact Staging Pattern

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `.ai-work/multidisciplinary-identities/LEARNINGS.md` § Decisions Made (implementation-planner, "Fitness test lands early via a pure-function/canary split")
- **Description**: A short addition to `skills/testing-strategy/references/gate-canaries.md` documenting the staging pattern used in this pipeline: an extensibility/fitness test can be authored and proven correct *before* the real artifacts it will eventually check exist, by splitting it into (a) helper functions plus synthetic-string canaries proving the assertion logic is sound, then (b) extending the same test file with real file-scanning assertions once the artifacts land in a later step. Cite this repo's own precedent (`test_meta_citation.py`) as the existing pattern this staging reuses.
- **Rationale**: A genuinely reusable technique for any roadmap that lands a fitness/extensibility test ahead of the artifacts it will check — directly useful to future implementation-planner steps. Kept at P2/seedling because this is a single observed instance (not yet a recurring pattern across multiple pipelines); worth capturing now while the reasoning is fresh, disposition later once it recurs.
- **Estimated scope**: SKILL.md + 1 reference (small addition to existing `references/gate-canaries.md`, no new file)
- **Overlap check**: `skills/testing-strategy/references/gate-canaries.md` (extends, does not duplicate — covers canary authoring generally but not the before-artifact-exists staging split)
- **Recommended delegation**: context-engineer (review scope) then implementer (content)
- **Suggested artifact path**: `skills/testing-strategy/references/gate-canaries.md`

### Proposal 4: Self-Hosting Plugin Version-Pin Verification Gate

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `.ai-work/multidisciplinary-identities/CONSULT_SMOKE_TEST.md` § Step 0 — Gate ("The previous session stopped here: the installed plugin was pinned at `0.16.0` while the consultant landed on `main` afterward... a spawn would have resolved non-deterministically between two roots")
- **Description**: A short, reusable checklist for any live agent smoke test in a self-hosting plugin repo (Praxion consuming its own `i-am` plugin): before spawning an agent to prove a shipped-plugin behavior, confirm the installed plugin cache copy is byte-identical to the repo HEAD the agent would resolve against in a managed (non-self-hosting) project — via `find ~/.claude/plugins/cache/.../<agent>.md` + `diff -q` against the repo copy. A spawn against a stale installed copy proves nothing (or proves self-hosting resolution only), and either a `[BLOCKED]` or a PASS from such a spawn is void.
- **Rationale**: A real, previously-hit failure mode ("the previous session stopped here") with a documented, cheap fix already executed once. Reusable for future Wave-2+ dogfood smoke tests and any other live-agent proof-of-shipped-behavior exercise. Flagged as ambiguous placement (skill vs. rule) — it is Praxion-specific (this project self-hosts its own plugin) rather than universal, so an always-loaded rule feels like the wrong tier; a reference note in a claude-ecosystem-adjacent skill (or the `swe-agent-coordination-protocol.md`'s Background/Proactive-Usage section, on a path-scoped or reference basis) is the better fit. Context-engineer is the authoritative placement decision-maker per this agent's own triage tree.
- **Estimated scope**: SKILL.md or reference addition only (small; exact home ambiguous, left to context-engineer)
- **Overlap check**: none found — no existing skill or rule addresses self-hosting-plugin version-pin verification
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: ambiguous — candidates are `skills/claude-ecosystem/` (if scoped there) or a new short reference under `skills/agent-evals/references/`; context-engineer to decide

### Proposal 5: Quantitative Acceptance Criteria Must Not Be Discharged by Structural Argument Alone

- **Disposition**: pending
- **Type**: rule (new) / skill (update), ambiguous
- **Maturity**: sapling
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/multidisciplinary-identities/VERIFICATION_REPORT.md` §1 AC15, §3 W-01 ("A quantitative criterion discharged by structural argument is exactly the failure mode CH-04 raised against this project's own gate"); `.ai-work/multidisciplinary-identities/CONSULT_statistician.md` CH-02, CH-04
- **Description**: A declarative addition (likely to `spec-driven-development`'s acceptance-criteria authoring guidance, or a verifier checklist item) stating: when an acceptance criterion is written as a measurement (a numeric threshold, a rate, a cost envelope with a comparator), it must be discharged by an actual recorded measurement — not by a structural argument that the bound is "plausibly held." If no measurement was taken, the criterion should be marked WARN (asserted, not verified) rather than PASS, or the criterion itself should be explicitly demoted to a qualitative/structural claim at authoring time.
- **Rationale**: This exact failure mode was independently flagged twice within hours in the same pipeline — once by the verifier (AC15/W-01, "never measured... discharged by structural argument") and once, earlier, by the feature's own statistician consultant (CH-02/CH-04, arguing the Wave-2 dismiss-rate gate is "asserted, not derived" and cannot be validly evaluated at its stated sample size). Two independent reviewers converging on the same abstract defect in one day, in two different artifacts, is strong signal this is a recurring authoring gap rather than a one-off. Ambiguous placement (declarative rule vs. skill-authoring-guidance update) is flagged for context-engineer; either home is defensible.
- **Estimated scope**: single rule file, or a small addition to `skills/spec-driven-development/SKILL.md`'s acceptance-criteria section — context-engineer to decide which
- **Overlap check**: `skills/spec-driven-development/SKILL.md` (acceptance-criteria authoring section exists but does not currently address the measurement-vs-structural-argument distinction, per targeted grep); `rules/ml/eval-driven-verification.md` (adjacent — already handles ML metric-threshold tolerance bands, but that rule assumes a measurement *was* taken; this proposal covers the case where none was)
- **Recommended delegation**: context-engineer (review scope) then implementer (content)
- **Suggested artifact path**: ambiguous — candidates are `skills/spec-driven-development/SKILL.md` (acceptance-criteria section) or a new rule `rules/swe/quantitative-acceptance-criteria.md`; context-engineer to decide

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | Rule update; load `rule-crafting`; extends `gate-liveness.md`'s existing four-clause structure |
| 2 | context-engineer | Rule update; likely same edit pass as Proposal 1 (sibling section in the same file) |
| 3 | context-engineer (review scope) then implementer (content) | Skill reference update; small, low-risk addition to `gate-canaries.md` |
| 4 | context-engineer | Placement decision needed first (skill vs. rule, which skill); then implementer for content |
| 5 | context-engineer (review scope) then implementer (content) | Placement decision needed first (SDD skill vs. new rule); then content |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 5 pending proposals.
- After approval, invoke `context-engineer` for the rule/skill updates; the agent will pick up the recommended delegations table. Proposals 1 and 2 both target `rules/swe/gate-liveness.md` — consider a single combined context-engineer pass if both are approved.
- Proposals 4 and 5 carry ambiguous placement by design (per this agent's triage tree, ambiguous cases are flagged rather than forced) — context-engineer is the authoritative placement expert for both.
- No discipline-gap signals were found this run; no follow-up needed on that front until a future harvest surfaces one.
