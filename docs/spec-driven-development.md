---
diataxis: reference
audience: developer
---

# Spec-Driven Development

This project uses behavioral specifications to bridge the gap between architectural design and implementation. Each requirement gets a unique ID that threads through the entire pipeline -- from the architect's design through planning, testing, verification, and archival. The approach scales proportionally: trivial and small tasks skip specs entirely, while medium and large features activate the full specification workflow with requirement traceability, structured decision documentation, and spec health monitoring.

## What Is SDD in This Project

Spec-driven development (SDD) is the practice of writing structured behavioral specifications with unique requirement IDs (REQ-01, REQ-02, ...) and threading those IDs through every pipeline phase. The systems-architect writes specifications during the architecture phase. The implementation-planner threads requirement IDs into test steps. The test-engineer encodes IDs in test names. The verifier produces a traceability matrix mapping each requirement to its tests and implementation. The planner archives the completed spec for cross-session reference.

This differs from spec-only tools (Spec Kit, Kiro, OpenSpec) that focus on specification and task generation but stop there. SDD in this project is one component of a complete pipeline -- specifications feed into planning, execution, verification, and learning capture rather than existing in isolation.

For the full SDD skill with agent-executable conventions, see [`skills/spec-driven-development/SKILL.md`](../skills/spec-driven-development/SKILL.md).

## When SDD Activates

Not every task needs a behavioral specification. The pipeline classifies each task into one of five complexity tiers and activates SDD only when the task warrants it.

| Tier | Signals | Spec Depth |
|------|---------|------------|
| Trivial | Single-file fix, config change, doc update, typo | No spec. No REQ IDs. |
| Small | 2-3 files, single behavior, clear scope | Lightweight acceptance criteria. No REQ IDs. |
| Medium | 4-8 files, 2-4 behaviors, architectural decisions | Full behavioral specification with REQ IDs. |
| Large | 9+ files, 5+ behaviors, cross-cutting concerns | Full spec + decision documentation + archival. |
| Spike | Exploratory/R&D, outcome uncertain | No spec. Spike step. Decision in LEARNINGS.md. |

File count is a proxy, not a rule. A 2-file change with complex state transitions may warrant medium treatment. Behavior count and the presence of architectural decisions matter more. When uncertain, default to the lower tier -- specs can be added later, but unnecessary overhead cannot be reclaimed.

## The Behavioral Specification Format

Each requirement uses the `When/and/the system/so that` pattern:

```
### REQ-01: [Short descriptive title]

**When** [trigger condition or user action]
**and** [optional additional precondition]
**the system** [expected response or behavior]
**so that** [observable outcome or user benefit]
```

The `and` clause is optional -- omit it when no precondition is needed. The `so that` clause is required -- it makes the intent explicit and distinguishes a behavioral requirement from a test assertion.

### Example: API error handling

```
### REQ-01: Expired session rejected on API request

**When** a client sends an API request with an expired session token
**and** the token has been expired for more than the grace period
**the system** returns a 401 Unauthorized response with a `session_expired` error code
**so that** the client knows to re-authenticate rather than retrying the same request
```

### Example: State transition

```
### REQ-02: Workflow transitions to review state

**When** all required approvals have been collected for a document
**the system** transitions the workflow state from `pending_approval` to `in_review`
  and notifies the assigned reviewer
**so that** the review process begins without manual intervention
```

### Why not EARS or Given/When/Then

The `When/and/the system/so that` format evolved from the ecosystem's existing acceptance criteria patterns. It adds structure (unique IDs, explicit intent via `so that`) without importing formalism the project does not need. EARS behavior-type classifications (ubiquitous, event-driven, state-driven) add categorization overhead without improving traceability. Given/When/Then couples to BDD test frameworks and serves a different purpose -- test specification rather than behavioral requirement documentation.

For detailed rationale and edge case handling, see [`references/spec-format-guide.md`](../skills/spec-driven-development/references/spec-format-guide.md).

## Requirement Traceability

