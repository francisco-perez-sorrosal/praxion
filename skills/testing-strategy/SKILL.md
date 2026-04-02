---
name: testing-strategy
description: >
  Language-independent testing knowledge: test strategy selection, test pyramid,
  mocking philosophy, fixture and test data patterns, test isolation, coverage
  approach, property-based testing, and naming conventions. Use when deciding
  test strategy, choosing between unit and integration and e2e tests, designing
  mocking boundaries, architecting fixtures, evaluating test coverage philosophy,
  or assessing property-based testing applicability. Also activates for test
  architecture, testing methodology, test pyramid, and test isolation questions.
allowed-tools: [Read, Glob, Grep, Bash]
compatibility: Claude Code
---

# Testing Strategy

Language-independent testing knowledge for making strategic testing decisions: what to test, at which level, with what techniques.

**Content boundary:** This skill provides *strategy knowledge* (what approaches exist, when to apply them). The [test-engineer](../../agents/test-engineer.md) agent provides *execution workflow* (how to implement tests step-by-step within a pipeline). The [testing-conventions](../../rules/swe/testing-conventions.md) rule provides *declarative constraints* (what must be true about test code).

**Satellite files** (loaded on-demand):

- [references/python-testing.md](references/python-testing.md) -- advanced pytest patterns: conftest architecture, hypothesis property-based testing, fixture composition, coverage strategy, plugin ecosystem

Future language references (e.g., `references/typescript-testing.md`, `references/rust-testing.md`) are added here without changes to this file's body.

## Gotchas

- **Over-mocking hides integration bugs.** Mocking internal collaborators makes tests pass in isolation while the real system fails. Mock only at system boundaries (external APIs, databases, file systems). If a unit test needs five mocks to work, the code under test has too many responsibilities.
- **Flaky tests from shared mutable state.** Tests that pass individually but fail when run together almost always share mutable state -- class-level variables, module globals, database rows left behind. Each test must create its own state and clean up after itself.
- **Coverage theater.** Chasing a line coverage target (e.g., 90%) incentivizes testing trivial code (getters, framework glue) while ignoring complex logic that is hard to cover. Use coverage to *discover gaps*, not to set targets. Mutation testing is a better proxy for test suite quality.
- **Testing implementation instead of behavior.** Tests that assert on internal method calls, private state, or exact SQL queries break on every refactor without catching real bugs. Test through public interfaces and assert on observable outcomes.
- **Sleep in tests.** `time.sleep()` and wall-clock waits make tests slow and non-deterministic. Use time-freezing libraries, explicit event waits, or polling with short timeouts instead.
- **Ignoring the project's package manager.** When a project uses a package or environment manager (pixi, uv, pnpm, yarn, etc.), run tests through it (e.g., `pixi run pytest`, `uv run pytest`, `pnpm exec vitest`) to ensure the correct virtual environment and dependencies are active. Detect the runner from lockfiles and config (`pixi.toml`, `uv.lock`, `pnpm-lock.yaml`, etc.) before invoking tests. If no runner is detected, invoking the test tool directly is fine.

## Test Strategy Selection

Choose the test type that matches the scope of the behavior under test. Default to unit tests; escalate only when behavior lives in the interaction between components.

### The Test Pyramid -- Pragmatically

| Level | Scope | Speed | Use When |
|-------|-------|-------|----------|
| **Unit** | Single function or class, no I/O | Fast (ms) | Pure logic, data transformations, business rules, algorithms |
| **Integration** | Multiple components or real I/O | Moderate (s) | Database queries, API client wiring, message queue handlers, middleware chains |
| **E2E / System** | Full stack, user-visible behavior | Slow (s-min) | Critical user journeys, smoke tests, deployment verification |
| **Contract** | Service boundary agreements | Fast | Consumer/provider APIs, schema compatibility, event formats |

### Decision Criteria

- **Could a unit test catch this bug?** If yes, write a unit test -- it is faster and more precise.
- **Does the behavior emerge from component interaction?** If yes, integration test. Mock only the outermost boundary (e.g., the actual HTTP call, not the service layer).
- **Is this a critical user path where failure means revenue loss or data corruption?** Add an E2E test in addition to lower-level tests, not instead of them.
- **Is this an API consumed by another team or service?** Add a contract test to catch schema drift independently of full integration.

## Test Isolation

Tests must be independent, deterministic, and order-insensitive.

- **No shared mutable state.** Each test creates its own preconditions. Shared *immutable* fixtures (e.g., configuration constants, schema definitions) are fine.
- **No execution order dependencies.** Tests must pass when run individually, in any order, or in parallel.
- **No wall-clock dependencies.** Freeze time or inject clocks. Never rely on "now" being a specific value.
- **No filesystem side effects.** Use temporary directories and clean up. Never write to project paths.
- **No network calls in unit tests.** External calls belong in integration tests, behind explicit markers.

## Mocking Philosophy

Mock at system boundaries. Use real collaborators everywhere else.

### Test Doubles Taxonomy

