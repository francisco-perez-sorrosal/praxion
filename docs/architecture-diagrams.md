---
diataxis: reference
audience: developer
---

# Architecture Diagrams

Praxion uses a **LikeC4 → D2 → SVG** toolchain for C4-style architectural diagrams. A
single `.c4` source file defines the architectural model; `likec4 gen d2` projects each
declared view into a `.d2` file; `d2` renders each `.d2` into a committed `.svg` that
documents embed directly. Source, generated D2, and rendered SVG are all committed together.

## Overview

- **Source**: `docs/diagrams/<name>.c4` — the single source of truth for a diagram set.
- **Generated**: `docs/diagrams/<name>/<view>.d2` — produced by `likec4 gen d2`.
- **Rendered**: `docs/diagrams/<name>/<view>.svg` — produced by `d2`; embedded in docs via `<img>`.

Architecture documents (`docs/architecture.md`, `.ai-state/DESIGN.md`) reference the
rendered SVG and quote the source DSL in a fenced `c4` block so reviewers see both in one
place. Non-C4 diagrams (sequence, state, ER, flowchart) stay in Mermaid — see
`rules/writing/diagram-conventions.md` for the coexistence policy.

## Install

Both binaries must be available for the pre-commit hook to regenerate diagrams. If either is
missing, the hook skips regeneration with a warning (commits still proceed). Install both
before editing `.c4` source files.

### LikeC4

```bash
npm install -g likec4   # installs the likec4 CLI globally
```

Version constraint: `^1.56` (verified against npm registry 2026-04-30).

To pin to the exact resolved version:

```bash
npm install -g likec4@1.56.0
```

Verify:

```bash
likec4 --version
```

### D2

macOS (Homebrew):

```bash
brew install d2
```

Linux / macOS (curl installer, pinned version):

```bash
curl -fsSL https://d2lang.com/install.sh | sh -s -- v0.7.1
```

Verify:

```bash
d2 --version
```

Version pin: `0.7.1` (last stable release as of 2026-04-30; treat as stable, version-pinned
per risk mitigation R2 in `SYSTEMS_PLAN.md`).

## Hook Behavior

A pre-commit hook (`scripts/diagram-regen-hook.sh`, called by
`scripts/git-pre-commit-hook.sh`) regenerates derived artifacts whenever `**/diagrams/*.c4`
files are staged for commit.

**Happy path** (both binaries installed, valid DSL):

1. Detects staged `.c4` files.
2. Runs `likec4 gen d2 <name>.c4 -o <name>/` to generate one `.d2` per declared view.
3. Runs `d2 <name>/<view>.d2 <name>/<view>.svg` for each generated `.d2`.
4. Stages all produced files with `git add`.
5. Commit proceeds with fresh artifacts.

**Error path** (DSL syntax error or render failure):

The hook prints the failing command and its stderr, then exits non-zero, aborting the commit.
Fix the DSL error and try again. To bypass for a known-broken state, use
`git commit --no-verify` (the CI gate will catch drift on the PR).

## Graceful-Degradation Path

When `likec4` or `d2` is not installed:

- The hook emits a warning to stderr and exits 0.
- The commit proceeds without regenerated artifacts.
- The committed `.c4` source is the SSOT; the stale `.svg` is still readable.
- The CI gate (TBD — see risk R7 in `SYSTEMS_PLAN.md`) regenerates and rejects PRs whose
  committed SVGs disagree with their source.

Workflow for contributors without local binaries:

1. Edit the `.c4` source and commit.
2. The hook warns that regeneration was skipped.
3. Open a PR; CI regenerates and fails if the committed SVG is stale.
4. Install binaries, regenerate locally, and push a fixup commit.

## AI Tooling

### LikeC4 Agent Skill (one-time, system-scope)

When authoring `.c4` files, register the LikeC4 DSL Agent Skill for in-editor guidance:

    npx skills add https://likec4.dev/

Claude Code, Cursor, and Windsurf auto-load this skill when editing `.c4` files.

### Full LikeC4 reference (headless / non-IDE contexts)

For full LikeC4 DSL/API reference outside the auto-loaded Agent Skill context
(e.g., headless agents, future MCP consumers, agents on systems without the
Vercel skills protocol registered), fetch `https://likec4.dev/llms-full.txt`
directly with a fetch-date annotation (per the `external-api-docs` skill's
freshness discipline). No chub upstream entry currently exists for LikeC4 —
the chub MCP has no ingestion tool for new entries; if one is added later,
this section can be updated to point at it.

The thin `https://likec4.dev/llms.txt` navigation index is intentionally not
vendored; its function is fully subsumed by either the Agent Skill or
`llms-full.txt`.
