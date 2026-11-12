---
name: test
description: Run the tests a change needs, derived from layout, imports, path literals and the declared list
argument-hint: "[path|all]"
allowed-tools: [Bash, Read, Grep, Glob]
---

Run tests via the derived-selection resolver, `resolve_test_scope.py`. Load the [testing-strategy](../testing-strategy/SKILL.md) skill for strategic guidance on test design and architecture decisions; runner and framework detection live inside the resolver's own inventory module, never re-derived here.

## Process

1. **Resolve the scope** from `$ARGUMENTS`:

   | `$ARGUMENTS` | Resolver flag |
   |---|---|
   | (none) | working tree (no flag) |
   | a path | `--changed <path>` |
   | `all` | `--full` |

   Invoke `resolve_test_scope.py [flags] --json` — on `PATH` via `install_claude.sh` in any project; Praxion self-host: `python3 scripts/resolve_test_scope.py [flags] --json`.

2. **Run the emitted invocations.** For each entry in the JSON `pockets[]`, run `invocations[].argv` with its working directory set to `invocations[].cwd`, without changing the session's own directory (a subshell, or the runner's directory option such as `uv run --directory <cwd>`), and with failures-first flags appended: `-q --tb=short -rf` for pytest, each other runner's quiet-with-failure-list equivalent (e.g. `--reporter=default` for vitest/jest, plain output for `cargo test`/`go test`). A pocket whose `selection` is `nothing` runs nothing.

   **Detach a run that may pass two minutes.** Long runs launched with `run_in_background` were reaped mid-run, reported killed at 16% and 55% and later under memory pressure (observed 2026-09 and 2026-10, not re-probed). A job started with `&` from the tool shell also ignores SIGINT, so a test that interrupts a child process fails in it and passes alone. Start the run from a small launcher script that calls `subprocess.Popen(argv, start_new_session=True, stdin=DEVNULL, stdout=<log>, stderr=STDOUT, preexec_fn=<reset SIGINT to SIG_DFL>)` and writes a done-file when the run ends. Prove it is alive (`pgrep -fl <runner>`), then wait with `Monitor` on `until [ -f <done-file> ]; do sleep 5; done`.

   **Leave the files the run reads alone while it runs.** A widened scope can take minutes, and an edit to a file the run reads mid-run turns its verdict into noise.

   When `decision` is `"widened"`, report every `widen[].reason`/`detail` before running — a widened run means every affected pocket runs its full suite, not a narrower one. A change the resolver cannot account for widens; it never narrows.

3. **Report results**: pass/fail counts per pocket, failing test names, and for a failure point at the relevant output rather than pasting the full run inline.
