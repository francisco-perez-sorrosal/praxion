# Diátaxis Modes for Architecture Documentation

[Diátaxis](https://diataxis.fr/) is a documentation framework that classifies content by reader intent into four modes: Tutorial (learning by doing), How-to (solving a specific problem), Reference (authoritative information lookup), and Explanation (understanding the rationale). For architecture documents at Praxion, each mode pairs with a default fence kind from the AaC fence convention in `rules/writing/aac-dac-conventions.md`. Choosing the correct fence makes regenerability intent explicit and prevents two silent failure modes: authored narrative placed inside `aac:generated` fences (where the validator will eventually seek a source to diff against), and regenerable inventory placed inside `aac:authored` fences (where drift from the LikeC4 model goes unchecked).

Back to [`../SKILL.md`](../SKILL.md).

---

## The Four Modes

### Tutorial

**Reader intent.** The reader is learning a concept or workflow by working through a structured exercise.

**Default fence kind.** `aac:authored` — tutorial content is curated pedagogical narrative; code samples are illustrative stepping stones, not a stable output regenerable from any source-of-truth model.

**Common pitfalls:**
- Placing tutorial prose inside `aac:generated` fences — the fence contract requires a `source=` and `view=` that the validator can diff against. A tutorial has no such source; the validator will fail on every check.
- Mixing tutorial steps with reference tables in the same fenced region — split them so each region carries a single intent.
- Marking tutorial code samples as generated — even if drawn from a working example, tutorial snippets are chosen for clarity, not completeness; they are authored selections, not regenerated output.

**Worked example:**

```markdown
<!-- aac:authored owner=systems-architect last-reviewed=2026-04-30 -->
## Walkthrough: Adding a New Service to the Model

1. Open `docs/diagrams/system.c4` and locate the `container` block for the API layer.
2. Add a new `component` declaration inside that block.
3. Run `bash scripts/diagram-regen-hook.sh` to regenerate the SVG views.
<!-- aac:end -->
```

---

### How-to

**Reader intent.** The reader has a specific goal and needs a reliable recipe to accomplish it.

**Default fence kind.** `aac:authored` for procedure prose — How-to recipes are human-curated step sequences. Embedded code or CLI examples that are sourced from a script or config file may use `aac:generated` for those specific snippets when they are literally regenerated from a declared source.

**Common pitfalls:**
- Burying "why we chose this approach" rationale inside a How-to — that content belongs in an Explanation region, not here. A How-to answers "how", not "why".
- Using `aac:generated` for the entire How-to section because it contains one generated snippet — fence individual snippets, not the whole procedure.
- Omitting `source=` and `view=` on the `aac:generated` inner fence — the validator requires both attributes; a generated fence without them is a FAIL.

**Worked example:**

```markdown
<!-- aac:authored owner=doc-engineer last-reviewed=2026-04-30 -->
## How to Regenerate Architecture Diagrams

Run the diagram hook after editing any `.c4` source file:

    bash scripts/diagram-regen-hook.sh

Commit both the `.c4` source and the regenerated `.d2`/`.svg` files together.
<!-- aac:end -->
```

---

### Reference

**Reader intent.** The reader needs an authoritative, complete listing — a component table, deployment topology, API surface, configuration option list, or dependency matrix.

**Default fence kind.** `aac:generated` — reference content derives from a source-of-truth model (LikeC4 `.c4` file, code, or config) and must stay in lockstep with it. The validator drift-checks `aac:generated` regions against their declared `source=` and `view=`; any silent model change surfaces as a FAIL on the next check.

**Common pitfalls:**
- Writing rationale or design narrative inside a Reference region — rationale belongs in Explanation (`aac:authored`). A Reference region that also contains "why we designed it this way" text will be partially erased when the generator next regenerates the content.
- Treating a component table as `aac:authored` because it was hand-written initially — if that table is meant to reflect the LikeC4 model, it must be `aac:generated` so drift is detected.
- Omitting `last-regen=` — while optional, it gives human reviewers and the staleness-check tooling a regeneration timestamp.

**Worked example:**

```markdown
<!-- aac:generated source=docs/diagrams/system.c4 view=L1Components last-regen=2026-04-30T12:00:00Z -->
| Component | Responsibility |
|-----------|---------------|
| API Gateway | Route and authenticate requests |
| Auth Service | Issue and validate session tokens |
| Notification Worker | Send async email and push notifications |
<!-- aac:end -->
```

---

### Explanation

**Reader intent.** The reader wants to understand the reasoning behind a design — the trade-offs, constraints, historical context, and alternatives considered.

**Default fence kind.** `aac:authored` — design rationale cannot be derived from any source-of-truth model. The validator has no target to diff against; there is no regeneration step that could produce a correct "why". This content is always human-authored and must be protected from accidental regeneration.

**Common pitfalls:**
- Placing inventory tables inside an Explanation region — if a region labelled "Design Rationale" contains a component count table, the table will not be drift-checked. Move it to a separate `aac:generated` Reference region.
- Using `aac:generated` for a region labelled "Architecture Decisions" — decision text is not generated from the LikeC4 model; giving it a generated fence causes the validator to seek a non-existent source and fail.
- Conflating ADR content with inline Explanation — Explanation in `.ai-state/DESIGN.md` summarises the decision; the ADR file at `.ai-state/decisions/<NNN>-<slug>.md` is the full record. Keep Explanation concise and link to the ADR.

**Worked example:**

```markdown
<!-- aac:authored owner=systems-architect last-reviewed=2026-04-30 -->
## Why a Gateway Layer

The API Gateway was chosen over per-service auth to centralise credential rotation.
Rotating a secret in one place is safer than synchronising rotation across N services.
The trade-off is a single point of failure at the network boundary, mitigated by
running the gateway behind a load balancer with automated failover.
<!-- aac:end -->
```

---

## Canonical Mapping Table

| Mode | Reader intent | Default fence | Why |
|------|---------------|---------------|-----|
| Tutorial | Learning by doing | `aac:authored` | Curated narrative; illustrative samples have no regenerable source |
| How-to | Solving a specific problem | `aac:authored` (with `aac:generated` for embedded code/CLI examples when sourced) | Recipe prose is human-curated; only inline sourced snippets qualify as generated |
| Reference | Authoritative information lookup | `aac:generated` | Inventory facts derive from a source-of-truth (LikeC4 model, code, or config) and must stay in lockstep |
| Explanation | Understanding rationale | `aac:authored` | Design rationale cannot be derived from any source; no regeneration target exists |

---

## How the Modes Pair with the AaC Fence Convention

**Fence kind is mechanical; mode is intent.** The `aac_fence_validator.py` script does not know which Diátaxis mode a region belongs to — it only checks that `aac:generated` regions stay in lockstep with their declared `source=` and `view=` attributes, and that `aac:authored` regions carry a valid `owner=` attribute. Choosing the fence kind is the author's responsibility. The Diátaxis mode is the intent that justifies that choice: Reference content gets `aac:generated` because it has a regeneration target; Tutorial, How-to, and Explanation content gets `aac:authored` because no regeneration target exists for narrative, recipes, or rationale.

**Mixed-mode content must be split.** A section that combines reference-style inventory (a component table) with explanation-style rationale (why those components exist) must be split into two separately-fenced regions: an `aac:generated` fence wrapping the table, and an `aac:authored` fence wrapping the rationale. Combining them in a single fence defeats both the fence contract and the mode discipline — either the validator tries to regenerate authored narrative (wrong), or it never drift-checks regenerable inventory (silent drift).

---

## See also

- [https://diataxis.fr/](https://diataxis.fr/) — full Diátaxis framework context, examples, and the four-quadrant model
- `rules/writing/aac-dac-conventions.md` — the AaC fence convention this reference builds on (fence schema, validator, authoring workflow)
- [`../SKILL.md`](../SKILL.md) — doc-management skill (gains a "Diátaxis Modes" section in Step C2 pointing here)
- `agents/doc-engineer.md` Phase 1 — doc-engineer agent (gains a reference instruction in Step C3 to consult this file when assessing architecture document fences)
