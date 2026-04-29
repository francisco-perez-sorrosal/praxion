# Python Testing with pytest

Advanced pytest patterns, fixture architecture, property-based testing, and plugin ecosystem. Reference material for the [Testing Strategy](../SKILL.md) skill.

**Runner awareness**: When the project uses a package or environment manager, invoke pytest through it — `pixi run pytest` (if `pixi.toml` or `[tool.pixi]`), `uv run pytest` (if `uv.lock` or `[tool.uv]`). If no runner is detected, bare `pytest` or `python -m pytest` is fine. Commands in this reference use `<runner> pytest` as placeholder — substitute with the project's actual runner or omit the prefix if none is configured.

## pytest Fundamentals

pytest discovers tests by scanning for `test_*.py` / `*_test.py` files, collecting `test_`-prefixed functions and `Test`-prefixed classes (without `__init__`).

**Assertion rewriting**: pytest rewrites `assert` at import time for detailed failure messages. This only works in test modules -- for helper libraries, call `pytest.register_assert_rewrite("my_helpers")`.

**Key flags**:

| Flag | Purpose |
|------|---------|
| `-x` | Stop on first failure |
| `-k "expr"` | Name expression filter (`-k "auth and not slow"`) |
| `-m "marker"` | Run by marker (`-m "not integration"`) |
| `--lf` / `--sw` | Re-run last failed / stepwise resume |
| `--tb=short` | Shorter tracebacks for large suites |

**Exit codes**: 0 = passed, 1 = failed, 2 = interrupted, 3 = internal error, 4 = usage error, 5 = no tests collected.

## Fixture Architecture

### Scope Hierarchy

Five scopes from narrowest to widest: `function` (default) < `class` < `module` < `package` < `session`. A wider-scoped fixture **cannot** depend on a narrower-scoped one (`ScopeMismatch` error).

```python
@pytest.fixture(scope="session")
def database_connection():
    conn = create_test_database()
    yield conn
    conn.drop()

@pytest.fixture  # function scope -- depends on wider session scope
def clean_tables(database_connection):
    yield database_connection
    database_connection.truncate_all()
```

### conftest.py Layering

`conftest.py` files form a hierarchy matching the directory tree. Deeper conftest fixtures override parent ones.

```text
tests/
    conftest.py              # Root: database, app client
    unit/conftest.py         # Lightweight, no I/O
    integration/conftest.py  # Real database, API stubs
```

Place fixtures in the nearest conftest covering all tests that need them. Avoid a bloated root conftest.

### autouse, Yield, and Built-in Fixtures

- **`autouse=True`**: Applies to every test in scope without explicit request. Use only for cleanup/environment reset -- never for data fixtures.
- **Yield fixtures**: Setup runs before `yield`, teardown after. Replaces `request.addfinalizer`.
- **`tmp_path`**: Per-test temporary `Path`. **`tmp_path_factory`**: Session-scoped, for creating multiple temp directories.

## Parametrize Patterns

### Data-Driven Tests with IDs

```python
@pytest.mark.parametrize("status, should_retry", [
    pytest.param(429, True, id="rate-limited"),
    pytest.param(500, True, id="server-error"),
    pytest.param(400, False, id="client-error"),
])
def test_retry_decision(status, should_retry):
    assert decide_retry(status) == should_retry
```

Always use `pytest.param(..., id=...)` for readable test output with complex objects.

### Indirect Fixtures

Route parameters through a fixture for setup/teardown:

```python
@pytest.fixture
def db_with_schema(request):
    db = create_database(schema=request.param)
    yield db
    db.drop()

@pytest.mark.parametrize("db_with_schema", ["v1", "v2"], indirect=True)
def test_migration(db_with_schema):
    assert db_with_schema.is_healthy()
```

### Combining Decorators

Stacking `@pytest.mark.parametrize` produces a cartesian product:

```python
@pytest.mark.parametrize("protocol", ["http", "https"])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_requests(protocol, method):  # Runs 4 times
    assert make_request(protocol, method).ok
```

## Markers and Selection

### Built-in Markers

| Marker | Purpose |
|--------|---------|
| `skip(reason="...")` | Unconditionally skip |
| `skipif(condition, reason="...")` | Conditional skip |
| `xfail(reason="...", strict=True)` | Expected failure; `strict` fails if it unexpectedly passes |

### Custom Markers and Strict Config

