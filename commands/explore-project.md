---
description: Explore and understand an unfamiliar project's architecture, patterns, and workflow
argument-hint: [guide|<focus-area>]
allowed-tools: [Read, Glob, Grep, Bash(git:*), Bash(wc:*), Bash(find:*)]
---

Explore an unfamiliar software project using the [project-exploration](../skills/project-exploration/SKILL.md) skill. Produces a layered understanding from executive summary to deep architectural analysis, adapted to the project's size, type, and documentation quality.

## Modes

Three exploration modes based on `$ARGUMENTS`:

| Argument | Mode | Behavior |
|----------|------|----------|
| _(none)_ | **Default** | Run Phases 1-3, produce executive summary with Mermaid architecture diagram |
| `guide` | **Guided** | Interactive step-by-step walkthrough -- present one phase at a time, developer controls depth |
| `<anything else>` | **Focused** | Run Phase 1 for context, then deep-dive Phase 4 on the specified area |

## Process

### 1. Parse Arguments and Verify

Determine the exploration mode from `$ARGUMENTS`:

- If empty or absent: **Default mode**
- If `$ARGUMENTS` equals `guide`: **Guided mode**
- Otherwise: **Focused mode** with `$ARGUMENTS` as the focus area

Verify this is a git repository:

```bash
git rev-parse --git-dir > /dev/null 2>&1
```

If not a git repo, note that git-based analysis (history, contributors, commit conventions) will be unavailable but proceed with filesystem analysis.

### 2. Load Skill and Characterize Project

Load the `project-exploration` skill methodology.

Run the **Project Characterization** sequence from the skill:

1. **Detect ecosystem**: Scan config files to identify language(s), framework(s), build system
2. **Classify size**: Count files (excluding .git, node_modules, .venv, vendor, target, dist, build) and classify as small/medium/large/monorepo
3. **Detect project type**: Match against type signals (web app, CLI, library, pipeline, etc.)
4. **Assess documentation quality**: Check README length, docs/ presence, CONTRIBUTING.md, comment density signals

Report the classification briefly before proceeding:

> **Detected**: {language} {framework} project | {size tier} ({file_count} files) | {project_type} | Docs: {quality}

### 3. Branch by Mode

#### Default Mode (Executive Summary)

Run Phases 1-3 from the skill methodology:

1. **Phase 1: First Impressions** -- Project identity, purpose, tech stack, size metrics, license
2. **Phase 2: Architecture Discovery** -- Module map, entry points, dependency direction, architecture pattern. **Produce a Mermaid architecture diagram** using the templates from `references/architecture-patterns.md`. Fill in actual module names. Verify arrows against real imports.
3. **Phase 3: Development Workflow** -- Build/test/lint commands, CI summary, git conventions

Present findings using the **Executive Summary Template** from the skill:

```
## Project: {name}

**Purpose**: {one-sentence description}
**Type**: {project type} ({domain})
**Size**: ~{LOC} LOC | {files} files | {modules} modules
**Stack**: {languages} | {frameworks} | {key deps}
**Architecture**: {pattern} -- {explanation}

{Mermaid architecture diagram}

**Build**: `{command}` ({tool})
**Test**: `{command}` ({framework}) | Tests in `{location}`
**Lint**: `{command}` ({linter})
**Entry points**:
- `{path}` -- {description}

**Key patterns**: {notable conventions}
**Documentation**: {quality} -- {assessment}
**Gotchas**: {non-obvious things to know}
```

End with: "Want me to explore any specific area deeper? Try `/explore-project guide` for an interactive walkthrough, or `/explore-project <area>` to dive into a specific module."

#### Guided Mode

Follow the **Guided Exploration Protocol** from the skill:

1. Run Phase 1 and present a condensed overview (~10 lines)
2. Ask: "Which area would you like to explore next?"
   - **Architecture** (Phase 2) -- module map, dependencies, Mermaid diagram
   - **Development workflow** (Phase 3) -- build, test, CI, conventions
   - **A specific area** (Phase 4) -- name any module, concept, or concern
3. Present one phase at a time. Within Phase 2, break into sub-steps (module map first, then dependencies, then Mermaid diagram)
4. After each phase: "What would you like to explore next? Or ask any question about what we've covered."
5. Introduce fewer than 7 new concepts per response before pausing

The developer controls pace and depth throughout.

#### Focused Mode

1. Run Phase 1 briefly (5-line context summary) to establish project identity
2. Run Phase 4 deep dive on the area specified in `$ARGUMENTS`
3. Use the relevant deep dive checklist from `references/analysis-checklists.md`
4. If the focus area is ambiguous (e.g., "data"), ask: "I found several areas related to 'data' -- which would you like to explore?" and list candidates

End with: "Want me to explore related areas or a different part of the project?"

### 4. Adapt Analysis

Apply the **Adaptation Rules** from the skill throughout all modes:

- **By size**: Small projects get full-scan single-pass. Large projects use sampling. Monorepos get territory mapping first.
- **By type**: Reorder Phase 2 emphasis based on project type (web app leads with routing; CLI leads with command dispatch; library leads with public API).
- **By documentation quality**: Rich docs get cross-referenced and summarized. Sparse/absent docs trigger heavier code-first analysis. **Misleading docs get flagged** -- source code is always the truth. For every discrepancy found, state clearly: "README says X, but code shows Y -- trust the code."
