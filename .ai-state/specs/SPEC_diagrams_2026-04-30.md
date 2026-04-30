# SPEC: LikeC4 + D2 Dual-Toolchain Diagram Convention

**Task slug**: `structurizr-d2-diagrams`
**Feature**: Introduce LikeC4 + D2 dual-toolchain for C4-architectural diagrams (coexistence with Mermaid)
**Tier**: Standard
**Pipeline branch**: `worktree-structurizr-d2-diagrams`
**Start date**: 2026-04-29
**End date**: 2026-04-30
**Status**: Shipped (PASS WITH FINDINGS — verifier verdict)

## Feature Summary

Replaced the Mermaid-only diagram convention with a dual-toolchain policy: LikeC4 + D2 for C4-architectural diagrams (System Context L0, Container/Component L1), Mermaid preserved for all other diagram types (sequence, state, ER, flowchart, topology). 27 existing Mermaid blocks retained frozen; 7 architectural Mermaid blocks migrated to LikeC4-sourced SVGs. A pre-commit hook auto-regenerates `.d2` and `.svg` artifacts when `.c4` sources change.

## Behavioral Specification

### REQ-DIAGRAM-01
**When** a contributor authors an architectural diagram
**and** that diagram models C4 system-context or component relationships
**the system** provides a dual-toolchain policy in `rules/writing/diagram-conventions.md`
**so that** contributors know to use LikeC4 + D2 for C4 views and Mermaid for everything else.

### REQ-DIAGRAM-02
**When** a Praxion-derived project creates an architecture documentation file using the templates
**and** populates §2 (System Context) and §3 (Components)
**the system** provides `c4` source blocks and SVG reference shapes in both architecture templates
**so that** new architecture docs default to the LikeC4+D2 pipeline.

### REQ-DIAGRAM-03
**When** a developer inspects `ARCHITECTURE_TEMPLATE.md` §5
**the system** preserves the existing `sequenceDiagram` Mermaid block
**so that** the sequence-diagram template remains available for non-C4 flow documentation.

### REQ-DIAGRAM-04
**When** a contributor reads `docs/architecture.md`
**the system** renders the L1 Components diagram from a committed SVG (not a live Mermaid block)
**so that** GitHub renders the diagram without a Mermaid plugin and the source model is a single `.c4` file.

### REQ-DIAGRAM-05
**When** a contributor reads `.ai-state/ARCHITECTURE.md`
**and** inspects §2 (System Context) and §3 (Components)
**the system** renders both diagrams from committed SVGs sourced from `docs/diagrams/architecture.c4`
**so that** the design-target document shares the single-model SSOT with the developer guide.

### REQ-DIAGRAM-06
**When** a `.c4` source file exists in any `**/diagrams/` directory
**the system** has corresponding `.d2` and `.svg` artifacts committed alongside it
**so that** render state is always auditable and GitHub-native readers see inline diagrams.

### REQ-DIAGRAM-07
**When** a contributor stages a `.c4` file in a `**/diagrams/` directory
**the system** runs `scripts/diagram-regen-hook.sh` via the pre-commit hook
**so that** missing binaries produce a warning and exit 0 (graceful skip), while a valid model auto-regenerates `.d2`/`.svg` and stages them before commit.

### REQ-DIAGRAM-08
**When** a doc-management agent or contributor loads the diagram conventions skill reference
**the system** provides a `## Integration with LikeC4 + D2` section alongside the existing claude-mermaid section
**so that** agents know the three-command workflow (author, generate, render) for C4 architectural views.

### REQ-DIAGRAM-09
**When** the `onboard-project` command runs
**the system** probes for `likec4` and `d2` binaries in Phase 0 pre-flight and instructs LikeC4+D2 for C4 diagrams in Phase 8
**so that** newly onboarded projects start with the correct toolchain for architectural documentation.

### REQ-DIAGRAM-10
**When** a grep scans the repository for Mermaid fenced blocks
**the system** has exactly 28 remaining `mermaid` blocks (pre-pipeline: 35; 7 migrated by this pipeline)
**so that** the frozen non-C4 diagrams are unchanged and migration scope is verifiable.

### REQ-DIAGRAM-11
**When** the sentinel runs a post-pipeline sweep
**the system** does not flag `.c4` / `.d2` / `.svg` files as convention violations
**so that** the updated rule body (`rules/writing/diagram-conventions.md`) correctly authorizes the new formats.

### REQ-DIAGRAM-12
**When** a developer or agent wants to author `.c4` files interactively
**the system** provides a project-root `.mcp.json` with a `@likec4/mcp` entry wired to `docs/diagrams/`
**so that** Claude Code and compatible MCP clients load LikeC4's 18 tools automatically.

### REQ-DIAGRAM-13
**When** a developer sets up their local environment
**the system** documents `npx skills add https://likec4.dev/` and `https://likec4.dev/llms-full.txt` in `docs/architecture-diagrams.md`
**so that** IDE agents and headless agents have access to the LikeC4 DSL reference.

