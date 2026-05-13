# SPEC: Multi-Language Support — Polyglot Skill Architecture

**Task slug**: `multi-language-support`
**Feature**: Extend Praxion from Python-only to full-stack TypeScript/Node/React/Vue via the polyglot skill pattern
**Tier**: Full
**Pipeline branch**: `worktree-multi-language-support`
**Start date**: 2026-05-11
**End date**: 2026-05-11
**Status**: Shipped — verifier PASS-WITH-WARNINGS (step-21); 2 catalog-text WARNs fixed post-verify; ADRs finalized as dec-135..dec-140 at merge-to-main

## Feature Summary

Extended Praxion from Python-only to a polyglot ecosystem covering Node.js, TypeScript, React 19, and Vue 3 by formalizing the **language-agnostic skill body + `contexts/<language|framework>.md`** pattern. The pipeline shipped: two new skills (`node-prj-mgmt`, `typescript-development`), eight new context files added to seven existing skills, two new reference files, one path-scoped rule (`rules/swe/coding-style-typescript.md`), one SKILL.md body restructure (`architectural-fitness-functions`), and one housekeeping migration (mcp-crafting `references/python-resources.md` → `contexts/python.md`). All new artifacts load on demand; the always-loaded surface (89,265 bytes baseline → 89,565 bytes post-pipeline, delta +300 bytes) is within the declared +2,000-byte tolerance. Six ADR drafts authored by the systems-architect formalize the key decisions.

## Acceptance Criteria

- [ ] **AC-01**: A formal **Polyglot Skill Template** specification exists as an ADR documenting (a) `references/` vs `contexts/` selection rules, (b) file-naming conventions, (c) SKILL.md body discipline, (d) the Language Contexts table format, and (e) the extension protocol for adding a new language.
- [ ] **AC-02**: A formal **Frontend Framework Nesting** specification exists as an ADR documenting where framework contexts live, the activation/redirect mechanic, and the composition model with the base language context.
- [ ] **AC-03**: An **Angular Exclusion** ADR records the durable rationale for excluding Angular from first-class `contexts/` coverage and names the conditions under which the decision should be revisited.
- [ ] **AC-04**: All five open questions raised by Phase 1b are answered in `SYSTEMS_PLAN.md` with rationale, each decision either (a) referenced to an ADR or (b) noted as a small housekeeping/scope-only choice.
- [ ] **AC-05**: The cross-skill **Zod v3 (MCP-crafting) vs Zod v4 (OpenAI Agents SDK)** version split is given a single canonical home and a systematic surfacing protocol for future cross-skill version conflicts.
- [ ] **AC-06**: A complete **artifact creation order** (with dependencies) is provided to the implementation planner, listing every new file the implementer must create and every existing file the implementer must touch.
- [ ] **AC-07**: The path-scoped rule `rules/swe/coding-style-typescript.md` is specified with mandatory frontmatter `paths: ["**/*.ts", "**/*.tsx", "**/*.mts", "**/*.cts"]`; its absence from the always-loaded surface is verified by the implementation planner before merge.
- [ ] **AC-08**: Token budget math is reconfirmed — no new always-loaded content is introduced by this pipeline; the rule diet remains explicitly OUT OF SCOPE.
- [ ] **AC-09**: `.ai-state/DESIGN.md` gains a new component row recording the polyglot skill plane; `docs/architecture.md` is updated to point developers at the new TypeScript surfaces once the implementer builds them (Built status only).

## Traceability Matrix

