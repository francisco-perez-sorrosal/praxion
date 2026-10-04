---
diataxis: reference
audience: developer
---

# Architecture Diagrams

Praxion draws its C4 architecture diagrams from a LikeC4 model. One command,
`scripts/regenerate_diagrams.py`, reads the model and writes one committed `.svg` (and its
intermediate `.d2`) per view, in a fixed visual vocabulary: a title naming the view and its C4
type, a legend, one drawing per element category. Source and renders are committed together, and
documents embed the `.svg`.

## Overview

- **Source**: `docs/diagrams/architecture/src/*.c4` — the model (`architecture.c4`) and the style kit (`_spec.c4`).
- **Rendered**: `docs/diagrams/architecture/rendered/<view-id>.svg` plus `<view-id>.d2`, one pair per view.
- **Catalog**: [`diagrams/README.md`](diagrams/README.md) lists every view with its title, C4 type and the documents that embed it.

Embed the render with a Markdown image, `![<view title> — <C4 type>: <gloss>](path/to/<view-id>.svg)`;
the alt text names the view's title and its C4 type. Never quote the DSL or paste diagram code
into a document. Non-C4 diagrams (sequence, state, ER, flowchart) stay in Mermaid — see
[`rules/writing/diagram-conventions.md`](../rules/writing/diagram-conventions.md) for the
coexistence policy. The pipeline in full (command flags, exit codes, determinism) is stated once in
[`skills/likec4-diagramming/references/render-and-regen.md`](../skills/likec4-diagramming/references/render-and-regen.md).

## Install

Both binaries must be installed, at the pinned versions, for the command to run. Install both
before editing `.c4` source files.

### LikeC4

Install the exact pin:

```bash
npm install -g likec4@1.59.4
```

Verify:

```bash
likec4 --version
```

### D2

Use the standalone build; the command scrubs the version stamp the standalone build writes, and
a package-manager build stamps it differently.

```bash
curl -fsSL https://d2lang.com/install.sh | sh -s -- --version v0.7.1 --method standalone
```

Verify:

```bash
d2 --version
```

## Regenerate

From the repository root:

```bash
python3 scripts/regenerate_diagrams.py
```

This renders every view in place and deletes any `.svg` or `.d2` in `rendered/` that no view
produces. Then confirm the committed renders match the model:

```bash
git status --porcelain -- docs/diagrams/
```

An empty listing means nothing drifted. For the full verdict, including the review checks
(legibility, proportion, contrast, and that every embed and the catalog describe the view), run:

```bash
python3 scripts/regenerate_diagrams.py --check
```

`--check` writes nothing in the checkout. It exits 0 only when no render drifted and no check
failed; exit 3 means `likec4` or `d2` is missing or off its pinned version.

## Add or change a view

1. Edit `docs/diagrams/architecture/src/architecture.c4`. Give each view one `#c4_*` type tag and a `title`.
2. Run `python3 scripts/regenerate_diagrams.py`.
3. Embed the new `.svg` with an alt text carrying the title and the C4 type, and add a row to the catalog in [`diagrams/README.md`](diagrams/README.md).
4. Run `python3 scripts/regenerate_diagrams.py --check` and fix every `FAIL` it prints.

## Where it runs

- **Pre-commit hook `diagram-regen`** (`scripts/diagram-regen-hook.sh`). When a `.c4` file is
  staged it runs the command with `--staged`, then stages `rendered/`. A regeneration failure
  aborts the commit and prints what happened, why and the exact fix. With `likec4` or `d2` absent or
  off its pin, the hook warns, writes nothing and lets the commit proceed.
- **CI job `regenerate-and-diff`** (`.github/workflows/architecture.yml`). Installs the two pins,
  runs the command and fails when `git status --porcelain -- docs/diagrams/` is non-empty. This
  catches renders committed from a skipped hook.
- **Managed projects** get a project-local copy of the command from onboarding
  (`scripts/install_diagram_kit.py`: a style kit, an example model and the workflow).

Contributors without the tools can commit the `.c4` edit; the hook warns, and CI rejects the pull
request until the renders are regenerated. Install the pins, regenerate and push a fixup commit.

## AI Tooling

### LikeC4 Agent Skill (one-time, system-scope)

When authoring `.c4` files, register the LikeC4 DSL Agent Skill for in-editor guidance:

    npx skills add https://likec4.dev/

Claude Code, Cursor, and Windsurf auto-load this skill when editing `.c4` files.

### Full LikeC4 reference (headless / non-IDE contexts)

For full LikeC4 DSL/API reference outside the auto-loaded Agent Skill context
(e.g., headless agents, future MCP consumers, agents on systems without the
Vercel skills protocol registered), fetch `https://likec4.dev/llms-full.txt`
directly with a fetch-date annotation (per the [current-docs protocol](../skills/software-planning/references/cross-agent-skill-conventions.md#current-docs-for-external-apis)'s
freshness discipline).

The thin `https://likec4.dev/llms.txt` navigation index is intentionally not
vendored; its function is fully subsumed by either the Agent Skill or
`llms-full.txt`.
