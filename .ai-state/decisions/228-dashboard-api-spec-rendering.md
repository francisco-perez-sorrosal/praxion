---
id: dec-228
title: Dashboard surfaces project API specs as rendered API reference (Scalar standalone)
status: accepted
category: architectural
date: 2026-06-16
summary: The doc manifest builder discovers API spec files and the dashboard renders them as API reference docs via a Scalar standalone bundle over the raw spec, served through the existing server-only data layer.
tags: [dashboard, api-documentation, doc-manifest, renderer, openapi, scalar]
made_by: agent
agent_type: systems-architect
branch: feat-api-documentation-skill
pipeline_tier: full
affected_files:
  - scripts/build_doc_manifest.py
  - skills/doc-management/references/doc-manifest-schema.md
  - dashboard_app/src/components/registry.ts
  - dashboard_app/src/server/view-models/documentation.ts
  - dashboard_app/src/app/documentation/page.tsx
re_affirms: dec-226
---

## Context

The `api-documentation` skill + `/document-api` command teach managed projects to produce
best-in-class docs of their own API surface (OpenAPI/AsyncAPI/GraphQL SDL/MCP). The user chose
the deepest dashboard-integration option: the Praxion dashboard must surface a project's API
specs as **rendered API reference docs**, not as a raw text dump.

Two facts shape the design:

1. `scripts/build_doc_manifest.py` walks `docs/**/*.md`, `.ai-state/`, `.ai-work/`, and a curated
   root-file list. It does **not** discover API spec files (`openapi.{yaml,json}`, `asyncapi.yaml`,
   GraphQL `.graphql`/SDL). The post-commit hook regenerates the manifest **wholesale**, so any
   surface must be produced by builder-side discovery — hand-authored manifest entries would be
   clobbered (this kills the previously-planned `assets/doc-manifest-entry.yaml`).
2. The dashboard's documentation page only consults the renderer registry for `type: markdown`.
   A `type: yaml|json` surface falls into `renderMode: "code"` and renders as a raw `<pre>` JSON
   dump in `getDocumentationSurfaceData()` — useless as API reference for either a human or an agent.

The renderer registry (`registry.ts` + `resolveRenderer`) is the established extension point, but it
is keyed off `diataxis`/`contentType` and is only reached on the markdown path.

## Decision

**The builder discovers API spec files and emits them as first-class manifest surfaces, and the
dashboard renders them through a new `api_reference` renderer that embeds a Scalar standalone bundle
over the raw spec.** Concretely:

- **Discovery (builder):** walk a bounded set of spec locations — project root, `docs/`, and an
  `openapi/`|`api/`|`spec(s)/` directory if present — for `openapi.{yaml,json}`,
  `asyncapi.{yaml,json}`, and `*.graphql`/`*.graphqls` SDL. Each becomes a surface with its existing
  `type` (`yaml`|`json`; SDL typed as `graphql` via a new ext mapping), `diataxis: reference`, and
  `renderer: api_reference`. `id` from the path-slug helper, `title` from the spec's
  `info.title`+`info.version` (OpenAPI/AsyncAPI) or filename fallback. Multi-surface projects
  (REST + GraphQL + MCP) appear as **one "API Reference" group with N entries**, cross-linked, not
  triplicated.
- **Rendering (dashboard):** a new `ApiReferenceShell` component embeds the **Scalar API Reference
  standalone bundle** (script-tag/web-component over the raw spec string). The spec is read
  server-side through the existing `getDocumentationSurfaceData()` data layer (server-only, no client
  fetch), then handed to the client component as the spec body. Register `api_reference` in
  `RENDERER_REGISTRY`; extend the documentation page so a surface carrying `renderer: api_reference`
  dispatches to the registry **regardless of `type`** (the current markdown-only gate is widened for
  this one renderer key), instead of falling into the `code` raw-dump branch.
- **MCP surface:** **out of scope for v1.** MCP "specs" are not OpenAPI; documenting an MCP server
  is a `tools/list`-introspection → generated Markdown catalog flow owned by the skill's
  `mcp-docs.md`. That generated Markdown is an ordinary `type: markdown`, `diataxis: reference`
  surface already handled by the existing pipeline — no new renderer. A future native MCP-catalog
  viewer can be added behind the same registry pattern if demand appears.

## Considered Options

### (a) Embed Scalar standalone over the raw spec — CHOSEN

- Pros: best-in-class try-it API reference UX; offline/local-first (bundle vendored or pinned, no
  external docs site); zero server-side spec→HTML build step; raw spec stays the agent surface and the
  single source of truth; Scalar is already the skill's recommended renderer (Q5), so dashboard and
  guidance agree; fits the renderer-registry extension point with no dashboard refactor.
- Cons: client-side JS bundle (~hundreds of KB) — but loaded only on the API-reference surface, not
  globally; pins a third-party bundle that needs occasional version bumps.

### (b) Link-out to a generated docs site

- Pros: zero dashboard rendering code.
- Cons: breaks the local-first, single-entry-point dashboard model; requires the project to host a
  docs site; nothing to show offline; rejected — defeats the "deepest integration" the user asked for.

### (c) Lightweight native spec viewer component

- Pros: no third-party bundle; full control; smallest footprint.
- Cons: re-implements operation/schema/try-it rendering that Scalar/Redoc already do well; high
  maintenance for a worse result; the dashboard's value is aggregation, not owning an OpenAPI renderer.
  Rejected on Simplicity-First and maintenance grounds.

## Consequences

**Positive:** API specs become rendered reference docs in the same dashboard the rest of the project
lives in; wholesale-regeneration model preserved (builder-side discovery, no hand entries); raw spec
remains canonical + agent-readable; one renderer key + one shell + a bounded builder edit, no dashboard
restructure (Stay Surgical).

**Negative / accepted:** adds a vendored/pinned client bundle to the dashboard (size + version
maintenance); the documentation page's render dispatch grows one branch (markdown-only → "markdown OR
renderer demands registry"); GraphQL SDL gets a new `type: graphql` mapping that, for v1, renders as a
read-only SDL view inside the same shell (Scalar covers OpenAPI/AsyncAPI; SDL falls back to a syntax-
highlighted read view until a GraphQL-native renderer is justified).

**Structural note:** this is a genuine structural addition to the dashboard subsystem (new doc-type +
renderer + spec-discovery walk). It warrants a one-line note in `.ai-state/DESIGN.md` (dashboard
component) and `docs/architecture.md`; the skill/command portion remains additive and does not.

## Prior Decision

Re-affirms `dec-226` (reference tiering) only in spirit — the renderer recommendation
(Scalar) made there for managed projects is the same choice adopted here for the dashboard itself,
keeping skill guidance and dashboard behavior consistent. No supersession.
