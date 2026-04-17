# Report Template

Canonical structure for code review reports. Used by the verifier agent (pipeline
mode) and the code-review skill (standalone mode).

## Full Template (Pipeline Mode)

```markdown
# Verification Report: [Feature Name]

## Verdict

[PASS / PASS WITH FINDINGS / FAIL]

Automated review complements but does not replace human judgment.

## Acceptance Criteria

| Criterion | Status | Evidence |
|-----------|--------|----------|
| [From SYSTEMS_PLAN.md] | PASS/FAIL/WARN | [What was observed] |

## Convention Compliance

| # | Severity | Location | Finding | Rule Reference |
|---|----------|----------|---------|----------------|
| 1 | FAIL | file.py:42 | Function exceeds 50-line ceiling (63 lines) | coding-style.md: Function Size |
| 2 | WARN | module.py:15 | Nesting depth at 4 levels (at threshold) | coding-style.md: Nesting Depth |

### Behavioral Contract Findings

Verifier emits the six canonical tags below when a contract violation is observed. Source of truth for the behaviors: `rules/swe/agent-behavioral-contract.md`.

| Tag | Behavior | Definition | Severity default | Example trigger |
|---|---|---|---|---|
| `[UNSURFACED-ASSUMPTION]` | Surface Assumptions | Agent acted on an assumption without stating it in LEARNINGS.md, VERIFICATION_REPORT.md, or the step's output. | WARN (escalates to FAIL if assumption was materially wrong) | Implementer wrote a retry loop assuming the API returns 429 on rate limit; no evidence gathered, no note recorded. |
| `[MISSING-OBJECTION]` | Register Objection | Agent complied with a directive that contradicted prior ADRs, behavioral specs, or evidence, without flagging the conflict. | FAIL | Systems-architect produced a design using a library deprecated in a prior ADR, without noting the override or recording a new ADR. |
| `[NON-SURGICAL]` | Stay Surgical | Agent modified files outside the assigned step's declared `Files` field, or modified lines unrelated to the change rationale. | FAIL | Implementer edited an unrelated helper "while I was in there"; change scope exceeded what the plan authorized. |
| `[SCOPE-CREEP]` | Stay Surgical | Agent added work not in the spec, plan, or user request. Distinct from `[NON-SURGICAL]`: creep is *new capability*, non-surgical is *collateral change*. | FAIL | Implementer added an admin endpoint not in the behavioral spec because "it'll be useful later". |
| `[BLOAT]` | Simplicity First | Solution is structurally larger than the behavior requires: new abstraction, speculative interface, unused parameter, premature configurability. | WARN (escalates to FAIL for removable cruft) | Test-engineer introduced a fixture factory for a single test case; a simple setup/teardown would have sufficed. |
| `[DEAD-CODE-UNREMOVED]` | Simplicity First | Debug prints, commented-out code, unused imports, or superseded functions left in the change set. | WARN | Implementer left a debug `print()` without the removal-marker comment required by global CLAUDE.md Technical Conventions. |

Example finding rows:

| # | Severity | Location | Finding | Rule Reference |
|---|----------|----------|---------|----------------|
| 3 | FAIL | plan.md:step-7 | `[MISSING-OBJECTION]` Implementer applied retry-in-storage directive despite a prior ADR placing retries at handler boundary; no objection recorded. | agent-behavioral-contract.md: Register Objection |
| 4 | WARN | tests/fixtures.py:12 | `[BLOAT]` Fixture factory introduced for a single test case; inline setup would suffice. | agent-behavioral-contract.md: Simplicity First |

## Test Coverage Assessment

[Summary of test adequacy for critical paths]
[Notes on untested edge cases or missing coverage for complex logic]

## Context Artifact Completeness

[Only included when the plan contained context artifact update steps]

| Planned Update | Status | Notes |
|---------------|--------|-------|
| [From IMPLEMENTATION_PLAN.md] | Done/Missing | [What was observed] |

## Recommendations

### FAIL Findings (correction needed)

1. [Prioritized corrective actions]

### WARN Findings (review recommended)

1. [Suggested improvements]

### Merge to LEARNINGS.md

Before deleting this report, merge recurring patterns and systemic
quality issues into LEARNINGS.md.

## Scope

- Files reviewed: [count]
- Commits reviewed: [hash range or branch comparison]
- Plan steps verified: [N of M] (pipeline mode only)
- Review timestamp: [ISO 8601]
```

## Standalone Template

Omit the following sections when producing a standalone review:

- Acceptance Criteria (requires `SYSTEMS_PLAN.md`)
- Context Artifact Completeness (requires `IMPLEMENTATION_PLAN.md`)
- "Plan steps verified" from Scope
- "Merge to LEARNINGS.md" from Recommendations (no pipeline context)

The remaining sections (Verdict, Convention Compliance, Test Coverage,
Recommendations, Scope) use the same format as the full template.
