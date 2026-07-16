---
id: dec-098
title: Hybrid generated/authored markdown contract via fenced HTML-comment regions
status: re-affirmation
category: configuration
date: 2026-04-30
summary: 'Standardize <!-- aac:generated source=... view=... --> / <!-- aac:authored owner=... --> / <!-- aac:end --> fences in ARCHITECTURE.md and docs/architecture.md, with a small Python validator detecting drift, broken sources, and unbalanced fences. Untagged content is authored-by-default for backward compatibility.'
tags: [aac, dac, markdown, fences, validation, drift-detection, architecture-docs, conventions]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - rules/writing/aac-dac-conventions.md
  - scripts/aac_fence_validator.py
  - skills/software-planning/assets/ARCHITECTURE_TEMPLATE.md
  - skills/doc-management/assets/ARCHITECTURE_GUIDE_TEMPLATE.md
re_affirms: dec-094
re_affirmed_by:
  - dec-100
---

## Context

`.ai-state/ARCHITECTURE.md` and `docs/architecture.md` mix two kinds of content: **structural inventory** (component tables, deployment topology, dependency graphs) that is regenerable from the LikeC4 DSL, and **authored narrative** (rationale, invariants, trade-offs) that the DSL cannot express. Without an explicit contract, two failure modes coexist:

- "Regenerate from model" force-erases authored narrative.
- "Treat as fully authored" loses the SSOT property and drift accumulates silently.

The seed brief and the Idea 2 ideation premise both call for a hybrid contract that lets one document carry both kinds of content while making the boundary mechanically detectable.

## Decision

Adopt a fence-comment convention at the markdown layer. Two fence kinds, one closer:

```markdown
<!-- aac:generated source=<path> view=<view> [last-regen=<iso8601>] -->
... derived content (LikeC4 gen output, rendered table, code block) ...
<!-- aac:end -->

<!-- aac:authored owner=<role-or-username> [last-reviewed=<iso8601>] -->
... authored narrative (rationale, invariants, trade-offs) ...
<!-- aac:end -->
```

**Required attributes:** `source` + `view` on `aac:generated`; `owner` on `aac:authored`. **Optional attributes:** `last-regen` and `last-reviewed` (informational; not enforced by v1's validator but reserved for the future sentinel staleness dimension).

**Backward-compatible default:** untagged content is treated as `aac:authored owner=unspecified`. Legacy `ARCHITECTURE.md` files require zero migration; the contract activates per region as fences are added.

A standalone Python validator (`scripts/aac_fence_validator.py`) provides drift detection:

1. Parse the markdown line-by-line; track fence-open/close balance.
2. For `aac:generated` fences, verify `source=<path>` resolves to an existing file.
3. For `aac:generated` fences, fetch current `likec4 gen` output for the declared `source`+`view`; compare to fenced content (whitespace-normalized); FAIL on mismatch.
4. For `aac:authored` fences, skip content drift (architect-validator and sentinel handle staleness later).
5. Idempotent and side-effect-free: never edits files; running twice produces identical output.

Graceful degradation: when `likec4` is unavailable in the validator's environment, emit a single WARN per fence ("validator-unable-to-verify-drift"), not a FAIL.

A new path-scoped rule `rules/writing/aac-dac-conventions.md` documents the contract; templates in `skills/software-planning/assets/ARCHITECTURE_TEMPLATE.md` and `skills/doc-management/assets/ARCHITECTURE_GUIDE_TEMPLATE.md` ship example fenced regions so future authors see the pattern.

This ADR re-affirms `dec-094` (commit-both DSL+rendered-SVG) by reusing its `<doc-dir>/diagrams/` storage convention as the source path for `aac:generated source=...` fences.

## Considered Options

### Option 1 — No contract (status quo)

**Pros:** Zero engineering effort; freezes existing markdown as-is.

**Cons:** Both failure modes (force-erasure on regen, silent drift on no-regen) persist. Cannot mechanically distinguish derived from authored content. Idea 4 (architect-validator) cannot validate generated regions without a way to identify them.

### Option 2 — Templating engine (Jinja2-style placeholders, separate authored sidecar files)

**Pros:** Strong contract; no ambiguity about generated vs authored regions.

**Cons:** Introduces a new templating runtime as a project dependency. Sidecar files double the file count and break the "one architecture document" property. Markdown renderers do not preview templated content. Heavy abstraction for a behavior that HTML-comment fences solve at zero runtime cost.

### Option 3 — HTML-comment fences (chosen)

**Pros:** HTML comments are already supported by every markdown renderer (GitHub, VS Code, mdbook, Docusaurus). Zero runtime dependency. Backward-compatible (untagged content is authored-by-default). The validator is a small Python script with no side effects. Future tooling (sentinel staleness, doc-engineer) can layer additional checks on the same fences.

**Cons:** A contributor could strip fences "for cleanliness" and break the contract silently. Mitigated by (a) the rule explicitly forbidding strip-for-cleanliness, (b) future Idea 10 sentinel check, (c) PR review.

### Option 4 — JSON sidecar files with markdown imports

**Pros:** Strong contract; fully machine-parseable.

**Cons:** Same drawbacks as Option 2; even more alien to contributors. Rejected.

## Consequences

**Positive:**

- Single document carries both derived structure and authored narrative without conflict.
- Mechanical drift detection on generated regions; silent narrative regions remain editable.
- Zero new runtime dependency (HTML comments already universal in markdown).
- Backward-compatible: legacy `ARCHITECTURE.md` files require no migration.
- The fence convention is the contract surface that the architect-validator agent (separate ADR) layers structural reasoning on top of.

**Negative:**

- Adoption friction during the contract's first quarter: contributors must learn the schema. Mitigated by template updates carrying examples.
- Stripped fences break the contract silently in v1. Mitigated by the rule's "do not strip" clause; the upcoming sentinel AC dimension (deferred to v1.1) will catch stripping at audit time.
- A contributor who accidentally writes `<!-- aac:generated -->` without `source`/`view` produces a malformed fence; validator catches this with a FAIL on attribute parsing.

**Operational:**

- The new rule `rules/writing/aac-dac-conventions.md` is path-scoped to `**/ARCHITECTURE.md`, `docs/architecture.md`, and `**/*.c4` so it does not consume always-loaded token budget.
- The validator script is invoked by (a) the `architect-validator` agent during Phase 3, (b) the verifier's Phase 8.5 fence-integrity sub-check, (c) the doc-engineer's Phase 4 path-existence cross-reference check, and optionally (d) CI as a fitness rule.
- Templates in `ARCHITECTURE_TEMPLATE.md` and `ARCHITECTURE_GUIDE_TEMPLATE.md` ship one designated `aac:generated` region (for the L1 component table) and one designated `aac:authored` region (for the design rationale section) so the convention is visible by example.

## Prior Decision

`dec-094` (commit-both diagram source DSL + rendered SVG; regenerate via repo hook) established `<doc-dir>/diagrams/<name>.c4` as the canonical DSL location. This ADR re-affirms that path convention by adopting it as the `aac:generated source=...` value. If `dec-094` is later superseded with a different storage scheme, the fence schema's `source=` semantics carry over; only the path values change.