```python
@pytest.mark.slow
def test_full_pipeline(): ...

@pytest.mark.integration
def test_database_roundtrip(): ...
```

Run by marker: `<runner> pytest -m "not slow"`, `<runner> pytest -m "integration or smoke"`.

Enforce registration to catch typos:

```toml
[tool.pytest.ini_options]
markers = [
    "slow: deselect with '-m \"not slow\"'",
    "integration: requires external services",
    "smoke: critical path verification",
]
addopts = "--strict-markers"
```

## Property-Based Testing with Hypothesis

### @given, @example, and Strategies

```python
from hypothesis import given, example, settings
from hypothesis import strategies as st

@given(st.text())
def test_roundtrip(text):
    assert decode(encode(text)) == text

@given(st.lists(st.integers()))
@example([])  # Always include edge cases explicitly
def test_sorted_output(items):
    assert all(a <= b for a, b in zip(my_sort(items), my_sort(items)[1:]))
```

### Strategy Composition

Build complex inputs with `@st.composite`:

```python
@st.composite
def user_strategy(draw):
    return User(
        name=draw(st.text(min_size=1, max_size=100)),
        age=draw(st.integers(min_value=0, max_value=150)),
        email=draw(st.emails()),
    )
```

### @settings and Profiles

Control generation per-test with `@settings(max_examples=500, deadline=timedelta(seconds=5))`. Configure environment profiles in `conftest.py`:

```python
settings.register_profile("ci", max_examples=1000)
settings.register_profile("dev", max_examples=50)
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "dev"))
```

### Stateful Testing

Model systems as state machines with `RuleBasedStateMachine` to discover invalid state transitions via random operation sequences. Define `@initialize` for setup and `@rule` methods for operations with strategy-generated arguments.

### Example Database

Hypothesis stores failing examples in `.hypothesis/` and replays them on subsequent runs. Add `.hypothesis/` to `.gitignore` -- it is a local cache.

## Coverage Strategy

### pytest-cov and Branch Coverage

```toml
[tool.coverage.run]
source = ["src"]
branch = true

[tool.coverage.report]
fail_under = 70
show_missing = true
exclude_lines = ["pragma: no cover", "if TYPE_CHECKING:", "raise NotImplementedError", "@overload"]
```

Run: `<runner> pytest --cov --cov-report=term-missing`.

- **Branch coverage** (`branch = true`): Checks both sides of every conditional -- catches missing `else` branches that line coverage misses
- **`--cov-fail-under` as ratchet**: Set to current level and only increase; goal is preventing regression, not hitting a target
- **Exclusions**: Type-checking blocks, abstract stubs, generated code. Be explicit in `exclude_lines` rather than scattering `# pragma: no cover`

## Async Testing

Set `asyncio_mode = "auto"` in `[tool.pytest.ini_options]` so all `async def test_*` functions run as async tests without `@pytest.mark.asyncio`.

**Pitfalls**:
- Async fixtures can only be used by async tests -- provide separate sync/async fixtures when both are needed
- pytest-asyncio creates a new event loop per test; for shared session-scoped async fixtures, configure `loop_scope = "session"` (0.23+)
- Use `pytest-timeout` to catch silently hanging async tests

## Plugin Ecosystem

| Plugin | Purpose | When to Use |
|--------|---------|-------------|
| **pytest-mock** | `mocker` fixture wrapping `unittest.mock` | Cleaner mock syntax with automatic per-test cleanup |
| **pytest-xdist** | Parallel execution (`-n auto`) | Large suites with fully isolated tests |
| **pytest-randomly** | Randomizes test order | Detecting order-dependent tests |
| **pytest-timeout** | Per-test time limits | Preventing hung tests, especially async |
| **pytest-sugar** | Progress bar and instant failures | Local developer experience |

**pytest-xdist**: `<runner> pytest -n auto`. If a test fails only under `-n auto`, it has hidden shared state. **pytest-mock**: `mocker.patch("path.to.func")` auto-undoes after each test -- no `with patch(...)` needed.

## pyproject.toml Configuration

Beyond the basics in [python-development](../../python-development/references/testing-and-tooling.md), consider these advanced options:

```toml
[tool.pytest.ini_options]
addopts = "-ra --strict-markers --tb=short"
asyncio_mode = "auto"
filterwarnings = ["error", "ignore::DeprecationWarning:third_party_lib.*"]
```

- `-ra`: Summary of all non-passing tests at the end
- `filterwarnings = ["error"]`: Surfaces deprecation warnings before they become breaking changes

