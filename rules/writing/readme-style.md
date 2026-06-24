---
paths:
- '**/README.md'
- '**/README_DEV.md'
core: false
---

## README Writing Style

Technical documentation style for README.md files. Applies the Adaptive Precision philosophy: every sentence must earn its place.

### Core Principle

**Self-contained and precise.** A README succeeds when the reader can understand what the artifact is, what it does, and how to use it — without leaving the document. When a topic requires depth beyond the README's scope, provide minimal inline context so the reader can decide whether to follow the link, then link to the authoritative source rather than inlining a verbose explanation.

### Decision Framework

Match content depth to complexity:

- **Simple/factual** (install command, license) — state it directly, no elaboration
- **Complex/technical** (architecture, non-obvious config) — include reasoning so the reader can apply it correctly
- **Multi-part** (setup steps, API reference) — numbered discrete sections, no connecting prose between them
- **Unclear scope** — state the most literal interpretation with basic prerequisites included

### Mandatory Inclusions

- Include reasoning when: the reader cannot apply the information without understanding the process
- Include prerequisites when: the reader's background knowledge is uncertain
- Include examples when: the concept requires process knowledge to execute correctly

### Mandatory Exclusions

- No social filler, hedging, encouragement, or satisfaction checks
- No redundant sections — if a section adds nothing the reader needs, omit it

### Emojis, Badges, and Color

These signals reduce cognitive load only when used selectively, and add noise when overused. Praxion's voice is professional-technical — calibrate accordingly.

- **Emojis**: status anchors (`✅`, `❌`, `⚠️`), category markers across a long list of similar rows, or a stable identifier for a recurring concept. At most one per heading, at most one per bullet, never in body prose. Pair every emoji with text so the meaning survives if the glyph fails to render. Never use in agent-intermediate documents (`.ai-work/`, `.ai-state/`) or in `CLAUDE.md` / `SKILL.md` / agent / rule / command files.
- **Badges**: 3–4 maximum, single row directly under the title, status-only (build, license, version, coverage). Each badge must be a live link. Skip vanity badges (stars, follower counts).
- **Color**: never use `<span style="color:...">` or other raw HTML for color. Color sources are limited to GitHub Alerts (theme-controlled), syntax-highlighted code blocks (set the language), badges (status-encoded), and inline `code` spans. Never rely on color alone — pair with shape, text, or icon.
- **Tone**: calm, periods over exclamation points; one concern per alert; consistent vocabulary across the project.

Depth, the decision framework, and cognitive-load heuristics live in [`skills/doc-management/references/advanced-markdown-patterns.md`](../../skills/doc-management/references/advanced-markdown-patterns.md).

### Structure Conventions

- Lead with what the project **is** and **does** — one or two sentences maximum
- Follow with what the reader needs to **use** it (install, configure, run)
- End with what the reader needs to **contribute** or **understand** the internals (only if applicable)
- Omit sections that have no content — an empty "Contributing" section is worse than none
- Use bullet points and numbered lists for scannable content
- Use code blocks for anything the reader will copy-paste

### Scaling Long READMEs

Add TL;DR + table of contents at 4-5+ sections. Split into companion documents (`.ai-state/DESIGN.md`, `CONTRIBUTING.md`) when depth exceeds entry-point scope.

### Markdown Enhancement Patterns

For human-facing, GitHub-rendered documents only (`README.md`, `docs/*.md`, `CONTRIBUTING.md`, `CHANGELOG.md`). These patterns reduce cognitive load in long documents without hiding essential content. The default is plain Markdown — each pattern must earn its place.

**`<details>`/`<summary>`** — collapse optional-depth content (troubleshooting, advanced config, long examples) that most readers can skip. Do not collapse core content, short sections (< 10 lines), or tables.

**GitHub Alerts** — use `> [!NOTE]`, `> [!TIP]`, `> [!IMPORTANT]`, `> [!WARNING]`, or `> [!CAUTION]` for information the reader must notice but that would be buried in prose. Limit to 2–3 per document; overuse degrades signal.

**Footnotes** (`[^1]`) — annotate prose with clarifications that would interrupt flow if stated inline (version qualifications, edge-case notes, citations). Keep to 4 or fewer per document.

**Anchor links** (`[text](#heading-slug)`) — for TL;DR sections, table-of-contents entries, and intra-document cross-references in documents with 4+ sections.

**Scope constraint**: never apply to agent-intermediate documents (`.ai-work/`, `.ai-state/`), context artifacts (`CLAUDE.md`, `SKILL.md`), or agent/rule/command definitions — these are not GitHub-rendered and the markup adds noise.

### Structural Integrity and Naming

- All filesystem paths, links, and cross-references must resolve to existing targets
- Catalog READMEs must list every artifact on the filesystem — no phantom or missing entries
- Counts in prose must match actual item counts; structure trees must match current filesystem
- Use exact filenames (minus extension), follow the project's naming convention consistently
- When an artifact is renamed, update all documentation references in the same change

### Writing Quality

- Imperative mood for instructions ("Install the package", not "You should install the package")
- Active voice — "The server handles requests" not "Requests are handled by the server"
- Specific over generic — "Requires Python 3.11+" not "Requires a recent Python version"
- One idea per sentence — break compound explanations into discrete statements
- Consistent terminology — pick one term for each concept and use it everywhere

### Termination Criteria

A section is complete when the reader has a direct answer and enough process knowledge to execute correctly (including *why* when the topic demands it). Stop there — additional content dilutes signal.
