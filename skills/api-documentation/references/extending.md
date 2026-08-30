# Extending: Add-a-Surface Pattern

Documenting an API surface the core six references don't cover — gRPC/protobuf, Go, Rust, AsyncAPI, or anything else. Back to [SKILL.md](../SKILL.md).

This reference does two things:

1. Gives you a **reusable, surface-agnostic pattern** for documenting any API surface — instantiating the universal core's checklist for a surface that has no dedicated reference yet.
2. Ships **seeded inline sections** for three surfaces (gRPC/protobuf, Go, AsyncAPI) — each a standard toolchain + one canonical source + minimal setup. These are intentionally shallow; the pattern is what makes them extensible. Rust has outgrown its stub — see [`rust.md`](rust.md).

**Honesty about depth**: the three seeded sections below are *starting points*, not exhaustive treatments. Each names the dominant toolchain, the docstring/annotation convention, and the minimal command — enough to get a project documenting that surface correctly. They are not as deep as `rest-openapi.md` or `python.md`. When a project leans hard on one of these surfaces, the obvious place to deepen is to **promote that section into its own `references/<surface>.md`** (mirroring the structure of the existing six) and add a Reference Routing row in `SKILL.md`. That promotion is the one canonical extension point — don't fork the pattern; instantiate it.

---

## The Add-a-Surface Pattern

Every API surface — no matter the protocol or language — is documented by answering the same five questions. This is the universal core (SKILL.md items 1–7) made operational for a surface you're adding. Walk it top to bottom:

### 1. Pick the spec source (what is canonical?)

Decide which artifact is the **source of truth** for the wire/code contract, per core item 2. Two shapes:

- **The spec *is* the doc** — the contract artifact carries descriptions natively and renders to docs directly (GraphQL SDL, AsyncAPI YAML, protobuf `.proto`). Document *in* the artifact; the renderer surfaces it.
- **The spec is *derived*** — docstrings/annotations in code generate the contract (Go doc comments → pkgsite; Rust `///` → rustdoc). The code is canonical; the rendered site is a projection.

Either way, the artifact must be **committed, CI-validated, and drift-checked** (core item 2). The authoring direction (spec-first vs code-first) is a non-issue *as long as the committed artifact is the one CI lints and diffs*.

### 2. Pick the doc tool (how is it rendered?)

Choose the **standard generator** for the surface — the one the ecosystem already converges on. Resist novelty: a well-known generator with broad tooling beats a clever one. Prefer a generator that:

- consumes the spec source from step 1 directly (no re-authoring),
- emits both a human-rendered site **and** keeps the raw spec available at a stable URL (core item 3 — the raw spec *is* the agent surface),
- runs in CI without a hosted-service dependency where possible.

The seeded sections below name the default per surface.

### 3. Pick the docstring/annotation convention + lint it

Pick **one** docstring or annotation style for the surface and **enforce it** (core: agent-metadata discipline). Mixed styles degrade every generator. Each surface has a native convention (Go doc comments, Rust Markdown doc comments, protobuf leading `//` comments, GraphQL `"""..."""`). Lint it in CI — a linter that fails on a missing description or example is your doc-coverage proxy.

The four agent-metadata fields from the core (stable identifier, one-line summary, precondition-stating description, ≥1 example) map onto every surface: a gRPC method's leading comment, a Go function's doc sentence, a Rust item's `///` block, an AsyncAPI message's `summary`/`description`.

### 4. Wire deprecation

Every surface has a **native deprecation mechanism** — use it, and document the replacement + removal timeline (not just the flag):

| Surface | Mechanism |
|---------|-----------|
| protobuf | `option deprecated = true;` on fields/methods/messages |
| Go | `// Deprecated:` paragraph in the doc comment |
| Rust | `#[deprecated(since = "...", note = "...")]` attribute |
| AsyncAPI | `deprecated: true` on the channel/operation/message |
| GraphQL | `@deprecated(reason: "...")` directive |
| OpenAPI | `deprecated: true` + `Sunset` header on the live endpoint |

A deprecation without a documented replacement and removal date is a documentation bug.

### 5. Make docs a CI artifact

Wire the surface's equivalent of the core's `lint → breaking-change diff → contract-test` gate (core item 5):