## What This Reference Does NOT Cover

- **Basic Python testing**: test structure, simple assertions, running `pytest`, basic fixtures and parametrize, basic `pyproject.toml` config -- see the [python-development](../../python-development/SKILL.md) skill and its [testing-and-tooling reference](../../python-development/references/testing-and-tooling.md)
- **Test-engineer agent workflow**: how tests are designed and executed within the agent pipeline -- see the [test-engineer agent](../../../agents/test-engineer.md)
- **Language-independent testing strategy**: test pyramid, mocking philosophy, isolation principles, coverage philosophy -- see the parent [Testing Strategy](../SKILL.md) skill

---

## Test Topology — Python Leaf

This section is the Python leaf for the language-agnostic test topology protocol defined in [`references/test-topology.md`](test-topology.md). The trunk defines the group schema, tier vocabulary, identifier registries, and closure semantics. This leaf provides the concrete pytest wiring: selector strategy identifiers, parallel runner identifiers, scope mapping, marker registration, and runner invocation examples.

**Read the trunk first** if you are unfamiliar with the protocol. This section does not repeat trunk definitions — it only extends them.

### Registry 1 — Selector Strategy Identifiers (Python)

The following identifiers are registered by this leaf in the trunk's Selector Strategy Registry (Registry 1). Each maps the abstract `strategy` value in a group's `selectors` entry to a concrete pytest invocation.

| Identifier | Pytest invocation | Argument shape |
|-----------|------------------|----------------|
| `pytest-globs` | `<runner> pytest <args>` | List of file path or glob strings (e.g., `["tests/memory_mcp/", "tests/hooks/"]`) |
| `pytest-markers` | `<runner> pytest -m "<m1> or <m2> or ..."` | List of snake_case marker name strings (e.g., `["memory_store_core", "hooks_inject_memory"]`) |
| `pytest-keywords` | `<runner> pytest -k "<expr>"` | A keyword expression string (e.g., `"memory and not slow"`) — use for ad-hoc filtering; prefer `pytest-markers` for declared groups |

`pytest-keywords` is optional within the Python leaf; it requires no pyproject marker registration. Use it only for transient or debug-scope selections where a named marker would be premature. For declared topology groups, always prefer `pytest-markers`.

### Registry 2 — Parallel Runner Identifiers (Python)

The following identifiers are registered by this leaf in the trunk's Parallel Runner Registry (Registry 2).

| Identifier | Concrete invocation | When to use |
|-----------|--------------------|-----------| 
| `pytest-xdist-loadfile` | `<runner> pytest -n auto --dist loadfile` | Default for parallel-safe groups. Workers are assigned by file; file-scoped fixture state is stable across tests in the same file. Preferred when groups have `shared_fixture_scope: per-file` or narrower. |
| `pytest-xdist-load` | `<runner> pytest -n auto --dist load` | Load-balanced distribution. Less robust when tests in the same file share fixture state. Use only when groups have `shared_fixture_scope: none` or `per-test`. |

The trunk's `none` identifier (sequential, no parallel runner) covers `parallel_safe: false` groups — these groups are never passed to xdist.

### shared_fixture_scope — Mapping to pytest Scope Keywords

| Trunk value | pytest scope | Notes |
|------------|-------------|-------|
| `none` | (no shared fixture) | All fixtures are function-scoped or inline; no setup cost across tests |
| `per-test` | `function` | Default pytest scope; setup and teardown for each test case |
| `per-file` | `module` | Runs once per test file; stable for loadfile distribution |
| `per-process` | `class` | Runs once per test class; use carefully — tests in different classes within the same file still share this state across a worker |
| `per-suite` | `session` | Runs once for the entire test session; requires filelock for xdist safety (see §filelock recipe below) |

### Marker Registration Recipe

Each group that uses a `pytest-markers` selector must be declared in the pocket's `pyproject.toml`. Without this, `--strict-markers` (enabled globally across pockets) will fail loudly on unregistered markers — which is the desired signal that a group was added to `TEST_TOPOLOGY.md` without updating the pyproject.

```toml
[tool.pytest.ini_options]
addopts = "--strict-markers"
markers = [
    "memory_store_core: tests for the memory store core subsystem",
    "hooks_inject_memory: tests for the memory injection hooks",
]
```

One `markers` entry per group id. The description after the colon is free-form prose for documentation purposes. `--strict-markers` is already enabled in Praxion's pockets via the global `addopts` setting; an unregistered marker is an immediate test collection failure, not a silent skip.

