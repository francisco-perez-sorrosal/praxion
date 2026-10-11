# Scripts for Agents

When to bundle a script in a skill, the contract an agent-facing script keeps, and how a skill's instructions refer to it. Reference material for the [Skill Creator](../SKILL.md) skill; the layout of the `scripts/` directory itself is in the entry page.

## When to Bundle

Bundle a script for deterministic work — validation, conversion, extraction, anything where a wrong answer is cheaper to prevent than to detect — and for a helper the agent keeps rewriting from scratch. A tested script is more reliable than regenerated code, costs no tokens to carry (only its output enters context) and behaves the same every run. Do not bundle for a step that needs judgment, or for a one-off command: a pinned tool invocation (`uvx ruff@0.8.0 check .`) belongs in the instructions, and moves into a script only once it is hard to get right on the first try.

## The Contract

An agent reads a script's standard output and standard error to decide its next move and cannot answer a prompt, so a bundled script:

- **Runs without interactive prompts.** Take every input from flags, environment variables or standard input; a script that waits on a TTY hangs for good. When a required input is missing, fail with a message naming the flag and its allowed values.
- **Documents itself through `--help`.** The help text is how the agent learns the interface: a one-line purpose, each flag, the exit codes and one or two examples. Keep it short, because it enters context.
- **Reports an error with what was wrong and what was expected.** `Error: --format must be one of: json, csv, table. Received: "xml"` lets the agent fix the next attempt; `invalid input` costs a turn. Reject ambiguous input rather than guessing.
- **Writes results to standard output and diagnostics to standard error.** Progress, warnings and debug lines go to standard error, so the agent can capture clean output. Make the results structured (JSON, CSV or TSV) when another program or the agent parses them.
- **Returns distinct, documented exit codes.** Separate "not found", "invalid arguments" and "failed precondition", and list them in `--help`.
- **Is safe to re-run.** Agents retry; "create if absent" beats "create and fail on a duplicate". Give anything destructive or stateful a `--dry-run` that previews the change, and require an explicit flag for the irreversible part.
- **Bounds its output.** Harnesses truncate large tool output, so default to a summary or a limit and offer `--offset` or an `--output FILE` for the rest.
- **Pins its dependencies.** Declare them inline with PEP 723 script metadata (`# /// script` block with PEP 508 specifiers such as `"beautifulsoup4>=4.12,<5"`, plus `requires-python`) and run it with `uv run`, or call a pinned runner (`npx eslint@9.0.0`). State prerequisites in the skill rather than assuming the environment has them.

## Solve, Don't Punt

**Solve, Don't Punt**: Handle error conditions explicitly rather than letting scripts fail for the agent to debug.

## Justify Constants

**Justify Constants**: Document why values exist -- no voodoo numbers:

```python
# Three retries balances reliability vs speed
# Most intermittent failures resolve by second retry
MAX_RETRIES = 3
```

## Execution vs Reference and MCP Tool Names

**Execution vs Reference**: Be explicit about intent:

- "Run `analyze_form.py` to extract fields" (execute)
- "See `analyze_form.py` for the extraction algorithm" (read as reference)

Reference a script from the instructions by its path relative to the skill root, and list the bundled scripts once so the agent knows they exist.

**MCP Tool Names**: Use fully qualified format: `ServerName:tool_name`
