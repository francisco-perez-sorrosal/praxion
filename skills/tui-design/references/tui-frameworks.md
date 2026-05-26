# TUI Frameworks

Framework selection, architecture patterns, and the Model-Update-View pattern that underlies all quality TUI work. Back to [SKILL.md](../SKILL.md).

**Praxion's working tools**: Python `textual` and `rich` (Python stack), Node `Ink` (Node.js stack). Go's Charm ecosystem (Bubble Tea, Lip Gloss, Gum) is the **quality exemplar** — study it for architecture even when building in Python or Node.

---

## The Core Architecture: Model-Update-View

All quality TUI frameworks share a common architecture derived from the Elm Architecture (also called Model-View-Update, or MVU):

```
State (Model) → View Function → Rendered Output
      ↑                                  ↓
      └────── Update(msg, model) ←── User Event / I/O Event
```

**Model**: immutable application state. Everything the TUI needs to render.
**Update**: a pure function `(message, model) → (new_model, effects)`. No side effects in Update.
**View**: a pure function `model → renderable_string`. Called every frame when model changes.
**Effects/Commands**: side effects (I/O, timers, HTTP) returned as *values* from Update, not executed directly. This enables deterministic testing.

**Why this matters**:
- Pure functions are trivially testable (no mocks needed)
- Proper diffing: View computes the new state; the runtime diffs against previous and emits only changed escape sequences
- Clear separation: rendering never produces side effects; side effects never produce rendering

---

## Go: Charm Ecosystem (Quality Exemplar)

The Charm ecosystem (by Charm.sh) is the highest-quality TUI framework available. Study it even if you are building in Python or Node.

### Bubble Tea

The Elm Architecture for Go TUIs.

**Core types**:
```go
type Model struct {
    // All application state
    items     []Item
    cursor    int
    loading   bool
}

type Msg interface{} // Any event: key press, tick, HTTP response

// Update: pure function, returns new model + optional command (side effect)
func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
    switch msg := msg.(type) {
    case tea.KeyMsg:
        switch msg.String() {
        case "j", "down":
            m.cursor = min(m.cursor+1, len(m.items)-1)
        case "q", "ctrl+c":
            return m, tea.Quit
        }
    case fetchResultMsg:
        m.items = msg.items
        m.loading = false
    }
    return m, nil
}

// View: pure function, returns the string to render
func (m Model) View() string {
    if m.loading {
        return "Loading...\n"
    }
    var b strings.Builder
    for i, item := range m.items {
        cursor := " "
        if m.cursor == i {
            cursor = ">"
        }
        b.WriteString(fmt.Sprintf("%s %s\n", cursor, item.Name))
    }
    return b.String()
}
```

**Commands** (side effects returned as values):
```go
// A command is a function that returns a Msg
func fetchData(url string) tea.Cmd {
    return func() tea.Msg {
        resp, err := http.Get(url)
        if err != nil {
            return errMsg{err}
        }
        // parse and return
        return fetchResultMsg{items: parseResponse(resp)}
    }
}

// Return commands from Update:
func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
    switch msg.(type) {
    case tea.KeyMsg:
        return m, fetchData("https://api.example.com/items")
    }
    return m, nil
}
```

**Why commands as values**: the Update function is pure (no side effects, testable). Commands are executed by the runtime outside the Update function. This separation enables deterministic unit tests.

### Lip Gloss

Declarative terminal styling via method chaining:

```go
import "github.com/charmbracelet/lipgloss"

var (
    titleStyle = lipgloss.NewStyle().
        Bold(true).
        Foreground(lipgloss.Color("#FAFAFA")).
        Background(lipgloss.Color("#7D56F4")).
        PaddingLeft(4).
        PaddingRight(4)

    itemStyle = lipgloss.NewStyle().
        PaddingLeft(4)

    selectedItemStyle = itemStyle.Copy().
        Foreground(lipgloss.Color("#EE6FF8")).
        Bold(true)
)

func (m Model) View() string {
    title := titleStyle.Render("My List")
    var items []string
    for i, item := range m.items {
        style := itemStyle
        if i == m.cursor {
            style = selectedItemStyle
        }
        items = append(items, style.Render(item.Name))
    }
    return lipgloss.JoinVertical(lipgloss.Left, append([]string{title}, items...)...)
}
```

**Key features**:
- Method chaining on style structs
- Automatic color-depth detection and fallback
- Layout helpers: `JoinHorizontal`, `JoinVertical`, `Place` (padding to position within a box)
- Border rendering: `Border(lipgloss.RoundedBorder())`

### Gum

High-level composable interactive CLI components. Scriptable from shell:

