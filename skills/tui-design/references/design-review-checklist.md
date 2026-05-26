# CLI/TUI Design Review Checklist

The quality audit checklist for terminal/CLI/TUI surfaces. Run this when reviewing a CLI tool, agent output formatting, TUI implementation, or preparing a PASS/FAIL/WARN Interface Design Review. Reference the in-scope skill reference files for depth on any item. Back to [SKILL.md](../SKILL.md).

---

## How to Use

For each item below, assess the implementation and mark:
- **PASS** — criterion met
- **WARN** — criterion partially met or edge case present; note what is borderline
- **FAIL** — criterion not met; cite the specific file/function/line where possible

A surface with any FAIL item fails the review. Surface FAIL and WARN items in findings sorted by severity.

---

## Output Routing (stdout/stderr)

- [ ] **Data on stdout** — all output that downstream programs would consume goes to stdout
- [ ] **Messages on stderr** — progress indicators, informational messages, warnings, errors go to stderr
- [ ] `myapp | cat` produces clean plain text with no ANSI escapes (TTY detection works)
- [ ] Piping the tool's stdout to `grep` or `jq` works as expected

---

## Color and ANSI Discipline

- [ ] **Color disabled** when stdout is not a TTY (`!isatty(stdout)`)
- [ ] **`NO_COLOR` honored** — no color output when `NO_COLOR` is set in the environment
- [ ] **`TERM=dumb` handled** — no color output when `TERM=dumb`
- [ ] **`--no-color` flag** present and works
- [ ] **Semantic colors only** — red = error, yellow = warning, green = success; no decorative color
- [ ] **No ANSI escape codes in non-TTY output** — checked by piping to a file and inspecting for `\033[` sequences
- [ ] **Color depth check** — 24-bit truecolor only used when `$COLORTERM=truecolor`; fallback to 16-color (ANSI)

---

## JSON Output

- [ ] **`--json` flag exists** for machine-readable output
- [ ] **JSON goes to stdout** (not stderr)
- [ ] **Consistent schema** — same fields in every invocation (no conditional field omission)
- [ ] **Valid JSON** — parseable by `jq .` without error

---

## Tables and Structured Output

- [ ] **Respects `$COLUMNS`** — tables truncate at the terminal width
- [ ] **Truncates, not wraps** — long values end with `...` at the column boundary
- [ ] **`--wide` flag** available for untruncated output when $COLUMNS is exceeded

---

## Progress and Feedback

- [ ] **Something shown within 100ms** for operations lasting >100ms
- [ ] **Spinner for unknown duration** operations; progress bar when percentage is computable
- [ ] **Progress suppressed in non-TTY** — no spinner output in CI logs
- [ ] **After every command**: user knows what happened and what to do next

---

## Help Text

- [ ] **Short usage shown** when required args are missing (3–5 lines max)
- [ ] **`--help` implemented** with full flag reference
- [ ] **Examples first** in `--help` output — EXAMPLES section before OPTIONS
- [ ] **Examples are runnable exactly as shown** — no `<placeholder>` in example commands
- [ ] **Three levels of help**: short usage / `--help` / documentation

---

## Error Messages

- [ ] **Three-part structure** — what went wrong / why / how to fix
- [ ] **Plain language** — no raw exception class names, no `ETIMEOUT`, no generic "Error"
- [ ] **Exact fix command** included when possible
- [ ] **No stack traces** as the primary error surface (only on `--debug`)
- [ ] **Specific not generic** — "Config file not found: ~/.praxion/config.yaml" not "File not found"

---

## Interactive vs Non-Interactive

- [ ] **TTY check before any prompt** — never prompt when stdin is not a TTY
- [ ] **`--no-input` flag** disables all interactive prompts
- [ ] **Never blocks a pipe** — missing required input in non-interactive mode exits with useful error
- [ ] **Fails fast** on missing required input in non-interactive mode (does not hang)

---

## Exit Codes

- [ ] **0 on success**
- [ ] **1 for general error**
- [ ] **2 for misuse** (wrong arguments, usage error)
- [ ] **Custom codes documented** — in `--help`, man page, or README if used
- [ ] **No 0 exit on error** — the tool never exits 0 when an error occurred

---

## TUI-Specific (when a full TUI is present)

- [ ] **Diff-before-render** — only changed cells emit escape sequences; no full-screen clear on every key press
- [ ] **DECSET 2026 synchronized output** wrapping all frame writes — no cursor-jump mid-redraw
- [ ] **≤50ms render budget** — frame time from input event to visible update
- [ ] **Stream-as-it-arrives** for streaming output — no buffering until complete
- [ ] **Active-line-only updates** for in-place streaming content (LLM output, log tails)
- [ ] **Keyboard navigation** covers all interactive elements (no mouse-only actions)
- [ ] **Escape key exits / dismisses** current context

---

## Terminal Accessibility

- [ ] **NO_COLOR respected** (covered above, but check the TUI framework explicitly)
- [ ] **16-color fallback** — works correctly in 16-color terminals, not just truecolor
- [ ] **No ANSI escapes in non-TTY output** — verified by inspection
- [ ] **Screen reader compatibility** — plain-text output under `NO_COLOR` is semantically correct

---

## Notes for Findings Report

When writing Interface Design Review findings for this checklist, use the format:

```
[FAIL|WARN|PASS] Category — Specific finding. File: path/to/file.py:line
```

Example:
```
[FAIL] Output Routing — Error messages are printed to stdout instead of stderr.
       When piping 'praxion deploy | grep success', error messages appear in the pipe.
       File: src/deploy.py:142

[FAIL] Error Messages — Error on missing config shows raw Python exception:
       "KeyError: 'output_dir'" with no user-oriented explanation or fix command.
       File: src/config.py:67

[WARN] TUI Render — Full-screen redraws on every keypress without DECSET 2026
       synchronized output. Visible cursor-jump on fast input.
       File: src/tui/viewer.py:render method
```
