---
name: typescript-development
description: >
  TypeScript development: strict-mode type system, Biome v2 (greenfield)/ESLint v9
  (framework projects), Vitest test discipline, React 19/Next.js 15/Vite, Vue 3/
  Nuxt 3. Triggers: writing/reviewing TypeScript source files, configuring tsconfig,
  choosing linter/formatter, setting up Vitest, bare-TS/Node services, React or Vue
  projects. Layered contexts: TypeScript baseline, React, Vue.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
staleness_sensitive_sections:
  - "Framework Contexts"
  - "Test Discipline"
  - "Gotchas"
---

# TypeScript Development

Language-agnostic guidance for TypeScript development. Runnable mechanics, toolchain
commands, and framework-specific details live in the per-language and per-framework
contexts loaded on demand.

**Satellite contexts** (loaded on demand):

- [contexts/typescript.md](contexts/typescript.md) — Node.js + TypeScript baseline: tsconfig strict mode, Biome/ESLint decision rule, Vitest, `tsc --noEmit` gate
- [contexts/react.md](contexts/react.md) — React 19 + Vite + Next.js 15; layers above `contexts/typescript.md`
- [contexts/vue.md](contexts/vue.md) — Vue 3 Composition API + Nuxt 3; layers above `contexts/typescript.md`

## Language Contexts

| Surface | Context File | Scope |
|---------|--------------|-------|
| Node.js + TypeScript baseline | [contexts/typescript.md](contexts/typescript.md) | All TS work — type system, linting, testing, type checking |

## Framework Contexts
<!-- last-verified: 2026-05-25 -->

| Framework | Context File | When to load alongside `contexts/typescript.md` |
|-----------|--------------|-------------------------------------------------|
| React 19 (Next.js 15, Vite) | [contexts/react.md](contexts/react.md) | `.tsx` files OR `react`/`next`/`vite` in deps |
| Vue 3 (Nuxt 3) | [contexts/vue.md](contexts/vue.md) | `.vue` files OR `vue`/`nuxt` in deps |

## Context Loading Decision Tree

The tables above are the lookup surfaces. Use this decision tree to route a session to the right context(s):

```
Working on *.ts / *.mts / *.cts files, no framework signals in package.json?
    -> Load contexts/typescript.md only.

Working on *.tsx files, OR package.json includes "react" / "next" / "vite" in deps?
    -> Load contexts/typescript.md (baseline) AND contexts/react.md.

Working on *.vue files, OR package.json includes "vue" / "nuxt" in deps?
    -> Load contexts/typescript.md (baseline) AND contexts/vue.md.
```

**Composition model**: framework contexts ASSUME the baseline `contexts/typescript.md`
is already loaded. They layer additional conventions on top; they do not restate
tsconfig, package manager, Vitest, or Biome/ESLint baseline details. Always load
`contexts/typescript.md` first when activating a framework context.

## Type System Philosophy

TypeScript's structural type system is a tool for expressing and verifying program
intent. Enable strict mode — it is not optional hardening but the baseline for
meaningful type checking.

Key discipline principles (language-agnostic; details in context files):

- Structural typing enables interface-based composition without inheritance hierarchies
- `strict: true` activates the essential type narrowing checks
- `noUncheckedIndexedAccess: true` catches the majority of runtime index errors at compile time
- `unknown` over `any` for untrusted boundaries — forces explicit narrowing at the call site
- Prefer named exports for explicit surface control; re-exports compound fragility

## Code Quality Trinity

All TypeScript projects enforce three checks in sequence:

1. **Format** — deterministic layout (Biome or Prettier; see `contexts/typescript.md` for the decision rule)
2. **Lint** — statically detectable errors and style violations (Biome or ESLint; same decision)
3. **Type check** — `tsc --noEmit` as a mandatory gate, not optional

Run all three before committing. Each check catches a different failure class; skipping one leaves a gap the others cannot cover.

For project-setup toolchain details (pnpm, volta, workspace config), see the `node-prj-mgmt` skill.

## Test Discipline
<!-- last-verified: 2026-05-25 -->

Vitest 4 is the default test runner for TypeScript projects. It shares the Vite config
surface, runs in parallel by default, and supports browser-mode testing for frontend
projects.

Key principles:

- Co-locate tests with source (`*.test.ts` or `*.spec.ts` next to the module under test)
- Use `@vitest/coverage-v8` for coverage reporting
- Type-check tests independently with `tsc --noEmit` (the same gate as production code)

For coverage configuration, thresholds, and CI integration, see the `test-coverage` skill's
TypeScript reference once available. For project-level test setup, see `contexts/typescript.md`.

## Gotchas
<!-- last-verified: 2026-05-25 -->

- **`tsc --noEmit` is mandatory, not optional**: many projects run only ESLint or only Biome and skip the type checker. ESLint `@typescript-eslint` does not replicate TypeScript's full type-inference — `tsc --noEmit` is the only check that catches generic constraint violations, overload mismatches, and mapped-type narrowing failures.
- **Biome and ESLint cannot coexist as formatters**: running both produces conflicting edits. Choose one formatter per project. For framework projects that need ESLint plugins (React hooks, Vue), use Prettier as the formatter and ESLint for linting. For greenfield/library projects, Biome handles both. See `contexts/typescript.md` for the full decision rule.
- **`strict: true` alone is not enough**: `noUncheckedIndexedAccess` is not included in `strict`. Add it explicitly or inherit from `@tsconfig/strictest` which includes it.
- **Framework contexts override Biome default**: `contexts/react.md` and `contexts/vue.md` route to ESLint+Prettier because framework-specific ESLint plugins (`eslint-plugin-react-hooks`, `eslint-plugin-vue`) have no Biome equivalents. Do not apply the Biome default to framework projects.

## Related Skills

- `node-prj-mgmt` — pnpm, volta, workspace config, tsconfig base packages, Zod coexistence gotchas
- `test-coverage` — coverage tooling, thresholds, CI integration (TypeScript reference forthcoming)
- `architectural-fitness-functions` — dependency-cruiser fitness rules for TypeScript
- `software-planning` — TypeScript quality gates in implementation plans (see `contexts/typescript.md` in that skill)
- `mcp-crafting` — MCP TypeScript SDK patterns
