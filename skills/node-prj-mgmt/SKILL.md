---
name: node-prj-mgmt
description: >
  Node.js project lifecycle: version pinning, package management, dependency
  graph hygiene, workspace/monorepo patterns, tsconfig baseline philosophy.
  Triggers: setting up a Node.js project, choosing a package manager, wiring
  a monorepo, managing transitive dependency conflicts, configuring tsconfig
  inheritance, auditing dependency graph health. Language module: TypeScript.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
staleness_sensitive_sections:
  - "Node Version Management"
  - "Workspace and Monorepo Patterns"
  - "Dependency Graph Hygiene"
  - "Gotchas"
---

# Node.js Project Management

Language-agnostic foundation for Node.js project lifecycle: version management,
package management, dependency graph hygiene, workspace and monorepo patterns,
and TypeScript configuration philosophy. Language-specific setup commands and
runnable mechanics live in the per-language context loaded on demand.

**Satellite files** (loaded on-demand):

- [contexts/typescript.md](contexts/typescript.md) — pnpm setup, volta pinning, `@tsconfig` inheritance, Vitest 4, Biome v2, Zod cross-skill gotcha

## Language Contexts

| Language | Context File | Tooling (project-owned) |
|----------|--------------|-------------------------|
| TypeScript | [contexts/typescript.md](contexts/typescript.md) | pnpm + volta + @tsconfig/node22 |

Future language contexts (e.g., `contexts/javascript.md`) are added here without
body changes to this file. New rows go into the Language Contexts table above.

## How to Choose a Context

```
Working in a Node.js / TypeScript project?
    -> Load contexts/typescript.md.

Working in a plain JavaScript (non-TypeScript) Node.js project?
    -> No context exists yet; use the body guidance and adapt.

Managing a monorepo with multiple packages?
    -> Load contexts/typescript.md (pnpm workspace and Turborepo/Nx patterns are there).
```

## Node Version Management
<!-- last-verified: 2026-05-25 -->

Pin Node.js versions at the project level, not at the developer's shell level.
Shell-level version managers (nvm, fnm) are fine for individual use but impose a
startup cost and provide no project-level enforcement. The goal is that any developer
who clones the repo gets the same Node version on first use.

**Selection criteria**:

| Tool | Use when | Notes |
|------|----------|-------|
| **volta** | Team setup; per-project pinning committed in `package.json` | 1ms startup; pins Node + npm/pnpm versions declaratively; `volta pin node@22` writes into `package.json` |
| **pnpm env** | pnpm-only projects; no extra tooling | `pnpm env use --global lts/iron`; no package.json integration |
| **fnm** | Individual devs; Rust-speed switching; no team pinning | 500× faster than nvm; no project-pinning protocol |
| **nvm** | Legacy / existing project constraint | 500ms shell init tax; not recommended for new setups |

Prefer **volta** for team projects and CI. See the language context for the
`package.json` field format and CI integration pattern.

## Package Management Concepts

Three principal package managers exist for Node.js: npm (bundled with Node),
pnpm (performance- and monorepo-optimized), and bun (full runtime alternative).
The language context documents the recommended default with rationale.

**Concepts that apply regardless of manager**:

- **Lockfile discipline**: commit the lockfile (`package-lock.json`, `pnpm-lock.yaml`,
  `bun.lock`) — it is the reproducibility guarantee. Never add it to `.gitignore`.
- **Peer dependencies**: a package that lists a peer dep does not install it; the
  consuming project must satisfy it. Unmet peer deps cause silent runtime failures.
- **Phantom dependencies**: packages available at runtime because they are transitive
  deps of a direct dep, but not listed in your `package.json`. pnpm's strict
  symlink-based layout makes phantom deps a hard error rather than a silent failure.
- **Version range semantics**: prefer exact `"1.2.3"` or tight `"^1.2.3"` ranges
  in application `package.json`; use open ranges in library `package.json` to avoid
  range conflicts in consumers.

## Dependency Graph Hygiene
<!-- last-verified: 2026-05-25 -->

A healthy dependency graph has no cycles, no orphans, and no phantom dependencies.
Maintain it through:

1. **Regular audits**: `pnpm audit` (security); `pnpm outdated` (version drift).
2. **Unused dependency detection**: `knip` (v5+) finds unused exports, files, and
   listed dependencies that are never imported.
