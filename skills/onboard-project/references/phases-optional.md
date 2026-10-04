# Praxion Onboarding — Opt-in Phase Bodies

Opt-in phase bodies for `skills/onboard-project/SKILL.md` — phases 8, 8b, 8c, 8d, 8e. See [../SKILL.md](../SKILL.md) for §Pre-flight, §Flow, §Phase Gates, and §Idempotency Predicates.

## §Capability × placement

Placement (`--placement in-repo|sidecar`) is *nearly* orthogonal to the G3 capability Profile below, but not entirely — several capabilities write **tracked** files, which is precisely the footprint sidecar placement exists to avoid. Each capability falls into exactly one of four classes under sidecar placement:

| Capability | Class under `sidecar` | Reason |
|---|---|---|
| `core` | **local** | every surface this phase file's siblings write redirects — `.gitignore` → `.git/info/exclude`, `.ai-state/` → shadow, `.gitattributes` + merge driver → the sidecar's own, `CLAUDE.md` blocks → per the placement-cases table (§Phase 6) |
| `observability` | **local** | a `.claude/settings.json` env toggle; redirects to the shadowed `settings.local.json` |
| `arch` | **local (with one share default)** | `.ai-state/DESIGN.md` is private in the sidecar; `docs/architecture.md` defaults to `share` — a plain doc the team benefits from, citing ADRs by id text and never by an `.ai-state/` path — with `--shadow docs/architecture.md` opting out |
| `ml` | **local** | `.ai-state/experiments/` and `gpu_budget.yaml` follow the shadow; the checkpoint `.gitignore` block goes to `.git/info/exclude`; `program.md` becomes a shadow |
| `aac` (§Phase 8b) | **local, shadowed** | `architecture/` and `fitness/` shadow into the sidecar; the Block D gate installs into the local hook chain only; the `.github/workflows/architecture.yml` sub-surface is **dropped** (GitHub-visible by construction, no invisible variant) |
| `quality` (§Phase 8e) | **share-gated** | `.editorconfig`, ruff/mypy `pyproject.toml` blocks, Biome/ESLint configs, `.pre-commit-config.yaml`, `CONTRIBUTING.md`, `.github/dependabot.yml` are all tracked — ordinary project hygiene, not Praxion branding. Offered, never silently: the operator sees the exact file list and confirms, or declines and proposes the same files to the team as a normal PR |
| `tests` (§Phase 8e) | **share-gated (workflows dropped)** | the `[tool.pytest.ini_options]` block, `tests/acceptance/README.md`, `tests/e2e/README.md` and `tests/declared-deps.toml` are tracked — same treatment as `quality`: named, confirmed, or declined. The `.github/workflows/test.yml` and `test-scheduled.yml` sub-surface (8e.13) is **dropped**, as with `aac`'s `architecture.yml` — GitHub-visible by construction, no invisible variant |
| `obsidian` (§Phase 8d) | **share-gated** | `.obsidian/app.json` link-safety keys are tracked. Same treatment as `quality` — named, confirmed, or declined. The `.gitignore` block redirects and the `CLAUDE.md` / settings blocks follow placement |
| `ci` (§Phase 8e) | **unavailable** | `.github/workflows/*`, `.github/labels.yml`, and two `gh secret set` calls are GitHub-visible by construction — there is no invisible variant. Refused at the Profile gate with a one-line reason naming the local hook chain as the closest equivalent |

**Invariant — no silent tracked write under sidecar placement.** No capability writes a tracked file without either the `share` intent recorded in the manifest or an explicit per-capability confirmation naming the files. A sidecar onboarding run that declines every share-gated capability leaves `git status --porcelain` empty.

## §Phase 8 — Architecture Baseline (opt-in, default-yes)

**Templates.** The architect doc uses `skills/software-planning/assets/ARCHITECTURE_TEMPLATE.md` (architect-facing design target — full section ownership tags). The developer doc uses `skills/doc-management/assets/ARCHITECTURE_GUIDE_TEMPLATE.md` (filtered to Built components only — every name and path code-verified). The agent's full standing contract is in `agents/systems-architect.md`; this phase invokes a *baseline-audit subset* of that contract, with the directives below as the diff.

**Predicate.** Skip the phase entirely if either of these holds:

- `test -e .ai-state/DESIGN.md` (architect-facing doc already present — likely a re-run on a fully-onboarded project, or a `new`-mode run whose seed pipeline (Phase 0s) already produced it)
- `test -e docs/architecture.md` (developer-facing doc already present — same provenance)

When skipped via predicate, emit: `Phase 8: skipped (architecture docs already exist — produced by the seed pipeline or a prior /onboard-project run)`. Skipping is idempotent and does not block Phase 9.

**Why this phase exists.** Praxion's `sentinel` coherence audits and future feature pipelines (`systems-architect` updates these docs incrementally) both benefit from an architectural baseline. Without it, the existing-project onboarding is half-complete from the agent ecosystem's perspective — every future agent runs context-poor on the codebase shape. Greenfield (`new` mode) gets this for free via the seed pipeline; existing-project needs the same treatment, which is what this phase delivers.

**Selection.** The `arch` capability row (Profile G3, `SKILL.md` §Capability IDs — pre-checked on unless `.ai-state/DESIGN.md` or `docs/architecture.md` already exists). No question fires here; this phase reads the resolved capability set. When `arch` is selected, delegate to `systems-architect` in baseline-audit mode (~5–15 minutes for a medium project under 500 source files, longer for large repos) and produce real, code-verified content for both architecture docs. When `arch` is not selected, skip Phase 8 entirely — future Standard-tier feature pipelines will create the docs when `systems-architect` runs for the first time; acceptable for lean onboarding when `/sentinel` isn't run immediately afterward.

**Action when `arch` is selected.**

Delegate to `systems-architect` via the `Task` tool. The delegation prompt MUST include all of these directives:

1. **Mode.** `Baseline-audit mode — no specific feature scope. Read the existing codebase and produce architecture docs that describe the as-built state, not a future design target.`
2. **Inputs.** Point the agent at the project root. Tell it which language/framework signals were detected in §Pre-flight (Python, JavaScript, Rust, Go, etc.) so it scopes the codebase scan correctly.
3. **Outputs (required).**
   - `.ai-state/DESIGN.md` — architect-facing design-target document. Use the `skills/software-planning/assets/ARCHITECTURE_TEMPLATE.md` template. Sections: System Overview, System Context (L0 — a committed render embedded with markdown image syntax and an alt text naming the view and its C4 type; the LikeC4 source lives under `<doc-dir>/diagrams/architecture/src/`), Components (L1 — committed render embed + table), Data Flow, Quality Attributes (testing, observability, deployment current state), Open Questions / Known Gaps. Mark unverified-by-code claims with section ownership tags so future updates can supersede cleanly.
   - `docs/architecture.md` — developer-facing navigation guide. Use the `skills/doc-management/assets/ARCHITECTURE_GUIDE_TEMPLATE.md` template. Filter `.ai-state/DESIGN.md` to the **Built** components only — every component name and file path must resolve on disk (verify with `Glob` or `ls`). Skip components that exist only in the design-target document.
