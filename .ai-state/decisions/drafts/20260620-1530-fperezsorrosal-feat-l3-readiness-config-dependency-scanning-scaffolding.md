---
id: dec-draft-bba71102
title: Add dependency-scanning scaffolding (dependabot) to the onboarding baseline
status: proposed
category: architectural
date: 2026-06-20
summary: New canonical dependabot.yml.tmpl in claude/project-baseline/ plus a /onboard-project Phase 8e.7 sub-step that installs an ecosystem-tailored .github/dependabot.yml.
tags: [dependency-scanning, dependabot, onboarding, scaffolding, readiness]
made_by: agent
agent_type: systems-architect
branch: feat-l3-readiness-config
pipeline_tier: full
affected_files:
  - claude/project-baseline/dependabot.yml.tmpl
  - commands/onboard-project.md
  - .github/dependabot.yml
dissent: Inline-authoring a dependabot.yml per project (no canonical asset) avoids adding template indirection to claude/project-baseline/ for a few lines per ecosystem; the asset-plus-sub-step machinery is arguably overhead for a low-churn config.
---

## Context

`c.security.dependency_scanning` is the one genuine *scaffolding* gap of the four L3 criteria. The detector (`_any_exists(_DEPENDENCY_SCANNING_FILES)`) is satisfied only by a literal `.github/dependabot.yml(.yaml)`, `renovate.json`, `.renovaterc(.json)`, or `.snyk` — a CI pip-audit/npm-audit step does NOT satisfy it. Praxion's onboarding (`/onboard-project` Phase 8e, `/new-project`) installs linter/formatter/typecheck/pre-commit/editorconfig/CONTRIBUTING baselines but has no dependency-scanning step in any command or `claude/` asset. So every managed project inherits the gap, and Praxion itself lacks the file.

## Decision

Add a canonical `claude/project-baseline/dependabot.yml.tmpl` (universal, ecosystem-spanning — alongside `editorconfig`, `pre-commit-config.yaml`, `CONTRIBUTING.md.tmpl`) and a new idempotent `/onboard-project` Phase 8e sub-step (8e.7) that reads the template, emits `updates:` blocks only for detected ecosystems (Python manifest → pip; `package.json` → npm; `.github/workflows/` present → github-actions), sets each `directory:` from the discovered manifest location, and writes `.github/dependabot.yml` — skipping when any dependency-scanning file already exists. `/new-project` needs no edit: it hands Phase 8e entirely to `/onboard-project` and inherits 8e.7. `sync_canonical_blocks.py` is not involved — the template is an installed, per-project-tailored asset, not a verbatim embedded block (same status as `pre-commit-config.yaml` and `editorconfig`, neither of which is in the sync registry).

## Considered Options

### Option 1 — Canonical asset in `claude/project-baseline/` + Phase 8e.7 (chosen)
- Pros: single source of truth; idempotent; consistent with the existing 8e pattern (mirrors 8e.4's language-block stripping); ecosystem-spanning asset in the right home.
- Cons: one more 8e sub-step.

### Option 2 — Inline-author a dependabot.yml per project in Phase 8e (no asset)
- Pros: no new asset file.
- Cons: no single source of truth; the YAML is re-derived each onboarding; drift across projects.

### Option 3 — Put the asset in a language skill's `assets/`
- Pros: co-located with other language assets.
- Cons: dependabot spans pip+npm+actions; no single language skill owns it — a category error.

## Consequences

- Positive: managed projects pass `c.security.dependency_scanning`; Praxion's own `.github/dependabot.yml` covers its four ecosystems (root/`task-chronograph-mcp`/`eval` pip, `dashboard_app` npm, github-actions); the `coding-style.md` baseline-set is extended consistently.
- Negative: a `directory:` mismatch would raise no updates (low impact; mitigated by per-ecosystem detection); the Gate 8e headline and action-range text must be updated from "8e.1–8e.6" to "8e.1–8e.7".

## Disconfirmation

- **Falsifier:** if a managed project already standardizes on Renovate or Snyk, installing a dependabot.yml would be redundant — the skip-predicate (any dependency-scanning file present) prevents this, so the decision holds.
- **Steelmanned runner-up:** Option 2 (inline, no asset) avoids adding a file to `claude/project-baseline/`; for a one-line-per-ecosystem config the indirection of a template could be seen as overhead. It loses because dependabot config grows (schedules, grouping, ignore rules) and a single editable asset is the established pattern for every other baseline.
- **Reversal trigger:** revisit if Praxion adopts a different dependency-scanner default (Renovate), or if Dependabot's schema changes enough that per-ecosystem tailoring no longer maps cleanly to the template.
