# Node.js Project Management — TypeScript Context

TypeScript-specific setup for Node.js project management: Node 22 LTS + pnpm v10 + volta + @tsconfig/node22. Back to [SKILL.md](../SKILL.md).

## Contents

- [Node Version Pinning with volta](#node-version-pinning-with-volta)
- [pnpm as Default Package Manager](#pnpm-as-default-package-manager)
- [TypeScript Configuration Baseline](#typescript-configuration-baseline)
- [Testing: Vitest 4 + @vitest/coverage-v8](#testing-vitest-4--vitestcoverage-v8)
- [Code Quality: Biome v2 (default) / ESLint v9 (framework path)](#code-quality-biome-v2-default--eslint-v9-framework-path)
- [pnpm Workspace Pattern (Monorepos)](#pnpm-workspace-pattern-monorepos)
- [Zod v3/v4 Coexistence Gotcha](#zod-v3v4-coexistence-gotcha)
- [MCP TypeScript SDK Version Baseline](#mcp-typescript-sdk-version-baseline)

## Node Version Pinning with volta

**Why volta over nvm**: nvm adds ~500ms to every shell startup. volta resolves the
active Node version in ~1ms and stores the pin in `package.json` so it is
committed with the project — no per-developer setup ceremony.

```bash
# Install volta (one-time, per developer machine)
curl https://get.volta.sh | bash

# Pin Node 22 LTS for the project (writes to package.json)
volta pin node@22

# Pin pnpm version alongside Node
volta pin pnpm@10
```

The resulting `package.json` block:

```json
{
  "volta": {
    "node": "22.x.x",
    "pnpm": "10.x.x"
  }
}
```

CI picks up the pin automatically when volta is installed in the CI environment
(standard in most Node CI images via `volta-cli/action` GitHub Action).

---

## pnpm as Default Package Manager

pnpm v10 is the recommended default for all TypeScript/Node projects. Rationale:

- 2–3× faster installs than npm via content-addressed store (no duplicate packages)
- Strict symlink layout eliminates phantom dependency bugs at the project boundary
- First-class workspace support for monorepos without extra tooling
- `pnpm env` can also manage Node versions if volta is not in use

```bash
# Initialize a new project
pnpm init

# Install dependencies
pnpm install

# Add a production dependency
pnpm add <package>

# Add a dev dependency
pnpm add -D <package>

# Remove
pnpm remove <package>

# Audit for security issues
pnpm audit

# Check for outdated packages
pnpm outdated
```

---

## TypeScript Configuration Baseline

### Recommended: `@tsconfig/node22`

Extend from the curated `@tsconfig/node22` preset rather than hand-rolling
`"target"`, `"module"`, and `"lib"` values.

```bash
pnpm add -D typescript @tsconfig/node22
```

`tsconfig.json`:

```json
{
  "extends": "@tsconfig/node22/tsconfig.json",
  "compilerOptions": {
    "rootDir": "src",
    "outDir": "dist",
    "noUncheckedIndexedAccess": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
```

### Strictest baseline: `@tsconfig/strictest`

When you want the maximum type safety (recommended for new libraries and tools):

```bash
pnpm add -D @tsconfig/strictest
```

```json
{
  "extends": "@tsconfig/strictest/tsconfig.json",
  "compilerOptions": {
    "rootDir": "src",
    "outDir": "dist"
  }
}
```

### Override philosophy

- `strict: true` is included in both presets — do not remove it.
- `noUncheckedIndexedAccess: true` is the single highest-signal flag not covered by
  `strict`; add it explicitly in `@tsconfig/node22` projects.
- Override only what the project genuinely needs to differ from the preset.
- Do not pin `"target": "ES2022"` or similar — inherit from the preset and let the
  preset track the Node LTS cadence.

---

## Testing: Vitest 4 + @vitest/coverage-v8

Vitest is the recommended TypeScript test runner: native ESM, Jest-compatible API,
10–20× faster in watch mode. For coverage details, see
`test-coverage/references/typescript.md` (once created — step-10 of this pipeline).

```bash
pnpm add -D vitest @vitest/coverage-v8
```

`vitest.config.ts` baseline:

```typescript
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov", "cobertura"],
      include: ["src/**/*.ts"],
      exclude: ["src/**/*.test.ts", "src/**/*.spec.ts"],
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

---

## Code Quality: Biome v2 (default) / ESLint v9 (framework path)

### Biome v2 — greenfield and Node-only projects

Single binary, zero dependencies, ~10–25× faster than ESLint+Prettier.

```bash
pnpm add -D @biomejs/biome

# Initialize biome.json with project defaults
pnpm biome init
```

`biome.json` baseline:

```json
{
  "$schema": "https://biomejs.dev/schemas/2.0.0/schema.json",
  "formatter": {
    "enabled": true,
    "indentStyle": "space",
    "indentWidth": 2
  },
  "linter": {
    "enabled": true,
    "rules": {
      "recommended": true
    }
  },
  "javascript": {
    "formatter": {
      "quoteStyle": "double"
    }
  }
}
```

`package.json` scripts:

```json
{
  "scripts": {
    "lint": "biome check .",
    "lint:fix": "biome check --write .",
    "format": "biome format --write ."
  }
}
```

### ESLint v9 + @typescript-eslint v8 — framework projects (React, Vue, Next.js)

Use ESLint when you need framework-specific plugins (`eslint-plugin-react-hooks`,
`eslint-plugin-vue`, `@next/eslint-plugin-next`). Biome does not yet ship
React/Vue-aware rules.

For the Biome-vs-ESLint decision rule, see
`typescript-development/contexts/typescript.md`.

---

## pnpm Workspace Pattern (Monorepos)

`pnpm-workspace.yaml` at the repo root:

```yaml
packages:
  - "packages/*"
  - "apps/*"
```

`package.json` at the root (workspace root, no `main` or `exports`):

```json
{
  "private": true,
  "scripts": {
    "build": "turbo build",
    "test": "turbo test",
    "lint": "turbo lint"
  },
  "devDependencies": {
    "turbo": "^2"
  }
}
```

Each workspace package has its own `package.json` with a `name` field matching the
workspace reference:

```json
{
  "name": "@myorg/utils",
  "version": "0.0.1",
  "exports": {
    ".": "./dist/index.js"
  }
}
```

Cross-workspace references use the workspace protocol:

```json
{
  "dependencies": {
    "@myorg/utils": "workspace:*"
  }
}
```

### Task Orchestration

**Turborepo** (`turbo.json`; use for < 50 packages):

```json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": ["dist/**"]
    },
    "test": {
      "dependsOn": ["build"]
    },
    "lint": {}
  }
}
```

**Nx** (prefer for 50+ packages, affected graph, generator support): use
`npx create-nx-workspace@latest` for initial setup. Nx's `@nx/eslint-plugin`
enforces module boundaries between packages.

---

## Zod v3/v4 Coexistence Gotcha

> **This is the canonical home for the Zod cross-skill version split.**
> Cross-references: `mcp-crafting/contexts/typescript.md` and
> `agentic-sdks/contexts/openai-agents-typescript.md` both point here.

The MCP TypeScript SDK v1.x stable depends on **Zod v3**. The OpenAI Agents SDK
for JavaScript requires **Zod v4** at runtime (silent schema validation failures
otherwise — not a startup error).

Projects using both SDKs simultaneously must manage two Zod majors. pnpm's
`overrides` field handles this cleanly:

```json
{
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1",
    "@openai/agents": "^0",
    "zod": "^4"
  },
  "pnpm": {
    "overrides": {
      "zod@<4": "$zod"
    }
  }
}
```

What this does:

- Your project code uses Zod v4 (`"zod": "^4"` in dependencies).
- The MCP SDK v1 depends on `zod@^3` as a transitive dep. The `overrides` entry
  `"zod@<4": "$zod"` forces pnpm to resolve any request for `zod@<4` to the
  same version as your project's `zod` dep (v4), deduplicating the install.
- In practice, the MCP SDK v1 accepts Zod v4 via duck-typed parsing for most
  schemas. Verify your specific MCP schemas before relying on this — some advanced
  Zod v3 APIs are not present in v4.

**npm equivalent** (uses `overrides` key in `package.json` directly since npm v8.3):

```json
{
  "overrides": {
    "zod": "^4"
  }
}
```

**yarn equivalent** (uses `resolutions`):

```json
{
  "resolutions": {
    "zod": "^4"
  }
}
```

**Resolution path**: When the MCP SDK v2 stable ships with Standard Schema support
(accepting Zod v4, Valibot, ArkType), this gotcha resolves naturally — the SDK
will no longer pin Zod v3. See the MCP SDK v2 promotion criteria ADR for the
trigger conditions under which to re-evaluate.

---

## MCP TypeScript SDK Version Baseline

The recommended baseline for MCP server development is `@modelcontextprotocol/sdk`
**v1.x stable** (monolithic package).

```bash
pnpm add @modelcontextprotocol/sdk
```

v2.0 alpha (`@modelcontextprotocol/server`, `@modelcontextprotocol/node`, etc.)
is a split-package architecture that adds Standard Schema support (Zod v4, Valibot,
ArkType). As of April 2026, v2.0 is alpha and NOT production-ready.

**v2 promotion triggers** (per the MCP SDK v2 Promotion ADR):

1. `@modelcontextprotocol/sdk` v2.0.0 stable release is announced upstream
2. The Anthropic-published MCP TypeScript SDK README declares v2 production-ready
3. Standard Schema bridge lands in stable v1 (Zod v3/v4 conflict resolves naturally)

Until any trigger fires, document and implement against **v1.x stable** patterns.
See `mcp-crafting/contexts/typescript.md` for the full MCP server implementation guide.