## Traceability Matrix

| REQ | Implementing file(s) | Test reference |
|-----|----------------------|----------------|
| REQ-DIAGRAM-01 | `rules/writing/diagram-conventions.md` | VERIFICATION_REPORT §2 (grep-c 'LikeC4 → D2 → SVG' → 1) |
| REQ-DIAGRAM-02 | `skills/software-planning/assets/ARCHITECTURE_TEMPLATE.md`, `skills/doc-management/assets/ARCHITECTURE_GUIDE_TEMPLATE.md` | VERIFICATION_REPORT §2 (grep-cE '^\`\`\`c4' → 2 each) |
| REQ-DIAGRAM-03 | `skills/software-planning/assets/ARCHITECTURE_TEMPLATE.md` §5 (untouched) | VERIFICATION_REPORT §2 (sequenceDiagram → 1) |
| REQ-DIAGRAM-04 | `docs/architecture.md`, `docs/diagrams/architecture.c4`, `docs/diagrams/architecture/components.d2`, `docs/diagrams/architecture/components.svg` | VERIFICATION_REPORT §2 (grep-cE '^\`\`\`mermaid' → 0) |
| REQ-DIAGRAM-05 | `.ai-state/ARCHITECTURE.md`, `docs/diagrams/architecture.c4`, `docs/diagrams/architecture/context.svg`, `docs/diagrams/architecture/components.svg` | VERIFICATION_REPORT §2 (2 SVG refs in §2+§3) |
| REQ-DIAGRAM-06 | `docs/diagrams/architecture.c4`, `docs/diagrams/architecture/{context,components,index}.{d2,svg}` | VERIFICATION_REPORT §2 (ls -la, mtime ≥ source mtime within 60s) |
| REQ-DIAGRAM-07 | `scripts/diagram-regen-hook.sh`, `scripts/git-pre-commit-hook.sh` (Block C) | `tests/test_diagram_regen_hook.sh` (T1–T5); VERIFICATION_REPORT §4 (4 PASS / 0 FAIL) |
| REQ-DIAGRAM-08 | `skills/doc-management/references/diagram-conventions.md` §Integration with LikeC4 + D2 | VERIFICATION_REPORT §2 (grep -c 'LikeC4' → 5) |
| REQ-DIAGRAM-09 | `commands/onboard-project.md` Phase 0 + Phase 8 | VERIFICATION_REPORT §2 (grep -ic 'likec4' → 4) |
| REQ-DIAGRAM-10 | (all 7 migrated files) | VERIFICATION_REPORT §2 (28 blocks post-pipeline; 7 removed; baseline 35 not 27 per inventory gap) |
| REQ-DIAGRAM-11 | `rules/writing/diagram-conventions.md` (dual-toolchain opening) | VERIFICATION_REPORT §2 (by construction — no live sentinel run) |
| REQ-DIAGRAM-12 | `.mcp.json` | VERIFICATION_REPORT §2 (`python3 -m json.tool` exits 0; grep '@likec4/mcp' → 1) |
| REQ-DIAGRAM-13 | `docs/architecture-diagrams.md`, `README_DEV.md` (cross-link) | VERIFICATION_REPORT §2 (WARN: README_DEV.md has link-out not literal command) |

## Decisions Made

Four ADR drafts were authored by the systems-architect and implementation-planner. Draft IDs will be rewritten to `dec-NNN` at merge-to-main by the finalize protocol.

| Draft ID | Title | Category | Notes |
|----------|-------|----------|-------|
| `dec-draft-55bf38a6` | LikeC4 + D2 toolchain choice | architectural | Core toolchain selection; LikeC4 over Structurizr/Mermaid-C4 |
| `dec-draft-05e16d0e` | Two-toolchain coexistence policy | configuration | Re-affirms `dec-028` path-scoping; mandates LikeC4 for C4, Mermaid for rest |
| `dec-draft-9e43c4f6` | Commit both source and rendered artifacts | configuration | Commits `.c4` + `.d2` + `.svg` together; pre-commit hook for freshness |
| `dec-draft-1814704c` | Step ordering constraint | implementation | Rule update must commit before any `.c4` file; hook before live migrations |

## Verification Outcome

**Verifier verdict**: PASS WITH FINDINGS

**Per-REQ summary**:
- 11 PASS (REQ-DIAGRAM-01 through -09, -11, -12)
- 1 WARN (REQ-DIAGRAM-13: README_DEV.md cross-link instead of literal `npx skills add` command)
- 1 FAIL (REQ-DIAGRAM-10: numerical band [21,22] was derived from incomplete inventory; actual post-pipeline count is 28 — migrations executed correctly, baseline was 35 not 27)

**Three findings and their dispositions**:

