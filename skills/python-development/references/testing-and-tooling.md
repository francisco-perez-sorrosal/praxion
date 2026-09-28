# Testing and Code Quality Tooling

Detailed pytest patterns, code quality tool configuration, and pre-commit setup. Reference material for the [Python Development](../SKILL.md) skill.

## Testing with pytest

**Test structure**:
```python
import pytest
from package_name.module import process_items

def test_process_items_returns_limited_results():
    items = ["a", "b", "c", "d", "e"]
    result = process_items(items, limit=3)
    assert result == ["a", "b", "c"]

def test_process_items_handles_empty_input():
    assert process_items([]) == []

@pytest.fixture
def sample_data():
    return ["item1", "item2", "item3"]

def test_with_fixture(sample_data):
    result = process_items(sample_data, limit=2)
    assert len(result) == 2
```

**Running tests**:
```bash
<tool> run pytest                    # Run all tests
<tool> run pytest tests/test_module.py  # Specific file
<tool> run pytest -v                 # Verbose
<tool> run pytest --cov=src         # With coverage
<tool> run pytest -k "test_name"    # Filter by name
```

**Test organization**:
- One test file per module: `test_module.py` for `module.py`
- Test names should describe behavior: `test_function_handles_edge_case`
- Use fixtures for shared setup
- Use parametrize for multiple similar tests

```python
@pytest.mark.parametrize("input_val,expected", [
    ([], []),
    (["a"], ["a"]),
    (["a", "b", "c"], ["a", "b"]),
])
def test_process_items_with_various_inputs(input_val, expected):
    assert process_items(input_val, limit=2) == expected
```

## Code Quality Tools

**Essential tools** in `pyproject.toml`:
```toml
[project]
requires-python = ">=3.11"

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
# Parallel by default (pytest-xdist); `large` (live external services) is the
# only marker, deselected by default. Debug a single test with `-n 0`, never
# `-p no:xdist` (it errors once xdist is already active via `-n auto`).
addopts = "-ra --strict-markers -n auto --dist load -m 'not large'"

[tool.coverage.run]
source = ["src"]
branch = true

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
]
```

**Pre-commit hooks** (optional but recommended):
```yaml
# .pre-commit-config.yaml
# Pin rev to the latest stable release — find current versions at each repo's releases page.
# Specific versions are not pinned here to avoid staleness; the pattern matters, not the pin.
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: <version>  # https://github.com/astral-sh/ruff-pre-commit/releases
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: <version>  # https://github.com/pre-commit/mirrors-mypy/tags
    hooks:
      - id: mypy
        additional_dependencies: [types-requests]
```
