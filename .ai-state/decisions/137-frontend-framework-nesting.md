---
id: dec-137
title: Frontend framework contexts nest inside typescript-development, not as sibling skills
status: accepted
category: architectural
date: 2026-05-11
summary: React 19 and Vue 3 contexts live under typescript-development/contexts/, layered above the baseline typescript.md context, rather than as sibling skills (react-development, vue-development).
tags: [skills, polyglot, typescript, react, vue, framework-nesting]
made_by: agent
agent_type: systems-architect
branch: worktree-multi-language-support
pipeline_tier: full
affected_files:
  - skills/typescript-development/SKILL.md
  - skills/typescript-development/contexts/typescript.md
  - skills/typescript-development/contexts/react.md
  - skills/typescript-development/contexts/vue.md
re_affirms: dec-139
---

## Context

The Phase 1b research lock decided that Praxion will support Node.js + TypeScript + React 19 + Vue 3 as first-class. The Polyglot Skill Template ADR (`dec-139`) formalizes the general polyglot pattern, but no existing Praxion precedent covers **frontend framework nesting** — stacking framework-specific contexts (React, Vue) above a language-baseline context (TypeScript).

The two structural options are: (a) frameworks as sibling skills (`skills/react-development/`, `skills/vue-development/`), or (b) frameworks nested as contexts inside a language-rooted skill (`typescript-development/contexts/react.md`). The decision matters because every future frontend framework (Svelte, Solid, etc.) inherits this pattern.

## Decision

Frontend framework contexts for the JS/TS ecosystem live under the language-rooted skill `typescript-development/contexts/`:

```
skills/typescript-development/
  SKILL.md
  contexts/
    typescript.md       # Node.js + TS language baseline
    react.md            # React 19 + Vite + Next.js 15 + ecosystem
    vue.md              # Vue 3 Composition API + Nuxt 3 + ecosystem
```

`contexts/typescript.md` is the **base**: tsconfig strictness, package manager, Vitest baseline, type checking. `contexts/react.md` and `contexts/vue.md` are **layers** that:

- Assume the baseline from `contexts/typescript.md` (do not restate)
- Add framework-specific conventions (Server Components, App Router, hooks-only rules in React; Composition API, vue-tsc, `@vue/test-utils` in Vue)
- Redirect for any re-statement: "for baseline tsconfig and package manager, see contexts/typescript.md"

Activation mechanics: the SKILL.md body's decision tree routes the session.

- `.ts` / `.mts` / `.cts` files (no framework signal) → `contexts/typescript.md` only
- `.tsx` files OR `react` / `next` / `vite` in `package.json` deps → `contexts/typescript.md` + `contexts/react.md`
- `.vue` files OR `vue` / `nuxt` in deps → `contexts/typescript.md` + `contexts/vue.md`

The SKILL.md body carries two tables: "Language Contexts" (Node+TS baseline) and "Framework Contexts" (React, Vue with activation signals).

Framework contexts MAY override baseline defaults when the framework materially differs (e.g., React projects need ESLint instead of Biome because of `eslint-plugin-react-hooks` requirement) but MUST NOT silently contradict the baseline.

## Considered Options

### Option 1 — Sibling skills: `skills/react-development/`, `skills/vue-development/`

**Pros**: Each skill has its own frontmatter description; activation by name is unambiguous; mirrors the framework-as-skill mental model of some other ecosystems.

**Cons**: (a) Forces duplication of TS baseline content (tsconfig, package manager) across N framework skills, or makes each framework skill cross-reference TS for the baseline; (b) inflates the skill catalog by N skills per language; (c) cross-skill activation friction (when working on a `.tsx` file, both `typescript-development` and `react-development` need to activate independently); (d) extension to a new framework adds a whole new skill rather than just a context file.

### Option 2 — Frameworks nested under language-rooted skill (chosen)

**Pros**: (a) Locality — TS guidance and framework guidance are one skill away; (b) baseline composition — `contexts/typescript.md` is loaded once and reused; (c) skill-count discipline — one skill per language plus N context files; (d) extension is purely additive (add `contexts/svelte.md`, add a row); (e) aligns with `agentic-sdks` precedent of multi-context-per-skill (though `agentic-sdks` nests framework × language, while this case nests language × framework).

**Cons**: (a) Bound to TypeScript-as-base; if a future framework is JS-only or another-language-first, pattern needs a parallel decision; (b) framework descriptions don't have first-class frontmatter activation surface — relies on agent reading the body's decision tree.

### Option 3 — `frontend-frameworks/` parent skill containing both

**Pros**: Frontend-specific concerns get their own bucket; backend TS and frontend TS are conceptually separated.

**Cons**: Most TS work involves both backend and frontend concerns; bisecting the skill catalog by frontend-vs-backend duplicates baseline content (same as Option 1's flaw); no clean place for non-frontend TS (Node services, CLI tools, library code).

## Consequences

### Positive

- Single language-rooted skill with multiple context files is easier to maintain and discover than N sibling skills
- Composition is natural: baseline + framework layer
- Future frameworks (Svelte, Solid, Astro) follow the same pattern by adding `contexts/<framework>.md`
- Aligns the JS/TS polyglot story with the Polyglot Skill Template ADR's "contexts/<framework>.md when language-rooted" naming case
- Praxion's skill catalog stays bounded — no per-framework inflation

### Negative

- Frameworks lack first-class skill descriptions; agent must read the SKILL.md body's decision tree to route correctly
- The pattern is TypeScript-specific in this rollout; future polyglot framework support (e.g., a hypothetical Rust+Yew or Python+FastHTML) needs to re-evaluate
- A developer searching the skill catalog for "React" gets `typescript-development` rather than a `react-development` skill — slightly higher discovery latency, mitigated by skill description text mentioning "React"

### Neutral

- Establishes a new layered-composition pattern in Praxion; future ADRs may reference this when expanding to other framework families
