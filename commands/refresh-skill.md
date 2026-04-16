---
description: Refresh version-sensitive sections of a skill against current upstream documentation
argument-hint: <skill-name>
allowed-tools: [Read, Edit, Write, Grep, Glob, AskUserQuestion]
---

Refresh the drift-prone sections of a skill declared in its `staleness_sensitive_sections:` frontmatter. Driven by the [external-api-docs](../skills/external-api-docs/SKILL.md) skill for fetching authoritative current-state docs. Gates every date bump on explicit user confirmation — never silently refreshes. See [rules/swe/staleness-policy.md](../rules/swe/staleness-policy.md) for the marker protocol.

## Arguments

- `$ARGUMENTS` — the skill name (directory name under `skills/`), e.g., `claude-ecosystem`

## Process

### 1. Parse Skill Frontmatter

Read `skills/$ARGUMENTS/SKILL.md`. Parse its YAML frontmatter and extract:

- `staleness_sensitive_sections:` — list of exact h2/h3 headings
- `staleness_threshold_days:` — integer; default **120** when absent

If `staleness_sensitive_sections:` is missing or empty: report "no sensitive sections declared for `$ARGUMENTS`" and exit without modifying files.

### 2. Locate Each Section

For every entry in `staleness_sensitive_sections:`:

- Find the matching h2/h3 heading in `SKILL.md` (case-sensitive exact match)
- Identify the `<!-- last-verified: ... -->` marker directly below it (may be missing)
- Capture the current section body — from the heading to the next heading of equal or greater level

If a listed title has no matching heading, report it as a rename/delete drift and skip that entry (the sentinel's F07 will flag it independently).

### 3. Fetch Authoritative Docs

For each sensitive section, use the [external-api-docs](../skills/external-api-docs/SKILL.md) skill to fetch the current state:

- Infer the topic from the section's heading and body content
- Prefer `chub_search` + `chub_get` for curated coverage; fall back to `WebFetch` / `WebSearch` for topics without chub entries
- Extract only the excerpts relevant to the section's claims — do not paste entire docs

### 4. Diff and Prompt

For each section, compare the current skill body against the fetched authoritative content. Present the diff to the user and ask per section:

- **Accept** — apply the revision to the section body; update the marker to `<!-- last-verified: <today> -->`
- **Revise** — user edits the section manually; after edit, update the marker to today's date
- **Skip** — leave the section untouched; marker is **not** bumped (section remains stale)
- **Permanent** — replace the marker with `<!-- last-verified: permanent -->` (use only for immutable guidance)

Use `AskUserQuestion` for the four-choice prompt. Never modify a marker or section body without explicit user choice.

### 5. Append Run Summary

After processing all sections, append one line to `.ai-state/staleness_refresh_log.md` (create if missing):

```
YYYY-MM-DD HH:MM | <skill-name> | <N> accepted, <N> revised, <N> skipped, <N> permanent
```

Use ISO 8601 UTC timestamps. The log is append-only — do not rewrite prior entries.

## Exit Conditions

- All sections current and no changes needed → report "no sections stale" and exit without writing to the log
- User cancels mid-run → persist any already-applied changes; append partial summary to the log
- Skill missing or frontmatter malformed → report the error and exit non-zero