- **Lint** the spec/doc-comments against a ruleset requiring descriptions, examples, and metadata.
- **Diff** the committed spec against its prior version to flag breaking changes before merge (Buf for proto, GraphQL Inspector for SDL, oasdiff for OpenAPI/AsyncAPI-as-OpenAPI).
- **Contract-test** or doctest so the live surface and the spec cannot silently diverge (Rust doctests are the cleanest example — examples that fail to compile fail CI).

Freshness is then a pipeline byproduct, not a manual chore. The failure mode to guard against is a code-first artifact that is generated but never re-committed.

---

## Seeded Surface Sections

Each section: **standard toolchain · docstring/annotation convention · one canonical source · minimal setup.** Shallow by design — see the honesty note at the top.

### gRPC / Protobuf

- **Toolchain**: `protoc-gen-doc` (HTML/Markdown/JSON from `.proto`) for static docs; **Buf** (`buf`) for lint + breaking-change detection, and the hosted **Buf Schema Registry (BSR)** which auto-generates docs on push.
- **Convention**: leading `//` comments on services, methods, messages, and fields become the docs. One comment block per element; first sentence is the summary.
- **Spec link**: the `.proto` *is* the contract. Buf diffs it for breaking changes — the RPC analog of GraphQL Inspector / oasdiff.
- **Deprecation**: `option deprecated = true;`.
- **Minimal setup**: add a `protoc-gen-doc` plugin entry to `buf.gen.yaml` and run `buf generate`; or push to BSR for hosted docs. Gate CI with `buf lint` + `buf breaking --against '.git#branch=main'`.
- **Canonical source**: https://buf.build/docs

### Go

- **Toolchain**: `go doc` / **pkgsite** (the engine behind pkg.go.dev) — zero-config, built into the toolchain. `golang.org/x/pkgsite/cmd/pkgsite` runs a local docs server.
- **Convention**: doc comments are plain sentences immediately above the declaration, starting with the identifier name (`// Marshal returns the JSON encoding of v.`). No tags, no markup language — gofmt-style doc comments. `gofmt` and `go vet` keep them well-formed.
- **Spec link**: pkgsite covers the **library** surface only. A Go service's wire contract still comes from a separate OpenAPI/proto spec — document that surface via `rest-openapi.md` or the gRPC section above, and cross-link.
- **Deprecation**: a `// Deprecated:` paragraph in the doc comment; tools strike the symbol through.
- **Minimal setup**: write doc comments; run `go doc ./...` or `pkgsite -open`.
- **Canonical source**: https://go.dev/doc/comment

### Rust

Rust now has a dedicated reference — see [`rust.md`](rust.md) for rustdoc
structure, the `# Errors`/`# Panics`/`# Safety` named-heading contract,
doc-tests as executed contracts (`should_panic`/`no_run`/`compile_fail`),
C-QUESTION-MARK, `#[deprecated]`, and the `cargo test --doc` CI gate
(including the nextest interaction).

### AsyncAPI / Event-Driven

- **Toolchain**: **AsyncAPI Generator** (`@asyncapi/generator`) + **AsyncAPI Studio** — the OpenAPI equivalent for message/event-driven APIs (Kafka, MQTT, WebSocket, AMQP).
- **Convention**: an `asyncapi.yaml` document describes channels, messages, and payload schemas (JSON Schema). `description`/`summary`/`deprecated` fields per element — the same agent-metadata discipline as OpenAPI operations.
- **Spec link**: AsyncAPI *is* the spec — it is canonical, like an OpenAPI document. The builder discovers `asyncapi.{yaml,json}` and renders it as an `api_reference` surface, identical to OpenAPI.
- **Deprecation**: `deprecated: true` on the channel/operation/message.
- **Minimal setup**: write `asyncapi.yaml`; `asyncapi generate fromTemplate asyncapi.yaml @asyncapi/html-template`. Lint with the AsyncAPI CLI (`asyncapi validate`) in CI.
- **Canonical source**: https://www.asyncapi.com/docs

---

## When You've Outgrown a Stub

If a project's docs lean heavily on one of these surfaces — or on a surface not listed at all — the pattern stays the same; only the depth changes. Promote the stub:

1. Create `references/<surface>.md` mirroring the six core references (the same surface-agnostic pattern, instantiated deeply).
2. Add a Reference Routing row in [SKILL.md](../SKILL.md) so the new reference is discoverable.
3. Leave a one-line pointer here in `extending.md` ("`<surface>` now has a dedicated reference: `references/<surface>.md`").

The five-question pattern at the top is the durable artifact. The seeded sections are scaffolding for the surfaces we haven't yet needed to treat deeply.
