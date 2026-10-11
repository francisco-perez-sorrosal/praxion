<!--
LANDSCAPE WATCHLIST TEMPLATE — shipped scaffold.

This template defines the schema and section structure for a project's
.ai-state/LANDSCAPE_WATCHLIST.md — a curated, machine-readable index of
external sources (peer projects, blogs, standards bodies, reference repos)
that the project's internal ideation agents (promethean, roadmap-cartographer)
consult to ground proposals in adjacent-project traction and ecosystem
evolution.

STRUCTURAL CONVENTION

The structure follows the llms.txt convention (https://llmstxt.org), inverted
in use: that convention defines how a website *exposes* a token-efficient
markdown index of its docs to external AI agents; this template uses the same
shape *inbound* — to expose curated *external* sources to the project's *own*
agents.

Mandated by the convention:
  - H1 (project name) is the only required element
  - Blockquote summary (one paragraph) is conventional; strongly recommended
  - H2 sections delimit "file lists"
  - Each entry is a markdown bullet: `- [name](url)` with optional `: notes`
  - The special H2 `## Optional` signals skip-if-tight-context-window — agents
    consult these only when budget allows; not a graveyard

PRAXION-SPECIFIC EXTENSION

Per-entry `last-checked YYYY-MM-DD` is appended to the description after a
` · ` separator. The base llms.txt spec defines no temporal field; this
extension fits inside the spec's free-form colon-notes affordance but is
non-standard. The /landscape-refresh skill relies on it to flag entries
older than 90 days. Entries under `## Inactive / archived` omit this field —
they are tombstoned.

FILLING INSTRUCTIONS (read before scaffolding a new watchlist)

The first agent or /landscape-refresh invocation that materializes this file
in a project must derive the H1 title and the blockquote summary from the
consuming project's actual context. Do NOT copy a fixed summary across
projects — the watchlist's purpose is genuinely different in each project.

1. Read the project's CLAUDE.md and README.md (or README*.md). Extract:
   - What the project DOES (its core goal — one sentence)
   - WHO uses Praxion (or the host platform) to build it (developer, team, AI agents themselves)
   - WHAT external signals therefore matter — peer projects to learn from,
     blogs that surface emergent patterns, governance bodies whose decisions
     ripple into the project's design space
2. Compose a project-specific blockquote (two sentences):
   - Sentence 1: project's stance + goal
   - Sentence 2: what kinds of external signals this watchlist tracks and
     which agents (promethean, roadmap-cartographer) consume it
3. Replace the H1 placeholder with `<Project Name> Landscape Watchlist`.
4. Leave the section scaffolds in place. Do NOT seed entries — the user owns
   the curation decisions for their project. Stop and ask the user to provide
   the first round of peer projects, blogs, and standards bodies. Bootstrapping
   without user input invents content that may be irrelevant to the project's
   actual domain.
-->

# [Project Name] Landscape Watchlist

> [Project-specific summary — REPLACE this placeholder per the FILLING INSTRUCTIONS above. Two sentences: (1) the project's goal and stance, (2) what kinds of external signals this watchlist tracks and which agents (promethean, roadmap-cartographer) consume it. Each project's blockquote should be genuinely different — do not duplicate across projects.]

## Peer projects

Active projects in adjacent or competing problem spaces. Watch for design patterns, traction signals, deprecations.

- [Example Peer Project](https://example.com): one-line stance — what to watch for · last-checked YYYY-MM-DD

## Blogs / writers / feeds

Practitioner writing with original signal. Prefer reputable individuals and engineering teams whose original ideas shape the field. Avoid pure marketing channels — quality of ideas is what matters.

- [Example Source](https://example.com): one-line stance · cadence note (e.g., "weekly", "RSS: …", "irregular high-impact") · last-checked YYYY-MM-DD

## Standards & convening bodies

Working groups, foundations, and protocol authors whose decisions ripple into the project's design space.

- [Example Body](https://example.com): one-line stance — current draft / roadmap link · last-checked YYYY-MM-DD

## Reference repos

Canonical implementations, exemplary docs, or pattern-defining artifacts worth modeling against.

- [Example Repo](https://example.com): one-line stance — what's exemplary · last-checked YYYY-MM-DD

## Optional

Lower-priority entries — agents may skip these under tight context-window budgets. Use sparingly: only entries worth keeping but rarely load-bearing for a given ideation pass. Not a graveyard; demoted, not deactivated.

- [Example Lower-Tier Source](https://example.com): one-line stance · last-checked YYYY-MM-DD

## Inactive / archived

Known-but-stale projects, kept here so future watchlist refreshes don't re-add them. Entries omit the `last-checked` field — they are tombstoned.

- [Example Archived Project](https://example.com): why stale (e.g., "shut down 2024", "renamed to X", "absorbed into Y")

<!--
SCHEMA NOTES (do not strip)

Active sections (Peer projects, Blogs, Standards, Reference repos, Optional):
  - Entry: `- [Title](URL): one-line stance · last-checked YYYY-MM-DD`
  - Optional cadence note (RSS URL, "weekly", etc.) goes between stance and date,
    separated by ` · `

Inactive section:
  - Entry: `- Title (no link if dead): why stale`
  - Omit `last-checked` — tombstoned entries are not roll-checked

Section discipline:
  - Add a new H2 only if the project's domain genuinely needs one. The watchlist
    is an index, not a knowledge base. Keep section count ≤ 7.
  - The `## Optional` H2 is semantic per the llms.txt spec; agents may skip it
    under tight context budgets. Use it for low-signal entries, not as a
    holding pen for "maybe drop these later".

Refresh discipline:
  - The /landscape-refresh skill flags entries with last-checked > 90 days.
  - When an entry is flagged, the user decides: keep + bump date · drop · move
    to Inactive.
-->
