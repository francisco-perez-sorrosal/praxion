# Advanced Markdown Patterns

Progressive disclosure and semantic enhancement for human-facing GitHub-rendered documentation. These patterns reduce cognitive load in long documents without hiding essential content.

**Back to**: [../SKILL.md](../SKILL.md)

## Scope Constraint

Apply these patterns **only to human-facing, GitHub-rendered documents**: `README.md`, `docs/*.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, and `docs/architecture.md`.

**Never apply** to:
- Agent-intermediate documents (`.ai-work/`, `.ai-state/` files)
- Context artifacts (`CLAUDE.md`, `SKILL.md`, agent/rule/command definitions)
- Any file primarily consumed by terminal `cat` or plain-text processors

---

## `<details>` / `<summary>` — Collapsible Sections

Collapses optional-depth content so readers who need the detail can expand it and readers who don't can skip it without visual noise.

### When to use

| Signal | Example |
|--------|---------|
| Section is optional depth — not required to complete the primary task | Troubleshooting, advanced config, migration notes |
| Section contains a long example that illustrates but isn't primary | Full output listings, extended code samples |
| Section answers "what if" or "why does this happen" | Edge cases, known limitations, platform quirks |
| Section would interrupt the main flow | Platform-specific notes embedded in a tutorial |

### When NOT to use

- Core content the reader needs to complete the primary task
- Short sections (< 10 lines) — collapsing adds overhead without benefit
- Tables — they lose scannability when hidden
- Documents that are not GitHub-rendered (see Scope Constraint above)

### Syntax

```html
<details>
<summary>Troubleshooting: connection refused error</summary>

Check that the server is running:

```bash
ps aux | grep server
```

Common causes: port conflict, missing env vars, firewall rule.

</details>
```

**Spacing rule**: leave a blank line after `</summary>` and before `</details>` so the enclosed Markdown renders correctly on GitHub.

**Nesting**: avoid nesting `<details>` more than one level deep — compound expansion is disorienting.

---

## GitHub Alerts — Semantic Callouts

Five alert types that render with distinct icons and background colors on GitHub and Claude. Surfaces information the reader must notice but that would be buried in prose.

### Alert types

| Type | Use when |
|------|----------|
| `[!NOTE]` | Non-obvious behavior the reader should know but won't break anything if missed |
| `[!TIP]` | Optional improvement — skipping it is fine |
| `[!IMPORTANT]` | Prerequisite or constraint the reader must know to proceed correctly |
| `[!WARNING]` | Common mistake with meaningful consequence |
| `[!CAUTION]` | Irreversible or high-risk action — destructive operations, breaking changes |

### Syntax

```markdown
> [!WARNING]
> Running this command against a production database drops all tables. Back up first.
```

### Usage constraints

- **Maximum 2–3 alerts per document** — overuse degrades signal; every alert competes with every other for attention
- **One concern per alert** — do not bundle unrelated warnings in a single block
- **Fallback rendering**: outside GitHub, alerts render as standard blockquotes — content stays readable but semantic emphasis is lost; keep alert prose self-explanatory without the icon
- **Never use in agent-intermediate documents** — agents do not benefit from visual callouts; the markup adds token noise

---

## Footnotes — Non-Primary Annotations

Annotate prose with clarifications that would interrupt flow if stated inline. Definitions collect at the document bottom.

### When to use

- Version-specific qualifications (`[^1]: Requires version 2.3+`)
- External citations or references that are supporting, not primary
- Clarifications relevant only to a subset of readers

### When NOT to use

- Information the primary reader needs inline — put it in the text
- A shortcut for rewriting unclear prose
- More than 4–5 footnotes per document (use a dedicated section instead)

### Syntax

```markdown
The installer requires elevated permissions[^1] on macOS.

[^1]: `sudo` is required on macOS 13+ due to System Integrity Protection.
```

GitHub auto-links markers and collects definitions at page bottom. Definition order does not matter; GitHub renumbers them sequentially.

---

## Anchor Links — Intra-Document Navigation

Link to specific headings within the same document. GitHub auto-generates an anchor for every heading.

### Anchor slug rules

| Heading text | Slug |
|-------------|------|
| `## Installation` | `#installation` |
| `## Quick Start` | `#quick-start` |
| `### Step 1: Configure` | `#step-1-configure` |

Rule: lowercase everything, replace spaces with `-`, strip punctuation except `-`.

### When to use

- TL;DR sections that jump the reader to a subsection
- Table of contents entries at the document top
- Cross-references within a long document ("see [Configuration](#configuration)")

### When NOT to use

- Documents with fewer than 4 sections — the reader can scroll
- Links to headings likely to be renamed (they break silently; verify with `Grep` after any rename)

---

## Decision Framework

Before applying any pattern, ask:

1. **Is this a human-facing, GitHub-rendered document?** No → do not apply.
2. **Does the content create cognitive load without delivering proportional value at that position?** Yes → consider `<details>`.
3. **Is there information the reader could easily miss that has meaningful consequences?** Yes → consider a GitHub Alert.
4. **Is there a clarification that would interrupt the primary prose if stated inline?** Yes → consider a footnote.
5. **Is the document long enough that the reader benefits from jump-links?** Yes → add anchor links to TOC or TL;DR.

The default is **no enhancement** — plain Markdown is always correct. These patterns earn their place only when they measurably reduce cognitive load.

## Cognitive Load Heuristics

These signals indicate a section is a good candidate for progressive disclosure:

| Heuristic | Suggests |
|-----------|---------|
| Section is > 30 lines and skippable by most readers | `<details>` |
| Section title starts with "Troubleshooting", "Advanced", "Migration", "Edge" | `<details>` |
| Prose contains "important:", "warning:", "note:", "caution:" in bold | GitHub Alert |
| An inline clarification starts with "Note that..." or "Keep in mind..." | Footnote |
| Document has 4+ `##` sections without a table of contents | Anchor links + TOC |
