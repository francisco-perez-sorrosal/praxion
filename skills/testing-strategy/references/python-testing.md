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
