---
id: dec-046
title: Staleness detection via per-section markers, frontmatter catalog, paths-scoped rule
status: accepted
category: behavioral
date: 2026-04-16
summary: Adopt `<!-- last-verified: YYYY-MM-DD -->` marker at h3 granularity (h2 fallback) with an in-frontmatter `staleness_sensitive_sections:` catalog; add sentinel F07/F08/F09 checks; new paths-scoped rule at `rules/swe/staleness-policy.md`; gated `/refresh-skill` command; default threshold 120 days
tags: [staleness, sentinel, skills, rules, commands, freshness]
made_by: agent
agent_type: systems-architect
pipeline_tier: full
affected_files:
  - rules/swe/staleness-policy.md
  - agents/sentinel.md
  - commands/refresh-skill.md
  - skills/claude-ecosystem/SKILL.md
  - skills/agentic-sdks/SKILL.md
  - skills/communicating-agents/SKILL.md
  - skills/deployment/SKILL.md
  - skills/python-prj-mgmt/SKILL.md
---

## Context

Skills with drift-prone content (API signatures, model lineups, platform comparisons) silently become stale: the sentinel can check structure (`N*` dimension) but not freshness-by-section. The ROADMAP proposed a staleness-marker convention; CONTEXT_REVIEW §4.3 identified ~14 section-groups across 5 named skills that would benefit. Missing mechanics: (a) marker syntax and placement, (b) per-section sensitivity catalog, (c) threshold policy, (d) sentinel enforcement, (e) user-gated refresh workflow.

## Decision

Adopt the marker syntax `<!-- last-verified: YYYY-MM-DD -->` at h3 subsection granularity (with h2-level fallback when a section has no h3 children). Maintain the sensitivity catalog inline in each skill's frontmatter via a new `staleness_sensitive_sections:` key. Add three new sentinel checks (F07, F08, F09) in the Freshness dimension. Create a new paths-scoped rule at `rules/swe/staleness-policy.md`. Ship a `/refresh-skill <skill-name>` command that gates date bumps on user confirmation.

**Default threshold: 120 days** (overriding the ROADMAP's 90-day proposal per CONTEXT_REVIEW §4.3 rationale — external API docs rev on 2–6 month cadence; 90 days produces noise the user tunes out).

**Frontmatter schema**: use **exact section titles** (not slug anchors), matched case-sensitively against the rendered h2/h3 text. Rationale: anchor slugs collapse punctuation and case in ways that are hard to read; titles are what authors see and edit.

```yaml
---
name: claude-ecosystem
description: ...
staleness_threshold_days: 120      # optional; defaults to rule's global default
staleness_sensitive_sections:
  - Current Model Lineup
  - Model Selection Heuristics
  - Server-Side Tools
  - Client-Side Tools
  - Tool Infrastructure
  - Context Management
  - Files
  - SDK Quick Reference
  - SDK Selection Guidance
---
```

**Rule contents** (`rules/swe/staleness-policy.md`, paths-scoped via `paths: skills/**/SKILL.md`):

1. Marker syntax (`<!-- last-verified: YYYY-MM-DD -->`), placement under the heading
2. Extended form (optional `; source: <name>`) — advisory, sentinel ignores
3. Frontmatter schema (`staleness_sensitive_sections:`, `staleness_threshold_days:`)
4. Threshold defaults (120 days global, per-skill override)
5. Exclusion semantics (`last-verified: permanent` suppresses the never-verified WARN)
6. Missing-marker semantics (never-verified = WARN, not FAIL)
7. Refresh workflow (point at `/refresh-skill`)
8. Link to sentinel F07/F08/F09 check IDs

**Sentinel F-dimension additions** (land alongside existing F01–F06):

| ID | Type | Rule | Pass criteria |
|---|---|---|---|
| F07 | A | Sections listed in `staleness_sensitive_sections:` exist and have a marker | Each listed title has a matching heading; that heading has a `<!-- last-verified: ... -->` marker within 5 lines below |
| F08 | A | Marker dates are within threshold | `(today - last-verified) ≤ staleness_threshold_days` (skill override wins over rule default); values ≥ threshold = FAIL; values within 15-day lookahead of threshold = WARN |
| F09 | A | Marker dates are valid and not future-dated | ISO 8601 `YYYY-MM-DD` format; date ≤ today (and not `permanent` — that is the exclusion keyword, handled before F09) |

**Cold-start handling**: for sections listed in the catalog that do not yet have a marker, F07 issues a **WARN** ("never verified") rather than a FAIL. This avoids the first-pass flood. Once the section gains a marker, F08 takes over.

**`/refresh-skill <skill-name>` command** (`commands/refresh-skill.md`). Flow: parse frontmatter → for each section, locate marker, compute age, identify candidate source URLs → for each out-of-date section, fetch current content via `external-api-docs` (fallback WebFetch), diff against existing → prompt user per section (Accept / Revise / Skip / Mark permanent) → apply revisions, update marker → append audit-log entry to `.ai-state/staleness_refresh_log.md` (append-only). **Gate**: the command never bumps a date without user confirmation on the diff. A "silent bump" mode is not provided.

## Considered Options

### Option 1 — Per-file marker instead of per-section

Rejected; forces re-verification of stable content every rotation. Excessive churn.

### Option 2 — Central policy file `staleness-policy.yml` at repo root

Rejected; creates drift risk between skill content and external catalog. Frontmatter is co-located.

### Option 3 — Auto-bump on CI with "last-sentinel-checked" semantics

Rejected; silences the signal without re-verification. Dec-010's "zero-LLM" philosophy applies here too: bumping needs a human judgment pass.

### Option 4 — Per-section marker + frontmatter catalog + gated command (chosen)

Co-located, greppable, user-gated; extends sentinel Freshness dimension without restructuring.

## Consequences

**Positive**: gives the sentinel teeth against drift; bounds the refresh workload via per-skill catalog (no whole-ecosystem scans); gates mechanical date-bumps on human gesture.

**Negative**: one new always-loaded-when-scoped rule (~80 lines, ~3KB, loaded only on skill sessions — effectively zero); one new command; three sentinel checks (additive). Skills must populate `staleness_sensitive_sections:` — one-time annotation effort across the 5 named skills (CONTEXT_REVIEW §4.3 identifies ~14 section-groups).

**Risk accepted**: cold-start flood of "never verified" WARNs in the first sentinel run after landing; mitigated by F07's WARN-not-FAIL cold-start semantics.
