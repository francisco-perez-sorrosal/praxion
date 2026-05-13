---
name: tui-design
description: >
  CLI/TUI design craft. Covers: clig.dev CLI contract (human-first, composable); output
  discipline (data→stdout, messages→stderr, TTY/NO_COLOR/TERM=dumb/--no-color, --json,
  $COLUMNS truncation, progress in non-TTY, --quiet/--verbose); help-text levels (short
  usage / --help examples-first / man page); three-part error messages (what/why/fix; no
  stack traces); TTY detection (--no-input, never block a pipe); exit codes (0/1/2 +
  custom); TUI frameworks (Python textual+rich, Node Ink; Go Charm/Bubble Tea+Lip Gloss
  as quality exemplar — Model-Update-View); TUI render (diff-before-render, DECSET 2026
  synchronized output, stream-as-it-arrives, ≤50ms budget); terminal accessibility
  (NO_COLOR, 16-color fallback, no ANSI outside TTY, screen readers). Use when designing
  or reviewing CLI tools, agent/tool terminal output, TUIs, help text, error messages,
  exit codes, or choosing a TUI framework. Do NOT use for web UI (web-ui-design) or
  API/agent-tool design (api-design-craft, agentic-interface-design).
staleness_sensitive_sections:
  - "Framework Selection Decision"
  - "The clig.dev Principles (Full Distillation)"
---

# TUI Design

CLI and terminal UI design is the craft of the boundary between a system and its human consumer through a terminal. The measure of quality is whether the output communicates clearly, composes with other programs, and degrades gracefully when the terminal is not interactive.

The durable cross-cutting fundamentals (Rams, Norman, Nielsen, Tufte, Bloch, perception thresholds) live in [`references/design-fundamentals.md`](references/design-fundamentals.md). Load it when you need the canon depth. This SKILL.md body carries the CLI/TUI-specific application.

**Separation of contexts**: this skill covers terminal/CLI/TUI only. For web UI design, use the `web-ui-design` skill. For API and agent-tool design, use `api-design-craft` or `agentic-interface-design`.

**Boundary note**: when a tool or agent *outputs to a terminal* that a human reads, that is a TUI concern (this skill). When the tool itself is invoked by a model (its name, description, schema), that is an agentic-interface concern — see `agentic-interface-design`. Both may apply to the same tool; load both when that is the case.

---

## The CLI Contract (Human-First)

CLIs are now primarily used by humans, not only piped between programs. The design priority is:

1. **Human-first**: design for the person reading the output. Clear, readable, well-formatted.
2. **Composable**: machine-friendly as a second mode. `--json` always. Respect pipes.
3. **Conversation-as-interface**: after each command, the user should know what happened and what to do next.

A CLI that produces beautiful human output but cannot be piped is unfriendly to automation. A CLI that produces clean machine output but is unreadable to humans is unfriendly to users. Both modes are required.

---

## Output Discipline: The Rules

| Concern | Rule |
|---------|------|
| **stdout vs stderr** | Data → stdout. Messages, warnings, errors, progress → stderr. Never mix. (`my-tool | grep pattern` must work.) |
| **Color** | Disable when: not a TTY, `NO_COLOR` is set, `TERM=dumb`, or `--no-color` flag passed. Enable is the exception. |
| **Semantic color** | Red = error only. Yellow = warning only. Green = success only. Never decorative. |
| **JSON mode** | Always provide `--json` for machine-readable output. Structure must be consistent and versioned. |
| **Tables** | Respect terminal width (`$COLUMNS`). Truncate at column boundaries, never wrap. Offer `--wide` for full output. |
| **Progress** | Show something within 100ms for operations >100ms. Spinner for unknown duration; bar when percentage is computable. Suppress both in non-TTY (CI logs get no spinners). |
| **Quiet mode** | `--quiet` / `-q` suppresses informational output. Errors always appear (on stderr). |
| **Verbose mode** | `--verbose` / `-v` adds debug context. Never verbose by default. |

---

## The Three-Part Error Message

Every error must answer three questions:

1. **What went wrong** — a plain-language statement of the failure
2. **Why it failed** — the cause (not the symptom)
3. **How to fix it** — the exact command or action

