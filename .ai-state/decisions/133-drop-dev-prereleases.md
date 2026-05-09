---
id: dec-133
title: "Drop PEP 440 dev pre-releases for simpler SemVer-only flow"
status: accepted
category: behavioral
date: "2026-05-08"
summary: "Remove .devN pre-release scheme; align all version files to last released stable; simplify versioning skill and release workflow"
tags: [versioning, simplification, commitizen, release-flow]
made_by: user
branch: main
pipeline_tier: direct
affected_files:
  - "pyproject.toml"
  - "memory-mcp/pyproject.toml"
  - "task-chronograph-mcp/pyproject.toml"
  - "eval/pyproject.toml"
  - ".claude-plugin/plugin.json"
  - ".github/workflows/release.yml"
  - "commands/release.md"
  - "skills/versioning/SKILL.md"
  - "skills/versioning/references/commitizen.md"
  - "README_DEV.md"
---

## Context

The project adopted PEP 440 dev pre-releases (`X.Y.Z.devN`) as a "between tags" working version on `main`. After each stable release, an automation step bumped every version file to the next patch dev version (e.g., `0.2.0` → `0.2.1.dev0`), with one carve-out: the marketplace-facing `.claude-plugin/plugin.json` was reset to the stable version because Claude Code uses its `version` field as a plugin-cache key, and a constant `.devN` string across many commits would pin every cached install to whichever snapshot landed first.

This produced two ongoing costs:

1. **Permanent file divergence.** Between releases, `.claude-plugin/plugin.json` showed the last stable while every other version file showed `X.Y.Z.devN`. Anyone reading any one file in isolation got a misleading answer.
2. **A shipped policy that explained the divergence.** The `versioning` skill — which installs into every consumer project that activates the plugin — included a 30-line "Plugin Marketplace Publishing" section plus a "Cache-staleness recovery" subsection with manual `rm -rf ~/.claude/plugins/cache/...` instructions. This is a workaround for a problem that only exists *because* dev versions are in use.

The dev-cycle pattern primarily solves a multi-committer coordination question — *"is `main` ahead of the last tag?"* — by encoding the answer in the version string. The repository has a single committer; the answer is known by definition. The `.devN` marker is ceremony with no offsetting benefit at the current scale.

## Decision

Remove PEP 440 dev pre-releases from the release flow:

- Version files reflect the last released stable version between releases. No `.devN` working state.
- `cz bump` is the only mechanism that changes version strings. Its run produces a new version + tag in one atomic operation across every `version_files` target including `.claude-plugin/plugin.json`.
- The release GitHub Actions workflow drops the post-release "open next dev cycle" step and the marketplace-version reset that compensated for it.
- The `/release` command drops the `dev` argument and intent mapping.
- The `versioning` skill (shipped to consumer projects) drops the `dev` flag-mapping row, the entire "Plugin Marketplace Publishing" section, and its "Cache-staleness recovery" companion. The companion `commitizen.md` reference drops the "PEP 440 Pre-Release Workflow" section and the `--prerelease` flag row.
- `README_DEV.md` "Releases" section is rewritten without dev-cycle examples.

`major_version_zero = true` stays — orthogonal to dev pre-releases. Pre-1.0 SemVer behavior (`feat!:` produces MINOR not MAJOR) is unaffected.

## Considered Options

### Option 1: Keep PEP 440 dev pre-releases (status quo)

- (+) Distinct version string for "between tags" working state, useful when multiple committers need to know "is main ahead of last tag?"
- (+) Optionality for future alpha/beta/rc preview releases without changing tooling
- (−) Permanent file divergence between `plugin.json` (stable) and other files (`.devN`)
- (−) Shipped skill carries 60+ lines of marketplace-cache-key workaround policy
- (−) Two-step release: stable bump + open-next-cycle bump, with a marketplace reset in between
- (−) No demonstrated benefit at single-committer scale

### Option 2: Drop dev pre-releases (selected)

- (+) Single source of truth: every version file shows the same string, always equal to the last released stable
- (+) `cz bump` is one atomic operation; no compensating step needed
- (+) Marketplace cache-key issue dissolves — no `.devN` ever in `plugin.json`
- (+) Shipped skill simplifies; consumer projects inherit a smaller, sharper conventions doc
- (−) No native pre-release mechanism for future alpha/beta/rc cycles. Re-introducing one would require reversing this ADR.
- (−) Existing CHANGELOG entries reference `.devN` versions — these stay as factual history; they read coherently because the policy was in force at the time

### Option 3: Keep `.devN` in internal files but stop syncing to marketplace

- (+) Preserves the "is main ahead of last tag?" signal in pyproject.toml
- (−) Requires the same compensating workflow step — divergence isn't solved, just relocated
- (−) Doesn't simplify the shipped skill

## Consequences

### Positive

- Permanent file divergence is gone. All version-file targets equal the last released stable between releases.
- `versioning` skill loses ~60 lines of marketplace-publishing policy and a recovery subsection. Consumer projects loading the skill get a cleaner mental model.
- Release workflow halves: bump-and-tag is the entire flow; no "open next cycle" step to maintain.
- Decision is reversible. If the project ever grows multi-committer or wants alpha/beta/rc preview releases, this ADR can be superseded by re-introducing PEP 440 pre-release support.

### Negative

- Loss of `.devN` / alpha / beta / rc capability until explicitly re-introduced. For pre-1.0 solo development, no loss is felt.
- Existing `bump:` commits in git history reference dev-cycle ceremony that no longer happens. They remain accurate as historical record.

### Relationship to Prior Decisions

ADR-006 (commitizen-over-release-please) stays accepted. Its tool choice — Commitizen for local-first CLI + `pyproject.toml` integration via `version_files` — is unaffected. One of ADR-006's three justifications ("native PEP 440 dev release support") becomes non-load-bearing under this decision. The other two justifications (local-first CLI operation; direct `pyproject.toml` integration) continue to hold and remain sufficient grounds for the Commitizen choice.