3. **Architectural layer enforcement**: use `dependency-cruiser` to enforce import
   boundaries between layers (presentation → business logic → infrastructure).
   See `architectural-fitness-functions` skill for the fitness-function pattern.
4. **Overrides for conflict resolution**: when two transitive deps require incompatible
   versions of a shared package, use package-manager overrides to pin one version.
   See Gotchas below for the canonical Zod v3/v4 case.

## Workspace and Monorepo Patterns
<!-- last-verified: 2026-05-25 -->

Node.js supports workspaces natively at the package-manager level. The workspace
wires packages; task orchestration is a separate concern.

**Three-tier decision model**:

| Scale | Package wiring | Task orchestration | When to choose |
|-------|---------------|-------------------|----------------|
| Single package | No workspace | None | One deliverable; no shared code |
| Small monorepo (2–10 packages) | pnpm workspaces | None or `pnpm -r` | Shared internal packages; no build cache needed |
| Mid monorepo (5–50 packages) | pnpm workspaces | **Turborepo v2** | Build cache + task dependency graph; Vercel CI remote cache |
| Large monorepo (50+ packages) | pnpm workspaces | **Nx v20** | `--affected` graph, generators, enforced module boundaries via `@nx/eslint-plugin` |

See the language context for `pnpm-workspace.yaml` syntax and Turborepo `turbo.json`
baseline configuration.

## tsconfig Baseline Philosophy

TypeScript compiler configuration decisions compound over time. Starting from
a curated baseline prevents hand-rolled `tsconfig.json` drift.

**Core principles**:

1. **Inherit, don't copy**: use `extends` to inherit from a published baseline
   (`@tsconfig/node22`, `@tsconfig/strictest`). Override only what the project
   genuinely needs to differ.
2. **Strict by default**: `strict: true` enables eight compiler checks simultaneously.
   Add `noUncheckedIndexedAccess: true` for safe array/map access — it is the single
   most impactful flag not covered by `strict`.
3. **`paths:` aliases vs relative imports**: TypeScript path aliases require build-tool
   alignment (Vitest `resolve.alias`, esbuild `alias`). Prefer explicit relative
   imports inside a package; use `paths:` only for cross-workspace imports where the
   resolver needs help.
4. **No version pins in tsconfig**: `"module": "NodeNext"` is correct for Node 22;
   `"target": "ES2022"` aligns with the Node LTS. Do not pin to a specific ES version
   that will become stale.

See the language context for the `@tsconfig/node22` inheritance snippet and
project-override patterns.

## Gotchas
<!-- last-verified: 2026-05-25 -->

- **Zod v3 (MCP TS SDK) and Zod v4 (OpenAI Agents SDK) coexist via package-manager overrides.**
  The MCP TypeScript SDK v1.x stable depends on Zod v3; the OpenAI Agents SDK for JS
  requires Zod v4 at runtime (silent schema failures otherwise). Projects using both
  must pin both. See `contexts/typescript.md` for the canonical `pnpm overrides`
  snippet. Cross-references: `mcp-crafting/contexts/typescript.md` and
  `agentic-sdks/contexts/openai-agents-typescript.md` both point here for the resolution.

- **pnpm phantom dependency errors look like import-not-found at runtime.** pnpm's
  strict store layout prevents importing packages that are not listed in your
  `package.json`. The fix is to add the phantom dep explicitly — do not switch to npm
  to silence the error.

- **`volta pin` writes to `package.json`, not `.nvmrc`.** Developers with nvm-only
  setups will not benefit from volta pins automatically. Document the volta setup
  requirement in the repo's `README.md`.

- **Turborepo `turbo.json` `pipeline` key is deprecated in v2.** Use `tasks` instead.
  Running an old config with v2 produces a silent migration warning, not an error.

- **`pnpm-lock.yaml` version mismatches break `pnpm install --frozen-lockfile`.** When
  the lockfile was generated by a different pnpm major, CI fails with a cryptic parse
  error. Pin pnpm version in CI and with volta to avoid the mismatch.

## Related Skills

- [`typescript-development`](../typescript-development/SKILL.md) — TypeScript language patterns, type system, Biome/ESLint, Vitest test discipline
- [`cicd`](../cicd/SKILL.md) — GitHub Actions CI/CD pipeline design for Node.js projects
- [`mcp-crafting`](../mcp-crafting/SKILL.md) — MCP TypeScript SDK patterns (references the Zod coexistence gotcha above)