**Bad**: `Error: ECONNREFUSED`

**Good**:
```
Cannot connect to memory MCP server (localhost:7474).
The server is not running (connection refused).
Start it with: memory-mcp start
Or set PRAXION_DISABLE_MEMORY_MCP=1 to skip.
```

**Grammar rules**:
- Start with the cause, not the symptom (not "Failed" → "Cannot connect")
- Use the user's vocabulary, not the system's (`connection refused on port 7474` not `ECONNREFUSED ::1:7474`)
- Give the exact command to fix when possible
- Never print a stack trace as the primary error surface — log it to a file or print on `--debug`

---

## TTY Detection and Exit Codes

### TTY Detection

Detect TTY before any interactive feature. If stdin is not a TTY, never prompt.

| Language | TTY Check |
|----------|----------|
| Python | `import sys; sys.stdin.isatty()` |
| Node.js | `process.stdin.isTTY` |
| Go | `isatty.IsTerminal(os.Stdin.Fd())` |
| Shell | `[ -t 0 ]` |

**`--no-input` flag**: an explicit way to disable all prompts. Idempotent in scripts. Required for any tool used in CI or automation.

**Never block a pipe**: if required input is missing in non-interactive mode, fail immediately with a useful error message — do not hang waiting for input.

```
Error: Required argument <name> not provided.
       In non-interactive mode, pass --name <value>.
```

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | General error (unspecified failure) |
| `2` | Misuse — wrong arguments, wrong usage |
| `126` | Command found but not executable |
| `127` | Command not found |
| Custom | **Document every custom code**. Example: `3` = "nothing to do" (for idempotent scripts), `4` = "config error". |

Scripts depend on exit codes. Always return the correct code. A command that exits `0` on error is a trap for every script that calls it.

---

## Help Text: Three Levels

Users expect three levels of help at different times:

| Level | Trigger | Content |
|-------|---------|---------|
| **Short usage** | Command run without required args, or with bad args | 3–5 lines: command name, one-line description, required args, hint to `--help` |
| **`--help` / `-h`** | Explicit help request | Full flag listing grouped by function; **examples first** (users read examples before prose); common use cases |
| **Man page / docs** | Deep reference | Full reference, edge cases, environment variables, all exit codes, configuration |

**Examples-first rule**: lead `--help` output with an EXAMPLES block before the option reference. Users find what they need faster from examples than from flag descriptions.

```
EXAMPLES
  # Create a new decision record
  praxion adr create "Use Postgres for persistence"

  # List all accepted ADRs
  praxion adr list --status accepted --json

OPTIONS
  --status string   Filter by status (proposed|accepted|superseded|rejected)
  --json            Output machine-readable JSON
  --quiet, -q       Suppress informational output
  --help, -h        Show this help
```

**`jq` as the exemplar**: `jq` without arguments shows usage + one example + "run jq --help for a list of options." Perfectly calibrated.

---

## When to Reach for Which Reference

| Task | Reference |
|------|-----------|
| clig.dev output rules in full, exemplar tools, composability | [`cli-output-and-ux.md`](references/cli-output-and-ux.md) |
| Help text design depth, error messages depth, interactive vs non-interactive, exit code table | [`cli-ux-patterns.md`](references/cli-ux-patterns.md) |
| Choosing a TUI framework, Model-Update-View architecture, Charm ecosystem, textual/rich/Ink | [`tui-frameworks.md`](references/tui-frameworks.md) |
| NO_COLOR, color depth, ANSI in non-TTY, screen readers, render performance (DECSET 2026) | [`terminal-accessibility.md`](references/terminal-accessibility.md) |
| Running a CLI/TUI quality audit | [`design-review-checklist.md`](references/design-review-checklist.md) |
| Durable design canon (Rams/Norman/Nielsen/Tufte/Bloch/Zhuo), perception thresholds | [`design-fundamentals.md`](references/design-fundamentals.md) |

---

## Cross-References

- **`web-ui-design`** — sibling hat for web UI design; when a product has both a web UI and a CLI.
- **`agentic-interface-design`** — when the CLI is invoked by a model (tool name, description, schema); the tool's agentic interface is a separate design concern from its human-facing terminal output.
