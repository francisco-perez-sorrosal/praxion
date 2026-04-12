# Architecture Documentation

Dual-audience living document methodology for architecture documentation. Back to [SKILL.md](../SKILL.md).

## Purpose

Architecture documentation serves two distinct audiences with different needs. Rather than compromising with a single document, the pipeline maintains two purpose-built documents that share the same 8-section structure but differ in framing, content policy, and validation:

- **`.ai-state/ARCHITECTURE.md`** — the architect-facing **design target**. Abstracts above concrete code to define the space of valid implementations. Answers: "What should X look like? Why?"
- **`docs/architecture.md`** — the developer-facing **navigation guide**. Every name and path is verified against the codebase. Answers: "What is X? Where is it?"

The developer guide is derived from the architect doc — it is a code-verified subset of the architect doc's Built components. The architect doc defines the design space; the developer guide captures what actually exists on disk.

## Two Documents, One Structure

Both documents use the same 8 sections (Overview, System Context, Components, Interfaces, Data Flow, Dependencies, Constraints, Decisions). The differences are in framing and content policy:

| Dimension | `.ai-state/ARCHITECTURE.md` | `docs/architecture.md` |
|-----------|----------------------------|------------------------|
| **Primary audience** | Architects designing/extending the system | Developers navigating the codebase |
| **Core question** | "What should X look like? Why?" | "What is X? Where is it?" |
| **Time orientation** | Design target (partial future) | Present-tense (verified against code) |
| **Trust model** | High depth, accuracy abstracted from codebase to encompass multiple implementations | High accuracy, code-verified |
| **Source of truth** | Evolves: spec → self + code → self + new research | Derived from architect doc + verified against code |
| **Components table** | Includes `Status` column (Designed / Built / Planned / Deprecated) | No Status column — only what exists on disk |
| **Overview metadata** | `Source stage` (tracks which pipeline phase last updated) | `Last verified against code` (YYYY-MM-DD) |
| **Planned items** | Allowed (marked with Status) | Not allowed |
| **File paths** | Illustrative (may reference planned paths) | Must resolve to existing files |
| **Validation model** | Design coherence (internal consistency, design accounts for reality) | Code verification (every name and path resolves on disk) |

## Document Lifecycle

### Architect Doc (`.ai-state/ARCHITECTURE.md`)

**Creation:** The **systems-architect** creates the document from the template (`skills/software-planning/assets/ARCHITECTURE_TEMPLATE.md`) during Phase 5 when the pipeline is Standard or Full tier. It fills in:
- Section 1 (Overview): quick-facts table with Source stage, summary
- Section 2 (System Context): L0 boundary diagram and external actors
- Section 3 (Components): skeleton with known components, Status column populated
- Section 5 (Data Flow): key scenario flows
- Section 7 (Constraints): known limitations and quality attributes
- Section 8 (Decisions): cross-references to architecture-related ADRs

Sections 4 (Interfaces) and 6 (Dependencies) are left with template guidance for the implementer to fill as-built.

Skip creation for trivially simple projects (single module, no external dependencies).

**Updates:** The **implementer** updates the architect doc after completing any step annotated with `[Architecture]` or that creates/modifies structural files (step 7.6):

| Change Type | Sections Updated |
|-------------|-----------------|
| New module/package created | 3 (Components: add to table with Status, update L1 diagram) |
| Interface/API changes | 4 (Interfaces: update contract table) |
| Data model changes | 5 (Data Flow: update flow descriptions) |
| New dependency added/removed | 6 (Dependencies: update table) |
| ADR created | 8 (Decisions: add cross-reference row) |

If `.ai-state/ARCHITECTURE.md` does not exist, the implementer skips — the systems-architect creates it.

**Validation:** The **verifier** checks design coherence during Phase 8:
- Components referenced in Data Flow (Section 5) appear in Components (Section 3)
- Status column is present with valid values
- ADR IDs in Section 8 correspond to actual files in `.ai-state/decisions/`
- File paths, when present, are advisory — WARN if many are broken, not FAIL
- Internal consistency: component names are used consistently across sections

A stale architect doc is a WARN, not a FAIL — it's advisory, not a gate.

