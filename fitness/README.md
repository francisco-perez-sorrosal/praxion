# Fitness Functions

Architectural fitness functions — invariants about *how the system is built*, not *what it does*.
Behavior tests live in `tests/`.

## Citation Contract

Every fitness rule MUST cite either an ADR id or a CLAUDE.md principle. The citation lives in:

- **pytest tests**: the module docstring of each test file
- **import-linter contracts**: the `broken_contract_guidance=` field of each `[importlinter:contract:*]` stanza, which import-linter prints when the contract breaks (2.16+ rejects any option a contract does not define, so `description=` fails the run)

Citation anchors must match one of:

- ADR id: `dec-\d{3,}` (e.g. `dec-101`)
- CLAUDE.md principle: `CLAUDE\.md§[A-Z][A-Za-z ]+` (e.g. `CLAUDE.md§Structural Beauty`)

The meta-fitness rule (`fitness/tests/test_meta_citation.py`) self-polices this contract — uncited rules cause the suite to FAIL.

## Waiver Pattern

When a structural violation must be permitted, add an inline comment:

```python
# fitness-waiver: <ADR-id-or-principle> <reason>
```

Each waiver MUST carry a citation-regex-matching anchor AND a non-empty reason. The meta-fitness rule scans for the `fitness-waiver:` marker and validates both fields are present.

## Running the Suite

```bash
# Fitness suite (architectural invariants)
uv run pytest fitness/tests/

# Standard behavior suite (separate invocation, separate report)
uv run pytest tests/
```

These are intentionally separate invocations — different category, different report. Do not add `fitness/tests` to `testpaths` in `pyproject.toml`.

## Layout

```
fitness/
  import-linter.cfg          # import-graph contracts
  tests/                     # pytest fitness rules (AST-based, etc.)
    __init__.py
    conftest.py              # shared fixtures (project_root, import_linter_cfg)
    test_starter_rule.py     # one real architectural invariant
    test_meta_citation.py    # self-policing of the citation contract
  README.md                  # this file
```

## Skill

For deeper guidance — decision rubric (import-graph invariants vs. AST-based rules), recipes, and authoring patterns — see `skills/architectural-fitness-functions/SKILL.md`.
