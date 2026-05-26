# Terminal Accessibility

NO_COLOR, color depth, ANSI escapes in non-TTY, screen readers, and TUI render performance (including DECSET 2026 synchronized output). Back to [SKILL.md](../SKILL.md). <!-- last-verified: 2026-05-12 -->

---

## NO_COLOR

[no-color.org](https://no-color.org/) is the de-facto standard for disabling ANSI color output. Any tool that produces colored output must honor it.

### The Contract

When the `NO_COLOR` environment variable is present in the environment (any value, including empty string), the program must not add ANSI color escape codes to output.

```python
import os
NO_COLOR = 'NO_COLOR' in os.environ

def colorize(text: str, color_code: str) -> str:
    if NO_COLOR or not sys.stdout.isatty():
        return text
    return f"\033[{color_code}m{text}\033[0m"
```

```go
import "os"
noColor := os.Getenv("NO_COLOR") != "" || os.Getenv("TERM") == "dumb"
```

```typescript
const noColor = 'NO_COLOR' in process.env || process.env.TERM === 'dumb';
```

### Priority Order

Check these conditions in order; disable color if any is true:
1. `NO_COLOR` environment variable is set
2. `TERM` is `dumb`
3. `--no-color` flag was passed
4. stdout is not a TTY (`!isatty(stdout)`)

If all conditions are false, color may be used.

### Why This Matters

Users who set `NO_COLOR` include:
- Screen reader users (ANSI escapes become garbage characters in non-ANSI-aware contexts)
- Users with visual sensitivities to color
- Users piping to tools that don't handle ANSI escapes
- Users in restricted environments (embedded terminals, log viewers, CI systems)
- Users who prefer plain text for aesthetic or accessibility reasons

Disrespecting `NO_COLOR` is an accessibility failure.

---

## Color Depth

Not all terminals support the same color depth. Check before using extended colors:

| Depth | ANSI codes | Detection | Colors available |
|-------|-----------|-----------|-----------------|
| 1-bit (monochrome) | None | `TERM=dumb` | Black and white only |
| 4-bit (16-color) | `\033[30m`–`\033[37m`, `\033[90m`–`\033[97m` | Default fallback | 8 + 8 bright variants |
| 8-bit (256-color) | `\033[38;5;Nm` | `$TERM` includes `256color` | 256 indexed colors |
| 24-bit (truecolor) | `\033[38;2;R;G;Bm` | `$COLORTERM=truecolor` | 16.7 million colors |

### Detection and Fallback

```python
import os

def get_color_depth() -> int:
    if os.environ.get('COLORTERM') in ('truecolor', '24bit'):
        return 24
    term = os.environ.get('TERM', '')
    if '256color' in term:
        return 8
    if os.environ.get('NO_COLOR') or term == 'dumb':
        return 0
    return 4  # default: ANSI 16-color

color_depth = get_color_depth()
```

**Rule**: use 16-color (4-bit) ANSI codes by default. Only use 256-color or truecolor when the terminal explicitly supports it. Libraries like `rich`, `lipgloss`, and `chalk` handle this automatically — use them rather than crafting ANSI codes by hand.

---

## Never ANSI Escapes Outside a TTY

ANSI escape codes (`\033[31m`, `\033[1m`, `\033[0m`, etc.) must never appear in output that goes to a non-TTY destination.

**Why**: when output is piped, redirected to a file, or consumed by a program, ANSI escapes appear as literal garbage characters:

```
^[[31mError: connection refused^[[0m
```

This makes log parsing, `grep`, `awk`, and automated processing fail or produce incorrect results.

**Detection**:
```python
import sys
is_tty = sys.stdout.isatty()  # stdout
is_stderr_tty = sys.stderr.isatty()  # stderr separately

# Only add color to stderr output when stderr is a TTY
if is_stderr_tty and not NO_COLOR:
    error_msg = f"\033[31m{error_msg}\033[0m"
```

Note: check TTY for each stream independently. Stdout might be piped while stderr goes to terminal.

---

## Screen Readers and Terminal Output

Screen readers (NVDA, JAWS on Windows; VoiceOver on macOS) can read terminal output, but they interact with it differently:

### What Screen Readers Read

- **NVDA/JAWS** read terminal output character by character or line by line, depending on configuration
- **VoiceOver** on macOS reads the terminal buffer
- **ANSI escape codes** in non-TTY output become garbage characters when read aloud

### Design Rules for Screen Reader Compatibility

**1. Avoid control characters in non-TTY output**:
Any escape sequences (`\033[...m`, `\033[?2026h`, etc.) that appear in non-TTY output will be read literally by screen readers as "escape open-bracket 31m" etc.

**2. Use plain text as the accessible layer**:
When `NO_COLOR` is set, the output should be pure plain text — screen readers can read plain text correctly. The color-stripped output IS the accessible output.

**3. Structure output for linear reading**:
Screen readers read linearly. Columnar output that depends on visual alignment (spaces to align columns) degrades for screen readers. Consider `--json` or a `--accessible` flag for structured output that screen readers can process programmatically.

**4. Progress indicators**:
Spinners and progress bars that use carriage returns (`\r`) to update in-place read poorly — the screen reader may read each update, flooding the user with noise. Suppress progress indicators when stdout is not a TTY or when `NO_COLOR` is set.

---

## TUI Render Performance

Terminal UIs have a tighter render budget than web UIs. Incorrect rendering produces flicker that users find distracting and that makes the tool feel low-quality.

### The 50ms Render Budget

Target: ≤50ms for a full terminal render cycle. Beyond this, the user perceives lag between input and display update.

This includes: state update + view function computation + escape sequence generation + write to terminal.

For streaming output (LLM tokens, log tails, build output), the budget is per-line: each line should appear within 50ms of being produced.

### Diff Before Render

**The most important optimization**: compare the new view against the previous view and emit only the escape sequences for changed cells.

**Why it matters**: a full-screen 80×24 terminal is 1,920 cells. Redrawing all of them on every key press emits thousands of escape sequences — most of which write the same content that is already there. This causes:
- Flicker (the screen momentarily shows a cleared state before the new content appears)
- High CPU usage
- Visible artifacts for screen readers and screen recorders

**How frameworks handle it**:
- Bubble Tea: built-in diffing — only emits changes between frames
- Textual: CSS-like layout engine with dirty-tracking — only re-renders changed cells
- Ink: React virtual DOM reconciliation applied to terminal cells
- `rich`'s `Live` context manager: computes diff before writing

**Implementing manually** (when not using a framework):
```python
class TerminalRenderer:
    def __init__(self):
        self._previous: list[str] = []
    
    def render(self, lines: list[str]) -> None:
        for i, (old, new) in enumerate(zip_longest(self._previous, lines, fillvalue="")):
            if old != new:
                # Move cursor to line i, clear it, write new content
                print(f"\033[{i+1};0H\033[2K{new}", end="")
        self._previous = lines[:]
```

### DECSET 2026: Synchronized Output

**The problem**: when a terminal redraws multiple lines in sequence, each line appears as it is written. If the write loop takes >16ms (one frame), the user sees a partial redraw — lines update progressively from top to bottom, creating a "scan line" artifact. This is visible flicker.

**Claude Code had this bug** (GitHub issue #37283): the TUI streamed output without synchronized output wrapping, causing visible cursor jumping on fast output.

**The solution**: wrap each logical redraw in DECSET 2026 (synchronized output mode):

```python
import sys

SYNCHRONIZED_OUTPUT_BEGIN = "\033[?2026h"
SYNCHRONIZED_OUTPUT_END = "\033[?2026l"

def render_frame(lines: list[str]) -> None:
    sys.stdout.write(SYNCHRONIZED_OUTPUT_BEGIN)
    sys.stdout.flush()
    
    # Move to home, write all lines
    sys.stdout.write("\033[H")
    for line in lines:
        sys.stdout.write(line + "\n")
    
    sys.stdout.write(SYNCHRONIZED_OUTPUT_END)
    sys.stdout.flush()
```

The terminal buffers all escape sequences between the begin and end markers and applies them atomically in a single paint operation. No partial redraws, no flicker.

**Support**: most modern terminals (kitty, WezTerm, iTerm2, Windows Terminal, recent versions of GNOME Terminal and Alacritty) support DECSET 2026. Terminals that do not support it silently ignore the escape sequences — the code is safe to use everywhere.

**All TUI frameworks should use DECSET 2026**. If your framework does not, it is a known quality issue (as Claude Code's was).

### Stream as It Arrives

For streaming output (LLM token streaming, build logs, file processing):
- **Do not buffer** — emit each line/token as it arrives
- **Update only the active line** for in-place content (streaming LLM response being built):

```python
# For streaming LLM output: update in-place, don't create new lines
for token in stream:
    accumulated += token
    # Clear current line and rewrite
    sys.stdout.write(f"\r\033[2K{accumulated}")
    sys.stdout.flush()
# Done: move to next line
print()
```

- **Batch line writes** when many lines arrive rapidly: buffer for one render cycle (~16ms) then write all accumulated lines at once

**Users find streaming output cognitively engaging**: they understand progress is happening and can read content as it arrives. Buffering until complete then dumping is significantly more frustrating.

### Avoiding Full Redraws

For any TUI with a static layout:
- Use **cursor positioning** to update individual regions, not full-screen clear + rewrite
- **Clear only the lines that changed** (with `\033[2K`)
- **Reserve stable areas** (header, footer) and only update the scrolling content area

```
┌─────────────────────────┐  ← Header: static, rarely update
│ ADR Viewer              │
├─────────────────────────┤
│ > dec-NNN  accepted ...  │  ← Scrolling list: update as needed
│   dec-NNN  proposed ...  │
│   dec-NNN  superseded... │
├─────────────────────────┤
│ j/k: navigate  q: quit  │  ← Footer: static
└─────────────────────────┘
```

Move cursor to the list region → update only that region → footer stays untouched.