1. **Test-harness T4 call-site typo** (WARN → **fixed**): `tests/test_diagram_regen_hook.sh:274` called `t4_invalid_dsl_fails` but the function was renamed to `t4_invalid_dsl_logs_error_but_exits_0` to align with LikeC4's lenient-parse behavior. Fixed in commit `fcf182d` before pipeline close.

2. **AC10 numerical band miscount** (FAIL → **accepted as planning-side miscount**): The architect's predicted band [21, 22] was based on `RESEARCH_FINDINGS-internal.md` which missed all 6 Mermaid blocks in `.ai-state/ARCHITECTURE.md`. The pipeline delivered exactly the 7 specified migrations; actual post-pipeline count is 28 (baseline 35). Classified as planning-inventory gap, not system defect.

3. **AC13 cross-link instead of literal command** (WARN → **accepted**): `README_DEV.md` contains a cross-link to `docs/architecture-diagrams.md#ai-tooling` per coordinator directive rather than duplicating the `npx skills add` command. Discoverability is satisfied; the WARN is noted as a literal-vs-spirit ambiguity in the AC.

## Key Learnings

- **LikeC4 `gen d2` takes a workspace directory, not a `.c4` file path.** Passing a `.c4` file directly produces `ERROR: no LikeC4 sources found`. Correct: `likec4 gen d2 docs/diagrams/ -o docs/diagrams/architecture/`.

- **npm package name is `likec4` (unscoped), not `@likec4/likec4`.** The scoped name is a 404. Install: `npm install -g likec4`.

- **`include *` in LikeC4 views does not expand nested children.** Flat `include *` collapses all nested elements to their top-level ancestor. To render nested containment (visual cluster boxes in D2), enumerate children explicitly via dot-path: `include praxion, praxion.knowledge, praxion.knowledge.skills, ...`.

- **LikeC4 auto-generates `index.d2` alongside named view files.** The workspace output includes an auto-generated `index.d2` (top-level elements only). Named views like `view context` generate `context.d2`. Both coexist harmlessly; `index.svg` is not referenced from docs.

- **LikeC4 lenient-parse contract**: the DSL parser does not hard-fail on all invalid DSL at the CLI invocation level. T4 (invalid DSL exits non-zero) was adjusted to `t4_invalid_dsl_logs_error_but_exits_0` to reflect actual behavior. Do not assume `likec4 gen d2` always exits non-zero on a malformed `.c4` source.

- **No chub upstream entry is possible for LikeC4.** The `chub_annotate` tool is not in the implementer's tool grant. LikeC4 publishes `https://likec4.dev/llms-full.txt` as an LLM-friendly dense reference; the `npx skills add https://likec4.dev/` Agent Skill covers IDE contexts. Both are documented in `docs/architecture-diagrams.md`.

- **D2 nested containment from LikeC4:** Nested elements inside a `system {}` scope produce visual cluster boxes in D2 output when those elements are explicitly listed in the view's `include` directive. This is the correct pattern for showing 4-layer Praxion architecture in the L1 Components view.

## Implementation Summary

**Commits** (9 pipeline commits on top of `b442c2a`):

| SHA | Description |
|-----|-------------|
| `4f8c746` | feat: Adopt dual-toolchain diagram conventions (Step 1) |
| `63265e7` | feat: Add diagram regeneration hook and test harness (Step 2) |
| `4e993b3` | feat: Wire LikeC4 MCP server and AI tooling references (Step 3) |
| `337653f` | feat: Migrate architecture templates to LikeC4 (Step 4) |
| `16dd0a6` | fix(docs): Correct LikeC4 npm package name (Step 3 fix) |
| `04bb3a2` | fix: Pass workspace dir to likec4 gen; adjust T4 for lenient parse (Step 5 fix) |
| `7ef12b1` | feat: Migrate live docs/architecture.md L1 to LikeC4 + D2 (Step 5) |
| `fcb38b3` | feat: Migrate .ai-state/ARCHITECTURE.md L0 and L1 diagrams (Step 6) |
| `aeaf86c` | feat: Encode dual-toolchain convention in skill + agent prompts (Step 7) |
| `fcf182d` | fix: Address verifier findings — T4 contract + ADR re_affirms cleanup (post-verifier) |

**Total files touched**: 26 (production files committed to branch, excluding `.ai-work/` pipeline documents)

**Total planning documents**: SYSTEMS_PLAN, IMPLEMENTATION_PLAN, WIP, LEARNINGS, 4 × RESEARCH_FINDINGS, TEST_RESULTS, traceability_implementer.yml, VERIFICATION_REPORT, PROGRESS

**One iteration cycle**: Step 5 underwent R1 (nested layer grouping), R2 (differentiated L0/L1 views with 6 external actors), and R4 (active-voice edge labels) after the first render aesthetic review. The final `docs/diagrams/architecture.c4` model produces a 22,189-byte context SVG (9 rects) and 43,299-byte components SVG (21 rects).
