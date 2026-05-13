# TypeScript Baseline Context

Node.js + TypeScript language mechanics for all TS work. Loaded first before any
framework context (`contexts/react.md`, `contexts/vue.md`).

For pnpm/volta/workspace setup, see [`node-prj-mgmt/contexts/typescript.md`](../../node-prj-mgmt/contexts/typescript.md).

**Related skills**:
- [TypeScript Development](../SKILL.md) — skill body with context routing decision tree
- [Node Project Management](../../node-prj-mgmt/SKILL.md) — pnpm, volta, workspace, Zod coexistence

---

## Code quality toolchain

Choose your path before reading further. The right tool depends on whether your project
has framework plugin requirements.

```
Greenfield project with no framework plugin dependencies?
   -> Biome v2 (default; faster; single tool)

Project uses React, Next.js, Vue, Nuxt, or any framework with required ESLint plugins
(e.g., eslint-plugin-react-hooks)?
   -> ESLint v9 + @typescript-eslint v8 + Prettier

Project mixes both (TS libraries + framework apps in one monorepo)?
   -> ESLint+Prettier (the union; Biome can coexist only for non-JS/TS files)
```

Framework contexts (`contexts/react.md`, `contexts/vue.md`) explicitly route to
ESLint+Prettier — they override this default.

### Path A — Biome v2 (greenfield default)

Install:

```bash
pnpm add -D @biomejs/biome
pnpm biome init
```

Minimal `biome.json`:

```json
{
  "$schema": "https://biomejs.dev/schemas/2.0.0/schema.json",
  "organizeImports": { "enabled": true },
  "linter": {
    "enabled": true,
    "rules": { "recommended": true }
  },
  "formatter": { "enabled": true, "indentStyle": "space" }
}
```

CI step:

```bash
pnpm biome ci .
```

Format + lint in fix mode (local):

```bash
pnpm biome check --write .
```

**Gotchas**:
- Biome format and ESLint format cannot coexist. Choose one formatter per project.
- Biome has no `eslint-plugin-react-hooks` equivalent — React/Vue projects must use Path B.
- `biome ci` exits non-zero on any finding. In CI, this is the correct behavior.

### Path B — ESLint v9 + @typescript-eslint v8 + Prettier (framework default)

Install:

```bash
pnpm add -D eslint @eslint/js typescript-eslint prettier eslint-config-prettier
```

Minimal `eslint.config.mjs` (flat config):

```js
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import prettierConfig from "eslint-config-prettier";

export default tseslint.config(
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  prettierConfig,
  {
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
  }
);
```

CI steps:

```bash
pnpm prettier --check .
pnpm eslint .
```

Fix mode (local):

```bash
pnpm prettier --write .
pnpm eslint --fix .
```

**Gotchas**:
- `projectService: true` requires `@typescript-eslint` v8+. Do not use the legacy `project: "./tsconfig.json"` form.
- `eslint-config-prettier` must be last in the config array — it disables ESLint formatting rules that conflict with Prettier.
- `tseslint.configs.strictTypeChecked` enables type-aware rules; these require `parserOptions.projectService`. Omitting `projectService` and using `strictTypeChecked` produces confusing errors.

---

## Node.js and TypeScript version baseline

| Runtime | Version | LTS status |
|---------|---------|------------|
| Node.js | 22 LTS | Active LTS (recommended) |
| Node.js | 24 LTS | Current (preview) |
| TypeScript | 5.x | Stable |

Do not ship code that requires Node.js < 22 LTS unless explicitly targeting a legacy environment.

---

## tsconfig strict configuration

Start from `@tsconfig/strictest` (the tightest community baseline):

```bash
pnpm add -D @tsconfig/strictest
```

`tsconfig.json`:

```json
{
  "extends": "@tsconfig/strictest/tsconfig.json",
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "outDir": "dist",
    "rootDir": "src",
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
```

`@tsconfig/strictest` already enables:

- `strict: true` (the full strict bundle)
- `noUncheckedIndexedAccess: true`
- `noImplicitReturns: true`
- `exactOptionalPropertyTypes: true`
- `noUncheckedSideEffectImports: true`

**Do not** disable any of these without an explicit, documented justification in the code.

For Node 22-specific module resolution, also add `@tsconfig/node22`:

```bash
pnpm add -D @tsconfig/node22
```

```json
{
  "extends": ["@tsconfig/strictest/tsconfig.json", "@tsconfig/node22/tsconfig.json"]
}
```

---

## Type-system discipline

Three constraints that the strict-mode flags above cannot enforce on their own.
Apply them as conventions across every TypeScript file.

### `any` usage

No `any` without an explicit disable comment and a reason. Prefer `unknown` for
genuinely-unknown values — it forces a type-narrowing check before use, where
`any` silently bypasses the type system.

```typescript
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- third-party callback has no typings
const handler: any = thirdPartyLib.registerCallback(fn);
```

### Import ordering

Keep imports sorted consistently. The sorter follows the linter choice from
§ "Code quality toolchain":

- **Biome projects**: Biome's built-in import sorter (`biome check --write`).
  No extra config needed.
- **ESLint projects**: `eslint-plugin-import` with the `import/order` rule
  configured.

Do not mix both sorters in one project.

### Named exports

Prefer named exports over default exports:

```typescript
// preferred
export function parseConfig(raw: unknown): Config { /* ... */ }
export type Config = { /* ... */ };

// avoid
export default function parseConfig(raw: unknown): Config { /* ... */ }
```

Named exports produce more stable import paths across renames and enable
better IDE auto-import. Default exports are acceptable only when a framework
convention requires them (e.g., Next.js page components, React lazy
boundaries).

---

## Type checking gate — `tsc --noEmit`

`tsc --noEmit` is a **mandatory gate**, not optional. Add it to every CI pipeline and
run it locally before committing.

```bash
pnpm tsc --noEmit
```

With a watch alias in `package.json`:

```json
{
  "scripts": {
    "typecheck": "tsc --noEmit",
    "typecheck:watch": "tsc --noEmit --watch"
  }
}
```

`tsc --noEmit` catches things ESLint and Biome cannot:
- Generic constraint violations
- Overload resolution mismatches
- Conditional-type narrowing failures
- Mapped-type structural errors

Run order: format → lint → typecheck → test. All four must pass.

---

## Vitest 4

Vitest 4 is the default test runner. Install:

```bash
pnpm add -D vitest @vitest/coverage-v8
```

Minimal `vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
    },
  },
});
```

`package.json` scripts:

```json
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest",
    "test:coverage": "vitest run --coverage"
  }
}
```

For coverage thresholds, CI integration, and framework-specific test setup, see the
`test-coverage` skill (TypeScript reference) once available.

**Gotcha**: Vitest and Jest share similar APIs but differ on `vi` (Vitest) vs `jest`
(Jest) for mocking. Do not mix the two in the same project.

---

## Framework pointers

For React projects: see [`contexts/react.md`](react.md). Load it alongside this file.

For Vue projects: see [`contexts/vue.md`](vue.md). Load it alongside this file.

Framework contexts assume this baseline is already loaded. They do not restate
pnpm setup, tsconfig, or Vitest configuration.
