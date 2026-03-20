---
name: code-review
description: >
  Structured code review methodology with finding classification (PASS/FAIL/WARN),
  language adaptation, and report templates. Use when reviewing code for convention
  compliance, conducting post-implementation verification, reviewing pull requests,
  or performing ad-hoc code quality assessments. Also activates for PR review,
  code audit, and code quality checks.
allowed-tools: [Read, Glob, Grep, Bash]
compatibility: Claude Code
---

# Code Review

Structured review methodology for assessing code against documented conventions.
Provides finding classification, language adaptation, and report templates.

**Satellite files** (loaded on-demand):

- [references/report-template.md](references/report-template.md) -- structured review report template with finding format and verdict scale

## Gotchas

- **Review scope in PR context**: Review only changed lines and their immediate context -- not the entire file. Reviewing unchanged code inflates findings and obscures the actual PR quality signal.
- **Language adaptation is additive**: Entries in the Language Adaptation table extend the coding-style rule's generic conventions for a specific language. They do not replace the generic checks -- both layers apply.
- **PASS verdict requires full coverage**: A PASS verdict means every convention category was checked and none produced FAIL or WARN findings. The absence of FAIL findings alone is not sufficient -- skipping a category entirely is not a PASS.
- **Structural findings belong to refactoring**: When review findings indicate structural issues (module too large, deep coupling, misplaced responsibility), flag them but defer remediation to the `refactoring` skill rather than prescribing structural fixes inline.

## Relationship to coding-style Rule

This skill does not define conventions -- it defines how to review against them.

- **coding-style rule** (auto-loaded): defines WHAT conventions to check
- **code-review skill** (this file): defines HOW to conduct a review
- **Language skills** (e.g., python): provide language-specific idioms when loaded

## Review Workflow

### 1. Scope

- Identify files under review (git diff, explicit file list, or PR scope)
- Detect primary language(s) from file extensions and project config
- Distinguish production code from test code

### 2. Convention Check

- Apply each coding-style rule section to the scoped files
- Use language adaptation (see below) for language-specific interpretation
- Focus on changed or added code -- do not review unchanged code

### 3. Test Coverage

- Identify critical paths in the reviewed code
- Check whether tests exist for those paths
- Note untested edge cases in complex logic
- Review test results if available

### 4. Findings

- Classify each finding using the system below
- Include location (file:line), evidence, and rule reference
- Group findings by severity

### 5. Report

- Determine report mode from available context (see Report Modes)
- Load the report template from [references/report-template.md](references/report-template.md)
- Produce the report with findings, verdict, and recommendations

## Finding Classification

| Level | Meaning | Action Required |
| --- | --- | --- |
| PASS | Convention met or criterion satisfied | None |
| WARN | Threshold approached, minor concern, or ambiguous evidence | Review recommended |
| FAIL | Convention violated or criterion not met | Correction needed |

Severity within FAIL/WARN:

- **Location**: file path and line number (or line range)
- **Evidence**: what was observed (e.g., "function is 63 lines")
- **Rule reference**: which coding-style section or acceptance criterion
- **Context**: why this matters in this specific case (optional, for non-obvious findings)

## Report Modes

The skill adapts its output based on available context:

### Pipeline Mode

When pipeline documents exist in `.ai-work/` (`SYSTEMS_PLAN.md`, `IMPLEMENTATION_PLAN.md`):

- **All sections**: Verdict, Acceptance Criteria, Convention Compliance, Test Coverage, Context Artifact Completeness, Recommendations, Scope
- Used by the verifier agent

### Standalone Mode

When invoked directly by a user (no pipeline documents):

- **Reduced sections**: Verdict, Convention Compliance, Test Coverage, Recommendations, Scope
- Acceptance Criteria and Context Artifact Completeness are omitted (no pipeline context)
- Used for ad-hoc reviews, PR reviews, non-pipeline work

## Language Adaptation

The coding-style rule is language-independent. This skill maps generic conventions
to language-specific idioms when reviewing code.

### Detection

- Read file extensions to determine primary language(s)
- Check project config files (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`)
- When a language-specific skill is loaded (e.g., python), reference it for additional language-specific review criteria

### Common Adaptations

| Generic Convention | Python | TypeScript | Go | Rust |
| --- | --- | --- | --- | --- |
| Immutability | frozen dataclasses, tuples | `readonly`, `const`, `Readonly<T>` | value receivers, unexported fields | ownership, borrowing |
| Error handling | explicit `try/except`, no bare `except` | explicit `try/catch`, typed errors | error returns, no `panic` in libraries | `Result<T, E>`, no `unwrap` in libraries |
| Naming | `snake_case` functions/vars, `PascalCase` classes | `camelCase` functions/vars, `PascalCase` types | `camelCase` unexported, `PascalCase` exported | `snake_case` functions/vars, `PascalCase` types |
| Code organization | packages with `__init__.py` | modules with `index.ts` | packages by directory | modules with `mod.rs` |

### Fallback

When no language-specific skill exists for the detected language, apply the
generic coding-style rule checks without language adaptation. Note in findings
that language-specific review was not available.

## Verdict Levels

- **PASS** -- no FAIL findings, no WARN findings
- **PASS WITH FINDINGS** -- no FAIL findings, one or more WARN findings
- **FAIL** -- one or more FAIL findings

## Report Template

See [references/report-template.md](references/report-template.md) for the
canonical `VERIFICATION_REPORT.md` structure. Load on demand when producing a report.

## Related Skills

- **`refactoring`**: When review findings reveal structural issues (oversized modules, deep coupling, misplaced responsibilities), hand off to the `refactoring` skill for remediation planning rather than prescribing structural changes in the review report.
