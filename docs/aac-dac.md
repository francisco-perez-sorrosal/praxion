---
diataxis: explanation
audience: developer
---

<!-- aac:authored owner=praxion-maintainers last-reviewed=2026-05-01 -->

# Architecture-as-Code + Documentation-as-Code

Praxion treats architectural knowledge as two co-equal halves. **Architecture-as-Code (AaC)**: structural
facts live in machine-readable models — a LikeC4 DSL, ADRs, traceability matrices — that can be queried,
diffed, and validated programmatically. **Documentation-as-Code (DaC)**: the rationale behind those facts
lives in authored prose alongside the model, committed to the same repository and reviewed through the same
pull-request process.

Neither half is optional. Structural facts without prose become illegible to future contributors. Prose without a
machine-readable model drifts silently from the code. Two CLAUDE.md clauses frame this cornerstone: under
*Context Engineering*, "structural facts in machine-readable models, rationale in authored narrative, both
versioned together, neither degrades silently"; under *Structural Beauty*, "the architecture you describe is
the architecture you ship." These are not aspirational — they are the invariants the mechanisms below enforce.

## Why This Matters

Architecture documentation fails in one of two directions.

**Model without narrative.** Code and diagrams show what the system does today; they cannot show what
alternatives were considered or why this shape over alternatives. A contributor reading the import graph can
trace dependencies but not know whether they are incidental or intentional. The same trade-offs get relitigated
because no one recorded the original reasoning.

**Narrative without a model.** `ARCHITECTURE.md` prose ages from the moment it is written. Components rename,
modules merge, deployment topology shifts — the document stays frozen. Within months it describes a system
that no longer exists. Reviews treat it as aspirational rather than authoritative.

Both failures share a root cause: the structural and narrative halves are managed by disconnected processes.
Praxion's fix is mechanical coupling. When structural facts live in a queryable model and rationale lives in
authored prose, both audited by the same toolchain and gated by the same CI pipeline, drift in either
direction becomes a failing check. A contributor who edits a generated diagram without regenerating it from
source fails the pre-commit hook. A narrative that names a component the LikeC4 model no longer defines
surfaces as a sentinel finding. Neither half degrades undetected.

## The Seven Mechanisms

