# Documenting a TypeScript / Node API Surface

How to document a TypeScript project's two doc surfaces — the **library** (a package others `import`) and the **service** (an endpoint others call) — and connect the service surface to the shared OpenAPI layer. Back to [SKILL.md](../SKILL.md).

In TypeScript the types *are* the signatures, so the library surface needs no separate annotation language — only doc comments. The service surface emits OpenAPI from one of three idioms; pick by what the project already uses. The two surfaces map directly onto core item 1 of the skill body.

Versions below are **defaults at time of writing, not pins** — verify the current release before adopting (`npm view <pkg> version` / the tool's changelog).

## Surface 1 — Library docs (from TypeScript types + TSDoc)

### Tool decision

| | TypeDoc | API Extractor (Microsoft) |
|---|---|---|
| Output | full HTML/Markdown API reference site | `.d.ts` rollup + `api.md` report + model JSON |
| Source | TypeScript types + TSDoc comments | TypeScript types + TSDoc comments |
| Primary job | publishable reference docs for consumers | track the **public API contract over time** |
| CI signal | builds the site | API report files diffed in CI catch unintended breaking changes |
| Use when | you need a docs site | you need to govern what's public + detect breaking changes |

**Recommendation:** **TypeDoc** for the published reference site; add **API Extractor** alongside it when the package has external consumers and you want the public-API surface reviewed and breaking-change-gated. They complement, they don't compete.

### Docstring convention — TSDoc, linted

Use **TSDoc** — the Microsoft-standardized doc-comment syntax (`@param`, `@returns`, `@remarks`, `@example`, `@deprecated`). Lint comments with `eslint-plugin-tsdoc` so they stay consistent and machine-parseable. Always give `@deprecated` a replacement and removal timeline, not just the tag.

```typescript
/**
 * Fetch one item by id.
 *
 * @param id - the item's stable identifier
 * @returns the item, or throws {@link NotFoundError} if absent
 * @deprecated Use {@link fetchItem} — removed in v3.0.
 */
export function getItem(id: string): Item { /* ... */ }
```

### Minimal setup

```
npx typedoc src/index.ts        # → docs site from types + TSDoc
```

API Extractor: `api-extractor run --local` against a configured `api-extractor.json`.

## Surface 2 — Service docs (OpenAPI from TypeScript)

Three idioms emit OpenAPI; all three produce a spec that drives Swagger UI / ReDoc identically to FastAPI.

| Approach | Source of truth | Best when |
|---|---|---|
| **zod-to-openapi** / **nestjs-zod** | Zod schemas (one schema → validation + type + OpenAPI via `.meta()`) | the project already uses Zod for runtime validation — avoids DTO duplication |
| **tsoa** | decorators (`@Route`, `@Get`, `@Body`) on controllers → OpenAPI + routes from actual code | framework-agnostic, decorator-driven REST (Express / Koa / etc.) |
| **`@nestjs/swagger`** | NestJS decorators (`@ApiProperty`, …) + CLI plugin | NestJS projects (native) |

**Recommendation:** **Zod-first** (`zod-to-openapi` / `nestjs-zod`) for new projects already using Zod — one schema becomes validation, types, and docs, so the contract cannot drift from the validator. Use **tsoa** for decorator-driven non-Nest REST, and **`@nestjs/swagger`** for NestJS. Express/Fastify projects without these fall back to hand-written spec or `swagger-jsdoc` (JSDoc comments → spec) — weaker, because the comments drift from the code.

> **Version drift risk — verify at use:** **tsoa v7** (which emits OpenAPI **3.1**) was at **alpha** as of late 2025; the stable line emitted 3.0. Check the installed tsoa version and which OpenAPI version it targets before relying on 3.1-only spec features. Likewise confirm `zod-to-openapi` ↔ Zod major alignment (the v8 line targets Zod v4 `.meta()`).

### Minimal setup (tsoa)

```
tsoa spec-and-routes          # → swagger.json + generated routes
# then serve with swagger-ui-express
```

Whichever idiom emits the spec, the spec layer itself — committing it, the Spectral ruleset, and the lint → breaking-change-diff → contract-test CI gate — is **shared across all REST surfaces** and lives in [`rest-openapi.md`](rest-openapi.md). These TS tools are just the code-first emitters feeding that pipeline; don't re-author the gate here.

## Both surfaces — cross-link

A package that ships a library *and* a service publishes both and bridges them: the TypeDoc site links to the live OpenAPI spec; the service docs link back to the TypeDoc reference for the shared model/Zod types. The user navigates one surface; links bridge to the others (skill core item 1).

## Sources

- [TypeDoc](https://typedoc.org/) — API docs from TypeScript types
- [TSDoc](https://tsdoc.org/) + [eslint-plugin-tsdoc](https://www.npmjs.com/package/eslint-plugin-tsdoc) — doc-comment standard + linter
- [API Extractor](https://api-extractor.com/) — public-API tracking + `.d.ts` rollup + report diffing
- [tsoa → OpenAPI (Speakeasy)](https://www.speakeasy.com/openapi/frameworks/tsoa) — decorators → OpenAPI 3.1 (v7 alpha)
- [NestJS → OpenAPI (Speakeasy)](https://www.speakeasy.com/openapi/frameworks/nestjs) + [nestjs-zod](https://www.npmjs.com/package/nestjs-zod)
- [zod-to-openapi](https://github.com/asteasolutions/zod-to-openapi) — Zod as single source of truth
- [`rest-openapi.md`](rest-openapi.md) — the shared OpenAPI spec layer and CI gate
