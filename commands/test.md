---
description: Auto-detect test framework and run tests
argument-hint: "[path|all]"
allowed-tools: [Bash, Read, Grep, Glob]
---

Detect the project's test framework automatically and run tests. Load the [testing-strategy](../skills/testing-strategy/SKILL.md) skill for strategic guidance on test design and architecture decisions.

## Process

1. **Detect test framework and project runner** from project config files. Always run tests through the project's package/environment manager — never invoke test frameworks directly.

   **Runner detection** (check in order, use first match):

   | Signal | Runner | Example |
   |---|---|---|
   | `pixi.toml` or `[tool.pixi]` in `pyproject.toml` | `pixi run` | `pixi run pytest` |
   | `uv.lock` or `[tool.uv]` in `pyproject.toml` | `uv run` | `uv run pytest` |
   | `pyproject.toml` exists (no pixi/uv) | `python -m` | `python -m pytest` |
   | `pnpm-lock.yaml` | `pnpm exec` | `pnpm exec jest` |
   | `yarn.lock` | `yarn` | `yarn jest` |
   | `package-lock.json` or `package.json` | `npx` | `npx jest` |
   | `Cargo.toml` | `cargo` | `cargo test` |
   | `go.mod` | `go` | `go test ./...` |

   **Framework detection** (after runner is determined):

   | Config Signal | Framework |
   |---|---|
   | `pyproject.toml` with `[tool.pytest.ini_options]` or `pytest` in dependencies | pytest |
   | `package.json` with `vitest` in devDependencies | Vitest |
   | `package.json` with `jest` in devDependencies | Jest |
   | `Cargo.toml` | cargo test (built-in) |
   | `go.mod` | go test (built-in) |

   If no framework is detected, report what was checked and ask the user which framework to use.

2. **Determine scope** from `$ARGUMENTS`:

   - **No argument**: Run tests on files changed since last commit. Use `git diff --name-only HEAD` to find changed files, then filter for test file patterns (`test_*`, `*_test.*`, `*_spec.*`, files under `tests/`). If no changed test files are found, report that and suggest running with `all`.
   - **A path**: Run tests in that file or directory.
   - **`all`**: Run the full test suite with no path filtering.

3. **Run tests** using the detected framework with appropriate flags:
   - **Changed files / path scope**: verbose output, fail-fast (`-x` for pytest, `--bail` for Jest, etc.) for quick feedback
   - **`all` scope**: verbose output, full run (no fail-fast), show complete results

4. **Report results**: Show pass/fail counts, list failing test names, and for failures suggest likely causes or point to the relevant test output.