REQ IDs flow through the pipeline in five stages, each consuming the output of the previous one.

![Spec-driven development five-stage flow — Stage 1 Behavioral Spec (architect) → Stage 2 Implementation Plan (planner) → Stage 3 Test Files (test-engineer) → Stage 4 Traceability Matrix (verifier) → Stage 5 Persistent Spec (planner archives to .ai-state/specs/)](diagrams/sdd-stage-flow/rendered/sdd-stage-flow.svg)

The verifier's traceability matrix is the conformance checkpoint -- it shows whether every requirement has tests and implementation. The archived spec preserves the full chain for cross-session reference.

## Where SDD Fits in the Pipeline

The pipeline consists of seven phases, each owned by a specialized agent. SDD touches four of them.

| Phase | Agent | What It Produces |
|-------|-------|-----------------|
| 1. Ideation | promethean | Feature proposals from project state |
| 2. Research | researcher | Codebase exploration, external docs |
| 3. Architecture + Specification | systems-architect | System design + **behavioral spec with REQ IDs** |
| 4. Planning | implementation-planner | Step decomposition + **REQ IDs threaded into test steps** |
| 5. Execution | implementer + test-engineer | Code + **tests with `req{NN}_` naming** |
| 6. Verification | verifier | Acceptance review + **traceability matrix** |
| 7. Learning | LEARNINGS.md + memory | Captured decisions and patterns |

**Bold** entries are SDD contributions. Phases without bold entries operate the same regardless of whether SDD is active.

Supporting capabilities that interact with SDD:

- **sentinel** -- audits archived specs for drift, completeness, and traceability coverage
- **context-engineer** -- manages context artifacts including spec-related pipeline documents
- **doc-engineer** -- updates documentation when specs affect public-facing content

## Spec Health Monitoring

The sentinel audits persistent specs in `.ai-state/specs/` as part of its ecosystem health assessment. Five checks compose the Spec Health (SH) dimension:

| Check | What It Verifies |
|-------|-----------------|
| SH01 | File paths referenced in specs still resolve |
| SH02 | Traceability matrices are present and non-empty |
| SH03 | Behavioral claims in specs still match current code |
| SH04 | Every requirement has at least one test (no UNTESTED entries) |
| SH05 | Key Decisions section includes rationale and alternatives |

SH01 and SH02 run automatically during the sentinel's first pass. SH03-SH05 require LLM judgment and run as a conditional batch -- only when `.ai-state/specs/` contains spec files.

For the full check catalog with evaluation criteria and common failure patterns, see [`references/sentinel-spec-checks.md`](../skills/spec-driven-development/references/sentinel-spec-checks.md).

## Comparison with Spec-Only Approaches

The table below compares this project's SDD integration with spec-focused tools across the full development lifecycle.

| Capability | Spec Kit / Kiro / OpenSpec | i-am SDD |
|-----------|---------------------------|----------|
| Ideation | -- | promethean generates feature proposals |
| Research | -- | researcher explores codebase and external docs |
| Architecture | Partial (some tools generate designs) | systems-architect produces full system design |
| Specification | Core focus | SDD skill: one component of the pipeline |
| Planning | Task decomposition from specs | implementation-planner: step decomposition with REQ threading |
| Execution | Implementation guidance | implementer + test-engineer with REQ IDs in test names |
| Verification | Partial (some check task completion) | verifier produces traceability matrix per requirement |
| Learning capture | -- | LEARNINGS.md + memory + skill-genesis |
| Ecosystem health | -- | sentinel audits spec drift and traceability coverage |
| Progressive disclosure | -- | Skills loaded on demand; reference files for depth |
| Proportional scaling | All-or-nothing | 5-tier triage: trivial through spike |

Spec-only tools excel at specification and task generation. This project's SDD integrates specification into a pipeline that also handles ideation, research, architecture, execution, verification, learning, and ongoing ecosystem health -- with proportional scaling that avoids imposing spec overhead on work that does not need it.
