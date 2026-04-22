# Spec Format Guide

Detailed format reference for behavioral specifications. Covers the `When/and/the system/so that` pattern with examples, rationale for format choices, traceability matrix template, persistent spec template, and edge case handling. Reference material for the [spec-driven-development](../SKILL.md) skill.

## Behavioral Specification Format

Each requirement follows the `When/and/the system/so that` pattern with a unique ID scoped to the feature.

### REQ-01: Expired session rejected on API request

**When** a client sends an API request with an expired session token
**and** the token has been expired for more than the grace period
**the system** returns a 401 Unauthorized response with a `session_expired` error code
**so that** the client knows to re-authenticate rather than retrying the same request

### REQ-02: Workflow transitions to review state

**When** all required approvals have been collected for a document
**the system** transitions the workflow state from `pending_approval` to `in_review` and notifies the assigned reviewer
**so that** the review process begins without manual intervention

### REQ-03: Invalid input rejected at API boundary

**When** a client submits a create request with a payload that fails schema validation
**and** the payload contains fields outside the allowed set
**the system** returns a 422 response listing each validation error with the field name and constraint violated
**so that** the client can fix all errors in a single retry rather than discovering them one at a time

### REQ-04: Resource not found returns stable error

**When** a client requests a resource by ID that does not exist in the datastore
**the system** returns a 404 response with a machine-readable error code and the requested ID echoed back
**so that** the client can distinguish "not found" from "not authorized" and log the missing ID for debugging

### REQ-05: Scheduled job retries on transient failure

**When** a scheduled background job fails with a transient error (network timeout, connection reset)
**and** the retry count has not exceeded the configured maximum
**the system** re-enqueues the job with exponential backoff and increments the retry counter
**so that** transient infrastructure issues do not cause permanent data processing gaps

## Why This Format

### Comparison with EARS

EARS (Easy Approach to Requirements Syntax) classifies requirements into behavior types: ubiquitous ("The system shall..."), event-driven ("When X, the system shall..."), state-driven ("While X, the system shall..."), optional ("Where X, the system shall..."), and unwanted ("If X, the system shall not...").

**Why the i-am format diverges:**

- Behavior type classification adds formalism that the ecosystem does not need -- the trigger description already implies whether the behavior is event-driven, state-driven, or boundary-related
- EARS' "shall" phrasing is suited to contractual/regulatory contexts, not iterative agent-driven development
- The `so that` clause (absent from EARS) captures intent, which is what agents need to make traceoff decisions during implementation

### Comparison with Given/When/Then

Given/When/Then (GWT) is the standard BDD notation used by Cucumber, Behave, and SpecFlow. A GWT scenario specifies preconditions (Given), actions (When), and assertions (Then).

**Why the i-am format diverges:**

- GWT couples to BDD test frameworks -- it is a test specification format, not a behavioral requirement format
- The `so that` clause serves a different purpose than `Then`: it documents *why* the behavior matters, not just *what* is observable
- GWT's `Given` clause often duplicates system state that the `When` trigger makes implicit
- Our `and` clause is optional and covers preconditions without a separate keyword

The i-am format sits between architecture and test design. GWT is downstream -- the test-engineer translates requirements into test assertions.

## Traceability Matrix Template

The verifier produces this matrix in `VERIFICATION_REPORT.md` by reading `.ai-work/<task-slug>/traceability.yml` (pipeline in flight) or the archived SPEC's matrix (post-archive). Test names describe behavior; the YAML holds the REQ-to-test mapping — see [`id-citation-discipline.md`](../../../rules/swe/id-citation-discipline.md) for why test names never carry REQ prefixes.

```markdown
## Spec Conformance

| Requirement | Test(s) | Implementation | Status |
|-------------|---------|----------------|--------|
| REQ-01 | tests/auth/test_session.py::test_expired_session_returns_401 | src/auth/session.py::validate() | PASS |
| REQ-02 | tests/workflow/test_engine.py::test_workflow_transitions_to_review | src/workflow/engine.py::advance() | PASS |
| REQ-03 | tests/api/test_validation.py::test_invalid_input_returns_422 | src/api/validation.py::validate_payload() | PASS |
| REQ-04 | (none) | src/api/resources.py::get_by_id() | UNTESTED |
| REQ-05 | tests/jobs/test_scheduler.py::test_transient_failure_retries | src/jobs/scheduler.py::retry() | FAIL |
```

**Column definitions:**

- **Requirement**: the `REQ-NN` identifier from the behavioral specification
- **Test(s)**: test file path + test function name (e.g., `tests/auth/test_session.py::test_expired_token_returns_401`) as recorded in `traceability.yml`; `(none)` if no test recorded
- **Implementation**: source file and function/method as recorded in `traceability.yml`
- **Status**: `PASS` (test exists and passes per `TEST_RESULTS.md`), `FAIL` (test fails or implementation missing), `UNTESTED` (no test recorded for this requirement)

## Persistent Spec Template

Archived to `.ai-state/specs/SPEC_<feature-name>_YYYY-MM-DD.md` during the end-of-feature workflow.

