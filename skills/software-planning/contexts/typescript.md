# TypeScript Planning Context

Language-specific planning guidance for TypeScript projects. Load alongside the [Software Planning](../SKILL.md) skill when planning TypeScript work.

**Related skills**:
- [TypeScript Development](../../typescript-development/SKILL.md) — tsconfig, Vitest, Biome/ESLint patterns, code quality
- [Node Project Management](../../node-prj-mgmt/SKILL.md) — pnpm, volta, workspaces, Zod coexistence

## Project Setup Steps

When a plan involves creating or initializing a TypeScript project, include an early step for environment setup. Decide on the package manager and toolchain based on project needs:

| Need | Tool | Reference |
|------|------|-----------|
| Node.js projects, monorepos, pnpm workspaces | pnpm + volta | [node-prj-mgmt](../../node-prj-mgmt/SKILL.md) |
| Greenfield TS library (no framework plugins needed) | Biome v2 | [typescript-development contexts](../../typescript-development/contexts/typescript.md) |
| React, Next.js, Vue, Nuxt (framework plugin deps) | ESLint v9 + Prettier | [typescript-development contexts](../../typescript-development/contexts/typescript.md) |

**Typical setup step**:

```markdown
### Step 1: Initialize TypeScript project with pnpm

**Implementation**: `pnpm init`, add core dependencies, configure tsconfig (extend `@tsconfig/strictest`), configure dev tools (Biome or ESLint, Vitest)
**Done when**: `pnpm tsc --noEmit` exits cleanly; `pnpm test` runs with zero failures
```

## Quality Gates

Every plan step that produces code should pass these checks before requesting commit approval. Run them in this order — each gate catches different failure classes.

```bash
# Biome path (greenfield / no framework plugins)
pnpm biome check --write .   # Format + lint in fix mode
pnpm tsc --noEmit             # Type check (mandatory gate)
pnpm vitest run               # Tests

# ESLint+Prettier path (framework projects)
pnpm prettier --write .       # Format (fix mode)
pnpm eslint --fix .           # Lint (fix mode)
pnpm tsc --noEmit             # Type check (mandatory gate)
pnpm vitest run               # Tests
```

For the Biome-vs-ESLint decision rule and setup details, see
[typescript-development/contexts/typescript.md](../../typescript-development/contexts/typescript.md).

### `tsc --noEmit` — mandatory type-check gate

`tsc --noEmit` is **not optional**. Add it to every CI pipeline and run it locally before
committing. It catches what Biome and ESLint cannot: generic constraint violations, overload
resolution mismatches, conditional-type narrowing failures, and mapped-type structural errors.

```bash
pnpm tsc --noEmit
```

Add a `typecheck` script to `package.json` so the gate is visible and CI-reproducible:

```json
{
  "scripts": {
    "typecheck": "tsc --noEmit"
  }
}
```

### Biome / ESLint CI step

Use the appropriate CI command for your toolchain path (see
[typescript-development/contexts/typescript.md](../../typescript-development/contexts/typescript.md)
for the full Biome-vs-ESLint decision rule and configuration):

```bash
# Biome path
pnpm biome ci .

# ESLint+Prettier path
pnpm prettier --check .
pnpm eslint .
```

### Vitest coverage threshold check

Run with coverage and enforce thresholds via `vitest.config.ts`:

```bash
pnpm vitest run --coverage
```

Minimal threshold configuration in `vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 75,
      },
    },
  },
});
```

CI fails on threshold violation — no manual review required. Thresholds are project-specific;
adjust up as test coverage matures. See the `test-coverage` skill (TypeScript reference) for
detailed threshold band guidance.

### dependency-cruiser `depcruise --validate` step

When architectural fitness functions are in scope, add a `depcruise --validate` gate:

```bash
pnpm depcruise --validate .dependency-cruiser.cjs src
```

Include this step when:
- The plan has an explicit layered architecture (e.g., `domain → application → infra`)
- A step restructures module boundaries or introduces new cross-cutting imports
- The plan involves a monorepo with package isolation contracts

See [`architectural-fitness-functions/contexts/typescript.md`](../../architectural-fitness-functions/contexts/typescript.md)
for dependency-cruiser rule recipes (forbidden, layered, orphan) and CI integration.

