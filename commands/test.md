---
description: Run the tests a change needs, derived from layout, imports, path literals and the declared list
argument-hint: "[path|all]"
allowed-tools: [Bash, Read, Grep, Glob]
---

Run tests via the derived-selection resolver, `resolve_test_scope.py`. Load the [testing-strategy](../skills/testing-strategy/SKILL.md) skill for strategic guidance on test design and architecture decisions; runner and framework detection live inside the resolver's own inventory module, never re-derived here.

## Process

1. **Resolve the scope** from `$ARGUMENTS`:

   | `$ARGUMENTS` | Resolver flag |
   |---|---|
   | (none) | working tree (no flag) |
   | a path | `--changed <path>` |
   | `all` | `--full` |

   Invoke `resolve_test_scope.py [flags] --json` — on `PATH` via `install_claude.sh` in any project; Praxion self-host: `python3 scripts/resolve_test_scope.py [flags] --json`.

2. **Run the emitted invocations.** For each entry in the JSON `pockets[]`, `cd` to `invocations[].cwd` and run `invocations[].argv` with failures-first flags appended: `-q --tb=short -rf` for pytest, each other runner's quiet-with-failure-list equivalent (e.g. `--reporter=default` for vitest/jest, plain output for `cargo test`/`go test`). A pocket whose `selection` is `nothing` runs nothing.

   When `decision` is `"widened"`, report every `widen[].reason`/`detail` before running — a widened run means every affected pocket runs its full suite, not a narrower one. A change the resolver cannot account for widens; it never narrows.

3. **Report results**: pass/fail counts per pocket, failing test names, and for a failure point at the relevant output rather than pasting the full run inline.