```markdown
# Spec: [Feature Name]

**Created**: 2026-03-13T14:30:00Z
**Pipeline run**: 2026-03-12 to 2026-03-13
**Status**: completed
**Complexity**: medium

## Requirements

### REQ-01: [Title]

**When** [trigger]
**and** [optional precondition]
**the system** [response]
**so that** [outcome]

### REQ-02: [Title]

**When** [trigger]
**the system** [response]
**so that** [outcome]

## Traceability

| Requirement | Test(s) | Implementation | Status |
|-------------|---------|----------------|--------|
| REQ-01 | tests/path/test_foo.py::test_behavioral_name | src/path/foo.py::function() | PASS |
| REQ-02 | tests/path/test_bar.py::test_another_behavior | src/path/bar.py::function() | PASS |

## Key Decisions

- **[systems-architect] Decision title**: What was decided. **Why**: rationale. **Alternatives**: rejected options.
- **[implementer] Decision title**: What was decided. **Why**: rationale. **Alternatives**: rejected options.
```

**Header fields:**

- **Created**: ISO 8601 timestamp of archival
- **Pipeline run**: date range from plan start to verification completion
- **Status**: `completed` (normal), `partial` (feature incomplete but archived for reference)
- **Complexity**: the tier classification (`medium` or `large`)

## Edge Cases and Ambiguity Resolution

### Optional `and` clauses

Use `and` when the precondition is not implicit in the trigger. Fold into the trigger when the precondition is inseparable from it.

- **Use `and`**: "When a client sends a request **and** the rate limit has been exceeded" -- the rate limit state is independent of the request itself
- **Fold in**: "When a client sends an expired token" -- expiration is a property of the token, not a separate condition

### Multiple `so that` outcomes

Split into separate requirements when outcomes serve different stakeholders or testing concerns. Keep compound when outcomes are inseparable consequences of the same behavior.

- **Split**: REQ-01 "so that the client re-authenticates" and REQ-02 "so that the audit log records the rejection" -- different testing concerns
- **Keep compound**: "so that the client knows to re-authenticate rather than retrying" -- single coherent outcome

### Compound requirements

One REQ per distinct behavior, not one REQ per user story. A user story ("As a user, I can reset my password") may produce multiple requirements: REQ-01 (reset email sent), REQ-02 (token validated), REQ-03 (password updated).

The test for correct granularity: if two behaviors could independently pass or fail, they belong in separate requirements.

### Negative requirements

Express what the system does, not what it avoids. Frame negatives as the positive behavior that prevents the unwanted outcome.

- **Avoid**: "the system does NOT allow unauthenticated access"
- **Prefer**: "the system returns 401 Unauthorized for requests without valid credentials"

When a negative is truly the clearest expression, use it -- but ensure the `so that` clause explains what the prevention achieves.

## Spec Delta Template

For brownfield features with prior archived specs, the systems-architect produces `SPEC_DELTA.md` in `.ai-work/<task-slug>/`. See the [SDD skill](../SKILL.md#spec-delta-format) for activation conditions and lifecycle.

```markdown
# Spec Delta: [Feature Name]

**Prior spec**: SPEC_<name>_YYYY-MM-DD.md
**Tier**: Standard | Full
**Baseline confidence**: High | Low (staleness caveat)

## Staleness Warning

Prior spec requirements with uncertain baselines (SH03 FAIL):
- REQ-03: [reason for uncertainty -- e.g., referenced function moved, behavior may have changed]

## Added Requirements

### REQ-04: [Title]

**When** [trigger]
**and** [optional precondition]
**the system** [response]
**so that** [outcome]

**Rationale**: [Why this requirement is new -- what gap or opportunity it addresses]

## Modified Requirements

### REQ-01: [New Title] (was: [Old Title])

**Before** (from SPEC_<name>_YYYY-MM-DD.md):
> **When** [old trigger]
> **the system** [old response]
> **so that** [old outcome]

**After**:
**When** [new trigger]
**the system** [new response]
**so that** [new outcome]

**Change rationale**: [What changed and why -- behavioral difference, not implementation detail]

## Removed Requirements

### ~REQ-02: [Title]~ (from SPEC_<name>_YYYY-MM-DD.md)

**Removal rationale**: [Why this behavior is no longer needed]
**Cleanup needed**: Yes | No -- [whether implementation artifacts (code, tests, config) remain]
```

**Format conventions**:

- **Added requirements** use the standard `When/and/the system/so that` format with fresh REQ IDs scoped to the new feature (not continuing the old spec's numbering)
- **Modified requirements** show before/after with blockquoted "before" text to visually distinguish prior from new. The `(was: [Old Title])` annotation preserves the cross-feature mapping
- **Removed requirements** use strikethrough on the REQ ID and title. The cleanup flag tells the planner whether dead code/tests need explicit removal steps
- **Baseline confidence** signals delta reliability: High when the sentinel's last SH03 check passed for the prior spec, Low when SH03 shows FAIL or no recent sentinel report exists
- **Staleness Warning** is conditional — omit the section entirely when baseline confidence is High

**When the delta is empty**: if comparison reveals no behavioral changes (pure refactoring or implementation-only changes), skip `SPEC_DELTA.md` entirely. The absence of a delta signals "no behavioral change" to the planner and verifier.
