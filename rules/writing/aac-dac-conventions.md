---
paths:
- '**/DESIGN.md'
- docs/architecture.md
- '**/*.c4'
core: false
---

## AaC Fence Convention

The architect-facing design doc (`.ai-state/DESIGN.md`) mixes two kinds of content: regenerable structural inventory (component tables, deployment topology, dependency graphs) derived from a LikeC4 DSL model, and authored narrative (rationale, invariants, trade-offs) that the DSL cannot express. Without an explicit boundary, two failure modes coexist: regenerating from the model silently erases authored narrative; treating the file as fully authored lets structural inventory drift silently. The fence convention makes the boundary mechanically detectable so neither half degrades silently.

## Fence Schema

Two fence kinds, one closer:

```
<!-- aac:generated source=<path> view=<view> [last-regen=<iso8601>] -->
... derived content (LikeC4 gen output, rendered table, SVG embed) ...
<!-- aac:end -->

<!-- aac:authored owner=<role-or-username> [last-reviewed=<iso8601>] -->
... authored narrative (rationale, invariants, trade-offs) ...
<!-- aac:end -->
```

**Required attributes:**
- `source` and `view` on `aac:generated` — path to the `.c4` source file and the view name to render.
- `owner` on `aac:authored` — role or username responsible for the narrative.

**Optional attributes:**
- `last-regen` on `aac:generated` — ISO 8601 timestamp of the last regeneration (informational; reserved for future staleness checks).
- `last-reviewed` on `aac:authored` — ISO 8601 timestamp of the last review (informational; reserved for future staleness checks).

**Closer:** `<!-- aac:end -->` closes both fence kinds. Every opener must have a matching closer; unbalanced fences are a validator FAIL.

**Worked example:**

```markdown
<!-- aac:generated source=docs/diagrams/system.c4 view=L1Components last-regen=2026-04-30T12:00:00Z -->
| Component | Responsibility |
|-----------|---------------|
| API Gateway | Route and authenticate requests |
<!-- aac:end -->

<!-- aac:authored owner=systems-architect last-reviewed=2026-04-30 -->
## Design Rationale

The gateway layer was chosen over per-service auth to centralize credential rotation.
<!-- aac:end -->
```

## Untagged Content Default

Untagged content (no fence) is treated as `aac:authored owner=unspecified`. Legacy architecture markdown files require zero migration; the contract activates per region as fences are added.

## Do Not Strip Fences

The fence comments are the contract surface that the validator and the architect-validator agent reason over. Stripping fences "for cleanliness" silently breaks drift detection. If a generated region is no longer needed, **delete the entire region — opener, content, and closer** — rather than removing only the fence comments and leaving the content behind.

## Authoring Workflow

- Author writes prose inside `aac:authored` fences (design rationale, trade-offs, invariants).
- Author runs `likec4 gen` (or the project's diagram regen hook) to refresh `aac:generated` regions; the validator detects when those regions are stale relative to their declared `source` and `view`.
- On PR, the architect-validator agent reads the fences and reports drift in `ARCHITECTURE_VALIDATION.md`.

## Validator

`scripts/aac_fence_validator.py` is the canonical check. It is stdlib-only, idempotent, and side-effect-free: it never edits files, and running it twice on the same input produces identical output. When `likec4` is unavailable in the validator's environment, it emits one WARN per `aac:generated` fence rather than failing. For the full CLI interface, run `python scripts/aac_fence_validator.py --help`.

## Override Syntax

When an editor must legitimately modify a generated artifact (a rendered `.d2`/`.svg` or content inside an `aac:generated` fence) without staging the corresponding source change, a line-adjacent override comment justifies the change. The comment captures the reason in one line so reviewers and future agents can audit whether the hand-edit was warranted.

**Code, D2, YAML, and shell files** (any file where `#` is the comment character):

```
# aac-override: <non-empty-reason>
```

**SVG, HTML, and Markdown files:**

```
<!-- aac-override: <non-empty-reason> -->
```

**Line-adjacency rule**: the override comment must appear on the same line as the change, or on the line immediately above it. A comment two or more lines above the change does not count.

**Reason requirement**: the reason must be non-empty — at least one non-whitespace token after the colon and space. An override with an empty or whitespace-only reason is treated as absent.

Enforcement: `scripts/check_aac_golden_rule.py --mode=gate` (wired into the pre-commit hook Block D) gates every commit that touches architectural surfaces. The same script in `--mode=audit` is consumed by the sentinel EC dimension for historical drift analysis.
