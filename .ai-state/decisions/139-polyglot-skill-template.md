---
id: dec-139
title: Polyglot skill template — references/ vs contexts/ separation with extension protocol
status: accepted
category: architectural
date: 2026-05-11
summary: Formalize the polyglot skill pattern — language-agnostic SKILL.md body + references/ for cross-language concepts + contexts/ for runnable language-specific mechanics, with a documented extension protocol.
tags: [skills, polyglot, multi-language, contexts, references, extension-pattern]
made_by: agent
agent_type: systems-architect
branch: worktree-multi-language-support
pipeline_tier: full
affected_files:
  - skills/agentic-sdks/SKILL.md
  - skills/mcp-crafting/SKILL.md
  - skills/test-coverage/SKILL.md
  - skills/node-prj-mgmt/SKILL.md
  - skills/typescript-development/SKILL.md
  - skills/architectural-fitness-functions/SKILL.md
---

## Context

Praxion is transitioning from Python-only to a polyglot meta-framework supporting Node.js / TypeScript / React 19 / Vue 3 (Phase 1 multi-language-support effort). Three existing skills (`agentic-sdks`, `mcp-crafting`, `test-coverage`) already implement a *de facto* polyglot pattern: language-agnostic SKILL.md body + `references/` and/or `contexts/` for per-language depth. The pattern is not formalized — `mcp-crafting/references/python-resources.md` lives in `references/` despite being Python-specific runnable content, inconsistent with `agentic-sdks` which keeps language code under `contexts/`. Without a formal specification, every future polyglot skill author re-invents the pattern (or worse, freezes the inconsistency).

This ADR formalizes the pattern so (a) the immediate Phase 1 pipeline can spawn `node-prj-mgmt` and `typescript-development` without ad-hoc decisions, (b) the `architectural-fitness-functions` body restructure has a clear target shape, and (c) future polyglot skills follow one canonical template.

## Decision

The polyglot skill template is defined by five rules, jointly enforced:

1. **Two satellite directories** — `references/` for language-agnostic conceptual depth (protocol specs, framework theory, comparison tables, methodology). `contexts/` for runnable language-specific mechanics (package commands, code examples, tool-specific patterns, version flags).

2. **File-naming convention:**
    - `contexts/<language>.md` for one-language-per-context (e.g., `contexts/python.md`, `contexts/typescript.md`)
    - `contexts/<framework>-<language>.md` when the skill is *about* a framework with per-language variants (e.g., `contexts/openai-agents-python.md`, `contexts/a2a-typescript.md`)
    - `contexts/<framework>.md` when the parent skill is language-rooted and frameworks sit *above* the language context (e.g., `typescript-development/contexts/react.md`)
    - `references/<language>-<concept>.md` is an acceptable hybrid for genuinely-language-scoped conceptual depth (`testing-strategy/references/typescript-testing.md`)

3. **SKILL.md body discipline:**
    - Language-agnostic prose; no language-specific code blocks in the body except (a) one-line pseudocode showing *shape*, (b) "Python: X / TypeScript: Y" inline pairs for direct comparison
    - Redirects ("See language context for X") at every point implementation diverges
    - Mandatory "Language Contexts" table with columns `Language | Context File | Tooling (project-owned)`
    - Frontmatter `description` ends with "Language modules available for `<list>`."
    - No version pins in the body — versions live in contexts

4. **Canonical example**: `test-coverage/SKILL.md` is the template. Reproduce its Language Contexts table format verbatim in any new polyglot skill.

5. **Extension protocol** to add a new language to an existing polyglot skill:
    - Create the appropriate `contexts/<language>.md` file
    - Add a row to the Language Contexts table
    - Update the frontmatter `description` to include the new language
    - Add language-specific gotchas if any (otherwise leave Gotchas untouched)
    - Body is NOT modified

The decision rule when authoring new content:

```
Does the content compile/run/install?       -> contexts/
Does the content explain a cross-language concept?  -> references/
Is the content a multi-language comparison? -> SKILL.md body or references/
```

A reference may use one language for illustrative examples but its *claims* must be language-agnostic. If claims fundamentally apply only to one language, the file is a context regardless of current directory.

## Considered Options

### Option 1 — Single `references/` directory with language tags inside files

**Pros**: One directory; fewer paths to learn.

**Cons**: Mixes runnable mechanics with conceptual depth; agents need to scan whole-file content to find language-specific sections; no clean activation surface for "load the Python parts of this skill"; inconsistent with three working precedents.

### Option 2 — Separate `references/` and `contexts/` directories (chosen)

**Pros**: Clear semantic separation; activation is local (load `contexts/typescript.md` without loading `contexts/python.md`); aligns with three working Praxion precedents; extension is purely additive.

**Cons**: Authors must learn the references-vs-contexts distinction; one housekeeping migration needed (`mcp-crafting/references/python-resources.md` → `contexts/python.md`).

### Option 3 — Per-language sibling skills (`mcp-crafting-typescript`, `mcp-crafting-python`)

**Pros**: Each skill is single-language; description activation is unambiguous.

**Cons**: Massive skill catalog inflation; cross-language comparison tables become awkward (no natural home); body content (protocol specs, common abstractions) duplicates across siblings; cross-skill cross-references multiply combinatorially.

## Consequences

### Positive

- All three working Praxion precedents (`agentic-sdks`, `mcp-crafting`, `test-coverage`) align retroactively under one specification
- Phase 1 multi-language-support pipeline has a stable target shape for `node-prj-mgmt`, `typescript-development`, and the `architectural-fitness-functions` restructure
- Future polyglot skill authors have one canonical template (`test-coverage`) to copy
- Extension to a new language is mechanical: add file, add row, update description — no body restructure ever
- No always-loaded token cost: all polyglot artifacts load on demand

### Negative

- One-time migration of `mcp-crafting/references/python-resources.md` to `contexts/python.md` (housekeeping, low risk)
- SKILL.md body discipline is enforced by documentation rather than mechanically — a sloppy author can still inline language-specific code; mitigated by sentinel/skill-genesis review
- Authors must internalize the references-vs-contexts decision rule; mitigated by the rule being short and binary

### Neutral

- Adds one sentence per polyglot skill's frontmatter description ("Language modules available for X and Y."); skill index growth is bounded (~50 chars × ~10 skills = ~140 tokens)
