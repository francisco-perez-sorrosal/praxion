# TypeScript Architectural Fitness Functions

TypeScript-specific implementation guide for architectural fitness functions. Load alongside
the generic [Architectural Fitness Functions](../SKILL.md) skill.

**Related skills:**
- [TypeScript Development](../../typescript-development/SKILL.md) -- tsconfig, toolchain, testing patterns
- [Node.js Project Management](../../node-prj-mgmt/SKILL.md) -- pnpm setup, volta, dependency management

## Table of Contents

- [Tooling Overview](#tooling-overview)
- [dependency-cruiser Quickstart](#dependency-cruiser-quickstart)
  - [Initialization](#initialization)
  - [Config Layout](#config-layout)
  - [Rule Recipes](#rule-recipes)
  - [Running dependency-cruiser](#running-dependency-cruiser)
- [ESLint `no-restricted-imports` Patterns](#eslint-no-restricted-imports-patterns)
- [ArchUnitTS Alternative](#archunitts-alternative)
- [Citation Locations — TypeScript](#citation-locations--typescript)
- [Authoring Workflow — TypeScript](#authoring-workflow--typescript)
- [CI Integration](#ci-integration)
- [Diagram Output](#diagram-output)

## Tooling Overview

TypeScript fitness functions use two complementary approaches:

| Tool | Invariant type | Config location |
|------|---------------|-----------------|
| `dependency-cruiser` | Module-level import graph rules (graph-rule) | `.dependency-cruiser.cjs` |
| ESLint `no-restricted-imports` | Per-file import restrictions | `eslint.config.js` |

`dependency-cruiser` (~978k weekly npm downloads) is the TypeScript equivalent of Python's
`import-linter`. It validates the entire dependency graph against named rules and produces
visualization output. ESLint import rules are complementary — they provide editor integration
and per-file feedback but cannot see the full graph.

Add `dependency-cruiser` as a dev dependency:

```bash
pnpm add -D dependency-cruiser
```

## dependency-cruiser Quickstart

### Initialization

Generate a config file tuned to your project structure:

```bash
npx depcruise --init
```

This creates `.dependency-cruiser.cjs` (CommonJS format, compatible with ESM projects)
with project-detected settings for TypeScript, Jest/Vitest, and the `tsconfig.json` path.

Review the generated config and enable the rules appropriate for your project. The output
targets `src/` by default — adjust to your actual source directory.

### Config Layout

`.dependency-cruiser.cjs` structure:

```javascript
/** @type {import('dependency-cruiser').IConfiguration} */
module.exports = {
  forbidden: [
    // Named rules — each gets its own entry with a comment field for citations
    {
      name: "no-circular",
      comment:
        "CLAUDE.md§Structural Beauty — circular dependencies prevent independent " +
        "testing and muddy module boundaries",
      severity: "error",
      from: {},
      to: { circular: true },
    },
    {
      name: "no-orphan",
      comment:
        "CLAUDE.md§Pragmatism — unreachable modules are dead code; " +
        "remove or wire them up",
      severity: "warn",
      from: { orphan: true },
      to: {},
    },
  ],
  options: {
    tsPreCompilationDeps: true,
    tsConfig: { fileName: "./tsconfig.json" },
    enhancedResolveOptions: {
      exportsFields: ["exports"],
      conditionNames: ["import", "require", "node", "default"],
    },
    reporterOptions: {
      archi: { collapsePattern: "^(node_modules|src/[^/]+)/" },
    },
  },
};
```

### Rule Recipes

**Forbidden import (X must never import Y):**

```javascript
{
  name: "no-domain-to-infra",
  comment:
    "dec-NNN (layered architecture) — domain layer must not depend on " +
    "infrastructure details; inject dependencies at the composition root",
  severity: "error",
  from: { path: "^src/domain" },
  to: { path: "^src/infra" },
},
```

**Layered import ordering (presentation → services → domain):**

```javascript
{
  name: "no-presentation-to-domain-direct",
  comment:
    "dec-NNN (layered architecture) — presentation layer must go through " +
    "services, not reach into domain directly",
  severity: "error",
  from: { path: "^src/presentation" },
  to: { path: "^src/domain", via: { path: "^src/services" } },
},
```

**Independence (two modules must not import each other):**

```javascript
{
  name: "auth-billing-independence",
  comment:
    "CLAUDE.md§Incremental Evolution — auth and billing must remain independently " +
    "deployable; shared types belong in a shared/ module",
  severity: "error",
  from: { path: "^src/auth" },
  to: { path: "^src/billing" },
},
{
  name: "billing-auth-independence",
  comment:
    "CLAUDE.md§Incremental Evolution — symmetric: billing must not import auth " +
    "for the same independence reason",
  severity: "error",
  from: { path: "^src/billing" },
  to: { path: "^src/auth" },
},
```

**No unreachable modules from entry point:**

```javascript
{
  name: "no-unreachable-from-root",
  comment:
    "CLAUDE.md§Pragmatism — modules unreachable from any entry point are dead code",
  severity: "warn",
  from: { path: "^src/index\\.ts$" },
  to: {
    path: "^src",
    reachable: false,
  },
},
```

### Running dependency-cruiser

Validate all rules (exits with code 1 on any `error`-severity violation):

```bash
npx depcruise src --validate
```

With explicit config path:

```bash
npx depcruise src --validate .dependency-cruiser.cjs
```

Report only failures (suppress passing rules):

```bash
npx depcruise src --validate --output-type err-long
```

## ESLint `no-restricted-imports` Patterns

ESLint's `no-restricted-imports` rule is complementary to dependency-cruiser. Use it for
quick, per-file restrictions that provide editor feedback without needing to run the full
graph analysis:

```javascript
// eslint.config.js (ESLint v9 flat config)
export default [
  {
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["../infra/*", "../../infra/*"],
              message:
                "Do not import infra from domain. Use dependency injection. " +
                "See dec-NNN.",
            },
          ],
        },
      ],
    },
  },
];
```

**When to use ESLint imports vs dependency-cruiser:**

| Need | Tool |
|------|------|
| Detect any circular dependency in the project | dependency-cruiser |
| Enforce full layer ordering across the graph | dependency-cruiser |
| Detect orphan/unreachable modules | dependency-cruiser |
| Quick per-file "never import X" with editor feedback | ESLint `no-restricted-imports` |
| Both editor feedback AND graph-level enforcement | Both (redundant is fine) |

## ArchUnitTS Alternative

[ArchUnitTS](https://lukasniessen.github.io/ArchUnitTS/) provides a test-suite-integrated
approach (rules written as Vitest/Jest tests) similar to Python's pytest-based fitness rules.

```typescript
// fitness/tests/arch.test.ts
import { Architectures } from "archunit";

const arch = Architectures.forRoot("src");

test("domain must not import infra", () => {
  const rule = arch
    .slices()
    .matching("domain..")
    .should()
    .notDependOn("infra..");
  expect(rule.check()).toEqual([]);
});
```

**Deferred preference**: ArchUnitTS has a smaller community than dependency-cruiser
(~978k vs ~5k weekly downloads). Prefer dependency-cruiser for new projects. Consider
ArchUnitTS when the test-suite-integrated approach is preferred over a separate CLI tool.

## Citation Locations — TypeScript

Every dependency-cruiser rule and ESLint import restriction **must** cite its architectural
justification in the `comment` field (dependency-cruiser) or in the `message` field
(ESLint `no-restricted-imports`).

| Rule type | Citation location | Example |
|-----------|-------------------|---------|
| dependency-cruiser `forbidden` rule | `comment` field of the rule object | `comment: "dec-NNN (layered arch) — ..."` |
| ESLint `no-restricted-imports` | `message` field of the pattern | `message: "See dec-NNN. ..."` |
| ArchUnitTS test | Test file docstring or test description | `test("domain must not import infra — dec-NNN", ...)` |

The citation regex (same as Python's meta-citation rule):

```
dec-\d{3,}|CLAUDE\.md§[A-Z][A-Za-z ]+
```

Write the citation **before** the rule logic — it forces upfront justification and
ensures the rule is tied to a decision, not to a developer's preference.

## Authoring Workflow — TypeScript

1. **Choose the tool** per the decision rubric in [SKILL.md](../SKILL.md): graph rule
   (dependency-cruiser) vs per-file restriction (ESLint `no-restricted-imports`).

2. **Write the citation first** — in the `comment` or `message` field — before writing
   the rule logic. This forces upfront justification.

3. **Write the rule** following the recipes above.

4. **Run the validation**:

   ```bash
   npx depcruise src --validate                  # graph rules
   npx eslint src --rule 'no-restricted-imports: ...'  # per-file restrictions
   ```

   All rules must pass before the rule is considered done.

5. **Verify no regression**: if a CI job exists for dependency validation, run it locally
   before pushing.

## CI Integration

Add a dependency-cruiser step to CI alongside the TypeScript build and test steps:

```yaml
# GitHub Actions example
- name: Dependency graph contracts
  run: npx depcruise src --validate .dependency-cruiser.cjs --output-type err-long

- name: TypeScript type check
  run: pnpm exec tsc --noEmit

- name: Tests
  run: pnpm exec vitest run
```

dependency-cruiser exits with code 1 on any `error`-severity violation — CI fails
automatically. `warn`-severity violations produce output but do not fail the build (useful
for incremental adoption of new rules).

## Diagram Output

dependency-cruiser produces Mermaid diagrams compatible with Praxion's
[diagram conventions](../../../rules/writing/diagram-conventions.md):

```bash
# Generate a Mermaid diagram of the dependency graph
npx depcruise src --output-type mermaid > diagrams/dependencies/src/dependencies.mmd

# Then render to SVG following diagram conventions
mmdc -i diagrams/dependencies/src/dependencies.mmd \
     -o diagrams/dependencies/rendered/dependencies.svg
```

Use `--include-only` to scope the output to a subsystem:

```bash
npx depcruise src/domain --output-type mermaid --include-only "^src/domain"
```