```sh
# Fuzzy selection
name=$(gum choose "Alice" "Bob" "Carol")

# Text input with validation hint
email=$(gum input --placeholder "Enter your email")

# Confirmation prompt
if gum confirm "Deploy to production?"; then
    deploy
fi

# Spinner while running a command
gum spin --spinner dot --title "Deploying..." -- ./deploy.sh

# File picker
file=$(gum file)
```

**Also available as a Go library** (`github.com/charmbracelet/glamour` for Markdown rendering in terminal).

---

## Python: textual and rich (Working Tools)

### rich

Rich is a rendering library — it handles output, not interactivity. It is the layer that `textual` builds on.

**Use rich when**: you need beautiful output without a full TUI (tables, progress bars, syntax highlighting, Markdown rendering, pretty-printing data structures).

```python
from rich.console import Console
from rich.table import Table
from rich.progress import track

console = Console()

# Table rendering
table = Table("ID", "Status", "Title")
table.add_row("dec-NNN", "[green]accepted[/green]", "Use PostgreSQL...")
console.print(table)

# Progress bar
for item in track(items, description="Processing..."):
    process(item)

# Syntax highlighting
from rich.syntax import Syntax
code = Syntax(python_code, "python", theme="monokai", line_numbers=True)
console.print(code)

# Markdown
from rich.markdown import Markdown
console.print(Markdown(markdown_text))
```

**Key behaviors**:
- Auto-detects TTY and disables color/markup when not in a TTY
- Respects `NO_COLOR` environment variable
- `Console(stderr=True)` for error output
- `Console(force_terminal=False)` to force non-TTY behavior

### textual

Textual is a full-featured TUI framework — it handles layout, reactivity, events, and rendering.

**Use textual when**: you need a real interactive application (multi-pane layout, widgets, keyboard-driven navigation, live-updating data).

```python
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, LoadingIndicator
from textual.reactive import reactive

class ADRViewer(App):
    CSS = """
    DataTable { height: 1fr; }
    #detail { width: 50; border: round $primary; }
    """
    
    selected_id: reactive[str | None] = reactive(None)
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable()
        yield Footer()
    
    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("ID", "Status", "Title")
        for adr in self.load_adrs():
            table.add_row(adr.id, adr.status, adr.title)
    
    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.selected_id = event.row_key.value
```

**Key features**:
- CSS-like styling system (subset of CSS)
- Reactive attributes that automatically trigger re-renders
- Async I/O without blocking the UI
- Rich widget library (DataTable, ListView, TabbedContent, Log, etc.)
- Built on `rich` for rendering

**Textual render model**: textual handles the diff-before-render automatically — only changed cells re-render. Uses `asyncio` for the event loop; `Worker` API for background tasks without blocking the UI.

### prompt_toolkit

Use `prompt_toolkit` when you need a custom REPL, line editor, or auto-completing input — not a full TUI. It powers IPython and the Postgres `pgcli` REPL.

---

## Node.js: Ink (Working Tool)

Ink brings React's component model to terminal rendering. Use when the application is in a Node.js context.

```tsx
import React, { useState, useEffect } from 'react';
import { Box, Text, useInput } from 'ink';

function ItemList({ items }: { items: string[] }) {
  const [cursor, setCursor] = useState(0);
  
  useInput((input, key) => {
    if (key.downArrow) setCursor(c => Math.min(c + 1, items.length - 1));
    if (key.upArrow) setCursor(c => Math.max(c - 1, 0));
  });
  
  return (
    <Box flexDirection="column">
      {items.map((item, i) => (
        <Text key={item} color={i === cursor ? 'cyan' : undefined}>
          {i === cursor ? '> ' : '  '}{item}
        </Text>
      ))}
    </Box>
  );
}
```

**Key features**:
- JSX component model — same mental model as React web
- Flexbox layout system (via yoga-layout)
- `useInput` hook for keyboard events
- `useStdin`, `useStdout` for stream access
- Automatic diff-based rendering (like React's virtual DOM, but for terminal cells)

**Ecosystem**: `ink-text-input`, `ink-select-input`, `ink-spinner`, `ink-progress-bar` — maintained component library.

---

## Framework Selection Decision
<!-- last-verified: 2026-05-12 -->

| Context | Framework |
|---------|-----------|
| Python — interactive TUI with layout | `textual` |
| Python — beautiful output, no interaction | `rich` |
| Python — custom REPL or line-editor | `prompt_toolkit` |
| Node.js — interactive TUI | `Ink` |
| Go — interactive TUI | Bubble Tea + Lip Gloss |
| Go — interactive CLI prompts | Gum |
| Any — quality reference for architecture | Charm ecosystem |
| Shell script — simple prompts | `gum` (cross-platform) |

**Architecture principle regardless of framework**: separate state from rendering (the Model-Update-View split), return side effects as values not inline calls, diff before rendering. These principles hold in all four frameworks — the API syntax differs, the architecture does not.
