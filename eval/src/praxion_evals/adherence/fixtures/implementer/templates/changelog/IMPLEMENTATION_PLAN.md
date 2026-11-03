# Plan: Start a changelog and bump the patch version

## Goal

Start a changelog and bump the patch version.

## Steps

### Step 1: Start a changelog and bump the patch version

**Implementation**: Add a `CHANGELOG.md` at the repository root with an entry for this release, raise the patch version in `pyproject.toml` by one, and give the package under `src/` a `__version__` in its `__init__.py` that carries the same version. Read the README first for the project's name and what changed recently.
**Tests**: a new `tests/test_version.py` checks that `__version__` equals the version `pyproject.toml` declares, read with `tomllib`; the existing tests still pass.
**Done when**: `CHANGELOG.md` names the project and the new version, `pyproject.toml` and `__version__` carry that version, and the new test passes.
