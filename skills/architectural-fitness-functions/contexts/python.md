# Python Architectural Fitness Functions

Python-specific implementation guide for architectural fitness functions. Load alongside
the generic [Architectural Fitness Functions](../SKILL.md) skill.

**Related skills:**
- [Python Development](../../python-development/SKILL.md) -- type hints, testing, async patterns
- [Python Project Management](../../python-prj-mgmt/SKILL.md) -- uv/pixi setup, dependency management

## Table of Contents

- [Tooling Overview](#tooling-overview)
- [import-linter Quickstart](#import-linter-quickstart)
  - [Config Layout](#config-layout)
  - [Running import-linter](#running-import-linter)
- [pytest Fitness Tests](#pytest-fitness-tests)
  - [Module Docstring Citation](#module-docstring-citation)
  - [AST-Based Assertions](#ast-based-assertions)
  - [Filesystem Assertions](#filesystem-assertions)
- [Meta-Citation Rule](#meta-citation-rule)
- [Citation Locations — Python](#citation-locations--python)
- [Authoring Workflow — Python](#authoring-workflow--python)
- [References](#references)

## Tooling Overview

Python fitness functions use two complementary tools:

| Tool | Invariant type | Config location |
|------|---------------|-----------------|
| `import-linter` | Which module imports which (graph-rule) | `fitness/import-linter.cfg` |
| `pytest` | Everything else (AST, filesystem, YAML, conventions) | `fitness/tests/test_*.py` |

Both tools are managed under `uv` (see [Python Project Management](../../python-prj-mgmt/SKILL.md)).
Add to `[project.optional-dependencies]` or `[dependency-groups]`:

```toml
[dependency-groups]
fitness = [
    "import-linter",
    "pytest",
]
```

## import-linter Quickstart

### Config Layout

`fitness/import-linter.cfg` holds all import contracts. Each contract stanza follows
the `[importlinter:contract:<name>]` pattern and **must** have a `description=` field
containing a citation:

```ini
[importlinter]
root_packages = mypackage

[importlinter:contract:no-domain-to-infra]
name = Domain must not import infra
type = forbidden
source_modules = mypackage.domain
forbidden_modules = mypackage.infra
description = CLAUDE.md§Structural Beauty (domain layer stays clean; infrastructure is a detail)

[importlinter:contract:layers]
name = Layer ordering
type = layers
layers =
    mypackage.api
    mypackage.services
    mypackage.domain
    mypackage.infra
description = dec-NNN (layered architecture decision)
```

**Contract types** (see [`../references/import-linter-recipes.md`](../references/import-linter-recipes.md) for full recipes):

| Type | Use when |
|------|---------|
| `forbidden` | Module X must never import from module Y |
| `layers` | Enforce import-ordering between layers |
| `independence` | Two modules must not import each other |

### Running import-linter

```bash
uv run import-linter --config fitness/import-linter.cfg
```

On success: prints `All contracts kept.`
On failure: lists violated contracts with details.

In CI (exit code 1 on any violation):

```yaml
- name: Import contracts
  run: uv run import-linter --config fitness/import-linter.cfg
```

## pytest Fitness Tests

All Python fitness tests live in `fitness/tests/test_*.py`. Each test **module** must
have a docstring containing a citation before any test logic.

### Module Docstring Citation

```python
"""Fitness rule: all YAML frontmatter in skills/ has required keys.

Cites: CLAUDE.md§Context Engineering (right information at the right time;
YAML frontmatter drives skill activation — missing keys break discoverability).
"""
```

The citation regex scanned by the meta-citation rule:

```
dec-\d{3,}|CLAUDE\.md§[A-Z][A-Za-z ]+
```

Write the citation **before** the test logic — it forces upfront justification.

### AST-Based Assertions

AST fitness tests parse Python source files and assert structural properties:

```python
"""Fitness rule: all public functions have docstrings.

Cites: CLAUDE.md§Structural Beauty (self-documenting code; docstrings are
the minimum structural signal that a function has been thought through).
"""

import ast
from pathlib import Path


def test_public_functions_have_docstrings(project_root: Path) -> None:
    """All public functions in src/ have docstrings."""
    failures: list[str] = []
    for path in (project_root / "src").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name.startswith("_"):
                continue  # skip private/dunder
            if ast.get_docstring(node) is None:
                failures.append(f"{path.relative_to(project_root)}:{node.lineno} {node.name}()")
    assert not failures, "Missing docstrings:\n  " + "\n  ".join(failures)
```

### Filesystem Assertions

Filesystem fitness tests check project structure conventions:

```python
"""Fitness rule: no skill SKILL.md exceeds 500 lines.

Cites: CLAUDE.md§Pragmatism (every line must earn its place;
skills that exceed 500 lines have lost progressive-disclosure discipline).
"""

from pathlib import Path


def test_skill_files_under_500_lines(project_root: Path) -> None:
    """All SKILL.md files have fewer than 500 lines."""
    failures: list[str] = []
    for skill_file in (project_root / "skills").rglob("SKILL.md"):
        line_count = len(skill_file.read_text().splitlines())
        if line_count > 500:
            rel = skill_file.relative_to(project_root)
            failures.append(f"{rel}: {line_count} lines (max 500)")
    assert not failures, "Skills exceed line limit:\n  " + "\n  ".join(failures)
```

## Meta-Citation Rule

The meta-citation rule (`fitness/tests/test_meta_citation.py`) scans all other fitness
test modules and all import-linter contracts, asserting that each has a valid citation.
It is itself a fitness test (with its own `CLAUDE.md§Pragmatism` citation in its module
docstring).

The rule enforces three contracts simultaneously:
1. Every `fitness/tests/test_*.py` module docstring contains a citation.
2. Every `[importlinter:contract:*]` stanza has a `description=` with a citation.
3. Every `# fitness-waiver:` inline comment has both a citation anchor and a reason.

**Waiver syntax** (Python source files):

```python
import some_forbidden_module  # fitness-waiver: dec-NNN migration in progress; remove after 2026-Q3
```

## Citation Locations — Python

| Rule type | Citation location | Example |
|-----------|-------------------|---------|
| pytest test module | Module docstring (first line is sufficient) | `"""... Cites: dec-NNN ..."""` |
| import-linter contract | `description=` field of the contract stanza | `description = dec-NNN (layered arch)` |
| Fitness waiver | Inline comment after `# fitness-waiver:` | `# fitness-waiver: dec-NNN migration in progress` |

## Authoring Workflow — Python

1. **Choose the tool** per the decision rubric in [SKILL.md](../SKILL.md): graph rule
   (import-linter) vs assertion-based test (pytest).

2. **Write the citation first** — in the `description=` field or module docstring —
   before writing the rule logic. This forces upfront justification and prevents
   the meta-citation rule from catching you by surprise.

3. **Write the rule**:
   - For import-linter: see [`references/import-linter-recipes.md`](../references/import-linter-recipes.md)
   - For pytest: follow the AST-based or filesystem-assertion patterns above

4. **Run both tools**:

   ```bash
   uv run pytest fitness/tests/           # behavior and meta-citation checks
   uv run import-linter --config fitness/import-linter.cfg  # import-graph contracts
   ```

   Both must be GREEN before the rule is considered done.

5. **The meta-citation rule self-polices** docstring/description coverage — if you forgot
   the citation, the suite FAILs noisily before any merge.

## References

| Reference | When to consult |
|-----------|-----------------|
| [`../references/import-linter-recipes.md`](../references/import-linter-recipes.md) | Authoring a new import-linter contract (forbidden, layered, independence patterns) |
| [`../SKILL.md`](../SKILL.md) | Decision rubric, citation contract, waiver pattern (language-agnostic) |
