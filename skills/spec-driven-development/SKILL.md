---
name: spec-driven-development
description: Behavioral specification methodology with requirement traceability for
  medium and large features. Covers spec format (When/and/the system/so that), complexity
  triage (trivial through spike), REQ ID conventions, traceability threading through
  the pipeline, decision documentation format, and spec archival. Use when working
  on behavioral specifications, requirement traceability, SDD methodology, spec format
  conventions, requirement format, REQ IDs, spec-driven development, complexity triage,
  or spec archival.
compatibility: Claude Code
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
---

# Spec-Driven Development

Behavioral specifications bridge architecture and implementation by giving each requirement a unique identity that threads through the entire pipeline -- from the architect's design through planning, testing, verification, and archival. SDD composes with the [software-planning](../software-planning/SKILL.md) skill: planning provides the three-document model and step decomposition; SDD provides the specification format and requirement traceability. Load both when working on medium or large features.

**Satellite files** (loaded on-demand):

- [references/spec-format-guide.md](references/spec-format-guide.md) -- full spec format with examples, EARS/GWT comparison, traceability matrix template, persistent spec template, spec delta template, edge cases
- [references/sentinel-spec-checks.md](references/sentinel-spec-checks.md) -- spec health check catalog for sentinel integration, pass conditions, integration guidance
- [references/calibration-procedure.md](references/calibration-procedure.md) -- structured tier assessment procedure with signal catalog, scoring matrix, evidence template, and calibration log format

## Gotchas

- **Over-specifying trivial tasks.** If the calibration tier is Direct or Lightweight, skip SDD entirely -- no REQ IDs, no behavioral spec. Agents default to producing specs for everything; the complexity triage exists to prevent this overhead.
- **REQ ID scope is per-feature, not global.** IDs reset for each new `SYSTEMS_PLAN.md`. REQ-01 in Feature A is unrelated to REQ-01 in Feature B. Do not attempt global uniqueness or cross-feature ID continuity.
- **Stale archived specs as baseline.** Before using an archived spec in `.ai-state/specs/` as a baseline for a spec delta, check `SENTINEL_LOG.md` for the most recent SH03 result. A FAIL means the spec's behavioral claims may have drifted from the code -- the delta's "before" side is unreliable.
- **Using Given/When/Then instead of ecosystem format.** Agents trained on BDD content default to Given/When/Then. This ecosystem uses `When/and/the system/so that` -- a distinct format that captures intent (`so that`) rather than test assertions (`Then`). Catch and correct GWT usage in specs.
- **Omitting the `so that` clause.** The `so that` clause is required, not optional. Without it, a requirement reads as a test assertion rather than a behavioral specification. The intent clause is what distinguishes SDD from a test plan.

## Process Calibration

Before selecting a process tier, the main agent runs a structured calibration assessment at task intake. The procedure collects 6 objective signals (file count proxy, behavior count, architectural scope, prior spec existence, test coverage, request complexity), scores them against a weighted matrix, and produces a tier recommendation with per-signal evidence. The user can override at any time. Decisions are logged to `.ai-state/calibration_log.md` for trend analysis.

**Calibration selects the tier; complexity triage refines spec depth within it.** Two stages of the same decision — calibration determines how much pipeline machinery to deploy (Direct through Full), then triage determines how detailed the behavioral specification should be (trivial through large).

--> See [references/calibration-procedure.md](references/calibration-procedure.md) for the full signal catalog, scoring matrix, evidence output template, and assessment examples.

## Complexity Triage

Classify every task before deciding whether to produce a behavioral specification. Tier selection is determined by the [calibration procedure](references/calibration-procedure.md). This triage refines SDD depth within the Standard and Full tiers — it governs how much specification to produce, not whether to use agents or planning documents.

| Tier | Signals | Spec Depth |
|------|---------|------------|
| Trivial | Single-file fix, config change, doc update, typo | No spec. No REQ IDs. Existing workflow unchanged. |
| Small | 2-3 files, single behavior, clear scope | Lightweight acceptance criteria (existing format). No REQ IDs. |
| Medium | 4-8 files, 2-4 behaviors, some architectural decisions | Full behavioral specification with REQ IDs. |
| Large | 9+ files, 5+ behaviors, architectural impact, cross-cutting concerns | Full behavioral specification + explicit decision documentation + archival. |
| Spike | Exploratory/R&D, outcome uncertain | No spec. Spike step in plan. Decision documented in LEARNINGS.md. |

