# Pre-Refactor Plan: extract-auth-validator-malformed

<!--
GOLDEN BAD-CASE for sentinel `PR01` (Pre-Refactor Plan Integrity dimension).

This fixture is well-formed in every section EXCEPT it omits the required
`## Loop-Back Conditions` section. The sentinel must FAIL on it. The
orchestrator's YAML parser must raise PreRefactorYamlError(error_id=
"missing-section").

Per `rules/swe/gate-liveness.md`, a gate is verified only by a paired
known-bad input that the gate flags — that is exactly what this fixture
provides.
-->

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

## Scope

### In scope

- `src/auth/request_handler.py` (extraction site)
- `src/auth/token_validator.py` (new module)
- `tests/auth/test_token_validator.py` (new characterization tests)

### Out of scope

- Adding new authentication mechanisms.
- Changing the public response shape.
- Refactoring the audit-logging code path itself.

## Affected td-NNN rows

| td-NNN | location | class | status-before | flipped-to |
|--------|----------|-------|---------------|------------|
| td-NNN | `src/auth/request_handler.py` | complexity | open | in-flight |

## Verifier Bypass Criteria

```yaml
- id: behavior-preservation-tests-green
  description: All characterization tests added in the mini-pipeline pass
  check: test-suite-result == green
```

## Resolved Tech Debt

_(populated at mini-pipeline completion; empty until then)_