**Auditing:** The **sentinel** checks design coherence with four checks:
- **AC01**: Architecture doc exists when project has 3+ interacting components
- **AC02**: Design coherence — component names are internally consistent and the design accounts for existing modules (abstract names allowed)
- **AC03**: File paths, when present, are illustrative — WARN if >50% are broken, PASS otherwise
- **AC04**: ADR cross-references in Section 8 are valid

### Developer Guide (`docs/architecture.md`)

**Creation:** The **systems-architect** creates the developer guide alongside the architect doc during Phase 5, using the template at `skills/doc-management/assets/ARCHITECTURE_GUIDE_TEMPLATE.md`. Content is derived from the architect doc but filtered:
- Only components with Status `Built` are included
- All component names and file paths are verified against the filesystem
- Present-tense framing throughout — no future tense, no "Planned" or "Designed" items
- "Last verified against code" date is set

Skip creation when the architect doc is skipped (trivially simple projects).

**Updates:** The **implementer** propagates changes to the developer guide after updating the architect doc (step 7.7):
- Only fires when step 7.6 was done AND `docs/architecture.md` exists
- Filters to Built components only — verify each with Glob/ls
- Uses present tense ("handles" not "will handle")
- Verifies all file paths against the filesystem
- No Status column

If `docs/architecture.md` does not exist, the implementer skips — the systems-architect creates it.

**Maintenance:** The **doc-engineer** maintains the developer guide at pipeline checkpoints by verifying content against the filesystem (code-verified accuracy). This is independent of the implementer's step 7.7 — it's a periodic freshness check.

**Validation:** The **verifier** checks code accuracy during Phase 9:
- Every component name in Section 3 matches an actual module/directory name on disk
- Every file path in the component table resolves to an existing file
- No Planned/Designed items present
- "Last verified" date is within the pipeline's timeframe
- Cross-consistency: every component in the developer guide appears in the architect doc

Skip Phase 9 if `docs/architecture.md` does not exist.

**Auditing:** The **sentinel** checks code accuracy with five checks:
- **AC05**: `docs/architecture.md` exists when `.ai-state/ARCHITECTURE.md` exists
- **AC06**: Every component name in Section 3 matches an actual module/directory name on disk
- **AC07**: Every file path in the component table resolves to an existing file
- **AC08**: No Status column or Planned/Designed items present
- **AC09**: Cross-consistency — every component in `docs/architecture.md` also appears in `.ai-state/ARCHITECTURE.md` (subset relationship)

## Section Ownership Model

Each agent owns specific sections to prevent conflicts:

| Section | `.ai-state/ARCHITECTURE.md` Owner(s) | `docs/architecture.md` Owner(s) | Update Trigger |
|---------|--------------------------------------|----------------------------------|----------------|
| 1. Overview | systems-architect | systems-architect, doc-engineer | Architecture changes |
| 2. System Context | systems-architect | systems-architect, doc-engineer | New external dependencies |
| 3. Components | systems-architect (skeleton), implementer (as-built) | implementer (as-built), doc-engineer (verification) | New module/package, major refactoring |
| 4. Interfaces | systems-architect (design), implementer (as-built) | implementer (as-built) | Interface changes |
| 5. Data Flow | systems-architect | systems-architect | Data model changes, new flows |
| 6. Dependencies | systems-architect, implementer | implementer, doc-engineer (verification) | Dependency additions/removals |
| 7. Constraints | systems-architect | systems-architect | Constraint discovery |
| 8. Decisions | systems-architect | systems-architect | ADR creation |

Natural pipeline sequencing prevents concurrent edits: architect writes first (Phase 3), implementer updates later (Execution), doc-engineer verifies at checkpoints, verifier validates last.

## Staleness Mitigation

Five layers of defense:

1. **Main agent awareness** — when modifying structural files in Direct/Lightweight tier (no pipeline), the main agent checks for both architecture documents and updates affected sections. This document's Coordinator Awareness section provides the guidance
2. **Implementer post-step** — in Standard/Full pipelines, updates both docs when structural files change (proactive, steps 7.6 and 7.7)
3. **Verifier Phase 8/9** — cross-checks both docs after implementation (reactive, per-pipeline)
4. **Sentinel audit** — checks both docs independently (reactive, periodic)
5. **Doc-engineer periodic verification** — verifies `docs/architecture.md` against the filesystem at pipeline checkpoints (reactive, per-pipeline)

Finding routing for architect doc (`.ai-state/ARCHITECTURE.md`):