**Classification signals to weigh:**

- **File count** is a proxy, not a rule -- a 2-file change with complex state transitions may warrant medium treatment
- **Behavior count** matters more than file count -- multiple independent behaviors need independent requirements
- **Architectural decisions** (new abstractions, interface changes, cross-cutting concerns) push toward medium or large
- **User override** is always valid -- "this needs a full spec" or "skip spec" from the user takes precedence
- **When uncertain**, default to the lower tier -- specs can be added later, but unnecessary overhead cannot be reclaimed

## Behavioral Specification Format

Place behavioral specifications in a `## Behavioral Specification` section of `SYSTEMS_PLAN.md`, after `## Acceptance Criteria` and before `## Architecture`.

Each requirement follows the `When/and/the system/so that` pattern:

```markdown
### REQ-01: [Short descriptive title]

**When** [trigger condition or user action]
**and** [optional additional precondition]
**the system** [expected response or behavior]
**so that** [observable outcome or user benefit]
```

The `and` clause is optional -- omit it when no precondition is needed. The `so that` clause is required -- it makes the intent explicit and distinguishes a behavioral requirement from a test assertion.

**Why this format:**

- **Evolved acceptance criteria** -- the ecosystem already uses "When X happens, the system does Y" patterns. This adds structure (unique IDs, explicit intent) without replacing familiar conventions.
- **Not EARS** -- EARS behavior type classifications (ubiquitous, event-driven, state-driven) add formalism the ecosystem does not need. The structured fields capture the same information without requiring classification knowledge.
- **Not Given/When/Then** -- GWT couples to BDD test frameworks (Behave, Cucumber) that may not match the project's test stack. The `so that` clause serves the same purpose as GWT's `Then` without implying a specific test runner.

--> See [references/spec-format-guide.md](references/spec-format-guide.md) for full examples, edge cases, and detailed format comparisons.

## Requirement ID Conventions

- **Format**: `REQ-NN` (zero-padded two digits, e.g., `REQ-01`, `REQ-12`)
- **Scope**: per feature — IDs reset for each new `SYSTEMS_PLAN.md`
- **In code, tests, docstrings, comments**: **never**. REQ/AC IDs are pipeline-local or feature-local metadata — they do not belong in durable source files. Tests describe behavior through their names; the archived SPEC's matrix holds the REQ-to-test mapping. See [`rules/swe/id-citation-discipline.md`](../../rules/swe/id-citation-discipline.md).
- **In IMPLEMENTATION_PLAN.md**: reference in the `Testing` field (e.g., "Validates REQ-01, REQ-03") — pipeline document, not code
- **In VERIFICATION_REPORT.md**: use full `REQ-NN` format in the traceability matrix — pipeline document
- **In `.ai-work/<task-slug>/traceability.yml`**: first-class keys mapping REQs to test and implementation file paths — ephemeral pipeline document, the canonical in-flight source of truth
- **In persistent archived specs** (`.ai-state/specs/SPEC_*.md`): IDs preserved in the rendered matrix for historical reference — the archived SPEC is the single source of truth post-archive

**Traceability matrix format** (produced by the verifier from `traceability.yml`):

| Requirement | Test(s) | Implementation | Status |
|-------------|---------|----------------|--------|
| REQ-01 | tests/auth/test_session.py::test_expired_token_returns_401 | src/auth/session.py::validate() | PASS |
| REQ-02 | tests/auth/test_roles.py::test_new_user_gets_default_role | src/auth/roles.py::assign_default() | PASS |
| REQ-03 | (none) | src/auth/audit.py::log_attempt() | UNTESTED |

Status values: `PASS` (test exists and passes), `FAIL` (test fails or implementation missing), `UNTESTED` (no test recorded in `traceability.yml` for this requirement).

**Mid-flight coverage**: The `/sdd-coverage` command reads `traceability.yml` (during pipeline) or the archived SPEC's matrix (post-archive) and produces this table at any time during development — not just at verification. The test-engineer also includes a coverage check when reporting step completion. Use these to catch gaps early rather than discovering them at the verifier stage.

