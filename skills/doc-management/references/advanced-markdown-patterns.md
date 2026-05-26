# Advanced Markdown Patterns

Progressive disclosure and semantic enhancement for human-facing GitHub-rendered documentation. These patterns reduce cognitive load in long documents without hiding essential content. Back to [SKILL.md](../SKILL.md).

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
- Cross-references within a long document ("see [Configuration](#configuration)") <!-- validate-references:ignore -->
<!-- The bracketed example above is illustrative; #configuration is a hypothetical anchor used for teaching, not a navigable link in this file. -->

### When NOT to use

- Documents with fewer than 4 sections — the reader can scroll
- Links to headings likely to be renamed (they break silently; verify with `Grep` after any rename)

---

## Emojis as Cognitive Anchors

Emojis are tools, not decoration. A well-placed emoji reduces cognitive load by giving the eye a non-text anchor it can find without reading. A poorly placed one adds noise, looks unprofessional, and on some renderers degrades to a tofu box.

### When to use

| Signal | Example | Why it earns its place |
|--------|---------|------------------------|
| Status at a glance | `✅ Passing` / `❌ Failing` / `⚠️ Flaky` | Reader scans status without parsing words |
| Stable category marker in scannable lists | `🔧 Setup`, `🔑 Credentials`, `🚀 Run` across a long TOC | Anchors the eye on row-type without re-reading the heading |
| Single sequence-step marker | `1️⃣ Install → 2️⃣ Configure → 3️⃣ Run` (inline only) | Reinforces ordering when the steps are visually linear |
| Recurring concept identifier | A section that always opens with `📚 Reference` | Trains the reader to find the same concept in the same shape |

### When NOT to use

- **Decorative emojis on every heading** — they stop being signal and become noise
- **Emojis in body prose** — they interrupt reading flow and hurt accessibility (screen readers read every one aloud)
- **More than one emoji per heading or per bullet** — competing anchors cancel each other out
- **Emoji-only labels** — `🚀 Run` is fine; `🚀` alone is hostile to screen readers, search, and copy-paste
- **Skin-tone modifiers, ZWJ sequences, recent additions** — rendering varies wildly across GitHub web, terminals, IDEs, and older platforms; stick to the broadly-supported set
- **Inside code blocks, tables of dense data, or anywhere monospace matters** — emoji glyph widths break column alignment

### Accessibility

Screen readers announce each emoji by its Unicode name. `✅` reads as "check mark button", `❌` as "cross mark". Pick emojis whose spoken name matches the intent — and always pair them with text so the message survives if the emoji fails to render.

### Limits

- **At most one emoji per heading**, and only when the emoji adds a non-redundant signal
- **At most one emoji per bullet** in a scannable list; never every bullet — the marker only stands out when it's selective
- **No emojis in agent-intermediate documents** (`.ai-work/`, `.ai-state/`) — agents do not benefit from visual anchors, and the bytes are waste in tight context windows
- **No emojis in `CLAUDE.md`, `SKILL.md`, or agent/rule/command definitions** — same reason, plus these files set the project's writing tone for agents

### Tone calibration

Praxion's documentation voice is professional-technical. Use emojis at the rate a senior engineer would in a release-notes summary, not the rate a marketing landing page would. If you would not say "🎉 yay" aloud in a code review, do not put it in a README.

---

## Color & Visual Tone

Markdown gives you very little color authority on purpose — and that's a feature, because color is the easiest signal to overuse. Where color does appear (GitHub Alerts, status badges, syntax-highlighted code), discipline matters more than palette choice.

### Color sources in GitHub-rendered Markdown

