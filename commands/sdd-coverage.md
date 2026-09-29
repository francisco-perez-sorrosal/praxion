---
description: Report spec-to-test and spec-to-code coverage for REQ IDs
argument-hint: "[spec-path]"
allowed-tools: [Read, Glob]
---

Read the canonical traceability source for a feature's behavioral specification and report which REQ IDs have tests, implementations, or are missing coverage. Runnable at any time during development — it reads state, never greps code.

## Process

1. **Locate the spec and traceability source** based on pipeline state:
   - If `$ARGUMENTS` points to an archived SPEC (`.ai-state/specs/SPEC_*.md`), read its `## Traceability` section directly — this is the frozen post-archive state.
   - Otherwise, look for `.ai-work/<task-slug>/SYSTEMS_PLAN.md` across task-scoped subdirectories (most recently modified if multiple exist). The traceability source is `.ai-work/<task-slug>/traceability.yml` in the same task directory. In parallel mode, read both `traceability_implementer.yml` and `traceability_test-engineer.yml` and merge per-REQ (union of every list-valued key: `tests`, `implementation`, `acceptance`).
   - If neither an archived SPEC nor an active pipeline with `SYSTEMS_PLAN.md` can be found, report "No behavioral specification found" and stop.

2. **Extract REQ IDs** from the spec (archived or in-flight): find all `### REQ-NN:` headings in the `## Behavioral Specification` (or `## Requirements`) section. For each, extract the ID and title.

3. **Read traceability**:
   - **Archived mode**: parse the `## Traceability` Markdown table from the archived SPEC; each row gives the REQ, test(s), implementation, and status.
   - **In-flight mode**: parse the YAML `requirements:` mapping. For each REQ key, read `tests:` and `acceptance:` (outer-loop nodes; optional, absent is valid), both lists of `<file>::<func>` entries, and `implementation:` (empty or absent means no implementation yet). A REQ counts as tested when `tests:` and `acceptance:` together are non-empty (union coverage: `skills/spec-driven-development/SKILL.md`, "Union coverage").

4. **Output the coverage table**:

```
## Spec Coverage: [Feature Name]

| REQ | Title | Tests | Implementation | Status |
|-----|-------|-------|----------------|--------|
| REQ-01 | Session expiry handling | tests/auth/test_session.py::test_expired_token_returns_401 | src/auth/session.py::validate() | COVERED |
| REQ-02 | Default role assignment | (none) | src/auth/roles.py::assign_default() | UNTESTED |
| REQ-03 | Audit logging | (none) | (none) | MISSING |

**Summary**: 1/3 covered, 1/3 untested, 1/3 missing
```

Status values:
Below, "tested" means `tests:` or `acceptance:` is non-empty. The `Tests` cell lists the nodes of both keys.

- **COVERED** — tested and `implementation:` populated in `traceability.yml`, or PASS in the archived SPEC matrix
- **UNTESTED** — `implementation:` populated but neither `tests:` nor `acceptance:` has an entry
- **MISSING** — nothing populated; REQ is not yet started
- **TEST-ONLY** — tested but `implementation:` empty (TDD in progress, pre-integration)

5. **Flag gaps**: If any requirement is UNTESTED or MISSING, list it as an action item:
   - "REQ-02: needs test coverage — add a behavioral test and record the mapping in `traceability.yml`"
   - "REQ-03: no implementation or tests found — may not have been started"

6. **Never grep code for REQ IDs.** Code and tests do not contain REQ/AC references ([`rules/swe/id-citation-discipline.md`](../rules/swe/id-citation-discipline.md)). The YAML and the archived SPEC matrix are the authoritative sources.