## Traceability Threading

REQ IDs flow through the pipeline in six stages via an **external two-layer mechanism** — ephemeral YAML during the pipeline, persistent matrix in the archived SPEC afterward. **IDs never appear in code, test names, docstrings, or comments** (see [`rules/swe/id-citation-discipline.md`](../../rules/swe/id-citation-discipline.md)).

```text
1. Architect creates    --> REQ-01..REQ-NN in SYSTEMS_PLAN.md Behavioral Specification
2. Planner threads      --> "Validates REQ-01, REQ-03" in test step Testing fields;
                            initializes empty .ai-work/<slug>/traceability.yml
3. Test-engineer writes --> tests with behavioral names; appends REQ-to-test entries
                            to traceability.yml (or traceability_test-engineer.yml fragment)
4. Implementer writes   --> production code with behavioral names; appends REQ-to-impl
                            entries to traceability.yml (or traceability_implementer.yml fragment)
5. Verifier produces    --> Traceability matrix in VERIFICATION_REPORT.md by reading
                            the YAML + TEST_RESULTS.md (never by grepping code)
6. Planner archives     --> Renders YAML into archived SPEC's matrix at feature end;
                            .ai-work/ cleanup then deletes the YAML
```

Each stage consumes the output of the previous one. `traceability.yml` is the single source of truth during the pipeline; the archived SPEC's matrix is the single source of truth afterward. The verifier's matrix in `VERIFICATION_REPORT.md` is a conformance snapshot.

**YAML schema**:

```yaml
requirements:
  REQ-01:
    tests:
      - tests/auth/test_session.py::test_expired_token_returns_401
      - tests/auth/test_session.py::test_grace_period_allows_refresh
    implementation:
      - src/auth/session.py::validate()
      - src/auth/session.py::refresh_grace_period()
  REQ-02:
    tests: []  # untested
    implementation:
      - src/auth/audit.py::log_attempt()
```

Absent `tests:` list (or empty list) means UNTESTED. Absent `implementation:` list means no implementation yet (pre-integration). An absent REQ key entirely means neither test nor implementation exists for that REQ.

**Parallel fragments**: `traceability_implementer.yml`, `traceability_test-engineer.yml`. Reconciliation is a per-REQ merge of `tests` and `implementation` arrays — no conflicts by construction because the two agents write to disjoint fields within each REQ key. The implementation-planner performs the merge at batch completion.

## Convergence via REQ-ID Stability

When multiple pre-implementation design sweeps produce the same REQ set, the design has converged on the *what* (behavior); Phase 7 then decides only the *how* (implementation trade-off). REQ churn across sweeps signals that REQs have leaked implementation details — re-draft the unstable REQs at the behavioral level before proceeding.

**3-step stability check** (architect runs when activation fires):

1. **Draft REQs** against the proposed behavior.
2. **Sketch design A**; record any Added / Modified / Removed REQ IDs.
3. **Sketch design B**; record the same deltas.

Stable = zero Added / Modified / Removed REQs between sweeps. Churn = at least one REQ changed; re-draft the churning REQs.

**Verifier check**: stability is mechanically verifiable by comparing REQ IDs across ADR revisions — the verifier reports stable/churned without needing to re-read prose.

