---
paths:
  - "tests/**"
  - "test_*"
  - "*_test.*"
  - "*_spec.*"
  - "**/*_test.py"
  - "**/test_*.py"
  - "**/*.test.ts"
  - "**/*.test.js"
  - "**/*.spec.ts"
  - "**/*.spec.js"
---

## Testing Conventions

Declarative constraints for test code. These define what must be true about tests -- not how to achieve it. For strategy and methodology, load the [testing-strategy](../../skills/testing-strategy/SKILL.md) skill.

### Naming

Test functions describe the behavior being verified, not the method being called.

- Good: `test_rejects_empty_input`, `test_expired_token_returns_401`, `test_retries_on_transient_failure`
- Bad: `test_validate`, `test_process_3`, `test_handler_method`

Names read as sentences: subject + condition + expected outcome. A reader should understand what broke from the test name alone, without reading the test body.

### Isolation

Each test runs independently. No shared mutable state between tests. No ordering dependencies. Tests must pass when run individually, in any order, or in parallel.

- No module-level mutable variables modified by tests
- No database records or files left behind for other tests to consume
- No assumptions about which test ran before or after

### Determinism

Tests produce the same result on every run, regardless of time, timezone, or environment.

- No `sleep()`, `time.time()`, or wall-clock dependencies -- use time freezing (`freezegun`, `timemachine`) or injected clocks
- No random values without fixed seeds -- use explicit seeds or deterministic generators
- No reliance on dictionary ordering, filesystem sort order, or other platform-variant behavior
- No tests that pass "most of the time" -- flaky tests are broken tests

### No Hardcoded Paths

Never hardcode absolute paths or assume a specific working directory.

- Use `tmp_path` (pytest), `tempfile` fixtures, or equivalent temporary directory mechanisms
- Use `pathlib.Path` relative to a known root, not string concatenation with `/`
- Test data files live in a dedicated directory (`tests/fixtures/`, `tests/data/`) referenced via relative paths

### Arrange-Act-Assert

Each test has three clear phases: setup, execution, verification.

- One logical assertion per test -- multiple `assert` statements are acceptable when they verify a single behavior (e.g., checking both status code and response body of one request)
- Separate tests for separate behaviors, even if they share setup
- When setup is substantial, extract to fixtures or helper functions -- not inline in every test

### Test Data

Use factories, builders, or fixture functions for complex test objects.

- Only include fields relevant to the behavior under test -- minimal data, not exhaustive
- Avoid inline dictionaries or constructors with many positional arguments
- Shared test data lives in conftest files or dedicated factory modules, not copy-pasted across tests

### Mocking Boundaries

Mock at system boundaries: external APIs, databases, file systems, network calls, clocks.

- Never mock the unit under test
- Never mock internal implementation details (private methods, internal data structures)
- Prefer fakes (in-memory implementations) over mocks when the boundary has complex behavior
- Integration tests that hit real external systems must be explicitly marked (e.g., `@pytest.mark.integration`)

### No Logic in Tests

Tests are straightforward sequences -- no conditionals, loops, or branching logic in test bodies.

- No `if`/`else` in test functions -- each branch should be a separate test
- No `for` loops asserting over collections -- use parametrize or dedicated assertions
- Complex setup logic belongs in fixtures or helper functions, not in the test body

### Error Path Testing

Test error cases explicitly, not just the happy path.

- Verify the specific error type or exception class, not just "an error was raised"
- Verify error messages contain actionable information -- assert on message content when the message is part of the contract
- Test boundary conditions: empty inputs, None/null values, maximum sizes, malformed data

### Cleanup

Tests leave no trace -- no temporary files, database records, environment variable changes, or monkey-patches persist after the test completes.

- Use context managers (`with`) or teardown fixtures for resource cleanup
- Prefer `tmp_path` and scoped fixtures over manual file creation and deletion
- Global state modifications (environment variables, module-level caches) must be reverted in teardown, not left for other tests to inherit

### No Commented-Out Tests

Never commit commented-out or skipped-without-reason tests. A disabled test is invisible debt.

- Commented-out test code must be deleted, not preserved
- `@pytest.mark.skip` and `@xfail` require a reason string explaining when the skip can be removed
- If a test is no longer relevant, delete it — version control is the history

### Assertion Messages

Include assertion messages when the failure output alone would be ambiguous.

- Not needed for simple equality checks (`assert result == 42` is self-explanatory)
- Required when asserting on opaque booleans, container membership, or complex conditions where the default failure message does not explain what went wrong

### Test File Organization

Test files mirror the source structure they test.

- `src/module/handler.py` → `tests/module/test_handler.py`
- Shared fixtures live in `conftest.py` at the appropriate scope level (directory-level for shared, root-level for global)
- Test utilities and custom assertions live in `tests/helpers/` or `tests/utils/`, never in production code
