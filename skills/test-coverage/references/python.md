# Python Reference

Python-specific mechanics for the [`test-coverage`](../SKILL.md) skill. Loaded on demand when the active project is detected as Python.

This reference does **not** install `pytest-cov` or any other tool. The project owns its coverage dependency. The default config block below is copy-pasteable into a project's `pyproject.toml`; adoption is the project's decision.

## Target-Discovery Probe Order

Probe these sources in order and stop at the first hit. Each check is a simple filesystem or file-content test — the skill does not execute anything during probing.

1. **Pixi tasks** — look for a coverage-oriented task in `pixi.toml` under `[tasks]` (commonly named `coverage`, `test-coverage`, `cov`, or similar). If present, invoke via `pixi run <task-name>`. Pixi projects almost always pin the correct invocation here, and running through pixi guarantees the project's environment is active.
2. **`pytest-cov` config in `pyproject.toml`** — check for either `[tool.pytest.ini_options]` with `addopts` containing `--cov`, or an equivalent `[tool.coverage.run]` / `[tool.coverage.report]` block. If present, invoke plain `pytest` — the flags are already picked up from config, and this is the most common canonical target for Python projects using `uv` or plain `pytest`.
3. **Raw `pytest --cov` fallback** — if `pytest-cov` is importable (detectable by a `pytest-cov` entry under `[dependency-groups]`, `[tool.poetry.group.dev.dependencies]`, `[project.optional-dependencies]`, a `requirements*.txt`, or `uv.lock` / `poetry.lock`) but no config block exists, fall back to `pytest --cov=<package>` where `<package>` is derived from `[project].name` or the top-level source directory. This is a best-effort branch — emit a clear message that no config was found and a bare flag was used.
4. **Makefile target** — if a `Makefile` exists with a target named `coverage`, `test-coverage`, or `cov`, invoke via `make <target>`. This is the lowest-precedence branch because it often shells out to a non-Python build system and the exact behavior is project-specific.

If all four probes fail, return a structured "no target found" result. The appropriate remediation is to add `pytest-cov` as a real dependency and adopt the default config block below — not to bootstrap anything from inside the skill.

## Invocation Conventions

- **Invoke through the project's package or environment manager when one is detected.** For pixi projects, `pixi run <task>`. For uv projects with a `uv.lock`, prefer `uv run pytest`. For plain `pytest`, invoke directly. Running tests through the project's runner ensures the correct virtual environment and dependency set are active; invoking a bare `pytest` from an unrelated shell can silently pick up a system Python with missing dependencies.
- **Stream output to stderr, not stdout.** The calling surface (command, metrics pipeline, verifier) may want stdout reserved for a clean result; coverage tool chatter belongs on stderr.
- **Propagate non-zero exits.** If `pytest` exits non-zero (test failure, collection error, missing tool), surface the exit code. Callers that want to downgrade failure to a warning (e.g., `/project-metrics --refresh-coverage`) wrap the invocation — the skill itself does not swallow failures.
- **Do not mutate project config.** The skill reads `pyproject.toml` during probing but never writes to it. Config adoption is a user-driven one-time decision, not a per-run side effect.
- **Artifact path assumption.** After a successful invocation, the skill expects `coverage.xml` at the project root. This matches the default config block below and the first candidate path probed by `scripts/project_metrics/collectors/coverage_collector.py`. If a project pins a different output path, its probe-1 (pixi) or probe-2 (pyproject) configuration must make that explicit; callers that parse the artifact should be passed the resolved path, not guess.

## Presentation Notes

The skill's rendering invariants are language-independent and defined in the main `SKILL.md`. Python-specific notes:

- **Repo-relative paths for `path` column.** Prefer paths like `src/foo/bar.py` over `/Users/.../foo/bar.py`. The coverage XML's `<class filename="...">` attribute is already repo-relative under the default config block — use it as-is.
- **Exclude `tests/` from the per-file breakdown by default.** Test files measuring themselves inflate the table without insight. The default config block below excludes `tests/*` via `[tool.coverage.run].omit`; renderers can trust that and skip explicit filtering. Projects that want to include tests override `omit`.
- **`covered/total` uses line counts, not branch counts.** Python coverage tools report both; the skill's `covered/total` column uses the line ratio to keep the visual consistent across languages (branches are not universally reported). Branch coverage, when present, belongs in an optional separate row or surface — not the default per-file table.

## Default Coverage Config Block

Copy the block below into the project's `pyproject.toml`. When present, `pytest` invoked at the project root produces `coverage.xml` at the project root on every run.

```toml
# --- test-coverage skill: default Python coverage config -------------------
# Produces `coverage.xml` (Cobertura format) at the project root, consumed by
# scripts/project_metrics/collectors/coverage_collector.py and any caller that
# loads the `test-coverage` skill. Override `omit`, `exclude_lines`, and the
# fail-under floor per project needs; leave the output path at `coverage.xml`
# so downstream tooling finds it at the first-candidate path.

[tool.pytest.ini_options]
addopts = "--cov --cov-report=xml --cov-report=term-missing"
testpaths = ["tests", "scripts"]
# Repo root on sys.path so tests can import source modules without requiring
# PYTHONPATH to be set by the invoker. Harmless for projects whose package is
# already installed (editable or otherwise); load-bearing for flat-layout
# projects that ship tests importing `<package>.<submodule>` directly from the
# working tree. Override to `["src"]` for src-layout projects, or remove
# entirely if all imports resolve via installed distributions.
pythonpath = ["."]

[tool.coverage.run]
branch = true
source = ["."]
omit = [
    "tests/*",
    "**/tests/*",
    "**/test_*.py",
    "**/conftest.py",
    ".venv/*",
    "build/*",
    "dist/*",
]

[tool.coverage.report]
# Show missing line numbers in the terminal summary; do not fail the run on
# coverage alone (projects that want a hard floor set `fail_under` explicitly).
show_missing = true
skip_covered = false
precision = 1
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]

[tool.coverage.xml]
# Canonical artifact path. Changing this breaks downstream discovery.
output = "coverage.xml"
# --- end test-coverage skill defaults ---------------------------------------
```

**Tool ownership.** The project still needs `pytest-cov` declared as a real dev dependency. For PEP 735 dependency groups that looks like:

```toml
[dependency-groups]
dev = [
    "pytest",
    "pytest-cov",
]
```

The skill does not manage this declaration — the project does.

**Adjusting the per-project floor.** If a project wants a hard failure when coverage drops below a threshold, add `fail_under = <float>` to `[tool.coverage.report]`. The skill does not set this by default, because a hard floor is a policy decision, not a mechanical default.

**Overriding threshold bands.** The rendering bands (red `<60`, yellow `<80`, green `≥80`) live in the skill's render functions, not in `pyproject.toml`. Projects that need different bands override them via the render API — changing the config block here has no effect on presentation.