See [design-synthesis.md — Convergence Signals](../software-planning/references/design-synthesis.md#convergence-signals) for the full four-signal convergence stack (stability + risk-budget + blast-radius + user-acceptance).

## Decision Documentation Format

For medium and large features, record decisions in the `Decisions Made` section of `LEARNINGS.md` using structured format:

```markdown
- **[agent-name] [Decision title]**: [What was decided]. **Why**: [rationale]. **Alternatives**: [what was considered and rejected].
```

This structure enables:

- The verifier to check for substantive decision documentation
- The persistent spec to archive decisions with full context
- The sentinel to assess decision quality in archived specs (SH05 check)

Trivial and small tasks use freeform decision notes -- the structured format adds value only when decisions are complex enough to have alternatives worth recording.

Decision-making agents (systems-architect, implementation-planner) also create an ADR file in `.ai-state/decisions/` following the [adr-conventions rule](../../rules/swe/adr-conventions.md). The human-readable format in LEARNINGS.md and the persistent ADR file coexist -- LEARNINGS.md is the ephemeral authoring surface, the ADR file is the permanent record.

## Spec Archival

When a medium or large feature completes, the implementation-planner archives the spec during the end-of-feature workflow.

**Location**: `.ai-state/specs/SPEC_<feature-name>_YYYY-MM-DD.md`

**Persistent spec template**:

```markdown
# Spec: [Feature Name]

**Created**: [ISO 8601 timestamp]
**Pipeline run**: [date range]
**Status**: completed
**Complexity**: medium | large

## Requirements

[Copy of Behavioral Specification section from SYSTEMS_PLAN.md]

## Traceability

[Copy of traceability matrix from VERIFICATION_REPORT.md]

## Key Decisions

[Extracted from LEARNINGS.md Decisions Made section]
```

The `.ai-state/specs/` directory is created on first use. Archived specs are committed to git alongside other persistent project intelligence. The sentinel audits these specs for drift, completeness, and traceability coverage.

## Spec Delta Format

For brownfield features — when `.ai-state/specs/` contains prior `SPEC_*.md` files relevant to the feature being designed and the process calibration tier is Standard or Full — the systems-architect produces a `SPEC_DELTA.md` alongside `SYSTEMS_PLAN.md`. The delta shows what behavioral requirements change before implementation planning begins.

**Activation condition**: prior archived specs exist for the affected area AND tier is Standard or Full. Greenfield work (no prior specs) skips delta production entirely.

**Document structure**:

- **Header**: prior spec reference, tier, baseline confidence (High/Low based on sentinel SH03 status)
- **Staleness Warning** (conditional): when the prior spec's SH03 check shows FAIL, lists requirements with uncertain baselines
- **Added Requirements**: new REQ IDs in standard `When/and/the system/so that` format with rationale
- **Modified Requirements**: before (blockquoted prior text) and after (new text) with change rationale
- **Removed Requirements**: prior REQ IDs with strikethrough, removal rationale, and cleanup flag

**Lifecycle**: ephemeral in `.ai-work/<task-slug>/`. Consumed by the implementation-planner (step ordering) and verifier (delta validation). Deleted after pipeline completion — the delta's content is subsumed by the archived spec.

**REQ ID convention**: fresh per-feature IDs as established by the existing convention. The delta provides the cross-feature mapping between old and new IDs.

--> See [references/spec-format-guide.md](references/spec-format-guide.md#spec-delta-template) for the full template with examples.

## Quick Reference

**When to apply SDD:**

- **Medium tasks** (4-8 files, 2-4 behaviors): full behavioral specification with REQ IDs
- **Large tasks** (9+ files, 5+ behaviors): full spec + structured decisions + archival

**What to skip:**

- **Trivial** (single-file fix, config, doc): no spec, no REQ IDs
- **Small** (2-3 files, single behavior): lightweight acceptance criteria only
- **Spike** (exploratory/R&D): no spec -- document conclusions in LEARNINGS.md

**Key locations:**

| Artifact | Location |
|----------|----------|
| Behavioral specification | `SYSTEMS_PLAN.md` `## Behavioral Specification` section |
| REQ threading (planning) | `IMPLEMENTATION_PLAN.md` step `Testing` fields |
| Test naming | Test code: **behavioral names only** (e.g., `test_expired_token_returns_401`) — never `test_req{NN}_...` |
| Traceability file (ephemeral) | `.ai-work/<task-slug>/traceability.yml` (fragment files in parallel mode) |
| Traceability matrix (verification) | `VERIFICATION_REPORT.md` `## Spec Conformance` section |
| Archived spec + matrix (persistent) | `.ai-state/specs/SPEC_<name>_YYYY-MM-DD.md` |
| Spec delta (brownfield) | `.ai-work/<task-slug>/SPEC_DELTA.md` (ephemeral, produced by architect) |
| Calibration log | `.ai-state/calibration_log.md` (persistent, append-only) |
| Decision documentation | `LEARNINGS.md` `### Decisions Made` section |
