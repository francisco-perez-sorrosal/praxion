---
description: Bootstrap or refresh the project's landscape watchlist — flag stale entries (>90 days) and optionally re-validate URLs
allowed-tools: [Read, Write, Edit, Bash, WebFetch, AskUserQuestion, Glob]
disable-model-invocation: true
---

Maintain `.ai-state/LANDSCAPE_WATCHLIST.md` — the curated index of external sources that ideation agents (`promethean`, `roadmap-cartographer`) consult to ground proposals in adjacent-project traction and ecosystem evolution. The watchlist follows the [llms.txt convention](https://llmstxt.org) inbound: an index of *external sources for our agents*, not docs we expose to others.

## When to run

- Before invoking `/roadmap` or `promethean` for fresh ideation, when stale entries would degrade their grounding.
- After significant time elapsed since the last watchlist edit.
- Manually after the user mentions new peer projects, blogs, or standards bodies they want tracked.
- On a project that doesn't yet have a watchlist — to bootstrap from the shipped template.

## Procedure

### Step 1 — Detect file presence

Check for `.ai-state/LANDSCAPE_WATCHLIST.md`. If missing, go to **Bootstrap mode**. If present, go to **Refresh mode**.

### Bootstrap mode — file does not exist

1. Read `skills/roadmap-synthesis/assets/LANDSCAPE_WATCHLIST_TEMPLATE.md` (the shipped template). Read its FILLING INSTRUCTIONS comment.
2. Read the project's `CLAUDE.md` and `README.md` (or `README*.md` if README.md is missing). Extract:
   - The project's core goal (one sentence)
   - Who uses the project (developers, team, AI agents themselves)
   - What external signals therefore matter
3. Copy the template to `.ai-state/LANDSCAPE_WATCHLIST.md`.
4. Replace the H1 placeholder with `<Project Name> Landscape Watchlist`.
5. Compose a **project-specific** blockquote summary (two sentences) and replace the placeholder. Make it genuinely different from any boilerplate — the goal is for each consuming project's watchlist to reflect that project's actual domain.
6. Leave the H2 section scaffolds in place with their example placeholder rows.
7. Stop and ask the user (`AskUserQuestion`): "Watchlist scaffold ready at `.ai-state/LANDSCAPE_WATCHLIST.md`. Provide the first round of peer projects, blogs, and standards bodies you want tracked, or invoke `/landscape-refresh` again later when ready." Do not invent entries.

### Refresh mode — file exists

1. **Compute today's date** via `Bash`: `date -u +%Y-%m-%d`. Compute the staleness cutoff: today minus 90 days.

2. **Parse every entry** under the active sections (Peer projects, Blogs, Standards, Reference repos, Optional) — skip `## Inactive / archived` (tombstoned, no `last-checked`).

3. **Extract `last-checked YYYY-MM-DD`** from each entry's description. For each entry:
   - Compare against the cutoff.
   - Mark stale if `last-checked` is older than 90 days.
   - Flag missing or malformed `last-checked` as stale by default (treat as needing user attention).

4. **If zero stale entries**, report `Clean — N entries, all checked within 90 days.` and stop.

5. **If stale entries exist**, present them to the user as a markdown table:

   | # | Section | Entry | Last-checked | Age (days) |
   |---|---|---|---|---|
   | 1 | Peer projects | Aider | 2026-01-15 | 105 |
   | 2 | Blogs | Simon Willison | 2026-01-20 | 100 |

6. **Ask the user (`AskUserQuestion`)** for a decision per stale entry:
   - **keep + bump** — entry is still relevant; update `last-checked` to today.
   - **drop** — remove from the watchlist.
   - **inactivate** — move to `## Inactive / archived` with a one-line reason; strip `last-checked`.
   - **revalidate** — `WebFetch` the URL first to confirm it still resolves and looks current; then prompt again with keep/drop/inactivate.

7. **Optional URL re-validation**: when the user picks **revalidate**, `WebFetch` the entry's URL. Report status (200 OK, redirect target, content currency hint based on visible dates if any). The user then decides keep/drop/inactivate based on the fresh signal.

8. **Apply edits**:
   - For **keep + bump**: rewrite the entry's `last-checked YYYY-MM-DD` to today.
   - For **drop**: remove the bullet.
   - For **inactivate**: cut the bullet from its section, append it under `## Inactive / archived` with the format `- Title: why stale (no last-checked)`.

9. **Save** `.ai-state/LANDSCAPE_WATCHLIST.md`.

10. **Report a one-line summary**: `Refresh complete — kept N · bumped N · dropped N · inactivated N · revalidated N.`

## Constraints

- **Do not invent entries.** Bootstrap mode leaves section scaffolds empty for the user to seed; refresh mode never adds entries on its own (it only mutates existing ones).
- **Stale threshold is 90 days.** Hardcoded — adjust by editing this command file rather than introducing a configuration setting.
- **Inactive entries are tombstoned.** Once a user picks `inactivate`, the entry stays in `## Inactive / archived` and is not roll-checked again. Future refreshes ignore it.
- **The `## Optional` section is rolled like any active section.** It is a relevance demotion, not an inactivity marker.
- **No commit.** This command modifies the working tree and stops; the user commits when ready.

## Implementation notes

- Date arithmetic in `Bash` (BSD `date` on macOS does not accept `-d`):
  ```bash
  today=$(date -u +%Y-%m-%d)
  # For each entry's last-checked YYYY-MM-DD:
  age_days=$(( ( $(date -u -j -f "%Y-%m-%d" "$today" +%s) - $(date -u -j -f "%Y-%m-%d" "$entry_date" +%s) ) / 86400 ))
  ```
  GNU `date` (Linux) uses `date -u -d "$date_str" +%s`. Detect platform via `uname -s` if portability matters; both forms are acceptable.

- Parse `last-checked` with a simple regex on each bullet: `last-checked (\d{4}-\d{2}-\d{2})`. Entries that don't match the regex are flagged stale-by-default (forces user attention to malformed entries).