| AC | Description | Implementing step(s) | Verification | Status |
|----|-------------|---------------------|--------------|--------|
| AC-01 | Polyglot Skill Template ADR on disk | Pre-condition (architect Phase 2); `dec-139` | ADR draft exists at `.ai-state/decisions/drafts/…polyglot-skill-template.md`; `python3 scripts/finalize_adrs.py --all --dry-run` exits 0; step-19 PASS | PASS |
| AC-02 | Frontend Framework Nesting ADR on disk | Pre-condition (architect Phase 2); `dec-137` | ADR draft exists at `.ai-state/decisions/drafts/…frontend-framework-nesting.md`; finalize dry-run exits 0; step-19 PASS | PASS |
| AC-03 | Angular Exclusion ADR on disk | Pre-condition (architect Phase 2); `dec-135` | ADR draft exists at `.ai-state/decisions/drafts/…angular-exclusion-from-contexts.md`; finalize dry-run exits 0; step-19 PASS | PASS |
| AC-04 | All 5 open questions answered in SYSTEMS_PLAN.md | Pre-condition (architect Phase 2 + implementation-planner) | SYSTEMS_PLAN.md §Decisions on Open Questions section present; verified by implementation-planner before plan approval | PASS |
| AC-05 | Zod v3/v4 split has canonical home in `node-prj-mgmt` | step-01, step-13 | `grep "overrides" skills/node-prj-mgmt/contexts/typescript.md` returns match (step-01 done-when); step-13 adds cross-ref to `agentic-sdks/contexts/openai-agents-typescript.md`; `dec-140` ADR documents the decision; step-19 PASS | PASS |
| AC-06 | Complete artifact creation order in IMPLEMENTATION_PLAN.md | Implementation plan itself (steps 01–21 with dependency graph and parallel groups A–F) | `IMPLEMENTATION_PLAN.md` exists with 21 steps and parallel group table; deliverable is the planning document itself | PASS |
| AC-07 | `coding-style-typescript.md` has required `paths:` frontmatter; not always-loaded | step-12 | `grep -q "^paths:" rules/swe/coding-style-typescript.md` exits 0; step-18 measured always-loaded surface — rule excluded; step-18 verdict: **AC-07 PASS** | PASS |
| AC-08 | Token budget unchanged; no new always-loaded surface | step-18 (measurement), step-14/15 (catalog updates only) | step-18: baseline 89,265 bytes → post-pipeline 89,565 bytes; delta +300 bytes; tolerance +2,000 bytes; step-18 verdict: **AC-08 PASS** | PASS |
| AC-09 | `.ai-state/DESIGN.md` + `docs/architecture.md` updated with polyglot skill plane | step-16, step-17 | step-16 adds polyglot skill plane component row to `.ai-state/DESIGN.md`; step-17 adds TypeScript surfaces (Built status) to `docs/architecture.md`; step-19 full pytest + dogfood PASS | PASS |

## Decisions Made

