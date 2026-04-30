---
id: dec-draft-9e43c4f6
title: Commit both diagram source DSL and rendered SVG; regenerate via repo hook
status: proposed
category: configuration
date: 2026-04-30
summary: 'For C4-architectural diagrams, commit the LikeC4 source `.c4`, the generated `.d2`, and the rendered `.svg` together; a pre-commit hook regenerates derived artifacts when source changes; CI validates freshness as a backstop.'
tags: [diagrams, c4, likec4, d2, hooks, ci, storage]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - hooks/
  - .github/workflows/
  - skills/doc-management/references/diagram-conventions.md
  - rules/writing/diagram-conventions.md
  - commands/onboard-project.md
---

## Context

The user's confirmed scope explicitly requires both the source DSL/D2 *and* the rendered SVG/PNG to be committed, and asks for a hook-based regeneration mechanism. Three storage shapes were nonetheless on the table; the architect must record which is canonical, where artifacts live, and what the hook does on failure.

The decision is downstream of the toolchain choice (`dec-draft-55bf38a6`); it re-affirms that decision in passing because the storage strategy presupposes LikeC4 source + D2 generated + D2-rendered SVG.

## Decision

For every C4-architectural diagram in a Praxion-managed project:

1. **Source DSL** lives at `<doc-dir>/diagrams/<name>.c4`. Single source per architectural model; multiple `view` declarations within.
2. **Generated D2** lives at `<doc-dir>/diagrams/<name>/<view>.d2`. Produced by `likec4 gen d2`.
3. **Rendered SVG** lives at `<doc-dir>/diagrams/<name>/<view>.svg`. Produced by `d2 <view>.d2 <view>.svg`.

All three are committed to git. The architecture document (`docs/architecture.md` or `.ai-state/ARCHITECTURE.md`) embeds the SVG with `<img>` and quotes the DSL source in a fenced ` ```c4 ` block immediately above or below the image so reviewers see both side-by-side.

A repo-local pre-commit hook detects staged changes to `**/diagrams/*.c4` and re-runs `likec4 gen d2` plus `d2 ... .svg` for the affected models, re-stages the regenerated derived files, and aborts the commit on render error. When `likec4` or `d2` is not present on the contributor's machine, the hook emits a warning and exits 0 (graceful skip); a CI workflow runs the same regeneration with strict failure as a backstop.

## Considered Options

### Option 1 — Commit only DSL source, render in CI for previews

**Pros:** Cleanest git history (no SVG diffs); simplest source-of-truth model. Minimal repo size growth.

**Cons:** GitHub readers see only the `.c4` source on the file page (no inline render). Architecture documents become unreadable on GitHub without a CI artifact link. Reviewers cannot see the rendered diagram in a PR diff without round-tripping through CI artifacts. Fails the user's stated scope (both committed).

### Option 2 — Commit only rendered SVG, treat DSL as transient build input

**Pros:** Smallest viewer experience friction; the doc renders inline on GitHub; no DSL clutter.

**Cons:** Rendered SVG is the lossy artifact; source-of-truth is gone. Editing the diagram requires a local checkout that recreates the DSL from scratch (or from memory). Single-model multi-view modeling is lost — the SSOT motivator collapses. Fails the user's scope.

### Option 3 — Commit both source and rendered (chosen)

**Pros:** Reviewers see both source and render in the PR diff. GitHub readers get the inline rendered SVG. The DSL is the single source of truth; the SVG is a generated mirror. Drift is detectable: if SVG mtime is older than `.c4` mtime, regeneration was missed. Aligns with the user's confirmed scope.

**Cons:** Each diagram edit produces a multi-line diff (DSL change + regenerated `.d2` + regenerated `.svg`). SVG blobs are large compared to text DSL. Requires hook + CI gate to keep SVG fresh.

## Consequences

**Positive:**

- GitHub-native viewers get inline rendered SVG with zero CI dependency for reading.
- PR reviewers see both source and rendered output in the diff.
- Drift is mechanically detectable (mtime comparison; CI regenerate-and-diff).
- DSL remains the editing surface; SVG is generated.

**Negative:**

- Larger commits when a diagram changes — the DSL change pulls along the regenerated `.d2` and `.svg`.
- Repo size grows with diagram complexity. Mitigated by the small overall diagram count (≤ 10 per Praxion-style project) and SVG's text-format compactness vs PNG.
- Hook adds ~100-150ms per modified diagram to commit time. Acceptable.

**Operational:**

- Hook lives in the canonical hooks location and is wired by the install/onboarding pipeline.
- CI workflow runs `likec4 gen d2 && d2 ... .svg` on every PR and rejects when committed SVGs differ from regenerated output (byte-for-byte after pin lock).
- Pin LikeC4 and D2 versions in onboarding install docs and CI to keep regenerated output stable across machines.
- The committed SVG is the canonical reader artifact — even if a contributor lacks `likec4`/`d2` locally, they can still read and merge.

## Prior Decision

This ADR re-affirms `dec-draft-55bf38a6` (toolchain choice) by presupposing it: storage paths and the hook command line both name LikeC4 and D2 specifically. Re-evaluating storage strategy without re-evaluating toolchain is not a reasonable cleavage; if the toolchain ADR is later superseded, this ADR's commands change but the *commit-both* policy carries over to whatever toolchain replaces LikeC4 + D2.
