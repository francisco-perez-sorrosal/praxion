# Pre-Refactor Plan: extract-auth-validator

## Goal

Extract the inline authentication-token validation block out of the request
handler so the planned audit-logging feature has a single, testable seam to
wrap.

## Behavior Preservation Contract

- Valid tokens continue to return the same authenticated principal object.
- Expired tokens continue to return HTTP 401 with the existing error body.
- Tokens with a future `nbf` claim continue to return HTTP 401, not 403.
- The `last_seen_at` audit field continues to update only on a successful
  validation, never on a rejection.

## Acceptance Criteria

- [ ] All existing request-handler tests pass after the extraction.
- [ ] The extracted validator module has its own characterization tests
      covering the four behaviors above.
- [ ] No request-handler call site references the inline validation code.
- [ ] Public response shapes are unchanged (assert against a golden body).

## Scope

### In scope

- `src/auth/request_handler.py` (extraction site)
- `src/auth/token_validator.py` (new module)
- `tests/auth/test_token_validator.py` (new characterization tests)

### Out of scope

- Adding new authentication mechanisms.
- Changing the public response shape.
- Refactoring the audit-logging code path itself (that is the parent feature).

## Affected td-NNN rows

| td-NNN | location | class | status-before | flipped-to |
|--------|----------|-------|---------------|------------|
| td-NNN | `src/auth/request_handler.py` | complexity | open | in-flight |

## Verifier Bypass Criteria

```yaml
- id: behavior-preservation-tests-green
  description: All characterization tests added in the mini-pipeline pass
  check: test-suite-result == green
- id: scope-respected
  description: All file changes fall within `## Scope` `### In scope`
  check: "git diff --name-only is a subset of in-scope-paths"
```

## Loop-Back Conditions

```yaml
- id: blast-radius-exceeded
  description: Refactor touched files outside the declared `## Scope`
  check: "git diff --name-only is not a subset of in-scope-paths"
- id: behavior-preservation-failed
  description: A characterization test fails or a behavior the architect
                declared preserved is observably changed
  check: characterization-tests-result == red
```

## Resolved Tech Debt

_(populated at mini-pipeline completion; empty until then)_