| Double | Purpose | When to Use |
|--------|---------|-------------|
| **Stub** | Returns canned data, no behavior verification | Replacing a dependency whose output you control (e.g., config provider) |
| **Spy** | Records calls for later assertion | Verifying that a side effect occurred (e.g., email sent) without replacing behavior |
| **Mock** | Pre-programmed expectations that fail if not met | Strict protocol verification (rarely needed -- prefer spies) |
| **Fake** | Working implementation with shortcuts | Replacing expensive infrastructure (in-memory database, local file store) |

### Boundary Rules

- **Mock what you do not own** -- external APIs, third-party services, infrastructure.
- **Wrap before mocking** -- if you mock a third-party type directly, your tests are coupled to its interface. Wrap it behind your own abstraction, then mock *your* abstraction.
- **Never mock the system under test** -- if you have to mock part of the class you are testing, the class has too many responsibilities.
- **Prefer fakes over mocks for stateful dependencies** -- an in-memory repository is more realistic than a mock that returns canned queries.

## Fixture and Test Data Patterns

Build test data with intent. Every value in a test fixture should be there for a reason.

- **Builders / Factories** -- construct test objects with sensible defaults, overriding only what the test cares about. This keeps tests focused on the relevant fields and insulates them from constructor changes.
- **Object mothers** -- named factory methods for common personas or scenarios (`expired_subscription()`, `admin_user()`). Useful when the same entity configuration appears across many tests.
- **Parameterized data** -- use the test framework's parametrize mechanism to test across equivalence partitions without duplicating test logic. Each parameter set should have a descriptive ID.
- **Minimal data** -- do not construct a full object when only two fields matter. If the constructor requires twenty fields, that is a signal the object is too large -- but in the meantime, use a builder with defaults.

## Coverage Philosophy

Coverage is a discovery tool, not a quality metric.

- **Use coverage to find untested code paths** -- particularly branches in complex logic, error handlers, and edge cases. Low coverage in a critical module is a signal. High coverage in a trivial module is noise.
- **Do not set coverage targets as gates.** A 90% target incentivizes testing boilerplate. A 60% codebase with mutation-tested critical paths is healthier than a 95% codebase with assertion-free tests.
- **Mutation testing** is the better proxy -- it verifies that tests actually detect code changes. If removing a line or flipping a condition does not fail any test, the test suite has a gap regardless of line coverage.
- **Exclude what does not benefit from testing** -- framework boilerplate, generated code, thin wrappers, CLI entry points. Configure exclusions explicitly rather than writing hollow tests to satisfy a metric.

## Property-Based Testing

Property-based testing generates random inputs and verifies that invariants hold across all of them. It excels at finding edge cases that example-based tests miss.

### When It Adds Value

- **Data transformations**: encode/decode, serialize/deserialize, parse/format -- the round-trip property (`decode(encode(x)) == x`) catches charset bugs, boundary overflows, and off-by-one errors.
- **Invariants**: sorted output stays sorted, total always equals sum of parts, valid input produces valid output.
- **Parsers and validators**: generate inputs across the full domain space instead of hand-picking examples.
- **Stateful protocols**: model the system as a state machine and generate random operation sequences to find illegal state transitions.

### When to Skip

- **UI rendering** -- visual correctness is not expressible as an algebraic property.
- **Integration tests** -- property-based tests are slow by nature; combining them with real I/O compounds the cost.
- **Simple CRUD** -- if the behavior is "store and retrieve," an example-based test is clearer and sufficient.

## Naming and Organization

### Naming Tests

Name tests after the behavior they specify, not the method they call. A reader should understand the guarantee without opening the implementation.

- **Pattern**: `test_<context>_<action>_<expected_outcome>` (e.g., `test_expired_token_returns_401`)
- **Avoid**: numbered tests (`test_validate_3`), implementation names (`test_calculate_discount_uses_percentage`), vague names (`test_it_works`)

### Organizing Test Files

- **Mirror production structure** -- tests for `payments/refund_policy.py` live in `tests/payments/test_refund_policy.py`.
- **DAMP over DRY** -- duplicate setup when it makes a test readable in isolation. Extract shared *mechanics* (builders, custom assertions) into helpers, but keep the *scenario* inline.
- **Shared fixtures** -- place reusable fixtures in the nearest common ancestor directory. Avoid global fixtures that every test inherits but few use.
- **Test utilities** -- when helper functions grow beyond a few lines, extract them into a `tests/helpers/` or `tests/support/` directory. Do not put test utilities in production code.

## Related Skills

- **[python-development](../python-development/SKILL.md)** -- basic pytest patterns, pyproject.toml configuration, running tests
- **[code-review](../code-review/SKILL.md)** -- test coverage assessment as part of code review workflow
- **[agent-evals](../agent-evals/SKILL.md)** -- evaluation patterns for non-deterministic AI agent behavior (distinct from traditional testing)
- **[refactoring](../refactoring/SKILL.md)** -- test suite restructuring follows refactoring methodology (behavior preservation, small steps)