4. **Outputs (optional, agent's call).**
   - One ADR draft under `.ai-state/decisions/drafts/` if the baseline reading surfaces a load-bearing architectural invariant worth preserving (e.g., a one-way module dependency, a layer boundary, a data-flow constraint). The ADR is *only* warranted when the invariant is non-obvious from the code; do not write a ceremonial "architecture is now baselined" ADR.
5. **Anti-instructions.**
   - Do NOT produce `SYSTEMS_PLAN.md` — there is no feature in scope for a baseline audit, and a SYSTEMS_PLAN without a feature is anti-pattern.
   - Do NOT produce `PRE_REFACTOR_PLAN.md` — Phase 2.5 is skipped in baseline-audit mode (no feature scope means no pre-refactor scope).
   - Do NOT invent components that don't exist on disk. Every component table row and SVG reference must be code-verified.
   - Do NOT exceed L1 detail in C4 diagrams; per-view size follows the advisory heuristic in `rules/writing/diagram-conventions.md`, and the review checks it links decide legibility. Author the real model against the installed style kit (`<doc-dir>/diagrams/architecture/src/_spec.c4`; Phase 8b.5 installs it — when Phase 8 runs first on a fresh project, run `python3 <plugin-root>/scripts/install_diagram_kit.py --project-root . --plugin-root <plugin-root> --diagrams-dir <doc-dir>/diagrams` before authoring; the installer is idempotent, so 8b.5 then reports every item skipped), regenerate with `python3 scripts/regenerate_diagrams.py`, and apply its `--check` review checks until every view passes. Use LikeC4 DSL for C4-architectural views; Mermaid for sequence/state/ER/flowchart. L2 internals are deferred to feature-pipeline updates.
   - Do NOT modify any source code, tests, or non-architecture documentation.

The architect operates in a fresh context window (`Task` tool spawn) and reports completion when both docs are written. The main agent reads the produced docs at completion to confirm shape, then proceeds to Phase 9.

**API-surface pointer (informational, not a gate).** If this project exposes an API surface (REST/OpenAPI, Python/TypeScript library, MCP server, GraphQL schema), tell the user: "Run `/document-api` to scaffold its documentation." This is a one-line pointer only — do NOT auto-invoke `/document-api` and do NOT add a gate.

**If the architect fails or times out**, emit a clear warning: `Phase 8 skipped — systems-architect did not complete the baseline audit. Architecture docs were not produced. Re-run /onboard-project to retry, or run a feature pipeline whose first stage will produce them.` Proceed to Phase 8b.

## §Phase 8b — AaC Tier Install (opt-in, default-skip)

**Why this phase exists.** Phase 8 produces architecture docs. Phase 8b installs the AaC enforcement layer: fence-region examples in those docs, fitness tests for architectural invariants, a golden-rule pre-commit block, CI workflow, and the diagram kit (style vocabulary, example model, the regeneration command and its hook wiring). All five surfaces are idempotent and independent — each sub-step is guarded by its own predicate so re-runs produce zero `git diff`. Sentinel-only surfaces (traceability convention, sentinel AC dimension) need no per-project install — the AaC convention and sentinel agent are global.

Note: AaC enforcement via Block D requires the `praxion` plugin to be installed. If the plugin is absent, the golden-rule hook block silently exits 0 — same behavior as Phase 4's id-citation check.

**Selection.** The `aac` capability row (Profile G3, `SKILL.md` §Capability IDs — pre-checked off; matches the existing-project principle "extend existing patterns; do not impose"). No question fires here; this phase reads the resolved capability set. When `aac` is not selected: no AaC scaffolding installed, Phase 9 verification handoff runs normally, re-run `/onboard-project --with aac` later when ready — all sub-steps are idempotent. When `aac` is selected: run all five sub-steps (8b.1–8b.5); each is independently idempotent, already-installed surfaces are silently skipped.

**Action when `aac` is selected.** Run sub-steps 8b.1 through 8b.5 in order. Each sub-step prints one line on completion or skip.

### Sub-step 8b.1 — Fence seed

**Predicate.** At least one of `**/DESIGN.md` or `docs/architecture.md` exists AND does NOT already contain the string `aac:generated` or `aac:authored`.

- If no architecture doc exists: skip silently. Phase 8 (if run) will produce one; a future feature pipeline may produce one. Re-running Phase 8b after an architecture doc exists will complete this sub-step.
- If an architecture doc exists but already contains `aac:generated` or `aac:authored` markers: skip with notice `8b.1: skipped (fence regions already present)`.

**Action.** For each architecture doc found (prefer `.ai-state/DESIGN.md`, then `docs/architecture.md`), append the following commented example stanza at the end of the file using `Edit`:

```markdown
<!-- AaC fence example — see rules/writing/aac-dac-conventions.md for the full convention.
     Replace this comment with real fence regions as you document components.

aac:authored id=example-component
This is a human-authored rationale paragraph. The agent reads this and preserves it.
aac:end

aac:generated id=example-component
<!-- agent-generated content lands here; never edit manually -->
aac:end
-->
```

Print: `8b.1: fence example appended to <filename> — edit the stanza to wrap real prose`.

### Sub-step 8b.2 — Fitness scaffold

**Predicate.** `fitness/` directory does NOT exist. If it exists: skip with notice `8b.2: skipped (fitness/ already present)`. Individual files within the scaffold are also checked — if a target file exists, skip that file and continue with others.

**Action.** Create `fitness/` and `fitness/tests/` directories. Copy from Praxion's AaC templates (in the plugin install path):

| Source template | Destination |
|---|---|
| `claude/aac-templates/fitness-import-linter.cfg.tmpl` | `fitness/import-linter.cfg` |
| `claude/aac-templates/fitness-test-meta-citation.py.tmpl` | `fitness/tests/test_meta_citation.py` |
| `claude/aac-templates/fitness-test-starter.py.tmpl` | `fitness/tests/test_starter.py` |
| `claude/aac-templates/fitness-conftest.py.tmpl` | `fitness/tests/conftest.py` |
| `claude/aac-templates/fitness-README.md.tmpl` | `fitness/README.md` |

Also create an empty `fitness/tests/__init__.py` (skip if exists). Templates are read from the Praxion repo (use `Read` on the template path relative to the plugin install path). Write each destination with `Write`.

Print: `8b.2: fitness/ scaffolded — read fitness/README.md and the architectural-fitness-functions skill to author your first invariant`.

### Sub-step 8b.3 — Block D append (pre-commit hook)

**Predicate.** `.git/hooks/pre-commit` exists AND does NOT contain the string `Block D` or `check_aac_golden_rule`.

- If `.git/hooks/pre-commit` does not exist: skip with notice `8b.3: skipped (no pre-commit hook — run Phase 4 first, then re-run Phase 8b)`.
- If `Block D` or `check_aac_golden_rule` is already present: skip with notice `8b.3: skipped (Block D already present)`.

**Action.** Read `.git/hooks/pre-commit`. Append the Block D fragment from `claude/aac-templates/precommit-block-d.sh.frag` using `Edit`. The fragment uses `${PLUGIN_ROOT}` resolution (mirrors Phase 4's `check_id_citation_discipline.py` pattern) and invokes `python3 ${PLUGIN_ROOT}/scripts/check_aac_golden_rule.py --mode=gate`. Appending AFTER existing checks ensures AaC failure does not mask id-citation failures.

Print: `8b.3: Block D appended to .git/hooks/pre-commit`.

### Sub-step 8b.4 — Workflow render

**Predicate.** `.github/workflows/architecture.yml` does NOT exist.

- If exists: skip with notice `8b.4: skipped (.github/workflows/architecture.yml already present)`.

**Action.** Run the diagram-kit installer, which renders `claude/aac-templates/architecture.yml.tmpl` with the placeholders below, validates the YAML, and skips the file when it is already present (the same run installs sub-step 8b.5's surfaces, so one invocation serves both and their order is immaterial):

```bash
python3 <plugin-root>/scripts/install_diagram_kit.py --project-root . --plugin-root <plugin-root> --diagrams-dir <doc-dir>/diagrams
```

The installer prints one `installed` or `skipped` line per file; exit 2 means a precondition failed (not a git repository, templates missing, a diagrams directory outside the project) and the sub-step reports `8b.4: skipped — <installer message>`. Placeholder substitution:

| Placeholder | Derivation | Default |
|---|---|---|
| `{{PROJECT_PATHS_DIAGRAMS}}` | The `--diagrams-dir` passed to the installer: the detected `<doc-dir>/diagrams/` | `docs/diagrams/` |
| `{{PROJECT_PATHS_ARCHITECTURE_DOCS}}` | Fixed | `**/DESIGN.md` |
| `{{PROJECT_PYTHON_VERSION}}` | `requires-python` lower bound from `pyproject.toml`, or fallback | `3.13` |
| `{{PROJECT_PLUGIN_DIR}}` | Plugin install scope; `.` works for user-installed plugins | `.` |

Print: `8b.4: .github/workflows/architecture.yml written` (or the installer's `skipped` line).

### Sub-step 8b.5 — Diagram kit

**Predicate.** No `*.c4` file exists under `<doc-dir>/diagrams/` (default `docs/diagrams/`). A bare or `.gitkeep`-only directory from an earlier onboarding does not satisfy the predicate, so projects onboarded before the kit existed receive it on a re-run. Per the forward-binding constraint on `<doc-dir>/diagrams/`, a top-level `architecture/` directory is NEVER created.

- If any `*.c4` exists under it: skip with notice `8b.5: skipped (model sources already present)`.

**Action.** The installer run of sub-step 8b.4 installs this sub-step's surfaces as one set: the style kit `<doc-dir>/diagrams/architecture/src/_spec.c4` (the floor vocabulary — Person, System in scope, External system, Container, Component, Data store — each with its drawing and legend entry), an example model beside it, the `rendered/` directory, and the regeneration command with its sibling modules under `scripts/`. When the pinned toolchain is present (pre-flight probe 4c), render once with `python3 scripts/regenerate_diagrams.py` so the committed renders exist from the first commit; otherwise print the probe's install pointer. No `.gitkeep` is written.

Print: `8b.5: diagram kit installed` (or the installer's `skipped` lines).

**Verification handoff.** After all five sub-steps complete, print the final-state checklist:

```
AaC tier install summary:
  8b.1 fence seed:        <installed | skipped (reason)>
  8b.2 fitness/:          <installed | skipped (reason)>
  8b.3 Block D:           <installed | skipped (reason)>
  8b.4 architecture.yml:  <installed | skipped (reason)>
  8b.5 diagram kit:       <installed | skipped (reason)>
```

Phase 9 verification handoff lists every staged file across all phases — Phase 8b's surfaces are included in that enumeration.

## §Phase 8c — ML/AI Training Scaffold (opt-in; default-yes when ML signals detected)

**Why this phase exists.** ML/AI training projects require scaffolding that general software projects do not: experiment tracking directories, checkpoint gitignore entries, compute-budget declarations, and a `program.md` meta-prompt. Phase 8c detects whether the project is ML-flavored and applies idempotent scaffolding so the first `/run-experiment` invocation finds the infrastructure already in place. It also surfaces the three operational modes (A/B/C) so the user knows how to configure their backend before dispatching a run.

**Detection signals.** Phase 8c fires when ANY of the following signals is present in the project root:

1. `train.py` or `prepare.py` exists at the project root
2. `pyproject.toml` (or `requirements.txt`, `setup.py`, `Pipfile`) declares `torch`, `jax`, or `tensorflow` as a dependency
3. `program.md` exists at the project root **and** contains ML-training vocabulary (`grep -qiE 'train|checkpoint|epoch|gpu|loss|dataset|ml-training' program.md` succeeds) — content-gated so a bare `program.md` with no training content is not an ML signal, and a non-ML project that happens to use that filename is not falsely scaffolded

When none of these signals is detected, skip Phase 8c entirely and emit: `Phase 8c: skipped (no ML training signals detected — train.py, torch/jax/tensorflow dependency, or program.md)`.

**Selection.** The `ml` capability row (Profile G3, `SKILL.md` §Capability IDs — pre-checked on iff ML signals were detected in §Pre-flight, off otherwise). No question fires here; this phase reads the resolved capability set. When `ml` is selected: run all five sub-steps (8c.1–8c.5); each is independently idempotent, already-present scaffolding is silently skipped. When `ml` is not selected: skip Phase 8c entirely — re-run `/onboard-project --with ml` later when ready, all sub-steps are idempotent.

**Action when `ml` is selected.** Run sub-steps 8c.1 through 8c.5 in order. Each sub-step prints one line on completion or skip.

### Sub-step 8c.1 — Experiment tracking directory

**Predicate.** `.ai-state/experiments/` does NOT exist. If it exists: skip with notice `8c.1: skipped (.ai-state/experiments/ already present)`.

**Action.** Create `.ai-state/experiments/` directory. Write `.ai-state/experiments/README.md`:

```markdown
# Experiment Tracking Directory

Experiment tracking artifacts live here — MLflow or W&B run metadata, artifact references,
and run-tag index entries. Generated content; committed selectively. See
`skills/experiment-tracking/SKILL.md` for tracker configuration and run conventions.
```

Print: `8c.1: .ai-state/experiments/ created`.

### Sub-step 8c.2 — Checkpoint `.gitignore` block

**Predicate.** `grep -q '# ML training checkpoints' .gitignore` is true. If detected: skip with notice `8c.2: skipped (checkpoint .gitignore block already present)`.

**Action.** Append to `.gitignore` (create if absent):

```gitignore
# ML training checkpoints (Praxion-managed)
runs/
checkpoints/
*.pt
*.bin
*.safetensors
wandb/
mlruns/
```

Print: `8c.2: checkpoint .gitignore block appended`.

### Sub-step 8c.3 — GPU budget declaration

**Predicate.** `test -e .ai-state/gpu_budget.yaml` is true. If file exists: skip with notice `8c.3: skipped (.ai-state/gpu_budget.yaml already present)`.

**Action.** Ask the user: `What is the project-level GPU hours budget per experiment? (Examples: 2.0 for a short validation run; 8.0 for an overnight run; 0 to declare later and enforce per-step)` Wait for input. Write `.ai-state/gpu_budget.yaml`:

```yaml
# GPU hours budget per experiment run (project-level default).
# Individual WIP.md steps may override this value via gpu_hours_budget: <float>.
# Convention: rules/ml/gpu-budget-conventions.md
gpu_hours_budget: <user-provided or 0>
```

Print: `8c.3: .ai-state/gpu_budget.yaml written (gpu_hours_budget: <value>)`.

### Sub-step 8c.4 — `program.md` scaffold

**Predicate.** `test -e program.md` at repo root is true. If `program.md` exists: skip with notice `8c.4: skipped (program.md already exists — user-authored meta-prompt preserved)`.

**Action.** Write `program.md` at the project root:

```markdown
# Program

<!-- program.md is the project-local meta-prompt for this experiment loop.
     It guides the autonomous training cycle. Praxion recognizes it as an
     artifact category alongside CLAUDE.md. See skills/ml-training/SKILL.md
     for the vocabulary and artifact types this file governs. -->

## Goal

[Describe the training objective: model architecture, dataset, target metric threshold]

## Hypothesis Space

[What configurations or architecture changes will this loop explore?]

## Simplicity Criterion

[What is the simplest run that would confirm the hypothesis? Start here.]

## Tracker

mlflow  # or: wandb

## Autonomy Contract

[How much should /run-experiment decide autonomously vs. pause for human input?]

## Current Run

[Leave empty — /run-experiment populates this section]

## History

[Summarize past runs, key results, and what changed between them]
```

Print: `8c.4: program.md scaffold written — fill in Goal and Hypothesis Space before running /run-experiment`.

### Sub-step 8c.5 — Operational modes callout

**Predicate.** None — always runs when Phase 8c fires.

**Action.** Print the operational modes summary:

```text
ML scaffold complete. Your project supports three operational modes:

  Mode A — Co-located owned GPU (Mac M-series, RTX, on-prem):
            set backend: local in .ai-state/neo_cloud_backend.yaml

  Mode B — Co-located rented GPU (SSH'd into an H100 box):
            same config as Mode A; SSH into the box with Praxion installed first

  Mode C — Separated cloud (SkyPilot or RunPod direct):
            set backend: skypilot or backend: runpod-direct

Full walkthrough: skills/ml-training/references/operational-modes.md

Next steps:
  1. Edit program.md — describe your training goal and tracker preference
  2. Run /run-experiment to dispatch a training run
  3. Run /check-experiment to monitor an in-flight or completed run
```

Conventions for tracker config, run-tag mapping, and experiment log format:
`rules/ml/experiment-tracking-conventions.md` and `skills/experiment-tracking/SKILL.md`.
Compute budget conventions: `rules/ml/gpu-budget-conventions.md` and
`skills/deployment/references/gpu-compute-budgeting.md`.

Print: `8c.5: operational modes callout printed`.

**Verification handoff.** After all five sub-steps complete, print the final-state checklist:

```text
ML scaffold summary:
  8c.1 .ai-state/experiments/:  <created | skipped (reason)>
  8c.2 checkpoint .gitignore:   <appended | skipped (reason)>
  8c.3 .ai-state/gpu_budget.yaml: <written (value) | skipped (reason)>
  8c.4 program.md:              <scaffolded | skipped (reason)>
  8c.5 mode callout:            printed
```

Phase 9 verification handoff lists every staged file across all phases — Phase 8c's surfaces are included in that enumeration.

## §Phase 8d — Obsidian Integration (opt-in, detection-gated default)

**Why this phase exists.** Projects that use Obsidian as a vault inside the repository benefit from four surfaces: a `.gitignore` block that keeps workspace state files out of commits, the `obsidian@obsidian-skills` marketplace plugin (installed at user scope via `./install.sh code`) so agents can navigate the vault, a link-safety config in `.obsidian/app.json` that pins Markdown-form links and disables auto link-rewrite so vault tooling cannot corrupt project-artifact links, and a `permissions.deny` block in `.claude/settings.json` that mechanically blocks the dangerous `obsidian` CLI subcommands. Without these, an agent can inadvertently commit Obsidian workspace noise, miss vault-navigation tools, rewrite project links into wikilink form, or be denied permissions silently without knowing why. Phase 8d verifies all four idempotently.

**Selection.** The `obsidian` capability row (Profile G3, `SKILL.md` §Capability IDs — pre-checked on only when both the `claude` CLI and the `obsidian@obsidian-skills` marketplace plugin are detected present; off otherwise). No question fires here; this phase reads the resolved capability set. When `obsidian` is selected: run all sub-steps (8d.1–8d.6); each is independently idempotent, already-installed surfaces are silently skipped. When `obsidian` is not selected: skip Phase 8d entirely — re-run `/onboard-project --with obsidian` later when ready, all sub-steps are idempotent.

**Action when `obsidian` is selected.** Run sub-steps 8d.1 through 8d.6 in order. Each sub-step prints one line on completion or skip.

### Sub-step 8d.1 — `.gitignore` Obsidian block

**Predicate.** `grep -q '^# Obsidian$' .gitignore`. If present: skip with notice `8d.1: skipped (.gitignore Obsidian block already present)`.

**Action.** Append to `.gitignore` (create if absent):

```gitignore
# Obsidian
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.obsidian/cache/
.obsidian/appearance.json
.obsidian/*.compat.json
.obsidian/hotkeys.json
```

Print: `8d.1: Obsidian .gitignore block appended`.

### Sub-step 8d.2 — Verify `claude` CLI present

**Predicate.** `command -v claude >/dev/null 2>&1`. If absent:

> `claude CLI not found — run install.sh code on the operator machine, then re-run this phase.`

Skip sub-steps 8d.3–8d.6. Print: `8d.2: claude CLI not found — skipping remaining sub-steps`.

If present, continue. Print: `8d.2: claude CLI found`.

### Sub-step 8d.3 — Verify marketplace plugin installed

**Predicate.** `claude plugin list 2>/dev/null | grep -q "obsidian@obsidian-skills"`. If the plugin is present: skip with notice `8d.3: skipped (obsidian@obsidian-skills already installed at user scope)`.

**Action when plugin is absent.** Warn:

> `Obsidian skills plugin not installed — run ./install.sh code, then re-run /onboard-project`

Skip sub-steps 8d.4–8d.6. Print: `8d.3: obsidian@obsidian-skills not installed — skipping remaining sub-steps`.

If the plugin is found, print: `8d.3: obsidian@obsidian-skills verified at user scope`.

### Sub-step 8d.4 — `.obsidian/app.json` link-safety config

**Why this exists.** Because the repository doubles as a vault, Obsidian's default link behavior would let vault tooling corrupt project-artifact links. New links default to `[[wikilink]]` form (Praxion uses Markdown `[text](path)` links and ADR id cross-references), and "Automatically update internal links" can rewrite link bodies across files on rename/move. Pinning two keys in `.obsidian/app.json` closes both vectors. Only these two keys are written, merged non-destructively — all other `.obsidian/app.json` keys (and the rest of `.obsidian/`) stay Obsidian-managed. `app.json` is committed (the `.gitignore` block from 8d.1 ignores workspace/cache/appearance/hotkeys, not `app.json`), so every clone inherits the safe defaults.

**Predicate.** Both keys already set to the safe values:
```bash
jq -e '(.useMarkdownLinks == true) and (.alwaysUpdateLinks == false)' \
  .obsidian/app.json 2>/dev/null
```
If exit 0 (both already pinned): skip with notice `8d.4: skipped (.obsidian/app.json link-safety keys already pinned)`.

**Action.** Create `.obsidian/` if absent, then merge the two keys into `.obsidian/app.json` (create `{}` if absent), preserving all existing keys:
```bash
mkdir -p .obsidian
[ -f .obsidian/app.json ] || echo '{}' > .obsidian/app.json
jq '.useMarkdownLinks = true | .alwaysUpdateLinks = false' \
  .obsidian/app.json > .obsidian/app.json.tmp && \
  mv .obsidian/app.json.tmp .obsidian/app.json
```

Print: `8d.4: .obsidian/app.json link-safety keys pinned (useMarkdownLinks=true, alwaysUpdateLinks=false)`.

### Sub-step 8d.5 — Append `## Obsidian Integration` block to `CLAUDE.md`

**Predicate.** `grep -q '^## Obsidian Integration$' CLAUDE.md`. If present: skip with notice `8d.5: skipped (## Obsidian Integration block already in CLAUDE.md)`.

**Action.** `CLAUDE.md` is guaranteed present (bootstrapped at §Phase 0.5). Append the §Obsidian Integration Block verbatim from this command's body at the end of the file with one blank line separating from preceding content.

Print: `8d.5: ## Obsidian Integration block appended to CLAUDE.md`.

### Sub-step 8d.5b — Write `permissions.deny` to `.claude/settings.json`

**Predicate.** Check whether all required deny entries are already present — a subset check, so re-running on a project onboarded under an older (smaller) entry set still adds the missing entries:
```bash
jq -e --argjson req '[
  "Bash(obsidian eval*)",
  "Bash(obsidian plugin:install*)",
  "Bash(obsidian plugin:enable*)",
  "Bash(obsidian plugin:disable*)",
  "Bash(obsidian plugin:uninstall*)",
  "Bash(obsidian theme:set*)",
  "Bash(obsidian theme:install*)",
  "Bash(obsidian delete --permanent*)",
  "Bash(obsidian move*)",
  "Bash(obsidian rename*)"
]' '($req - (.permissions.deny // [])) | length == 0' \
  .claude/settings.json 2>/dev/null
```
If exit 0 (no required entry missing): skip with notice `8d.5b: skipped (permissions.deny obsidian entries already present)`.

**Action.** Read `.claude/settings.json` (create `{"permissions":{}}` if absent). Merge `permissions.deny` non-destructively:
- Preserve all existing top-level keys.
- Preserve the existing `permissions.allow` array.
- Add the ten deny entries below. The `jq` merge is idempotent (`unique` dedupes), so entries already present are not duplicated — and entries missing from an older install are added on re-run.

Deny entries:

```json
"Bash(obsidian eval*)",
"Bash(obsidian plugin:install*)",
"Bash(obsidian plugin:enable*)",
"Bash(obsidian plugin:disable*)",
"Bash(obsidian plugin:uninstall*)",
"Bash(obsidian theme:set*)",
"Bash(obsidian theme:install*)",
"Bash(obsidian delete --permanent*)",
"Bash(obsidian move*)",
"Bash(obsidian rename*)"
```

Use `jq` to perform the merge:

```bash
jq '.permissions.deny = ((.permissions.deny // []) +
  ["Bash(obsidian eval*)",
   "Bash(obsidian plugin:install*)",
   "Bash(obsidian plugin:enable*)",
   "Bash(obsidian plugin:disable*)",
   "Bash(obsidian plugin:uninstall*)",
   "Bash(obsidian theme:set*)",
   "Bash(obsidian theme:install*)",
   "Bash(obsidian delete --permanent*)",
   "Bash(obsidian move*)",
   "Bash(obsidian rename*)"]
  | unique)' .claude/settings.json > .claude/settings.json.tmp && \
  mv .claude/settings.json.tmp .claude/settings.json
```

Print: `8d.5b: permissions.deny Obsidian CLI block written to .claude/settings.json`.

**Security note.** Eight of the denied subcommands are blocked for security: `obsidian eval` executes arbitrary JavaScript in the Obsidian renderer (remote code execution risk); the plugin lifecycle commands expose OS-level attack surface; `theme:set`/`theme:install` run theme code with app privileges; `obsidian delete --permanent` bypasses the trash and is unrecoverable. The remaining two — `move` and `rename` — are blocked for **link integrity**, not security: renaming or moving a tracked file through Obsidian can rewrite link bodies across the repo and hides the rename from git. Renames go through `git mv` instead. The `*` wildcard after each subcommand blocks all argument forms. Live end-to-end verification (actually calling a denied subcommand and observing the harness reject it) is deferred to first use in a Claude Code session with this `settings.json` applied.

### Sub-step 8d.6 — Print summary

Print:

```text
Obsidian integration install complete:
  obsidian@obsidian-skills plugin: verified at user scope (run: claude plugin list | grep obsidian-skills)
  .obsidian/app.json: link-safety keys pinned (or already present)
  CLAUDE.md: ## Obsidian Integration block appended (or already present)
  .claude/settings.json: permissions.deny Obsidian CLI block written (or already present)

CLI allowlist policy: obsidian file CRUD, search, link analysis, properties, tags, and
read-only diagnostics are ALLOWED. Dangerous subcommands (eval, plugin lifecycle, theme:set,
delete --permanent) are DENIED for security; file move/rename are DENIED for link integrity
(use git mv). Link safety: .obsidian/app.json pins Markdown-form links and disables Obsidian's
auto link-rewrite, so vault tooling cannot corrupt project-artifact links.

See docs/obsidian-integration.md for installation, configuration, troubleshooting, and the
full allowlist rationale.
```

**Verification handoff.** After all sub-steps complete, the summary above serves as the handoff. Phase 9 verification handoff lists every staged file across all phases — Phase 8d's surfaces are included in that enumeration.

## §Phase 8e — Code-quality baseline (opt-in, default-yes)

**Why this phase exists.** Praxion's onboarding establishes universal infrastructure and domain scaffolds, but historically left a gap: it never established the **code-quality baseline** every project needs. The `coding-style.md` mandate "every change must pass the linters/formatters/type-checks" is vacuous when no config exists, and the agent-readiness rubric flags the absences across four pillars: Style (`c.style.linter_config`, `c.style.formatter_config`, `c.style.editorconfig` at L1–L2; `c.style.precommit_config` at L3), Code Quality (`c.codequality.typecheck_config` at L3), Documentation (`c.docs.contributing` at L3), and Security (`c.security.dependency_scanning` at L3). This phase closes the gap from first principles: it installs the **canonical, single-sourced baselines** so the mandate is real and the rubric passes. The configs are owned by the language skills and `claude/project-baseline/`, never hand-rolled here — see [`coding-style.md`](../../../rules/swe/coding-style.md) § Baseline Configuration. Runtime-service signals (a logging dependency, a health check) are deliberately *not* installed here — they are service-conditional, not universal: the `observability` skill owns them and a feature pipeline wires them when a service is actually built (forcing them onto a library or research harness would be wrong).

**Stack reuse.** This phase consumes the **Stack detection** captured in §Pre-flight (step 4) — Python, JavaScript/TypeScript, etc. It performs no new detection beyond reading `package.json` dependencies to distinguish framework (React/Vue/Next) from non-framework JS/TS.

**Asset resolution.** Canonical assets live in the praxion plugin install (the `installPath` captured in §Pre-flight): `skills/python-development/assets/{ruff-baseline.toml, mypy-baseline.toml, pytest-baseline.toml}`, `skills/typescript-development/assets/{biome.json, eslint.config.mjs, prettierrc.json, tsconfig.json}`, `claude/project-baseline/{editorconfig, pre-commit-config.yaml, CONTRIBUTING.md.tmpl, dependabot.yml.tmpl}`, `claude/project-baseline/ci-autofix/{ci-autofix.yml.tmpl, autofix-policy.yml.tmpl, cross-model-review.yml.tmpl}`, `claude/project-baseline/labels/{labels.yml.tmpl, labels-reconcile.yml.tmpl}`, and `claude/project-baseline/tests/{test.yml.tmpl, test-scheduled.yml.tmpl, declared-deps.toml, acceptance-README.md, e2e-README.md}`. Read the asset from there; write the materialized file into the project. Edit the asset (never the per-project copy) to evolve the baseline.

**Selection.** Three independent capability rows (Profile G3, `SKILL.md` §Capability IDs) govern this phase's sub-steps — no question fires here, this phase reads the resolved capability set: `quality` (sub-steps 8e.1–8e.7 — pre-checked on if any stack was detected in §Pre-flight, off otherwise), `ci` (sub-steps 8e.8–8e.9 — pre-checked **off** by default, on only under `--profile all`, since it is the only capability with out-of-band prerequisites — two `gh secret set` calls), and `tests` (sub-steps 8e.10–8e.13 — pre-checked on in `new` mode, off in `existing` mode, included under `--profile all`). Each sub-step is independently idempotent and skips when its config already exists; none overwrites an existing config — the baseline is additive only.

**Action.** When `quality` is selected, run sub-steps 8e.1 through 8e.7 in order. When `ci` is selected, run sub-steps 8e.8 through 8e.9 in order. When `tests` is selected, run sub-steps 8e.10 through 8e.13 in order. Any combination may run per the Profile's resolved selection. Each sub-step prints one line on completion or skip.

### Sub-step 8e.1 — Universal `.editorconfig`

**Predicate.** `.editorconfig` exists at the repo root → skip with `8e.1: skipped (.editorconfig already present)`.

**Action.** Copy `claude/project-baseline/editorconfig` (from the plugin install) to `<repo-root>/.editorconfig`, stripping the leading template-doc comment lines. Print: `8e.1: .editorconfig installed (universal baseline)`.

### Sub-step 8e.2 — Python linter + formatter (ruff)

**Predicate.** No Python signal in the detected stack → skip with `8e.2: skipped (no Python detected)`. OR `pyproject.toml` already contains a `[tool.ruff]` section → skip with `8e.2: skipped ([tool.ruff] already configured)`.

**Action.** If `pyproject.toml` exists, append the `[tool.ruff]`, `[tool.ruff.lint]`, and `[tool.ruff.format]` blocks from `skills/python-development/assets/ruff-baseline.toml` (this single asset satisfies both the linter and formatter criteria). If no `pyproject.toml` exists, emit `8e.2: deferred (no pyproject.toml — add a build manifest first, then re-run)` rather than creating one (manifest creation is the project-management skill's concern). Print: `8e.2: ruff lint+format config appended to pyproject.toml`.

### Sub-step 8e.2b — Rust formatter + linter policy + toolchain pin

**Predicate.** No Rust signal in the detected stack (`Cargo.toml` absent) → skip the whole sub-step with `8e.2b: skipped (no Rust detected)`. This is the only whole-sub-step gate — each of the three artifacts below independently guards its own write, so a partially-set-up project (e.g. one that already hand-wrote `rustfmt.toml` but has no `[lints]` policy or toolchain pin yet) still gets the artifacts it is missing.

**Action.**

1. **`rustfmt.toml`.** If `rustfmt.toml` / `.rustfmt.toml` already exists at the repo root, skip this item with `8e.2b: rustfmt.toml skipped (already present)`. Otherwise copy `skills/rust-development/assets/rustfmt.toml` (from the plugin install) to `<repo-root>/rustfmt.toml`, stripping the leading template-doc comment lines.
2. **`[lints]` policy.** Determine whether the repo-root `Cargo.toml` is a **virtual manifest** (`[workspace]` present, no `[package]` table) or a **package manifest** (`[package]` present):
   - **Package form.** If the root `Cargo.toml` declares no `[lints.rust]` / `[lints.clippy]` table yet, append the package-form `[lints.rust]` / `[lints.clippy]` blocks from `skills/rust-development/assets/cargo-lints.toml`.
   - **Workspace form.** If the root `Cargo.toml` is a virtual manifest, append the asset's `[workspace.lints.rust]` / `[workspace.lints.clippy]` blocks (the asset's commented workspace-form section, uncommented) to the root manifest. Then, for every member listed under `[workspace.members]` whose own `Cargo.toml` does not already declare a `[lints]` table, append:
     ```toml
     [lints]
     workspace = true
     ```
   - Never overwrite a manifest (root or member) that already declares `[lints]` / `[lints.rust]` / `[lints.clippy]` / `[workspace.lints.*]`.
3. **`rust-toolchain.toml`.** If neither `rust-toolchain.toml` nor the legacy bare-channel `rust-toolchain` file exists at the repo root, copy `skills/rust-development/assets/rust-toolchain.toml`, stripping the leading template-doc comment lines.
4. **`cargo-deny` — print, never run.** Print (do not execute): `cargo deny init` — scaffolds a `deny.toml` for dependency-policy enforcement (license/advisory/ban rules); a deliberate per-project decision the user runs by hand (same print-not-run precedent as sub-step 8e.3's npm install command).
5. **Never scaffold `clippy.toml`.** Unlike `[lints]` (a *level* policy this baseline can set safely), `clippy.toml` holds project-specific lint *values* (cognitive-complexity thresholds, MSRV, disallowed-methods lists) with no universal baseline to ship.

Print: `8e.2b: rustfmt.toml + Cargo.toml [lints] policy + rust-toolchain.toml installed (Rust code-quality baseline)` — or, when one artifact was individually skipped, a per-artifact variant, e.g. `8e.2b: rustfmt.toml installed; [lints] policy skipped (already present); rust-toolchain.toml installed`.

### Sub-step 8e.3 — JS/TS linter + formatter (Biome, or ESLint+Prettier for frameworks)

**Predicate.** No JavaScript/TypeScript signal (`package.json` absent) → skip with `8e.3: skipped (no JS/TS detected)`. OR any of `biome.json` / `biome.jsonc` / `eslint.config.*` / `.eslintrc.*` already exists → skip with `8e.3: skipped (JS/TS linter already configured)`.

**Action.** Read `package.json` dependencies. If a framework is present (`react`, `vue`, or `next`), install `eslint.config.mjs` + `prettierrc.json` (→ `.prettierrc.json`) from the typescript-development assets — framework ESLint plugins have no Biome equivalent (see the skill's Biome-vs-ESLint decision rule). Otherwise install `biome.json` (one tool, lint + format). Do **not** install npm dev-dependencies; print the one-line install command instead (`npm i -D @biomejs/biome`, or `npm i -D eslint @eslint/js typescript-eslint prettier` for the framework path). Print: `8e.3: <biome.json | eslint.config.mjs + .prettierrc.json> installed (run the printed npm install to enable)`.

### Sub-step 8e.4 — Pre-commit config (linter + formatter + secret scanner)

**Predicate.** `.pre-commit-config.yaml` OR `.pre-commit-config.yml` exists at the repo root → skip with `8e.4: skipped (pre-commit config already present)`.

**Action.** Read `claude/project-baseline/pre-commit-config.yaml` (from the plugin install) and write it to `<repo-root>/.pre-commit-config.yaml`, stripping the leading template-doc comment lines. Then **strip the non-applicable language blocks** per the detected stack: remove the `# --- PYTHON` repo block when no Python signal is present, the `# --- JS/TS` repo block when `package.json` is absent, and the `# --- RUST` repo block when `Cargo.toml` is absent. The `# --- UNIVERSAL` block (file hygiene + the gitleaks secret scanner) is always kept. Do **not** run `pre-commit install` for the user; print the one-line activation command instead. Print: `8e.4: .pre-commit-config.yaml installed (run \`pre-commit install\` once to activate the git hook)`.

### Sub-step 8e.5 — Static type-checker config

**Predicate.** **Python path:** `pyproject.toml` already contains a `[tool.mypy]` or `[tool.pyright]` section, OR `mypy.ini` / `.mypy.ini` / `pyrightconfig.json` exists → skip the Python action with `8e.5: skipped (Python type-checker already configured)`. **TS path:** `tsconfig.json` exists → skip the TS action with `8e.5: skipped (tsconfig.json already present)`. **Rust path:** `Cargo.toml` detected → always the named skip below (there is no config to install or to check for pre-existence). With none of Python, JS/TS, or Rust detected → skip entirely with `8e.5: skipped (no typed stack detected)`.

**Action.** For a Python stack with a `pyproject.toml`: append the `[tool.mypy]` block from `skills/python-development/assets/mypy-baseline.toml` (this satisfies the type-check criterion via the `[tool.mypy]` section). If Python is detected but no `pyproject.toml` exists, emit `8e.5: deferred (no pyproject.toml — add a build manifest first, then re-run)`. For a JS/TS stack: install `tsconfig.json` from `skills/typescript-development/assets/tsconfig.json` (strict baseline). Wire type-checking into CI is the project's concern (the `cicd` skill owns the workflow step); the config presence is what the rubric checks. Print: `8e.5: <mypy config appended to pyproject.toml | tsconfig.json installed>`.

**Rust action.** No separate type-checker config exists or is installed for Rust — the compiler *is* the type checker, and `[lints]` (installed in sub-step 8e.2b) carries the policy layer a config file would otherwise hold. Print the explicit named skip: `8e.5: skipped (Rust — the compiler is the type checker; no separate config)`.

### Sub-step 8e.6 — Contributing guide

**Predicate.** Any of `CONTRIBUTING.md` / `CONTRIBUTING.rst` / `CONTRIBUTING` / `docs/CONTRIBUTING.md` / `.github/CONTRIBUTING.md` exists → skip with `8e.6: skipped (contributing guide already present)`.

**Action.** Read `claude/project-baseline/CONTRIBUTING.md.tmpl` (from the plugin install). Strip the leading HTML template-doc comment, then fill the `<lint command>` / `<typecheck command>` / `<test command>` / `<build command>` placeholders per [shared-procedures.md § Stack command resolution](shared-procedures.md#-stack-command-resolution) — reuse the exact values already resolved for Phase 6's Project Essentials block rather than re-deriving them. Write the result to `<repo-root>/CONTRIBUTING.md`. Print: `8e.6: CONTRIBUTING.md installed (filled from detected stack commands)`.

### Sub-step 8e.7 — Dependency-scanning config

**Predicate.** Any of `.github/dependabot.yml` / `.github/dependabot.yaml` / `renovate.json` / `.renovaterc` / `.renovaterc.json` / `.snyk` exists → skip with `8e.7: skipped (dependency-scanning config already present)`.

**Action.** Read `claude/project-baseline/dependabot.yml.tmpl` (from the plugin install). Strip the leading template-doc comment lines. Emit `updates:` blocks only for detected ecosystems: a Python manifest present anywhere in the repo → include the `pip` block with `directory:` set to the discovered manifest directory; a `package.json` present anywhere in the repo → include the `npm` block with `directory:` set to the discovered `package.json` directory; a `Cargo.toml` present anywhere in the repo → include the `cargo` block with `directory:` set to the discovered manifest directory (a workspace's root virtual manifest counts as one directory — dependabot resolves the whole workspace's `Cargo.lock` from there, not per-member manifest); a `.github/workflows/` directory present → include the `github-actions` block. Multiple Python, npm, or Cargo manifests at different directories each get their own `updates:` entry. Strip blocks for undetected ecosystems. Write the result to `<repo-root>/.github/dependabot.yml` (creating `.github/` if absent). Print: `8e.7: .github/dependabot.yml installed (dependency scanning enabled for detected ecosystems)`.

### Sub-step 8e.8 — CI autofix caller + policy + cross-model review gate

**Predicate.** `.github/workflows/ci-autofix.yml` OR `.github/autofix-policy.yml` already exists at the repo root → skip with `8e.8: skipped (ci-autofix caller or policy already present)`. Never overwrite an existing installation — this mirrors 8e.7's file-existence guard exactly.

**Action.** Read `claude/project-baseline/ci-autofix/ci-autofix.yml.tmpl`, `claude/project-baseline/ci-autofix/autofix-policy.yml.tmpl`, and `claude/project-baseline/ci-autofix/cross-model-review.yml.tmpl` (from the plugin install) and strip each file's leading template-doc comment header. Fill the caller template's three placeholders:

- `{{WATCHED_WORKFLOWS}}` → the comma-separated, quoted names of the project's own CI workflows (detected under `.github/workflows/`, confirmed with the user). GitHub Actions requires `on.workflow_run.workflows` to be a static literal, so this cannot be read from the policy at runtime — keep it in sync with the policy's `watched_workflows` by hand. **When `tests` is also selected in this run**, include `"Test"` and `"Test (scheduled)"` in both lists even though sub-step 8e.13 writes those workflows later — omit a name only when 8e.13 will skip that workflow because its file already exists (the existing file is then detected above and watched under its own `name:`).
- `{{PRAXION_HUB}}` → `francisco-perez-sorrosal/praxion` (the public hub's owner/repo).
- `{{HUB_SHA}}` → resolved per [shared-procedures.md § Hub SHA resolution and template self-check](shared-procedures.md#-hub-sha-resolution-and-template-self-check).

After writing, apply the `{{`-survivor self-check from that same section to `.github/workflows/ci-autofix.yml`.

Write the rendered caller to `<repo-root>/.github/workflows/ci-autofix.yml` and the rendered policy to `<repo-root>/.github/autofix-policy.yml` (creating `.github/workflows/` if absent).

**Cross-model review gate (policy-gated, own idempotency guard).** IF `.github/workflows/cross-model-review.yml` already exists → skip this part with `8e.8: cross-model caller skipped (already present)` and never overwrite it — the same file-existence idempotency guard as the ci-autofix caller above, applied to its own file. ELSE IF the policy just written has `review.cross_model_gate` explicitly set to `off` → the system never installs the cross-model caller — an explicit opt-out means the project is not forced into a second vendor's secret requirement. OTHERWISE — the install proceeds whenever `review.cross_model_gate != off` (the template default `agent-prs`, or `all-prs`, both qualify) — fill `{{PRAXION_HUB}}` and the same resolved, real, current 40-hex `{{HUB_SHA}}` into `cross-model-review.yml.tmpl`, self-check for a surviving `{{` and abort loudly if one remains, and write the rendered result to `<repo-root>/.github/workflows/cross-model-review.yml`.

Do **not** execute any secret-setup or org-configuration command on the operator's behalf — **print** these one-time manual steps instead:

- Secret setup: `gh secret set CLAUDE_CODE_OAUTH_TOKEN` — the autofixer authenticates the hub's fixer with this token; without it the fixer step no-ops.
- When the cross-model caller is installed: `gh secret set CURSOR_API_KEY` — the review gate's reviewer authenticates with this token; without it the review step no-ops. This is a real, unconditional one-time operator step whenever the caller is installed, never a deferred aside.
- Org Actions-allowlist: if the caller repo's org restricts Actions to an allowlist, the repo owner must add the hub explicitly using the reusable-workflow `OWNER/REPOSITORY/PATH/FILENAME@<ref>` syntax — e.g. `francisco-perez-sorrosal/praxion/.github/workflows/reusable-ci-autofix.yml@<HUB_SHA>` — substitute the same resolved SHA used in the caller's `uses:` line above, not the literal string `<HUB_SHA>` (or use a wildcard covering the hub). This is a one-time, deliberate operator step, never auto-injected.

Print: `8e.8: .github/workflows/ci-autofix.yml + .github/autofix-policy.yml installed (ci-autofix caller wired to the public hub — see the printed one-time operator steps to activate)`. When the cross-model caller is also installed, print an additional line: `8e.8: .github/workflows/cross-model-review.yml installed (cross-model review gate wired to the public hub)`.

**Verification handoff.** Phase 9 lists every file staged here. The agent-readiness Style, Code Quality, Documentation, and Security criteria covered by this phase (linter/formatter/editorconfig/pre-commit, type-check, contributing, dependency-scanning) flip to pass on the next `/project-metrics --refresh` run.

### Sub-step 8e.9 — Label taxonomy manifest + reconciler caller

**Predicate.** `.github/labels.yml` OR `.github/workflows/labels-reconcile.yml` already exists at the repo root → skip with `8e.9: skipped (labels manifest or reconciler caller already present)`. Never overwrite an existing installation — this mirrors sub-step 8e.8's own file-existence idempotency guard exactly.

**Action.** Read `claude/project-baseline/labels/labels.yml.tmpl` and `claude/project-baseline/labels/labels-reconcile.yml.tmpl` (from the plugin install) and strip each file's leading template-doc comment header. Fill the caller template's two placeholders:

- `{{PRAXION_HUB}}` → `francisco-perez-sorrosal/praxion` (the public hub's owner/repo).
- `{{HUB_SHA}}` → resolved per [shared-procedures.md § Hub SHA resolution and template self-check](shared-procedures.md#-hub-sha-resolution-and-template-self-check) (reuse the SHA already resolved earlier in this same onboarding run if sub-step 8e.8 ran first).

After writing, apply the `{{`-survivor self-check from that same section to `.github/workflows/labels-reconcile.yml`.

Write the rendered manifest to `<repo-root>/.github/labels.yml` and the rendered caller to `<repo-root>/.github/workflows/labels-reconcile.yml` (creating `.github/workflows/` if absent).

Print: `8e.9: .github/labels.yml + .github/workflows/labels-reconcile.yml installed (label taxonomy reconciler wired to the public hub)`.

**Verification handoff.** Phase 9 lists every file staged here. Committing `.github/labels.yml` triggers the reconciler on push, so any label the self-healing loop depends on is created or updated automatically — no manual `gh label create` needed.

### Sub-step 8e.10 — Test runner config (parallel on, coverage off)

**Predicate.** **Python path:** `pyproject.toml` already contains a `[tool.pytest.ini_options]` section, OR `pytest.ini` exists, OR `tox.ini` contains `[pytest]`, OR `setup.cfg` contains `[tool:pytest]` → skip with `8e.10: skipped (pytest already configured)`. **JS/TS path** and **Rust path:** always the named notes below — there is no config to install. With none of Python, JS/TS, or Rust detected → skip with `8e.10: skipped (no test stack detected)`.

**Action.** For a Python stack with a `pyproject.toml`: append the `[tool.pytest.ini_options]` block from `skills/python-development/assets/pytest-baseline.toml` — `-n auto --dist load` parallelism, the `large` marker deselected by default, and no `--cov` (coverage is the CI backstop's measurement, taken in 8e.13's workflow). If Python is detected but no `pyproject.toml` exists, emit `8e.10: deferred (no pyproject.toml — add a build manifest first, then re-run)`. Do **not** install dev dependencies; print the detected manager's one-line add command instead (e.g. `uv add --dev pytest pytest-xdist pytest-cov`). Print: `8e.10: parallel, coverage-off pytest config appended to pyproject.toml (run the printed install; debug one test with -n 0)`.

**JS/TS note.** vitest and jest already run test files in parallel with coverage off by default. Print: `8e.10: skipped (JS/TS — the runner is parallel and coverage-off by default)`.

**Rust note.** Print (do not execute) the parallel-runner suggestion: `8e.10: suggestion — cargo install cargo-nextest --locked (process-per-test parallelism; keep cargo test --doc for doc-tests)`.

### Sub-step 8e.11 — Outer-loop test directories

**Predicate.** Each of the two READMEs guards its own write: `tests/acceptance/README.md` exists → skip that item; `tests/e2e/README.md` exists → skip that item. An existing directory without a README still gets one; no existing test file is touched.

**Action.** Copy `claude/project-baseline/tests/acceptance-README.md` to `<repo-root>/tests/acceptance/README.md` and `claude/project-baseline/tests/e2e-README.md` to `<repo-root>/tests/e2e/README.md`, creating the directories if absent. Each README states the ownership rule: the implementer runs these tests but never edits them. Print: `8e.11: tests/acceptance/ + tests/e2e/ installed (outer-loop tests — run, never edited, by the implementer)`, or a per-item variant when one README was individually skipped.

### Sub-step 8e.12 — Declared test-dependency list

**Predicate.** `tests/declared-deps.toml` exists → skip with `8e.12: skipped (tests/declared-deps.toml already present)`.

**Action.** Copy `claude/project-baseline/tests/declared-deps.toml` verbatim to `<repo-root>/tests/declared-deps.toml` — `schema = 1` and no entries. Keep its header comment: it is the file's own documentation of the `[[dep]]` / `[[inert]]` entry kinds, not a template-doc header. The file lives under `tests/` whatever the project's test layout (co-located or mirrored). Print: `8e.12: tests/declared-deps.toml installed (empty — test selection is derived from the code; add entries only for non-code dependencies)`.

### Sub-step 8e.13 — Test and scheduled test-health workflows

**Predicate.** Placement is `sidecar` → skip with `8e.13: skipped (sidecar placement — workflows are GitHub-visible by construction)`. Otherwise each workflow guards its own write: `.github/workflows/test.yml` exists → skip that workflow with `8e.13: test.yml skipped (already present)`; `.github/workflows/test-scheduled.yml` exists → skip that workflow likewise. A Rust-only stack skips the scheduled workflow with `8e.13: test-scheduled.yml skipped (Rust — no scheduled health job for this stack)`. Never overwrite an existing workflow.

**Action.** Read `claude/project-baseline/tests/test.yml.tmpl` and `claude/project-baseline/tests/test-scheduled.yml.tmpl` (from the plugin install) and strip each file's leading template-doc comment header. **Strip the non-applicable stack blocks** exactly as sub-step 8e.4 does: remove the `# --- PYTHON` job when no Python signal is present, the `# --- JS/TS` job when `package.json` is absent, and the `# --- RUST` job when `Cargo.toml` is absent. When a kept stack's manifest lives in a subdirectory, set that job's `defaults.run.working-directory` to the manifest directory; when the default branch is not `main`, rewrite the `branches:` filters to it. Fill the placeholders:

- `{{FULL_TEST_COMMAND}}` → filled per kept block with that stack's full-suite command, resolved per [shared-procedures.md § Stack command resolution](shared-procedures.md#-stack-command-resolution). Each block appends runner flags, so the value must invoke the runner directly — `uv run pytest` (not a wrapper script), `npx vitest run` or `pnpm exec vitest run` (not `npm test`), `cargo test --workspace`. The Python blocks set up uv; when the project uses another manager, replace that setup step with the manager's own and print a one-line `8e.13: TODO` naming the swap. The JS/TS blocks assume vitest; for another runner, drop the scheduled block's junit reporter flags and print a `8e.13: TODO` naming the runner's junit equivalent.
- `{{COVERAGE_FLOOR}}` (Python block only) → `new` mode: `80`. `existing` mode: the root `line-rate` of `coverage.xml` × 100, rounded down, when that file is present; otherwise `0`, with a printed `8e.13: coverage floor set to 0 — raise it to the measured value after the first CI run`. The floor is a ratchet: it only ever rises.
- `{{PRAXION_HUB}}`, `{{HUB_SHA}}` (scheduled workflow) → resolved per [shared-procedures.md § Hub SHA resolution and template self-check](shared-procedures.md#-hub-sha-resolution-and-template-self-check), reusing the SHA already resolved earlier in this run. The scheduled job sparse-checks out the hub's `scripts/` at that SHA to run the selection audit; when the hub cannot be fetched it warns and skips the audit only.

After writing, apply the `{{`-survivor self-check from that same section to both installed files — placeholder tokens only; GitHub `${{ … }}` expressions are not placeholders. Write the rendered results to `<repo-root>/.github/workflows/test.yml` and `<repo-root>/.github/workflows/test-scheduled.yml` (creating `.github/workflows/` if absent).

**Watched-workflow rule.** When `ci` ran in this same run, sub-step 8e.8 already listed `"Test"` and `"Test (scheduled)"` among its watched workflows. When a ci-autofix installation already existed (8e.8 skipped), never edit it — print: `8e.13: add "Test" and "Test (scheduled)" to .github/workflows/ci-autofix.yml's workflows list and to .github/autofix-policy.yml's watched_workflows by hand`. For a private hub fork or an org Actions allowlist, print the same one-time allowlist step 8e.8 prints, naming the hub.

Print: `8e.13: .github/workflows/test.yml + .github/workflows/test-scheduled.yml installed (full parallel suite with a <floor>% coverage floor; weekly flaky/large/selection-audit/slow-test job)`, or a per-workflow variant when one was individually skipped.

**Testing block.** After 8e.13, append the `## Testing` block per [claude-md-blocks.md § Testing Block](claude-md-blocks.md) (guarded by `grep -q '^## Testing$'`; installed once, never refreshed), filling its placeholders from what this run detected.

**Verification handoff.** Phase 9 lists every file staged by sub-steps 8e.10–8e.13 and the `## Testing` block. The first push runs `test.yml`; the scheduled job first runs on its weekly cron, or on demand via `workflow_dispatch`.
