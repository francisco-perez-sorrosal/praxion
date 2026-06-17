# REST / OpenAPI Documentation Pipeline

The OpenAPI 3.1 doc pipeline: spec-as-truth, lint → breaking-change diff → contract-test, renderer choice, mandatory doc structure, and CI publishing. Back to [SKILL.md](../SKILL.md).

This reference expands core items 2–5 of the [universal core](../SKILL.md#the-universal-core) for a REST surface with an OpenAPI spec. Tool versions named below are **defaults, not pins** — verify the current release before adopting; the recommendation (which tool, which trade-off) is stable, the version drifts.

## 1. Spec Is the Truth — Spec-First vs Code-First

OpenAPI **3.1** is the settled baseline (full JSON Schema 2020-12 alignment). Treat **one OpenAPI document as the single source of truth** from which reference docs, SDKs, mocks, and contract tests are all generated — this is the central lever against drift.

The authoring direction is a non-issue **as long as the spec is canonical**:

| Direction | What it is | When | Invariant |
|-----------|-----------|------|-----------|
| **Spec-first** (design-first) | Author the spec before/independent of code | Public, versioned, cross-team APIs; enables mocking + parallel client/server dev. The consensus "best-practice" direction. | Spec is the artifact by construction |
| **Code-first** | Derive the spec from code annotations/types (FastAPI, django-ninja, Litestar, tsoa, springdoc) | Small/internal APIs, rapid iteration | Acceptable **only if** the generated spec is committed, linted, and contract-tested in CI — otherwise it silently drifts |

The universal rule is **"committed, linted, drift-checked spec,"** not "hand-author YAML." This keeps guidance language-agnostic. The failure mode to guard against is a code-first spec that is generated but never regenerated/committed.

## 2. The CI Gate — Lint → Diff → Contract-Test

The minimal pipeline that keeps the spec honest:

```
lint  →  breaking-change diff  →  contract-test
```

### Lint

Validate the spec against a ruleset on every change; fail the build on errors.

| Linter | Lang | Notes |
|--------|------|-------|
| **Spectral** (Stoplight) | Node | De-facto standard; most flexible custom rulesets; largest ecosystem. Slower on large specs. **Default for ruleset familiarity.** |
| **Vacuum** (daveshanley) | Go | ~3× faster than Redocly, much faster than Spectral; 100% Spectral-ruleset compatible; OpenAPI 3.0/3.1/3.2; stricter defaults. **Default when spec size / CI speed matters** (drop-in, same rulesets). |
| **Redocly lint** | Node | `redocly.yaml` config (error/warn/off); faster than Spectral but shares its scaling ceiling; integrated with the Redocly toolchain. |

Ship a **baseline ruleset** requiring: `operationId`, `summary`, `description`, request/response `examples`, documented error responses, and `tags` on every operation. This ruleset is also the practical **doc-coverage proxy** — there is no single canonical coverage tool; lint rules are the mechanism. (Scoring tools like RateMyOpenAPI exist but are advisory.) Linting is universal; the specific ruleset content is progressive-disclosed per project maturity.

### Breaking-change diff

Diff the spec against the prior committed spec to flag breaking changes **before merge**.

- **oasdiff** (Go) — detects 100+ breaking-change classes across ERR/WARN tiers; runs as CLI / GitHub Action / commit-status check. Reviewers approve or reject each flagged change.

### Contract-test

Verify the live API and the spec cannot silently diverge.

- **Schemathesis** — property-based; generates test cases directly from the spec. Any deviation fails the build.
- **Dredd** — alternative; transaction-based validation against the spec.

Pattern: commit the spec; in CI regenerate-or-validate it from the implementation, contract-test, and diff against the previous spec to block accidental breaking changes.

## 3. Rendering — Pick the Human Surface

The renderer choice is **progressive-disclosed** (project/host-specific). The one universal rule: **publish the raw spec at a stable, versioned URL** alongside whatever is rendered — that raw spec *is* the agent-consumable surface (see [`agent-consumable.md`](agent-consumable.md)). Renderer choice matters mainly for humans.

| Tool | Style | Try-it | Notes |
|------|-------|--------|-------|
| **Scalar** | Modern 3-panel + built-in API client | Yes (built-in client) | Lightest despite most features; actively growing. **Emerging default for new projects.** |
| **Redoc / Redocly** | Clean read-only 3-panel | OSS Redoc: no; Redocly (paid): yes | Beautiful read-only brand-controlled docs; mature. |
| **Swagger UI** | Classic interactive | Yes | Reference implementation; ubiquitous but dated UX. **Safe zero-risk fallback, no longer the new-project default.** |
| **Stoplight Elements** | Embeddable component | Yes | Momentum risk post-SmartBear acquisition. |
| **RapiDoc** | Web-component, single-file | Yes | Lightweight embed; smaller community. |
| **Docusaurus + OpenAPI plugin** | Docs site + reference | Plugin-dependent | Best when reference must live inside a broader docs site. |

**Recommended defaults (hedged):**
- New project (2025–2026): **Scalar** — polished UX, built-in try-it, low maintenance, single package.
- Read-only public reference, brand-controlled: **Redoc / Redocly**.
- Reference inside a larger docs site: **Docusaurus + OpenAPI plugin** (or a Scalar embed).
- Universal regardless of choice: **raw spec at a stable URL**.

## 4. Doc Structure — Diátaxis Applied to APIs

Map Diátaxis's four modes onto API docs, and wrap each section in the matching AaC fence (core item 6):

| Diátaxis mode | API mapping | Content |
|---------------|-------------|---------|
| **Tutorial** | Quickstart / Getting-started | Shortest path to a first successful authenticated call; assumes no prerequisite knowledge |
| **How-to** | Task recipes | "authenticate," "paginate a list," "handle rate limits," "verify a webhook," "migrate vN → vN+1" |
| **Reference** | The generated OpenAPI render | Information-oriented, exhaustive, generated from the spec — never hand-edited |
| **Explanation** | Concepts | Auth model, idempotency, versioning policy, pagination rationale |

### Mandatory sections (universal)

1. **Quickstart** — auth + first call, copy-pasteable.
2. **Authentication** — schemes, obtaining/rotating credentials, header/signature format.
3. **Reference** — generated from the spec.
4. **Error / status-code catalog** — **RFC 9457 `application/problem+json`** (`type`, `title`, `status`, `detail`, `instance`, + extensions). RFC 9457 supersedes RFC 7807; use stable `type` URIs and document each as a browsable catalog (IANA + SmartBear problem-type registries are reference sources).
5. **Pagination** — state the model explicitly. Cursor is preferred at scale (offset has O(N) scan cost); never assume the reader knows the cursor mechanics.
6. **Rate limits** — limits, headers returned (`Retry-After`), retry/back-off behavior.
7. **Changelog + versioning + deprecation** — see §6.

A missing section is a documentation bug. The Diátaxis structure and the section list are universal; auth-scheme specifics and error-catalog content are per-API.

## 5. Examples, Code Samples, Try-It

- **Request/response examples** — attach `examples` to spec components/operations; the linter ruleset should *require* them. The generated reference renders them automatically.
- **Multi-language code samples** — the **`x-codeSamples`** OpenAPI extension (formerly `x-code-samples`) is the widely-supported standard; Redoc and Scalar display them in the right panel.
- **Generated, in-sync SDK snippets (preferred over hand-written)** — **Speakeasy** and **Fern** generate SDKs *and* matching code samples from one spec, push a code-samples overlay (e.g. `code-samples.yaml`) back into the document, and regenerate on every spec change via CI. This is the key anti-drift property: snippets stay aligned with real SDK logic. Hand-written samples are acceptable only for small/internal APIs.
- **Runnable / try-it** — Scalar (built-in client) and Swagger UI execute in-page; pair with a hosted mock generated from the spec so try-it works before/without a live backend.

`x-codeSamples` and "require examples" are universal; the SDK-generator choice is progressive-disclosed (it adds a hosted-service dependency).

## 6. Publishing, Versioning, Deprecation

- **Spec lives in-repo**, versioned with the code; the docs site is generated *from* it — single source, no separate doc repo to drift.
- **CI generation** — any spec change triggers lint → diff → regenerate reference + SDKs + snippets → deploy.
- **Preview-on-PR** — deploy a docs preview per PR so reviewers see rendered changes (standard with Redocly, Bump.sh, Scalar, Fern, Mintlify, Docusaurus + Netlify/Vercel).
- **Versioned docs** — publish per major version; keep prior versions live during the deprecation window. Publish the **raw spec** at a stable, versioned URL for agent consumption.

**Settled deprecation conventions:**
- Version from day one (`/v1/`); maintain backward compatibility within a version.
- Breaking change → new version + **migration guide**.
- **`Sunset` header** + documented timeline; a common pattern is a ~12-month window (announce → email → response-body warnings → throttle → `410 Gone`).
- Changelog as a checklist: version + date, breaking changes (called out separately), new endpoints, deprecated endpoints with hard sunset dates, auth/rate-limit changes.

CI publish, PR preview, and versioned docs are universal patterns; the specific host (Vercel / Netlify / Redocly / Bump.sh) is progressive-disclosed.

## Recommended Defaults (summary)

| Concern | Default | Strong alternative |
|---------|---------|--------------------|
| Canonical artifact | OpenAPI **3.1**, committed in-repo | — |
| Authoring direction | Spec-first; code-first allowed if spec is committed + CI-validated | — |
| Linter | **Spectral** (ecosystem) | **Vacuum** (speed/scale, Spectral-compatible) |
| Breaking-change gate | **oasdiff** in CI | — |
| Contract test | **Schemathesis** | Dredd |
| Renderer (new project) | **Scalar** | Redoc/Redocly; Swagger UI (fallback) |
| Error format | **RFC 9457 problem+json** + documented `type` catalog | — |
| Pagination | Cursor (scale); document the model explicitly | Offset (simple/small) |
| Code samples | Generated via **Speakeasy/Fern** + `x-codeSamples` | Hand-written (small/internal only) |
| Deprecation | `Sunset` header + migration guide + ~12-mo window | — |

**Contested vs settled.** *Settled:* OpenAPI 3.1 baseline; spec-as-source-of-truth; RFC 9457 errors; lint + diff + contract-test in CI; `x-codeSamples`. *Contested/evolving:* spec-first vs code-first (converging on "committed spec regardless"); best renderer (Scalar rising vs Swagger UI incumbency); generated vs hand-written samples for small APIs.

## Sources

- [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html) — canonical error format
- [Swagger: Problem Details (RFC 9457) — Doing API Errors Well](https://swagger.io/blog/problem-details-rfc9457-doing-api-errors-well/) — practical guidance + registries
- [Diátaxis — Reference](https://diataxis.fr/reference/) — doc-structure model
- [Vacuum — about](https://quobix.com/vacuum/about/) / [daveshanley/vacuum](https://github.com/daveshanley/vacuum) — Go linter, Spectral-compatible
- [API Linting: Vacuum vs Spectral vs Redocly (CloudAPPi)](https://cloudappi.net/en/vacuum-spectral-redocly-linter-apis-en/) — performance/strictness
- [oasdiff — breaking-change detection](https://www.oasdiff.com/) / [oasdiff/oasdiff](https://github.com/oasdiff/oasdiff) / [oasdiff-action](https://github.com/oasdiff/oasdiff-action)
- [Scalar vs Swagger UI vs Redoc 2026 (APIScout)](https://apiscout.dev/guides/scalar-vs-swagger-ui-vs-redoc-2026) — renderer comparison
- [Best API Documentation Tools 2025 (DEV)](https://dev.to/_d7eb1c1703182e3ce1782/best-api-documentation-tools-for-developers-in-2025-swagger-redoc-scalar-and-more-3d7g) — renderer landscape
- [Speakeasy: x-codeSamples](https://www.speakeasy.com/openapi/guides/x-codesamples) / [Generate code samples](https://www.speakeasy.com/docs/sdk-docs/code-samples/generate-code-samples) — code-sample overlay pattern
- [Fern: API documentation best practices](https://buildwithfern.com/post/api-documentation-best-practices-guide) — SDK + docs generation, CI publish
- [API Deprecation Strategy: Sunset Headers (Codelit)](https://codelit.io/blog/api-deprecation-strategy) — deprecation timeline + Sunset header
