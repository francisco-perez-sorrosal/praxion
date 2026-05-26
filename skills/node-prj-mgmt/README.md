# Node.js Project Management

Node.js project lifecycle: version management, package management, dependency graph hygiene, workspace and monorepo patterns, and TypeScript configuration philosophy. Language-specific runnable mechanics live in the per-language context loaded on demand.

## When to Use

- Setting up a Node.js project (version pinning, package manager choice)
- Choosing between npm, pnpm, and bun
- Wiring a monorepo with pnpm workspaces and Turborepo or Nx
- Managing transitive dependency conflicts (including the Zod v3/v4 coexistence case)
- Configuring tsconfig inheritance via `@tsconfig/node22` or `@tsconfig/strictest`
- Auditing dependency graph health with `pnpm audit`, `knip`, `dependency-cruiser`

## Activation

Auto-triggers on Node.js project lifecycle tasks: version pinning, package manager setup, monorepo wiring, transitive dependency conflicts.

Trigger explicitly by mentioning "node project", "pnpm", "volta", "npm", "monorepo", "tsconfig", "Turborepo", "Nx", "Zod coexistence", or "dependency graph".

## Skill Contents

- `SKILL.md` — language-agnostic foundation: version management selection, package management concepts, dependency graph hygiene, workspace/monorepo patterns, tsconfig baseline philosophy, gotchas
- `contexts/typescript.md` — TypeScript-specific setup: pnpm v10 + volta + @tsconfig/node22, Vitest 4, Biome v2, Zod v3/v4 coexistence pnpm overrides, MCP TS SDK version baseline

## Related Skills

- [`typescript-development`](../typescript-development/SKILL.md) — TypeScript language patterns, type system, Biome/ESLint, Vitest test discipline
- [`cicd`](../cicd/SKILL.md) — GitHub Actions CI/CD pipeline design for Node.js projects
- [`mcp-crafting`](../mcp-crafting/SKILL.md) — MCP TypeScript SDK patterns (references the Zod coexistence gotcha)
