---
description: Report spec-to-test and spec-to-code coverage for REQ IDs
argument-hint: [spec-path]
allowed-tools: [Read, Grep, Glob]
---

Scan the behavioral specification for REQ IDs and report which have tests, implementations, or are missing coverage. Runnable at any time during development.

## Process

1. **Locate the spec**: If `$ARGUMENTS` is provided, use it as the spec path. Otherwise read `.ai-work/SYSTEMS_PLAN.md`. If neither exists, report "No behavioral specification found" and stop.

2. **Extract REQ IDs**: Find all `### REQ-NN:` headings in the `## Behavioral Specification` section. For each, extract the ID and title.

3. **Scan for tests**: For each REQ-NN, search test files for patterns:
   - `req{NN}_` in function names (e.g., `test_req01_session_expired`)
   - `REQ-{NN}` in docstrings or comments
   - Use `Grep` with pattern `req0?{N}_|REQ-0?{N}` across test directories

4. **Scan for implementations**: For each REQ-NN, search non-test source files for patterns:
   - `REQ-{NN}` in comments
   - Function/class names matching the requirement's behavioral description (best-effort heuristic)
   - Files referenced in `decisions.jsonl` entries with matching `affected_reqs` (if the file exists)

5. **Output the coverage table**:

```
## Spec Coverage: [Feature Name]

| REQ | Title | Tests | Implementation | Status |
|-----|-------|-------|----------------|--------|
| REQ-01 | Session expiry handling | test_req01_session_expired | src/auth/session.py | COVERED |
| REQ-02 | Default role assignment | (none) | src/auth/roles.py | UNTESTED |
| REQ-03 | Audit logging | (none) | (none) | MISSING |

**Summary**: 1/3 covered, 1/3 untested, 1/3 missing
```

Status values:
- **COVERED** — both test(s) and implementation found
- **UNTESTED** — implementation found but no test
- **MISSING** — no test and no implementation found
- **TEST-ONLY** — test found but no implementation yet (TDD in progress)

6. **Flag gaps**: If any requirement is UNTESTED or MISSING, list it as an action item:
   - "REQ-02: needs test coverage — consider adding `test_req02_default_role_assignment`"
   - "REQ-03: no implementation or tests found — may not have been started"
