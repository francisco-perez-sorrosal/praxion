---
description: Scaffold best-in-class API documentation for a project's own API surface — detects language/protocol/surface, scaffolds the Diátaxis skeleton + Spectral ruleset + CI gate, idempotent (skip-or-merge, never clobbers authored content)
argument-hint: "[path] [--lang python|typescript] [--surface rest|graphql|mcp|library|asyncapi|grpc]"
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash(find:*), Bash(ls:*), Bash(cat:*), Bash(head:*), Bash(grep:*), Bash(test:*), Bash(python3 scripts/build_doc_manifest.py:*), AskUserQuestion, Task]
disable-model-invocation: true
---

Scaffold documentation for the **current project's own API surface** so both humans and AI agents can consume it. This command operationalizes the `api-documentation` skill: it detects what kind of API the project exposes, confirms with you, then drops a Diátaxis doc skeleton, a Spectral ruleset, and a lint→diff→contract-test CI gate. It never invents the methodology — **load the `api-documentation` skill** when this command runs; that skill governs content quality, this command governs the scaffold.

This is a scaffolding action, not an auto-wire. It is the deliberate counterpart to `/onboard-project` (whose Phase 8 only *points* here). Re-running is safe.

## Inputs

- **`$1` (optional)** — target project path. Defaults to the current working directory.
- **`--lang`** — override language auto-detection (`python`, `typescript`).
- **`--surface`** — override protocol/surface auto-detection (`rest`, `graphql`, `mcp`, `library`, `asyncapi`, `grpc`). Repeatable for multi-surface projects.

When overrides are given, skip the matching detection probe and trust the override; still report what was assumed.

## Process

### 1. Load the skill

Load the `api-documentation` skill before doing anything else. Its Universal Core (two doc surfaces, spec-as-source-of-truth, human-vs-agent divergence, mandatory sections, docs-as-CI-artifact, Diátaxis↔AaC fences) is the contract the scaffold encodes. Route per-surface depth through its Reference Routing table.

### 2. Detect the surface(s)

Probe the target path (read-only — no writes yet). Skip any probe whose dimension was supplied via `--lang`/`--surface`.

**Language** — `pyproject.toml` / `setup.py` → Python; `package.json` → TypeScript/Node.

**Protocol / service surface** — in priority order:
- Existing committed spec: `openapi.{json,yaml}`, `asyncapi.{json,yaml}`, `*.proto`, GraphQL SDL (`*.graphql` / `*.graphqls`) → that protocol, spec already present.
- Code-first emitters via imports/deps: FastAPI / `tsoa` / NestJS / `zod-to-openapi` → REST (spec generated from code); `strawberry` / `graphql` / Apollo → GraphQL.

**MCP surface** — an `mcp` dependency, a `FastMCP(`/`Server(` server definition, or a discoverable `tools/list` introspection target → MCP server surface.

**Library surface** — a public package API: `__init__.py` with a non-trivial public surface (Python) or a package `index.ts` / `exports` map (TypeScript) → library docs (docstring/type-signature sourced).

A project may match **several** surfaces (e.g. a Python library that also exposes a REST service and an MCP server). Collect all of them.

### 3. Report and confirm (no silent action)

Print the detected language and surface(s) — what was found, where (the file that triggered each detection), and what will be scaffolded for each. Then use `AskUserQuestion` to confirm before any write. Offer the user the chance to add or drop a surface (their override wins over detection). **Never scaffold without confirmation** — detection misfires on unusual layouts, and this is the guardrail.

### 4. Scaffold (idempotent)

For each confirmed surface, copy the matching subtree from the skill's `assets/api-docs-skeleton/` into the project's docs location (e.g. `docs/api/` or the project's existing docs root), and:

- **Substitute real spec paths for the `source=<spec>` placeholders.** The skeleton's `aac:generated source=<spec>` fences carry a `<spec>` placeholder; replace `<spec>` with the project's actual committed spec path (e.g. `source=openapi.yaml`). This resolves the template placeholder so the scaffolded reference docs pass the AaC live-source gate. For a library surface, point the generated fence at the docstring/type source per the skill's `python.md` / `typescript.md` guidance.
- **Drop `assets/spectral-ruleset.yaml`** into the project (REST/OpenAPI surfaces) so the lint step has a ruleset.
- **Drop `assets/ci-snippet.yml`** as the lint → breaking-change diff → contract-test gate.
- **Cross-link, do not duplicate.** For a multi-surface project, scaffold each surface once and cross-link them (the skill's two-doc-surface rule). Never triplicate the same content across surfaces — the user navigates one surface; links bridge to the others.

### 5. Idempotency — skip-or-merge, never clobber

Before writing each file, check whether it already exists:

- **Authored content present** (an `aac:authored` region with real prose, a hand-edited tutorial/quickstart) → **skip it**, never overwrite. Report it as "already present, left untouched."
- **Generated/placeholder region** (`aac:generated source=<spec>` with the `<spec>` still unresolved, or an unmodified skeleton stub) → safe to re-resolve the `source=` path or refresh the stub.
- **Spectral ruleset / CI snippet already present** → skip; report it.

At the end, print a summary of what was created, what was skipped (and why), and what was merged. A re-run on an already-scaffolded project must be a no-op that simply reports the existing state.

### 6. Registration — do NOT hand-write a manifest entry

The doc manifest builder (`scripts/build_doc_manifest.py`) **auto-discovers** API-spec surfaces (`openapi.*`, `asyncapi.*`, `*.graphql`) and emits their descriptors itself. A hand-written `doc_manifest.yaml` entry would be **clobbered** the next time the builder runs (it regenerates the manifest wholesale). So:

- Do **not** add a `doc_manifest.yaml` entry by hand.
- Instead, run `python3 scripts/build_doc_manifest.py` after committing the spec — the manifest is regenerated **manually**, not by an automatic hook; sentinel **F11** flags the manifest as stale (advisory) when its `generated_at` predates a later commit touching indexed surfaces, so a missed regen is detected, not silent. The builder picks up the committed spec and registers it with `renderer: api_reference`, `diataxis: reference`, in the `api-reference` group.

### 7. Hand off and point to depth

Close with pointers, not inlined methodology:

- For **content** depth — the loaded `api-documentation` skill and its per-surface references.
- For **MCP tool design** questions that surface during documentation (naming, schema, fat-vs-thin, error grammar) — route to `agentic-interface-design`. This command and the `api-documentation` skill *document* an existing MCP server; they do not *design* its tools.
- Mechanical, high-volume doc generation may be delegated to the `doc-engineer` agent (via `Task`); detection and scaffolding judgment stay inline here.

## Notes

- Detection reports findings and confirms before scaffolding — there is no silent write path.
- The scaffold is additive and idempotent; re-running reports existing artifacts rather than duplicating or clobbering them.
- The methodology lives in the `api-documentation` skill — this command is the bootstrap, not the source of truth.