| Check | Finding | Recommended Owner | Fix Action |
|-------|---------|-------------------|------------|
| AC01 | 3+ components, no architecture doc | systems-architect | Create both docs from templates on next pipeline |
| AC02 | Design incoherence (components internally inconsistent) | systems-architect | Reconcile Section 3 component inventory |
| AC03 | >50% of file paths broken | implementer or main agent | Update illustrative file references |
| AC04 | ADR reference in Section 8 invalid | systems-architect | Fix or remove broken ADR reference |

Finding routing for developer guide (`docs/architecture.md`):

| Check | Finding | Recommended Owner | Fix Action |
|-------|---------|-------------------|------------|
| AC05 | Architect doc exists but no developer guide | systems-architect | Create `docs/architecture.md` from template on next pipeline |
| AC06 | Component name doesn't match actual module | implementer or doc-engineer | Sync Section 3 with actual module names |
| AC07 | File path doesn't resolve to existing file | implementer or doc-engineer | Update stale file references |
| AC08 | Status column or Planned items present | implementer or doc-engineer | Remove Status column and non-Built items |
| AC09 | Component not in architect doc (subset violation) | systems-architect | Add missing component to architect doc or remove from developer guide |

The sentinel detects but never fixes (read-only). Its report routes findings to the appropriate agent or the main agent for next-session pickup.

## Relationship to ADRs

ADRs document *why* an architectural decision was made. Both architecture documents reference ADR IDs in Section 8 for rationale:

- Architecture-related ADRs include `ARCHITECTURE.md` in `affected_files`
- Never duplicate ADR rationale in either architecture document — just link
- Both documents independently cross-reference the same ADRs

## Relationship to SYSTEM_DEPLOYMENT.md

Both architecture documents and SYSTEM_DEPLOYMENT.md are complementary:

- **Architecture docs** define the building blocks — components, interfaces, data flow, constraints
- **SYSTEM_DEPLOYMENT.md** describes how those blocks land on infrastructure — containers, ports, config, runbook

Architecture is upstream; deployment is downstream. Cross-reference when SYSTEM_DEPLOYMENT.md exists; do not add forward references to a non-existent deployment doc.

**Boundary rule**: if the content describes *what the system is or should be* (structure, behavior, contracts), it belongs in the architecture documents. If it describes *how the system runs* (containers, ports, health checks, scaling, runbook), it belongs in SYSTEM_DEPLOYMENT.md.

## Coordinator Awareness

For Direct/Lightweight tier work (no pipeline agents), the main agent should be aware of both architecture documents:

- **Discovery**: Target projects should add to their CLAUDE.md: "Architecture: design target at `.ai-state/ARCHITECTURE.md`, developer guide at `docs/architecture.md`"
- **When to read**: Before making structural decisions (adding modules, changing interfaces, introducing dependencies). Read `docs/architecture.md` for current state, `.ai-state/ARCHITECTURE.md` for design intent.
- **When to update**: After structural changes — new modules, interface changes, dependency additions/removals. Update both documents.
- **When NOT to update**: Bug fixes, refactoring within existing modules, test changes, documentation updates

The systems-architect adds the CLAUDE.md mention when creating the initial architecture documents. No hook injection or path-scoped rule is needed — this is on-demand, progressive disclosure.

## Diagram Conventions

Follow the project's Mermaid diagram conventions (see `rules/writing/diagram-conventions.md`):

- **10-12 nodes maximum** per diagram
- **L0/L1/L2 decomposition**: L0 for system context, L1 for components, L2 for internals (only when needed)
- **Standard shapes**: rectangles for components, `[(Database)]` for storage, `([Queue])` for messaging
- **Solid arrows** (`-->`) for direct dependencies, **dotted** (`-.->`) for async/event-based
- **Subgraphs** for logical boundaries (layers, bounded contexts)
- **Labels over IDs**: `App[Web App]` not bare `App`

## Bootstrap for Existing Projects

For projects that already have code but no architecture docs:

1. The sentinel's AC01 check flags the gap (3+ interacting components, no ARCHITECTURE.md)
2. The systems-architect creates both documents when next invoked for a Standard/Full pipeline
3. Read existing code structure, imports, and config to populate components, interfaces, and dependencies
4. Read existing ADRs in `.ai-state/decisions/` to populate Section 8
5. The developer guide is derived from the architect doc by filtering to Built components and verifying all paths
