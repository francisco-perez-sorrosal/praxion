---
paths:
- tests/**
- test_*
- '*_test.*'
- '*_spec.*'
- '**/*_test.py'
- '**/test_*.py'
- '**/*.test.ts'
- '**/*.test.js'
- '**/*.spec.ts'
- '**/*.spec.js'
core: false
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

- No `sleep()`, `time.time()`, or wall-clock dependencies -- use time-freezing libraries (e.g., `freezegun` in Python, `jest.useFakeTimers()` in JS) or injected clocks
- No random values without fixed seeds -- use explicit seeds or deterministic generators

**ML training-loop exception:** The determinism requirement above does NOT apply to stochastic
operations inside ML training-loop code — data shuffles, dropout, `torch.cuda` non-determinism
(e.g., `cudnn.benchmark = True`), and parameter initialization are intentionally stochastic and
must not be flagged as violations. This exception applies only to:

- The training loop itself (the per-step `optimizer.step()`-bearing function)
- Inference/eval code where dropout is disabled but other stochasticity may persist

The determinism requirement is RETAINED for data-pipeline code (loading, preprocessing,
augmentation), model-architecture code (layer definitions, weight initialization shapes), and
evaluation/metric-computation code. For ML training stochasticity, apply the metric-threshold
model in `rules/ml/eval-driven-verification.md` instead.

- No reliance on dictionary ordering, filesystem sort order, or other platform-variant behavior
- No tests that pass "most of the time" -- flaky tests are broken tests

### No Hardcoded Paths

Never hardcode absolute paths or assume a specific working directory.

- Use the framework's temporary directory mechanism (e.g., `tmp_path` in pytest, `os.tmpdir()` in Node, `t.TempDir()` in Go)
- Use path abstractions relative to a known root, not string concatenation with separators
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
- Shared test data lives in shared fixture files (e.g., `conftest.py` in pytest, setup modules in Jest) or dedicated factory modules, not copy-pasted across tests

### Fixtures Under Gitignored Paths

A committed bad-case fixture only reaches a fresh checkout or CI if git tracks its path. When the input shape a test exercises lives under a gitignored location (e.g. an ephemeral `.ai-work/<slug>/`-shaped directory), a fixture committed there passes locally yet is invisible after a clean clone -- the test sees an empty directory and its failure path never triggers (a silent false green).

- Build such inputs at runtime in the framework temp dir (`tmp_path`, `t.TempDir()`, `os.tmpdir()`) -- gitignore constrains git, not filesystem reads, so the runtime construction is itself the proof the test can actually fail
- Choose the fixture strategy by whether the input's location is git-tracked: a committed fixture when the path is tracked, runtime construction when it is ignored

### Mocking Boundaries

Mock at system boundaries: external APIs, databases, file systems, network calls, clocks.

- Never mock the unit under test
- Never mock internal implementation details (private methods, internal data structures)
- Prefer fakes (in-memory implementations) over mocks when the boundary has complex behavior
- Integration tests that hit real external systems must be explicitly marked (e.g., `@pytest.mark.integration` in pytest, test file naming convention in other frameworks)

### No Logic in Tests

Tests are straightforward sequences -- no conditionals, loops, or branching logic in test bodies.

- No `if`/`else` in test functions -- each branch should be a separate test
- No `for` loops asserting over collections -- use the framework's parametrize/data-driven mechanism or dedicated assertions
- Complex setup logic belongs in fixtures or helper functions, not in the test body

### Error Path Testing

Test error cases explicitly, not just the happy path.

- Verify the specific error type or exception class, not just "an error was raised"
- Verify error messages contain actionable information -- assert on message content when the message is part of the contract
- Test boundary conditions: empty inputs, None/null values, maximum sizes, malformed data

### Cleanup

Tests leave no trace -- no temporary files, database records, environment variable changes, or monkey-patches persist after the test completes.

- Use context managers (`with`) or teardown fixtures for resource cleanup
- Prefer framework-provided temporary directory mechanisms over manual file creation and deletion
- Global state modifications (environment variables, module-level caches) must be reverted in teardown, not left for other tests to inherit

### No Commented-Out Tests

Never commit commented-out or skipped-without-reason tests. A disabled test is invisible debt.

- Commented-out test code must be deleted, not preserved
- Skip/xfail markers (e.g., `@pytest.mark.skip`, `@xfail`, `it.skip()`) require a reason string explaining when the skip can be removed
- If a test is no longer relevant, delete it — version control is the history

### Assertion Messages

Include assertion messages when the failure output alone would be ambiguous.

- Not needed for simple equality checks (`assert result == 42` is self-explanatory)
- Required when asserting on opaque booleans, container membership, or complex conditions where the default failure message does not explain what went wrong

### Test File Organization

Test files mirror the source structure they test.

- `src/module/handler.py` → `tests/module/test_handler.py`
- Shared fixtures live in the framework's fixture sharing mechanism (e.g., `conftest.py` in pytest, setup files in Jest) at the appropriate scope level
- Test utilities and custom assertions live in `tests/helpers/` or `tests/support/`, never in production code