### Token budget measurement note

When a plan step adds always-loaded content to a TypeScript skill's `SKILL.md` (content
outside a `paths:`-scoped rule or a satellite reference file), measure the token impact
before committing:

```bash
python3 scripts/measure_token_budget.py        # real tokenizer; file set encoded in the script
```

The always-loaded surface budget is **25,000 tokens**. Prefer satellite reference files
(`references/`, `contexts/`) for content that activates on demand rather than every session.

Include quality gates in the plan's commit checklist — they augment the generic checklist
from the software planning skill.

## Step Templates

Common step shapes for TypeScript projects. Adapt to your plan's granularity.

### Add a dependency

```markdown
### Step N: Add <library> for <purpose>

**Implementation**: `pnpm add [-D] <library>`, import and wire into <module>
**Testing**: Verify import works; add smoke test if integration is non-trivial
**Done when**: Existing tests pass; `pnpm tsc --noEmit` clean; new dependency resolves cleanly
```

### Create a new module

```markdown
### Step N: Create <module_name> module

**Implementation**: Create `src/<module_name>.ts` with typed public API; add barrel export if needed
**Testing**: Unit tests in `src/<module_name>.test.ts` (or `tests/`) for critical paths
**Done when**: `pnpm tsc --noEmit` passes; tests cover primary behavior
```

### Add CLI / entry point

```markdown
### Step N: Add CLI entry point

**Implementation**: Create `src/cli.ts` using a CLI library (e.g., commander, yargs), wire to `package.json` `bin` field
**Testing**: Test argument parsing and basic invocation via `vitest run`
**Done when**: `pnpm <package-name>` runs successfully; `pnpm tsc --noEmit` passes
```

### Refactor / extract module

```markdown
### Step N: Extract <concern> from <source> into <target>

**Implementation**: Move related functions/types, update imports, verify no circular dependencies
**Testing**: Existing tests pass without modification (behavior preservation)
**Done when**: Biome/ESLint clean; `pnpm tsc --noEmit` passes; all tests green
```

## Testing Patterns for Plan Steps

When writing the **Testing** field of a plan step, choose the appropriate level:

| Step type | Testing approach |
|-----------|-----------------|
| New module with logic | Unit tests with Vitest; parametrize edge cases with `test.each` |
| Integration / wiring | Smoke test that exercises the integration path end-to-end |
| Data validation | Tests covering valid, invalid, and boundary inputs |
| API endpoint | Request/response tests with a test client (e.g., `supertest`, Hono `testClient`) |
| Refactoring | Existing tests must pass unchanged |
| Dependency addition | Import smoke test; integration test if non-trivial |
| Configuration | Validate config loads correctly with test fixtures |

Reference the [TypeScript Development](../../typescript-development/SKILL.md) skill for
Vitest patterns (mocking with `vi`, fixtures, `test.each`).

## Common Plan Shapes

Starter outlines for typical TypeScript projects. Each is a sequence of plan steps —
adapt and split further based on the [step size heuristics](../SKILL.md#step-size-heuristics).

### Library

1. Initialize project (pnpm, tsconfig strict, Biome or ESLint, Vitest)
2. Define core types (`types.ts` or `models.ts`)
3. Implement primary module with typed public API
4. Add tests for critical paths
5. Add secondary modules as needed
6. Document public API (TSDoc, README usage example)

### CLI Application

1. Initialize project with `bin` entry point in `package.json`
2. Define configuration (Zod schema or typed interface for settings)
3. Implement core logic as testable module (no CLI coupling)
4. Add CLI layer wiring to core (`commander`, `yargs`, or similar)
5. Add integration tests for CLI invocation
6. Handle error cases and user-facing messages

### Data Pipeline / Backend Service

1. Initialize project with relevant runtime dependencies
2. Define input/output schemas (Zod models)
3. Implement extraction / ingestion step
4. Implement transformation step with validation
5. Implement output / persistence step
6. Add end-to-end test with fixture data

### API Service

1. Initialize project with web framework (Hono, Fastify, Express)
2. Define request/response schemas (Zod)
3. Implement core domain logic (framework-independent)
4. Add API routes wiring to domain logic
5. Add request validation and error handling
6. Add API tests with test client