Six ADR drafts authored by the systems-architect in Phase 2 were promoted to stable identifiers `dec-135` through `dec-140` at merge-to-main by `scripts/finalize_adrs.py` (step-19's dry-run had confirmed all 6 parse cleanly).

| ADR | Title | Category | Key Decision |
|----------|-------|----------|--------------|
| `dec-139` | Polyglot skill template — references/ vs contexts/ separation with extension protocol | architectural | `contexts/` for runnable mechanics; `references/` for language-agnostic concepts; Language Contexts table is the canonical extension surface |
| `dec-137` | Frontend framework contexts nest inside typescript-development, not as sibling skills | architectural | Framework contexts live under `typescript-development/contexts/<framework>.md`; activation is redirect-based from the base TypeScript context |
| `dec-135` | Angular intentionally excluded from first-class typescript-development contexts | architectural | Angular excluded from `contexts/` because it ships its own CLI toolchain and design philosophy incompatible with the Biome/Vitest defaults; revisit if 3+ Praxion-managed Angular projects emerge |
| `dec-140` | Zod v3/v4 cross-skill version split — canonical home in node-prj-mgmt | implementation | Zod coexistence gotcha (pnpm `overrides` pattern) lives in `node-prj-mgmt/contexts/typescript.md`; cross-references from `mcp-crafting` and `agentic-sdks` contexts point back |
| `dec-138` | MCP TypeScript SDK v2 promotion — trigger-based review, not date-based | behavioral | SDK v2 promotion criteria: v2 reaches stable AND at least one Praxion-managed project uses it in production; no calendar date trigger |
| `dec-136` | Biome / ESLint coexistence in typescript-development — one context file, conditional guidance | configuration | Single `contexts/typescript.md` file with a top-level conditional decision rule (Biome v2 default for greenfield; ESLint v9 for framework path); framework contexts override explicitly when they diverge |

### Additional implementation-planner decisions recorded in LEARNINGS.md

- **Step ordering for mcp-crafting migration**: step-05 (migrate python-resources.md) runs before step-06 (create mcp-crafting/contexts/typescript.md) because the Zod cross-link requires step-01's node-prj-mgmt to exist first. Broken links at commit time violate known-good-increment discipline.
- **No `dec-draft-*` IDs embedded in shipped artifacts**: SKILL.md files and context files reference architectural decisions in prose only (`rules/swe/shipped-artifact-isolation.md` constraint). Draft IDs dangle when the plugin lands in another project.
- **No new ADR authoring steps in the plan**: The 6 ADR drafts are Phase 2 outputs; including re-authoring steps would duplicate prior-phase work.
- **Group C step ordering — step-07 depends on step-02**: `dependency-cruiser` cross-link in the architectural-fitness-functions restructure requires `typescript-development/contexts/typescript.md` to exist first.

## Known Issues / Tech Debt

No new technical debt introduced by this pipeline. All implementations are on-demand artifacts (Markdown files); no production code was added or modified. Pre-existing tech debt entries in `.ai-state/TECH_DEBT_LEDGER.md` (td-002 through td-021) are unrelated to this pipeline.

## Implementation Summary

**Total new files created**: 13
- `skills/node-prj-mgmt/SKILL.md`
- `skills/node-prj-mgmt/contexts/typescript.md`
- `skills/typescript-development/SKILL.md`
- `skills/typescript-development/contexts/typescript.md`
- `skills/typescript-development/contexts/react.md`
- `skills/typescript-development/contexts/vue.md`
- `skills/mcp-crafting/contexts/typescript.md`
- `skills/deployment/contexts/typescript.md`
- `skills/software-planning/contexts/typescript.md`
- `skills/test-coverage/references/typescript.md`
- `skills/agent-evals/references/typescript.md`
- `rules/swe/coding-style-typescript.md`
- `.ai-state/specs/SPEC_multi-language-support_2026-05-11.md` (this file)

**Existing files modified**: 10
- `skills/mcp-crafting/SKILL.md` (removed python-resources.md satellite ref; contexts/python.md already in Language Contexts table)
- `skills/mcp-crafting/contexts/python.md` (merged content from references/python-resources.md; date-stale claims softened)
- `skills/mcp-crafting/references/resources.md` (stale cross-refs cleaned up)
- `skills/architectural-fitness-functions/SKILL.md` (body restructured to language-agnostic; Python content extracted to contexts/python.md)
- `skills/agentic-sdks/contexts/openai-agents-typescript.md` (Zod cross-ref paragraph added to Common Pitfalls)
- `skills/README.md` (new skills cataloged; polyglot expansion note added)
- `rules/README.md` (new path-scoped rule entry added)
- `.ai-state/DESIGN.md` (polyglot skill plane component row added)
- `docs/architecture.md` (TypeScript surfaces added with Built status)
- Deleted in this pipeline: skills/mcp-crafting/references/python-resources.md — content merged into `skills/mcp-crafting/contexts/python.md`

**Parallel execution**: 6 parallel groups (A–F); Group C had 7 concurrent implementers on disjoint file sets. Maximum wall clock savings achieved within the pipeline's dependency graph.

**Test results**: All step-18 (AC-07 + AC-08) and step-19 (dogfood: pytest + finalize dry-run + meta-citation + canonical-block drift) checks PASS. See `TEST_RESULTS.md` for full evidence.
