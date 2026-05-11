---
id: dec-136
title: Biome / ESLint coexistence in typescript-development — one context file, conditional guidance
status: accepted
category: architectural
date: 2026-05-11
summary: typescript-development/contexts/typescript.md documents both Biome (default for greenfield/library) and ESLint+Prettier (default for framework projects with required plugins) in one file with a clear decision rule.
tags: [skills, typescript, biome, eslint, code-quality, toolchain]
made_by: agent
agent_type: systems-architect
branch: worktree-multi-language-support
pipeline_tier: full
affected_files:
  - skills/typescript-development/contexts/typescript.md
  - skills/typescript-development/contexts/react.md
  - skills/typescript-development/contexts/vue.md
re_affirms: dec-139
---

## Context

Phase 1b research mapped the TypeScript code-quality toolchain landscape and found two viable paths:

1. **Biome v2** — single binary, Rust-based, ~10–25× faster than ESLint+Prettier, ~80% ESLint rule coverage; lacks framework-specific plugins (no `eslint-plugin-react-hooks` equivalent).
2. **ESLint v9 + `@typescript-eslint` v8 + Prettier** — mature, vast plugin ecosystem, framework support; slower; multiple config files.

Recommendation: Biome for greenfield Node/TS-only projects; ESLint+Prettier for framework projects (React, Vue, Next.js, Nuxt) where framework plugins are mandatory. The open question is **how to express both paths in Praxion**: one file with conditional guidance, two separate files (`contexts/biome.md` + `contexts/eslint.md`), or three files (baseline + biome + eslint).

## Decision

ONE file documents both paths: `typescript-development/contexts/typescript.md` contains a decision rule at the top and dedicated sections for each toolchain.

**Decision rule** (verbatim text the implementer copies into the file):

```
Greenfield project with no framework plugin dependencies?
   -> Biome v2 (default; faster; single tool)

Project uses React, Next.js, Vue, Nuxt, or any framework with required ESLint plugins
(e.g., eslint-plugin-react-hooks)?
   -> ESLint v9 + @typescript-eslint v8 + Prettier

Project mixes both (TS libraries + framework apps in one repo)?
   -> ESLint+Prettier (the union)
```

Framework contexts (`contexts/react.md`, `contexts/vue.md`) explicitly override the default to ESLint+Prettier — these contexts assume the baseline `contexts/typescript.md` is loaded, see the decision rule, and route to the ESLint branch.

The `contexts/typescript.md` file is structured with clear section headers:

```markdown
## Code quality toolchain

[decision rule]

### Path A — Biome v2 (greenfield default)

[Biome setup, biome.json, CI step, gotchas]

### Path B — ESLint v9 + @typescript-eslint v8 + Prettier (framework default)

[ESLint flat config, projectService, Prettier integration, CI step, gotchas]
```

## Considered Options

### Option 1 — Single file with conditional guidance (chosen)

**Pros**: One file to maintain; one activation surface; decision rule is local; framework contexts override the default in their own files; shared TS-baseline content (tsconfig, package manager, Vitest) isn't duplicated.

**Cons**: File is longer than a pure-Biome or pure-ESLint file would be; agents skim more text.

### Option 2 — Two separate files: `contexts/biome.md` and `contexts/eslint.md`

**Pros**: Each file is focused; agents loading only one toolchain see only that content.

**Cons**: Duplicates baseline TS content across two files OR forces a third baseline file; agent has to know which file to load before activating; the "I'm not sure which to use" agent has to load both to compare; doesn't match how the Phase 1b research naturally describes the decision (one decision rule, two outputs).

### Option 3 — Three files: baseline + biome + eslint

**Pros**: Maximally decomposed; baseline shared.

**Cons**: Three files to load when working on a project that needs both baseline and a toolchain; activation cost; the decision rule lives in baseline but the activations are in two separate files — the indirection is harder to navigate.

## Consequences

### Positive

- Single decision surface per project; one place where the Biome-vs-ESLint trade-off is documented
- Framework contexts cleanly override the default without restating Biome content
- Maintenance cost is lower than the multi-file alternatives
- Aligns with `agentic-sdks/contexts/openai-agents-typescript.md` precedent of one framework-language file housing the full TS guide
- Decision rule format (Q&A) is the standard Praxion content pattern (`test-coverage` Threshold Bands, `mcp-crafting` transport selection)

### Negative

- The file is longer than each path alone (~600–900 lines projected); managed by clear section headers and a TOC
- Agents loading the file for Biome-only work pay a small token cost for the ESLint content they don't use; mitigated by clear section structure that lets agents skim
- A future third toolchain (e.g., oxlint becoming primary) requires extending the decision rule rather than adding a sibling file; acceptable for now given oxlint's "no formatter" gap

### Neutral

- Establishes a precedent for "conditional toolchain inside one context file" — applicable to any future polyglot context where multiple tools serve overlapping purposes
