# CLI Output and UX

Full clig.dev distillation, exemplar CLI tools with their lessons, output design rules in depth, composability, and the conversation-as-interface pattern. Back to [SKILL.md](../SKILL.md).

---

## The clig.dev Principles (Full Distillation)
<!-- last-verified: 2026-05-12 -->

[clig.dev](https://clig.dev/) is the authoritative reference for human-first CLI design. Key principles:

### Human-First

CLIs are now primarily used by humans, not only piped between programs. Optimize for the human first; make it machine-friendly second. The two are not opposites — they are sequenced.

Human-first means:
- Output that reads naturally (not `{"status":"ok"}` as default output)
- Color, formatting, and structure when in a TTY
- Prose confirmations that tell the user what happened and what to do next
- Helpful error messages, not error codes

Machine-friendly means:
- `--json` output that is consistent and versioned
- Exit codes that scripts can check
- No prompts in non-interactive mode
- Output to stdout (data) and stderr (messages) cleanly separated

### Composability

The Unix philosophy: each program does one thing well; programs compose via pipes.

**Stdout vs stderr rule** (required for composability):
- **Stdout**: data output — the result of the command, what the next program in the pipe will consume
- **Stderr**: messages — progress indicators, informational messages, warnings, errors

If you put errors on stdout, `myapp | grep success` will match error messages. If you put data on stderr, `myapp 2>/dev/null | process-data` will eat your data.

**Testing composability**: `myapp | cat` should produce clean plain-text output. If it produces ANSI escapes, you failed the TTY check.

### Conversation as Interface

After every command, the user should understand:
1. What happened
2. Whether it succeeded
3. What they should do next (if anything)

Proactively suggest the next step:
```
✓ Project created: my-project
  Next: praxion init my-project --template nextjs
```

Not:
```
Done.
```

---

## Output Design Rules (In Depth)

### Color Discipline

**Disable color when**:
- `stdout` is not a TTY (`isatty(stdout)` returns false)
- The `NO_COLOR` environment variable is set (any value — per [no-color.org](https://no-color.org/))
- `TERM` is `dumb`
- The `--no-color` flag was passed

**Enable color when**: all of the above are false, AND you have verified the terminal supports color.

**Color semantics** — use color only for these meanings:
- Red: error, failure, danger
- Yellow: warning, caution
- Green: success, completion
- Blue/Cyan: informational, active state
- Dim/gray: secondary information, timestamps, metadata

Never use color decoratively (random rainbow banners, colorful ASCII art in normal output).

**Color depth**: assume 8-color (ANSI) minimum. Use `$COLORTERM=truecolor` to check for 24-bit support before using hex colors. Fallback to ANSI 16-color when unset.

### JSON Mode

`--json` should:
- Output valid JSON (parseable by `jq`, Python `json.load`, etc.)
- Maintain a consistent schema across versions (treat as an API)
- Include all data the human-readable output shows, plus additional fields that may be useful for scripting
- Output to stdout (not stderr)
- Be documented (what fields exist, what they mean)

Example:
```
praxion adr list
  → human table: Date, ID, Title, Status, Category

praxion adr list --json
  → [{"id": "dec-NNN", "title": "...", "status": "accepted", "date": "2026-01-15", ...}]
```

Never silently change the JSON schema — this is a breaking change for all scripts depending on it.

### Table Output

When rendering tabular data in a TTY:
- Respect `$COLUMNS` (the terminal width environment variable; default to 80 if unset)
- **Truncate columns**, not wrap — `Title...` not `Title wraps to\nnext line`
- Offer `--wide` to disable truncation when the user explicitly requests full output
- Use box-drawing characters only when they add clarity, not always (plain-space alignment is often cleaner)
- For sortable data: note available sort options in a footer line or in `--help`

```
ID       Status     Title
dec-NNN  accepted   Use PostgreSQL for ...  (truncated to fit $COLUMNS)
dec-NNN  proposed   Adopt RFC 9457 for ...
```

### Progress Indicators

**Show something within 100ms** for any operation that might take longer. Silence for >100ms → the user thinks the program is broken.

**Spinner**: for operations of unknown duration where a percentage cannot be computed.
- Use a simple Unicode spinner: `⣾ ⣽ ⣻ ⢿ ⡿ ⣟ ⣯ ⣷` or `◐ ◓ ◑ ◒`
- Update at ~10fps (100ms interval)
- Show a label: `⣾ Connecting to server...`
- Suppress in non-TTY (CI logs get no spinners — they produce noise)

**Progress bar**: for operations where a count or percentage is known.
```
Downloading... [████████░░░░░░░] 53% (1.3/2.4 MB)
```

**Streaming output**: for operations that produce output incrementally (git clone, build logs, streaming LLM responses) — stream each line as it arrives. Do not buffer and dump at the end. Users find streaming output cognitively engaging; buffered blobs are frustrating.

### Quiet and Verbose Modes

- `--quiet` / `-q`: suppress all informational output. Only output data (on stdout) and errors (on stderr). Respect this flag in CI environments.
- `--verbose` / `-v`: add debug context. Timestamps, duration, internal state transitions, API calls being made.
- Never verbose by default. The user opted in to see more; do not assume they want it.
- Multiple `-v` levels (`-v`, `-vv`, `-vvv`) are an acceptable pattern for graduated verbosity.

---

## Modern CLI Exemplars

| Tool | The One Lesson |
|------|----------------|
| **`gh` (GitHub CLI)** | Human-first output with `--json` for machine output. `gh pr list` gives a readable table; `gh pr list --json` gives machine output. Help text leads with examples. Perfect model for "progressive disclosure from human to machine." |
| **Stripe CLI** | Three-part error messages are gold standard. `stripe listen --forward-to` shows real-time event streaming — output that arrives as it happens, not buffered. |
| **`fzf`** | Fuzzy search as a composable Unix primitive. `cat list | fzf` — takes stdin, returns selection on stdout. The design is maximally composable. Response latency <10ms. |
| **`bat`** | Color-on-TTY, plain-on-pipe via automatic TTY detection. Adds git markers to the gutter. Respects `NO_COLOR`. Shows that enriched terminal output and composability are not opposites. |
| **`eza`** | Replaces `ls` with icons, color, git status in TTY — outputs plain text when piped. The right behavior: rich in TTY, clean in pipes. |
| **`delta`** | Syntax-highlighted diffs with side-by-side mode. Shows that terminal output can be dense and readable simultaneously. |
| **`lazygit`** | TUI done right — keyboard-driven, modal approach à la Vim, every action visible in the help bar at the bottom. The help bar is a model for progressive disclosure in a TUI. |
| **`k9s`** | High-density TUI with live-updating data. Demonstrates that real-time data in terminals can be flicker-free when rendering is done correctly (diff-before-render, synchronized output). |
| **`jq`** | `jq` without arguments: short usage + one example + "run jq --help for a list of options." The most calibrated help design in any CLI tool. |

---

## The Conversation Design Pattern

Every CLI command is one turn in a conversation between the user and the system. Design each turn to advance the conversation:

**After a successful create operation**:
```
✓ ADR created: .ai-state/decisions/<NNN>-<slug>.md
  title: Use PostgreSQL for persistence
  status: proposed
  id: dec-NNN

  Review and approve: praxion adr accept dec-NNN
  View all ADRs:      praxion adr list
```

**After a successful delete**:
```
✓ Deleted 3 temp files (142 KB freed)
```

**After a dry run**:
```
Dry run — no changes made.
Would delete:
  tmp/build-2026-01-15/
  tmp/cache-stale/
Run without --dry-run to apply.
```

The pattern is: confirm what happened → show the result → suggest the next step. Not just "Done."