### Kebab → snake_case Mapping Rule

Group ids in `TEST_TOPOLOGY.md` are kebab-case (e.g., `memory-store-core`). The pytest marker form substitutes each `-` with `_` (e.g., `memory_store_core`). The mapping is mechanical:

```
kebab-id:    memory-store-core
marker form: memory_store_core
```

This one-way transformation is required because pytest marker names must be valid Python identifiers (PEP 8), which do not allow hyphens. The kebab id is the canonical topology identity; the snake_case form is only used in pytest invocations, pyproject marker declarations, and `TEST_TOPOLOGY.md` `selectors` entries where `strategy: pytest-markers` is specified.

### Reserved Name Set

The following names must not be used as group `id` values in `TEST_TOPOLOGY.md`. After kebab → snake_case transformation, none may collide with an entry in this set.

**Built-in pytest markers** (reserved at the runner level):

- `parametrize` — built-in parametrize decorator
- `skipif` — built-in conditional skip
- `xfail` — built-in expected failure
- `usefixtures` — built-in fixture applicator
- `xdist_group` — pytest-xdist worker grouping marker
- `parallel_unsafe` — placeholder reserved for future topology tooling

**Tier keywords** (reserved at the trunk protocol level; no leaf extension needed):

- `unit`, `integration`, `contract`, `e2e`

If your group id would produce a snake_case marker that collides with any of the above, rename the group id. Sentinel check TT05 enforces this constraint.

### Parallel-Unsafe Group Runner Separation

When a step's `Tests:` field includes groups with `parallel_safe: false`, those groups must run in a separate sequential pytest invocation, isolated from the parallel-safe groups. Never mix safe and unsafe groups in the same `-n auto` invocation.

```bash
# Parallel-safe groups (run these first to pay xdist startup cost up front)
uv run pytest -m "memory_store_core or hooks_inject_memory" -n auto --dist loadfile

# Parallel-unsafe groups (sequential, isolated)
uv run pytest -m "project_metrics_fixture_rebuild" -n 0
```

The `-n 0` flag disables xdist entirely for the unsafe invocation. Results from both invocations are aggregated into a single `TEST_RESULTS.md` block per step.

### filelock-Based Session-Fixture Recipe

Groups with `shared_fixture_scope: per-suite` and `parallel_safe: true` need a filelock to ensure the session-scoped setup runs exactly once across all xdist workers. Without the lock, multiple workers may race to run the session fixture concurrently, causing corruption or redundant initialization.

The pattern (from `scripts/project_metrics/tests/conftest.py:26-49`):

```python
import pytest
from filelock import FileLock
from pathlib import Path

@pytest.fixture(scope="session", autouse=True)
def _rebuild_shared_resource(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Run expensive session-scoped setup exactly once across all xdist workers.

    Uses a file lock so the first worker to acquire it performs the build;
    subsequent workers wait and then skip the redundant rebuild.
    """
    root_tmp = tmp_path_factory.getbasetemp().parent
    lock_path = root_tmp / "shared_resource.lock"
    with FileLock(str(lock_path)):
        marker = root_tmp / "shared_resource.done"
        if not marker.exists():
            # Perform expensive one-time setup here
            _do_expensive_setup()
            marker.touch()
```

`filelock` is a `pytest-xdist` dependency — it is available in any project that uses xdist. The `tmp_path_factory.getbasetemp().parent` path is a shared directory accessible across all workers in the same pytest session.

Groups with `parallel_safe: false` do not need the filelock pattern — they run sequentially and have exclusive access to any shared state.

### Invocation Example

A concrete implementer/test-engineer invocation for a single group:

```bash
uv run pytest -m "memory_store_core" -n auto --dist loadfile
```

This materializes the `memory-store-core` group (kebab id in `TEST_TOPOLOGY.md`) using the `pytest-markers` selector strategy and the `pytest-xdist-loadfile` parallel runner.

### Worked pyproject.toml Snippet

```toml
[tool.pytest.ini_options]
addopts = "-ra --strict-markers --tb=short"
markers = [
    "memory_store_core: memory store persistence and retrieval",
    "observation_pipeline: observation ingestion and search pipeline",
]
```

Replace the placeholder group ids with the snake_case forms of your topology groups. One entry per group that uses a `pytest-markers` selector. Groups that use `pytest-globs` selectors do not require a marker registration entry.