| Source | Color comes from | Author control |
|--------|------------------|----------------|
| **GitHub Alerts** (`> [!WARNING]` etc.) | GitHub's theme — distinct icon + tinted background per type | Type choice only; never override |
| **Syntax-highlighted code blocks** | Language identifier on the fence (` ```python `) | Set the language; the renderer does the rest |
| **Status badges** (shields.io and similar) | Badge service — color encodes status (green = passing, red = failing) | Choose meaningful badges; cap the count |
| **Inline `code spans`** | Theme — usually a subtle background tint | Apply to identifiers, paths, commands |

**Never** reach for `<span style="color:...">` or other raw HTML to inject color. It does not render uniformly across GitHub web, mobile, and Claude's renderer; it breaks accessibility; and it signals an author trying to manually art-direct what is meant to be a uniform reading surface.

### Badge discipline

Badges are the one place where color is reader-facing visual signal in most READMEs. Keep them honest:

- **Status badges only** — build status, license, package version, coverage. Skip vanity badges (stars, follower counts).
- **Cap at 3–4 per README**, in a single row directly under the title.
- **Each badge must be a live link** to the underlying source (the CI run, the license file, the package page) — never a screenshot or hard-coded color.
- **Order**: most reader-relevant first (CI status before download count).

### Visual hierarchy without color

Pair color with shape or text — never rely on color alone. The hierarchy strength order, weakest to strongest signal:

1. **Color alone** — weakest; fails for color-blind readers (~8% of men) and in monochrome renders
2. **Position** — early-in-document signals importance
3. **Weight / boldness** — `**bold**` and headings carry more weight than color
4. **Size** — heading levels (`#` vs `###`) and badge size
5. **Combined signals** — bold + alert icon + first paragraph; this is what GitHub Alerts already do well

For HTML and dashboard surfaces, the depth lives in [`skills/web-ui-design/SKILL.md`](../../web-ui-design/SKILL.md) and its references — contrast ratios, grayscale-first palette construction, semantic token system, the full WCAG 2.2 AA bar. Markdown authors do not need to load it; HTML authors do.

### Tone defaults

The Praxion docs voice across Markdown and HTML:

- **Calm, not exclamatory** — periods over exclamation points; no "Awesome!" or "🎉"
- **Specific, not encouraging** — "Requires Python 3.11+" beats "You can use any recent Python!"
- **One concern per alert** — splitting two warnings across two alerts beats stuffing them into one
- **Consistent across the project** — pick a color/emoji vocabulary at the project level and apply it everywhere; mixed styles read as multiple voices

### When to consult `web-ui-design`

Three Markdown-rendering situations benefit from loading the design canon:

1. **HTML share-out artifacts** (`share_out: true` frontmatter) — these go to non-GitHub readers; load `web-ui-design` for contrast, focus, motion, dark-mode safety
2. **`docs/architecture.md`** when it embeds diagrams — diagram colors and node weights are visual-design decisions
3. **`README.md` with significant badge strips or visual TOCs** — composition discipline is a design-canon question

---

## Decision Framework

Before applying any pattern, ask:

1. **Is this a human-facing, GitHub-rendered document?** No → do not apply.
2. **Does the content create cognitive load without delivering proportional value at that position?** Yes → consider `<details>`.
3. **Is there information the reader could easily miss that has meaningful consequences?** Yes → consider a GitHub Alert.
4. **Is there a clarification that would interrupt the primary prose if stated inline?** Yes → consider a footnote.
5. **Is the document long enough that the reader benefits from jump-links?** Yes → add anchor links to TOC or TL;DR.
6. **Would a small, stable set of category emojis help the reader scan a long list of headings or rows?** Yes → add emoji anchors, one per row, one per heading, never in body prose.
7. **Is there a high-stakes status, license, or version signal currently buried in prose?** Yes → add a 3–4-badge strip directly under the title.
8. **Does the doc rely on color alone to convey any meaning?** Yes → pair color with shape, text, or icon; never `<span style="color:...">`.

The default is **no enhancement** — plain Markdown is always correct. These patterns earn their place only when they measurably reduce cognitive load.

## Cognitive Load Heuristics

These signals indicate a section is a good candidate for one of the patterns above:

| Heuristic | Suggests |
|-----------|---------|
| Section is > 30 lines and skippable by most readers | `<details>` |
| Section title starts with "Troubleshooting", "Advanced", "Migration", "Edge" | `<details>` |
| Prose contains "important:", "warning:", "note:", "caution:" in bold | GitHub Alert |
| An inline clarification starts with "Note that..." or "Keep in mind..." | Footnote |
| Document has 4+ `##` sections without a table of contents | Anchor links + TOC |
| Headings repeat the same category (Setup, Run, Reference) across a long doc | Emoji category markers (one per heading) |
| Status, license, version, or CI state is currently stated in prose only | Badge strip under the title |
| Author has reached for `<span style="color:...">` or other raw HTML for emphasis | Switch to GitHub Alert / bold / code span — never raw color HTML |
| Every heading already has an emoji and they all read the same | Remove emojis — selective use only |
| README contains "🎉", multiple `!`s, or marketing-tone prose | Tone-down pass: drop decorative emojis, replace exclamations with periods |
