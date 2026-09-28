## Testing

Tests are selected from the change, never listed by hand: a resolver derives the tests a diff needs from the test layout, imports, path literals, and `tests/declared-deps.toml` — and widens to the full suite whenever it cannot account for a changed file.

- **Layout** — `<layout>`: `<source file>` is tested by `<test file>`.
- **Selected run** (after every change): `/test`, or `resolve_test_scope.py --changed-from <base branch> | sh -e`.
- **Full run** (before handing work off; CI runs it on every push): `<full run>`.
- **Non-code dependencies** — when a test reads a file no code names (a fixture, a generated artifact), declare the pair in `tests/declared-deps.toml`; a change to that file then selects the test.
- **Outer loop is read-only** — the implementer runs `tests/acceptance/` and `tests/e2e/` but never edits them; a failing outer-loop test is fixed in production code or raised with its author.
