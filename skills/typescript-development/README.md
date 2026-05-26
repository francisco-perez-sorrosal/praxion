# TypeScript Development

TypeScript development conventions: strict-mode type system, Biome v2 / ESLint v9 toolchain selection, Vitest 4 test discipline, React 19 / Next.js 15, and Vue 3 / Nuxt 3. Framework-specific patterns layer on top of the shared TypeScript baseline via a `contexts/` directory.

## When to Use

- Writing or reviewing TypeScript source files
- Configuring `tsconfig.json` (strict mode, `noUncheckedIndexedAccess`, path aliases)
- Choosing between Biome and ESLint/Prettier for a project
- Setting up Vitest for TypeScript projects
- Working on bare Node.js + TypeScript services
- React 19 (Vite, Next.js 15) or Vue 3 (Nuxt 3) projects

## Activation

Auto-triggers on TypeScript development tasks: writing `.ts`/`.tsx`/`.vue` files, configuring tsconfig, choosing a linter/formatter, setting up Vitest.

Trigger explicitly by mentioning "typescript", "tsconfig", "Biome", "Vitest", "React", "Vue", "Next.js", or "Nuxt".

## Skill Contents

- `SKILL.md` — type system philosophy, Code Quality Trinity (format/lint/type-check), test discipline, gotchas, context routing decision tree
- `contexts/typescript.md` — Node.js + TypeScript baseline: code quality toolchain, strict tsconfig, type-system discipline, `tsc --noEmit` gate, Vitest 4 setup
- `contexts/react.md` — React 19 + Vite + Next.js 15: ESLint/Prettier override, hooks patterns, App Router, React Testing Library, Playwright
- `contexts/vue.md` — Vue 3 Composition API + Nuxt 3: ESLint path, vue-tsc, `<script setup>`, @vue/test-utils, Nuxt 3 conventions

## Related Skills

- [`node-prj-mgmt`](../node-prj-mgmt/SKILL.md) — pnpm, volta, workspace config, tsconfig base packages, Zod coexistence gotchas
- [`test-coverage`](../test-coverage/SKILL.md) — coverage tooling, thresholds, CI integration
- [`mcp-crafting`](../mcp-crafting/SKILL.md) — MCP TypeScript SDK patterns
