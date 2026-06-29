---
schema_version: 1
report_id: skill-genesis-2026-06-28_00-30-00
generated_at: 2026-06-28T00:30:00Z
task_slug: ad-hoc
agent_version: skill-genesis@443f698
invocation_args: { since: null, scope: "full ecosystem harvest", dry_run: false }
review_status: pending
disposition_count: { pending: 4, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-06-28 00:30:00

## Summary

7 LEARNINGS.md files analyzed, 1 VERIFICATION_REPORT.md, 1 sentinel report (2026-06-20), 1 idea ledger.
14 discrete learning items extracted.
4 items pass deduplication and triage (2 rule proposals, 2 skill-update proposals).
10 items skipped (already covered by existing artifacts or too narrow/transient to formalize).
Review status: pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| LEARNINGS.md (readiness-eval-feedback) | `.ai-work/readiness-eval-feedback/LEARNINGS.md` | 3 | Read |
| VERIFICATION_REPORT.md (readiness-eval-feedback) | `.ai-work/readiness-eval-feedback/VERIFICATION_REPORT.md` | 2 | Read |
| LEARNINGS.md (skills-coherence-pass) | `.ai-work/skills-coherence-pass/LEARNINGS.md` | 2 | Read |
| LEARNINGS.md (skills-conformance) | `.ai-work/skills-conformance/LEARNINGS.md` | 2 | Read |
| LEARNINGS.md (production-gate-cohort) | `.ai-work/production-gate-cohort/LEARNINGS.md` | 2 | Read |
| LEARNINGS.md (wal-bound-brief-floor) | `.ai-work/wal-bound-brief-floor/LEARNINGS.md` | 1 | Read |
| LEARNINGS.md (l3-readiness-config) | `.ai-work/l3-readiness-config/LEARNINGS.md` | 1 | Read |
| LEARNINGS.md (agent-truncation-recovery) | `.ai-work/agent-truncation-recovery/LEARNINGS.md` | 1 | Read |
| SENTINEL_REPORT_2026-06-20_13-34-25.md | `.ai-state/sentinel_reports/SENTINEL_REPORT_2026-06-20_13-34-25.md` | 2 | Read |
| IDEA_LEDGER.md | `.ai-state/idea_ledgers/IDEA_LEDGER.md` | — | Read (no new harvest candidates; pending SIA-1…SIA-6 items are already documented) |
| ADRs (recent) | `.ai-state/decisions/DECISIONS_INDEX.md` | 2 | Read — patterns in dec-248…dec-252 consumed; no standalone ADR candidates identified |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | Fresh-bang-backtick is a shell-execution injection vector in agent-loaded surfaces | skills-coherence-pass/LEARNINGS.md | **Rule (new)** | Declarative constraint with clear pattern + remedy; cross-cutting (all SKILL.md, agent prompts, pipeline docs); NOT in any existing rule or skill |
| 2 | Pinned pre-commit ruff (0.8.6) vs local ruff (0.15.4) causes infinite commit-abort loop | l3-readiness-config/LEARNINGS.md + user context | **Rule (update coding-style.md)** | Declarative gotcha about a specific tool configuration skew; fits the existing `coding-style.md` Baseline Configuration section which already covers pre-commit |
| 3 | Read all matching ADRs before recommending supersession or ≥3-file convention changes | skills-conformance/LEARNINGS.md | **Rule (update adr-conventions.md)** | Declarative discovery discipline; not a workflow but a precondition constraint; topically belongs in the ADR conventions rule |
| 4 | Context-engineer multi-skill dispatch: skeleton-first + inline-return + audit-then-edit-one-pass | skills-conformance/LEARNINGS.md | **Skill (update software-planning/references/coordination-details.md)** | Procedural operational pattern with explicit steps; not declarative; fits the coordination-details reference which already covers delegation checklists |
| 5 | dec-draft- citation skew in DESIGN.md (use dec-draft-<hash> not dec-<hash>) | verification-report W-01 | Skip | Already explicitly covered in `rules/swe/adr-conventions.md` § Linking to ADRs ("cite by its `dec-draft-<hash>` id") |
| 6 | PROMPT gate vs CODE gate proof shape distinction | wal-bound-brief-floor/LEARNINGS.md | Skip | Already covered in `rules/swe/gate-liveness.md` § Two gate kinds, two proofs |
| 7 | skills/README.md staleness is a recurring sentinel finding | sentinel report I2 | Skip | Process maintenance issue, not a formalizable artifact; sentinel already flags and recommends action; would be a doc-engineer task |
| 8 | Always-loaded token budget at 0.9% headroom | sentinel report I1 | Skip | Sentinel has already identified the specific fix (extract Cross-Agent Skill Conventions); this is a context-engineer task, not a new artifact |
| 9 | Tier 1 (git diff + tests) always arbitrates; WIP.md is a validated cache | agent-truncation-recovery/LEARNINGS.md | Skip | Architectural decision already captured in dec-248 and the reconcile_pipeline_state.py component; operational not learnable as a rule/skill |
| 10 | fire-but-annotate pattern for mechanical-only gates | readiness-eval-feedback/LEARNINGS.md | Skip | Too domain-specific to the readiness gate design; not a broadly reusable pattern outside that context |
| 11 | deferred production_gate must be bare (no :ref) | production-gate-cohort/LEARNINGS.md | Skip | Praxion-internal artifact-registry code convention; too narrow and transient |
| 12 | Filename-chronological sort (YYYY-MM-DD_HH-MM-SS) is lexicographically reliable | readiness-eval-feedback/LEARNINGS.md | Skip | Already implied by naming conventions in agent-intermediate-documents.md; adding it explicitly adds marginal value |
| 13 | pyproject.toml dep placement: runtime dep vs dev dep distinction | l3-readiness-config/LEARNINGS.md | Skip | Basic Python project knowledge; already derivable from python-development skill and pyproject.toml conventions |
| 14 | Subagent Write to .ai-work/ is blocked — inline return workaround | skills-conformance/LEARNINGS.md | Skip (partial) | Write-block already documented in CLAUDE.md "Known Claude Code Limitations" and docs/claude-code-limitations.md. The inline-return workaround is the procedural complement captured in Proposal 4 (coordination-details update) |

## Proposals

### Proposal 1: Agent-Loaded Surface Injection Guard

- **Disposition**: pending
- **Type**: rule (new)
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P0 (this-cycle)
- **Source(s)**: `skills-coherence-pass/LEARNINGS.md` § "Fresh-bang-backtick in an agent-loaded surface is a live command-injection landmine"; three context-engineer instances crashed at startup during that campaign
- **Description**: A new path-scoped rule documenting the fresh-bang-backtick injection vector in Claude Code: an exclamation mark preceded by whitespace/line-start and immediately followed by a backtick-quoted command string fires as a shell invocation when the file is rendered as an agent instruction surface. The rule names the firing surfaces (SKILL.md bodies, agent prompts, `.ai-work/<slug>/` pipeline docs), the symptom (agent crashes at startup with "command not found"), the fix (spell out "bang-prefixed" in prose; put runnable examples in fenced blocks with obviously-inert commands), and the non-firing surface (backtick, bang, backtick inside a code span). It also distinguishes "read by a human" from "ingested by an agent" — the triggering condition is the latter.
- **Rationale**: This vector crashed multiple agents during the skills-coherence-pass campaign and was discovered only because the symptom was reproducible. It is a non-obvious footgun that affects every author of SKILL.md files, agent prompts, and pipeline docs. No existing rule, skill, or CLAUDE.md entry captures it. Its declarative nature (a constraint on what patterns must never appear in rendered surfaces) makes it a rule, not a skill. P0 because a fresh skill or agent with a fenced example of `! \`git status\`` in its body will silently execute that command on every activation in every session until the rule is known.
- **Estimated scope**: Single rule file — `rules/swe/agent-surface-injection.md` (~40 lines); path-scoped to `skills/**/*.md`, `agents/**/*.md`, `.ai-work/**/*.md` so no always-loaded budget impact
- **Overlap check**: `agent-runtime-guardrails` skill covers prompt injection from external sources at runtime, not Claude Code's bang-prefix dynamic-context feature in authored files. `context-security-review` covers code security review, not this authoring-time vector. No existing rule overlaps.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/agent-surface-injection.md`

---

### Proposal 2: Pre-commit Linter Version Skew Warning

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P0 (this-cycle)
- **Source(s)**: `l3-readiness-config/LEARNINGS.md` § API Version Drift; user session context (pinned pre-commit ruff 0.8.6 vs local ruff 0.15.4 → format churn, UP017 datetime.UTC revert, UP007 "Convert to X|Y" error breaking Python 3.9, infinite commit-abort loop); persistent agent memory `feedback_ruff_version_skew_precommit.md`
- **Description**: An update to `rules/swe/coding-style.md` adding a "Pre-commit version skew" gotcha to the Baseline Configuration section. The update documents: (1) pre-commit hooks pin linter versions separately from the project's own installed versions; (2) a skew between the two causes format churn (each `Edit` triggers a reformat, each commit re-triggers the pre-commit formatter, producing a loop); (3) specific known consequence: ruff 0.8.6 vs 0.15.4 differ on UP017 (`timezone.utc` → `UTC`) and UP007 (`Optional[X]` → `X | None`) which can break Python 3.9 compatibility; (4) escape: when trapped in a commit-abort loop caused by this skew, `git add` the pre-commit-formatted tree and commit via `git commit` directly (never re-Edit, as that re-introduces the local format); (5) long-term fix: align pre-commit pinned version to the project's installed version.
- **Rationale**: This gotcha caused a real, painful infinite loop during the current session. It is not obvious (the symptom looks like a linting error, not a version skew), is reproducible whenever pre-commit is introduced (which is now mandated by coding-style.md itself), and has a specific escape that is counterintuitive (commit the "wrong" format, not your edit). The knowledge is entirely declarative (a warning + escape instruction), which makes it a rule update rather than a skill. Path-scoped so zero always-loaded budget impact. P0 because the mandate to use pre-commit (already in coding-style.md) guarantees this skew will recur in every new project that follows the baseline config.
- **Estimated scope**: `rules/swe/coding-style.md` edit — approximately 12-15 lines added to the Baseline Configuration section as a gotcha paragraph
- **Overlap check**: `rules/swe/coding-style.md` already covers pre-commit in Baseline Configuration but says nothing about version skew. No other rule or skill covers this. Complementary to `skills/python-development/` which handles Python tooling specifics.
- **Recommended delegation**: context-engineer (review scope and wording to avoid bloating the path-scoped rule)
- **Suggested artifact path**: `rules/swe/coding-style.md` (update)

---

### Proposal 3: ADR Discovery Before Convention Change

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `skills-conformance/LEARNINGS.md` § FM-01 "Recommended ADR supersession without first reading the ADR record"; corrective rule stated: "Before any recommendation that would supersede an ADR, change a documented convention, or churn ≥3 skills/files for 'standards alignment', grep `.ai-state/decisions/` for the topic and read every matching ADR first"
- **Description**: An update to `rules/swe/adr-conventions.md` adding a "Discovery Before Change" sub-section to the existing Discovery Protocol. The update states: before any recommendation that would supersede an ADR, change a documented convention, or churn ≥3 skills/files for alignment purposes, perform ADR discovery first — grep the DECISIONS_INDEX for the topic and read every matching ADR. Reasoning from skill structure, external spec text, or current file state is a fallback, not a substitute for the decision record. The ADR is the highest-evidence input for decisions already made. The sub-section names the specific failure mode: assuming "no relevant ADR objects" is an assumption that must be explicitly surfaced and verified, per the Surface Assumptions behavioral-contract requirement.
- **Rationale**: The skills-conformance campaign documented a concrete, costly instance: a main agent recommended superseding 4 ADRs and migrating ~25 files without first reading those ADRs, because the assumption "no relevant ADR objects" was never surfaced. Reading ADR-139 revealed a well-reasoned binary decision rule (compiles/runs? → contexts; explains concept? → references) that the external spec was silent on. The corrective is not covered by the existing `adr-conventions.md` Discovery Protocol (which is passive/lookup-oriented) or the `agent-behavioral-contract.md` (which names Surface Assumptions generally but not this specific pre-check). This update closes the gap declaratively in the rule most likely to be loaded during ADR work. P1 (not P0) because the Surface Assumptions contract already nominally covers it; this is a targeted, topical clarification.
- **Estimated scope**: `rules/swe/adr-conventions.md` update — approximately 8-10 lines added as a new "Discovery Before Change" clause within the existing Discovery Protocol section
- **Overlap check**: `rules/swe/adr-conventions.md` § Discovery Protocol partially overlaps (covers how to discover ADRs) but does not say "you must do this before recommending a change." `rules/swe/agent-behavioral-contract.md` Surface Assumptions nominally applies but is too general to reliably trigger this specific check. No skill covers this.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/adr-conventions.md` (update)

---

### Proposal 4: Context-Engineer Multi-Skill Dispatch Operational Patterns

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `skills-conformance/LEARNINGS.md` § Wave 1 retrospective (both context-engineers ran out of turn budget), Wave 2 retrospective (subagent Write to `.ai-work/` is blocked), PLAYBOOK fixes applied in Waves 2-4; `skills-coherence-pass/LEARNINGS.md` (context-engineer crash on fresh-bang)
- **Description**: An update to `skills/software-planning/references/coordination-details.md` adding a "Context-Engineer Multi-Skill Audit Dispatch" sub-section. The update documents three operational patterns learned from the skills-conformance campaign: (1) **Skeleton-first return contract** — when dispatching a context-engineer to audit N skills, instruct it to return the full audit report INLINE (below a `---` separator in the final reply) because subagent Write to `.ai-work/` is blocked in Claude Code; the orchestrator persists to disk; (2) **Turn-budget management** — initialize report skeleton (all rows as "pending") immediately on dispatch; fill row-by-row after each skill; stop at ~60% turn budget if behind and return the partial report with named pending items; (3) **Audit-then-edit-one-pass** — read the SKILL.md, read each reference file header (use `head -3` not full Read for headers), batch all edits for one skill before moving to the next; defer non-blocking WARNs to the report as open items rather than spending tool calls on them. These patterns prevent the "missing report" failure mode observed in Wave 1 (both context-engineers hit budget on the report-writing pass).
- **Rationale**: The skills-conformance campaign ran context-engineer agents across 56 skills in 4 waves. Wave 1 produced zero reports because agents hit turn budget before writing them. The root cause was the combination of a many-roundtrips-per-skill pattern and the Write-block constraint. The three patterns above, applied in Waves 2-4, produced clean handoffs. This is procedural expertise (how to operate the context-engineer in a multi-skill dispatch) that belongs in a skill reference rather than a rule. The coordination-details.md is the canonical reference for per-agent delegation patterns and already covers parallel execution, fragment files, and the return contract. P1 because the skill-audit workflow is not on the critical path for every pipeline, but will recur whenever the ecosystem undergoes a coherence pass.
- **Estimated scope**: `skills/software-planning/references/coordination-details.md` update — approximately 25-30 lines as a new sub-section under the Delegation Checklists section
- **Overlap check**: `skills/software-planning/references/coordination-details.md` already covers the return contract ("a terse summary + artifact path") and the Write-block limitation is in `CLAUDE.md#known-claude-code-limitations`. Neither covers the multi-skill audit dispatch pattern specifically. No other skill or rule covers this.
- **Recommended delegation**: context-engineer (review scope) then implementer (content write)
- **Suggested artifact path**: `skills/software-planning/references/coordination-details.md` (update)

---

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 — Agent-Loaded Surface Injection Guard | context-engineer | New rule; load rule-crafting skill; path-scope to agent-authored surfaces to avoid always-loaded budget |
| 2 — Pre-commit Linter Version Skew Warning | context-engineer | Update existing coding-style.md; scope review important — keep addition under 20 lines; load rule-crafting skill |
| 3 — ADR Discovery Before Convention Change | context-engineer | Update adr-conventions.md Discovery Protocol section; single clause addition; load rule-crafting skill |
| 4 — Context-Engineer Multi-Skill Dispatch Patterns | context-engineer (review scope) then implementer (content) | Update coordination-details.md; context-engineer validates placement and scope, implementer writes the sub-section |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 4 pending proposals.
- After approval, invoke `context-engineer` for Proposals 1, 2, 3 (rule creation/update) and for scope review of Proposal 4 before implementer execution.
- Both P0 proposals (1 and 2) should be prioritized — Proposal 1 can crash agents at activation; Proposal 2 causes infinite commit-abort loops.
- Re-run `/skill-genesis` after the next Standard/Full pipeline completes if `LEARNINGS.md` accumulates further items.

## Appendix — Items Skipped and Why

| # | Item | Reason for Skip |
|---|---|---|
| dec-draft- citation skew | `rules/swe/adr-conventions.md` § Linking to ADRs already covers this explicitly ("cite by its `dec-draft-<hash>` id") |
| PROMPT vs CODE gate distinction | `rules/swe/gate-liveness.md` § Two gate kinds, two proofs already covers this with a clear table |
| skills/README.md staleness pattern | Operational maintenance; sentinel already flags as I2/EC02; no new artifact warranted |
| Always-loaded budget at 0.9% | Sentinel already recommends specific fix (extract Cross-Agent Skill Conventions); context-engineer task, not a new artifact |
| Tier 1 always arbitrates; WIP.md is a cache | Architectural decision in dec-248; implemented in reconcile_pipeline_state.py; already operational |
| fire-but-annotate for mechanical gates | Domain-specific to readiness gate; not broadly reusable pattern outside that context |
| deferred production_gate must be bare | Narrow Praxion-internal registry code convention; transient |
| Filename-chronological sort | Already implied by naming conventions; marginal value as explicit rule |
| pyproject.toml runtime vs dev dep placement | Basic Python project knowledge in python-development skill |
| Subagent Write to .ai-work/ is blocked | Already in CLAUDE.md Known Limitations; procedural complement captured in Proposal 4 |