The AaC+DaC stack is implemented across seven complementary mechanisms. Each solves a distinct problem; they
compose into a single feedback loop described in [How They Compose](#how-they-compose).

### 1. The Fence Convention (Idea 2)

Architecture documents mix two content kinds: regenerable structural inventory (component tables, deployment
topology) that derives from the LikeC4 model, and authored narrative (rationale, invariants, trade-offs) that
no model can express. Without an explicit boundary, regenerating from the model silently erases narrative.
Treating the document as fully authored lets structural content drift silently.

The fence convention makes the boundary mechanically detectable using HTML comment markers — zero new runtime,
supported by every markdown renderer:

```markdown
<!-- aac:generated source=docs/diagrams/system.c4 view=L1Components last-regen=2026-04-30T12:00Z -->
| Component | Responsibility |
|-----------|----------------|
| API Gateway | Route and authenticate requests |
<!-- aac:end -->

<!-- aac:authored owner=systems-architect last-reviewed=2026-04-30 -->
The gateway layer was chosen over per-service auth to centralise credential rotation.
<!-- aac:end -->
```

Required attributes: `source` and `view` on `aac:generated`; `owner` on `aac:authored`. Untagged content
defaults to `aac:authored owner=unspecified` so legacy documents need no migration. The validator
`scripts/aac_fence_validator.py` checks fence balance, required attributes, and source-path resolution.
Fence rules are defined in [`rules/writing/aac-dac-conventions.md`](../rules/writing/aac-dac-conventions.md)
(dec-098).

### 2. The LikeC4 Model and Querying Skill (Idea 9)

The LikeC4 DSL is the single source of structural truth: component definitions, relationships, deployment
topology, and element metadata. Views are projections over this model — a LikeC4 source file may yield a
System Context (L0), Container/Component (L1), and Internals (L2) view without duplicating any fact.

The `likec4-querying` skill (`skills/likec4-querying/SKILL.md`, path-scoped) gives agents an eight-task
decision rubric for when to call the LikeC4 MCP server versus read `.c4` files directly. The rubric
matters: calling `read-project-summary` repeatedly when a single `Read` of a 100-line file would suffice is
latency waste; reading every `.c4` file when one `search-element` call would suffice is token waste. The MCP's
`query-by-metadata` tool enables indexed structural queries — "which elements carry REQ-03?" becomes one call,
not a grep over the whole codebase (dec-109).

### 3. Architectural Fitness Functions (Idea 5)

The `fitness/` directory at project root holds architectural invariants as executable code:
`import-linter.cfg` for import-graph contracts and `pytest` tests for everything else. These are not
tests of behavior — they are tests of architecture. An import-linter contract might declare that no skill
module imports an agent module; a pytest fitness rule might verify that every Built component appears in the
LikeC4 DSL.

Every rule must cite its authority — an ADR id matching `dec-\d{3,}` or a CLAUDE.md principle reference
matching `CLAUDE\.md§<Principle>` — in the rule's module docstring (pytest) or `description=` field
(import-linter). A meta-citation rule (`test_meta_citation.py`) scans every sibling rule and FAILs the suite
when any rule lacks a citation. Waivers use an inline `# fitness-waiver: <anchor> <reason>` comment; the
meta-rule validates each waiver carries both an anchor and a non-empty reason. Uncited rules and uncited
waivers indicate fuzzy thinking — the friction is the feature (dec-101).

### 4. The Golden-Rule Enforcement Hook (Idea 6)

At commit time, `scripts/check_aac_golden_rule.py` (stdlib-only, idempotent, side-effect-free) runs as
Block D of the pre-commit hook. It checks two things:

- **Path-pair detection.** A staged generated-output file (a `.d2`/`.svg` render in `docs/diagrams/`) must
  be accompanied by a staged change to its corresponding `.c4` source, or carry a line-adjacent
  `<!-- aac-override: <reason> -->` comment explaining the hand-edit.
- **Fence-interior detection.** A staged edit inside an `aac:generated` region in `ARCHITECTURE.md` must
  be accompanied by a staged change to the fence's `source=` path, or carry an override comment.

Gate mode exits non-zero on violation; audit mode scans recent commits and produces JSON findings for the
sentinel. The `# aac-override: <reason>` escape hatch covers legitimate hand-edits (a typo fix in a
rendered SVG before the next regen) without permanently blocking the commit — but the reason is audited.
Block D runs only when staged paths match architectural-trigger globs, adding milliseconds to
non-architectural commits (dec-108, dec-110).

### 5. The Architect-Validator Agent (Idea 4)

The `architect-validator` agent is an Opus-tier reviewer that verifies the **code↔DSL↔ADR triangle** is
consistent. It operates in two modes:

- `--mode=on-demand` — always writes a report to `ARCHITECTURE_VALIDATION.md`; never blocks anything.
- `--mode=pre-merge` — CI gate; exits non-zero on any FAIL so the harness can block the merge.

The three-section report covers: **Model→Code drift** (does the code import what the DSL declares?),
**ADR→Model drift** (is each recorded decision still reflected in the DSL?), and **Generated-region drift**
(do `aac:generated` fences match their declared sources?). FAIL findings become TECH_DEBT_LEDGER rows
(`class: drift, source: architect-validator`), ensuring unresolved structural drift accrues as tracked debt
rather than evaporating with the ephemeral report (dec-100).

### 6. The Architecture CI Pipeline (Idea 7)

`.github/workflows/architecture.yml` runs three parallel jobs on every PR that touches an architectural
path (`docs/diagrams/**`, `**/*.c4`, `**/ARCHITECTURE.md`, `.ai-state/decisions/**`, `fitness/**`,
`scripts/aac_fence_validator.py`, `scripts/check_aac_golden_rule.py`):

1. **`regenerate-and-diff`** — re-runs the diagram regen hook and checks `git diff --exit-code` on
   `docs/diagrams/`. Any committed render that disagrees with a fresh generation fails this job.
2. **`fitness-functions`** — runs `uv run pytest fitness/tests/` and `uv run lint-imports`. Both must pass.
3. **`dsl-validate`** — runs the fence validator (mechanical, fast-fail before API spend), then invokes the
   `architect-validator` agent in `--mode=pre-merge` via `anthropics/claude-code-action`.

Path-filter triggers keep the pipeline off non-architectural PRs. The mechanical fence check runs first inside
`dsl-validate` to avoid burning Opus-class API budget on a check a Python script can do in milliseconds
(dec-106).

### 7. REQ↔Architectural-Element Traceability and Sentinel AC Audit (Idea 3, Idea 10, Idea 12)

The behavior↔structure gap closes through a bidirectional convention: LikeC4 elements declare which
behavioral requirements they implement via `metadata.req_ids = "REQ-01, REQ-03"`; archived SPECs declare
which architectural elements implement their requirements via `architectural_elements: [auth.service, ...]`
in frontmatter. The LikeC4 MCP's `query-by-metadata` tool supports the indexed lookup on both sides.

The verifier renders a four-column traceability matrix: Requirement, Test(s), Implementation, Architectural
Element(s). Absent `architectural_elements:` for a REQ is not a FAIL — it signals "not yet mapped," not
"untested" (dec-111).

The sentinel's AC dimension audits the substrate periodically:

- **AC10** — fence integrity: `aac:generated`/`aac:authored`/`aac:end` balance and required attributes.
- **AC11** — model↔markdown agreement: components named in ARCHITECTURE.md correspond to LikeC4 elements.
- **AC12** — traceability orphans: REQs with no element claiming them; elements citing nonexistent REQs.

Each check activates only when its substrate is present, mirroring the TT-dimension's conditional-activation
idiom. AC12 fires only after at least one feature has populated both sides of the convention — until then it
emits an INFO note and exits (dec-112).

## How They Compose

The seven mechanisms are not independent tools. They form a single feedback loop in which every change that
touches architectural surfaces passes through multiple check points, and every finding eventually returns to
the author as tracked work.

<!-- aac:authored owner=praxion-maintainers last-reviewed=2026-05-01 -->

The loop:

1. **Author writes** an ADR (DaC: the "why") and updates the LikeC4 model (AaC: the "what").
2. **Author seeds** an `aac:generated` fence in `ARCHITECTURE.md` citing `source=` from the model.
3. **At commit**, Block D runs `check_aac_golden_rule.py --mode=gate`. A staged edit to a generated region
   without a corresponding source change fails immediately — the cheapest feedback point.
4. **At PR time**, three CI jobs cover disjoint failure modes: render drift (`regenerate-and-diff`), invariant
   regression (`fitness-functions`), and structural coherence (`dsl-validate` → fence validator →
   `architect-validator --mode=pre-merge`).
5. **The architect-validator** sweeps its three-section report. FAILs become `TECH_DEBT_LEDGER` rows
   (`class: drift`) that accumulate as tracked debt visible to the next planning cycle.
6. **Periodically**, the sentinel's AC10–AC12 checks catch drift that landed via PRs outside the
   architectural-touch slice gate: stripped fences, model↔markdown disagreements, traceability orphans.
7. **The loop closes** when the planning cycle consumes the ledger. Drift findings become inputs to the next
   architect's work, eliminating the gap between "detected" and "addressed."

<!-- aac:end -->

The Mermaid diagram below represents this loop. It is authored prose today and could become an
`aac:generated` region once a corresponding LikeC4 view (`docs/diagrams/aac-dac-loop.c4`) is created.

![AaC+DaC feedback loop: author writes ADR + LikeC4 DSL + ARCHITECTURE.md with aac fences; pre-commit golden-rule gate, CI jobs, and architect-validator feed FAILs into the tech-debt ledger; sentinel performs periodic AC-dimension audits; feedback routes back to author for resolution](diagrams/aac-dac-feedback-loop/rendered/aac-dac-feedback-loop.svg)

## Adopting It

**Existing projects** — run `/onboard-project`. A gate between Phase 8 and Phase 9 presents: `Skip AaC
(recommended)` (default), `Install AaC tier`, or `Run all rest`. The default is OFF — retrofitting fence
regions into established documents requires deliberate author review.

**Greenfield projects** — run `/new-project` or `new_project.sh`. AaC is default-ON. Opt out with
`new_project.sh --no-aac` or `PRAXION_NEW_PROJECT_NO_AAC=1`.

**What lands per project**: `fitness/` scaffold, `.github/workflows/architecture.yml` (rendered from
`claude/aac-templates/architecture.yml.tmpl`), `docs/diagrams/` directory, Block D fragment in
`.git/hooks/pre-commit` (invokes `check_aac_golden_rule.py` via `${PLUGIN_ROOT}` — no per-project copy),
and a commented-out fence example seeded into `ARCHITECTURE.md` when present.

**What is global** (no per-project install): the SDD skill's traceability convention, the fence validator
and golden-rule scripts (canonical in the plugin path), the sentinel agent's AC10–AC12 audit, and the
architect-validator agent (dec-113).

> [!NOTE]
> AC10–AC12 and the architect-validator activate conditionally on substrate presence. A project with no `.c4`
> files and no fenced `ARCHITECTURE.md` gets INFO notes, not false positives.

## See Also

- [`docs/architecture.md`](architecture.md) — Praxion's developer-facing architecture guide; code-verified
  component list and file paths
- [`docs/spec-driven-development.md`](spec-driven-development.md) — REQ ID convention and the bidirectional
  REQ↔architectural-element traceability extension
- [`skills/doc-management/references/diataxis-modes.md`](../skills/doc-management/references/diataxis-modes.md)
  — the four-mode documentation taxonomy (Tutorial, How-to, Reference, Explanation) that governs fence
  selection; this document is Explanation mode (`aac:authored` throughout)
- [`rules/writing/aac-dac-conventions.md`](../rules/writing/aac-dac-conventions.md) — the fence schema
  reference: attributes, validator CLI, override syntax
- [`.ai-state/decisions/DECISIONS_INDEX.md`](../.ai-state/decisions/DECISIONS_INDEX.md) — the full ADR set;
  dec-097 through dec-113 covers the AaC+DaC stack

<!-- aac:end -->
