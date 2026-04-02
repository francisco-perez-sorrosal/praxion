---
description: Run tests using the project's test framework
argument-hint: [path|all]
allowed-tools: [Bash, Read, Grep, Glob]
---

Detect the project's test framework automatically and run tests. Load the [testing-strategy](../skills/testing-strategy/SKILL.md) skill for strategic guidance on test design and architecture decisions.

## Process

1. **Detect test framework** from project config files, checking in priority order:

   | Config Signal | Framework | Run Command |
   |---|---|---|
   | `pyproject.toml` with `[tool.pytest.ini_options]` or `pytest` in dependencies | pytest | `<runner> pytest` where `<runner>` is `uv run`, `pixi run`, or `python -m` depending on lockfile present |
   | `package.json` with `jest` in devDependencies | Jest | `npx jest` |
   | `package.json` with `vitest` in devDependencies | Vitest | `npx vitest run` |
   | `Cargo.toml` exists | cargo test | `cargo test` |
   | `go.mod` exists | go test | `go test ./...` |

   If no framework is detected, report what was checked and ask the user which framework to use.

2. **Determine scope** from `$ARGUMENTS`:

   - **No argument**: Run tests on files changed since last commit. Use `git diff --name-only HEAD` to find changed files, then filter for test file patterns (`test_*`, `*_test.*`, `*_spec.*`, files under `tests/`). If no changed test files are found, report that and suggest running with `all`.
   - **A path**: Run tests in that file or directory.
   - **`all`**: Run the full test suite with no path filtering.

3. **Run tests** using the detected framework with appropriate flags:
   - **Changed files / path scope**: verbose output, fail-fast (`-x` for pytest, `--bail` for Jest, etc.) for quick feedback
   - **`all` scope**: verbose output, full run (no fail-fast), show complete results

4. **Report results**: Show pass/fail counts, list failing test names, and for failures suggest likely causes or point to the relevant test output.
