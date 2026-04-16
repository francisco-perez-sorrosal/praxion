---
paths:
  - "skills/**/SKILL.md"
---

## Staleness Policy

Convention for marking and maintaining drift-prone sections in skill files.
Paths-scoped — loaded only when a skill's `SKILL.md` is being read or edited.

### Marker Syntax

Mark a sensitive section with an HTML comment placed **directly below the section's h2/h3 heading** (no blank line between heading and marker):

```markdown
### Current Model Lineup
<!-- last-verified: 2026-04-16 -->

... section body ...
```

The short form — `<!-- last-verified: YYYY-MM-DD -->` — is the canonical form. Date must be ISO 8601 (`YYYY-MM-DD`) and not in the future.

### Extended Form

An optional extended form adds a human-readable audit trail:

```markdown
<!-- last-verified: 2026-04-16 by: fperez note: refreshed against claude-ecosystem docs v1.2 -->
```

The `by:` and `note:` fields are advisory — the sentinel ignores them for staleness calculation but they are preserved for human review. Order is fixed: date first, then optional `by:`, then optional `note:`.

### Frontmatter Schema

Each skill declares its sensitive sections in its `SKILL.md` frontmatter:

```yaml
---
name: claude-ecosystem
description: ...
staleness_sensitive_sections:
  - "Current Model Lineup"
  - "Server-Side Tools"
  - "SDK Quick Reference"
staleness_threshold_days: 120   # optional per-skill override
---
```

Titles are matched **case-sensitively against the rendered h2/h3 text** — not against slug anchors. Rename a heading and the sentinel's F07 check catches the drift on the next pass.

### Threshold Defaults

- **Global default**: 120 days (skills without `staleness_threshold_days:` use this value).
- **Per-skill override**: set `staleness_threshold_days:` in the skill's frontmatter. Typical overrides: 60 days for fast-moving API surfaces, 180 days for slow-moving conventions.
- **Escalation**: beyond 2× threshold (default 240 days) a stale section escalates from WARN to FAIL.

### Exclusion Semantics

To mark a section as permanent (never stale), use the exclusion keyword:

```markdown
### Using Lowercase Tags
<!-- last-verified: permanent -->
```

The sentinel treats `permanent` as never-expiring. Reserve this for genuinely immutable guidance — naming conventions, structural invariants, syntax rules. Do **not** use it for anything tied to an external API version.

### Missing-Marker Semantics

A section listed in `staleness_sensitive_sections:` that has no marker below its heading triggers a **WARN** (not FAIL) from sentinel check F07 — the "never verified" cold-start state. Rationale: backfill campaigns would otherwise produce a flood of FAILs on first sentinel pass. WARN signals "this needs attention" without blocking.

Once a marker exists, F07 stops firing for that section and F08 takes over (age check).

### Refresh Workflow

To refresh one or more sensitive sections in a skill, invoke the slash command:

```
/refresh-skill <skill-name>
```

The command iterates every section listed in `staleness_sensitive_sections:`, fetches current-state docs via the [external-api-docs](../../skills/external-api-docs/SKILL.md) skill, diffs against the section body, and prompts per-section: Accept / Revise / Skip / Permanent. Date bumps require explicit user confirmation — no silent refreshes.

See [commands/refresh-skill.md](../../commands/refresh-skill.md).

### Sentinel Check IDs

The staleness protocol is enforced by three checks in the sentinel's Freshness (F) dimension:

| ID  | Check                                    | Severity                              |
|-----|------------------------------------------|---------------------------------------|
| F07 | Cataloged section missing marker         | WARN                                  |
| F08 | Marker age > threshold                   | WARN (→ FAIL beyond 2× threshold)     |
| F09 | Marker invalid format or future-dated    | FAIL                                  |

See [`agents/sentinel.md`](../../agents/sentinel.md) for the full check catalog.
