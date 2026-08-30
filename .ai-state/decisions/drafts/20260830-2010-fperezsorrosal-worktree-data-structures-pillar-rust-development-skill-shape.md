---
id: dec-draft-bcb2a103
title: Rust ships as one unified rust-development skill, not a rust-development / rust-prj-mgmt pair
status: proposed
category: architectural
date: 2026-08-30
summary: Create a single skills/rust-development/ skill covering language idioms, Cargo/workspace/toolchain, crate selection, unsafe/concurrency, and scaffolding — rejecting the python-development/python-prj-mgmt and typescript-development/node-prj-mgmt twin-skill split, because those splits exist to arbitrate a package-manager choice that Cargo removes, and because the unified name is the one three agent prompts already reference.
tags: [skills, polyglot, rust, cargo, skill-shape, dangling-reference, progressive-disclosure]
made_by: agent
agent_type: systems-architect
branch: worktree-data-structures-pillar
pipeline_tier: full
dissent: "Supply chain, release automation and cross-compilation are a genuinely different concern with a different audience and activation moment than type design and error hygiene; a split would keep each half small and sharply triggered, and the unified skill risks loading lifecycle material into language-only tasks and vice versa."
re_affirms: dec-139
affected_files:
  - skills/rust-development/SKILL.md
  - skills/rust-development/references/type-and-api-design.md
  - skills/rust-development/references/error-and-panic.md
  - skills/rust-development/references/toolchain-and-workspace.md
  - skills/rust-development/references/essential-crates.md
  - skills/rust-development/references/unsafe-and-concurrency.md
  - skills/rust-development/references/project-scaffolding.md
  - skills/rust-development/assets/rustfmt.toml
  - skills/rust-development/assets/cargo-lints.toml
  - skills/rust-development/assets/rust-toolchain.toml
  - agents/implementer.md
  - agents/test-engineer.md
  - agents/cicd-engineer.md
affected_reqs: [REQ-01, REQ-02, REQ-03]
---

## Context

Praxion's per-language skill surface is currently Python and TypeScript. Both ship as a **pair**:
`python-development` + `python-prj-mgmt`, and `typescript-development` + `node-prj-mgmt`. A
codebase survey established that Rust has no member of that pattern at all — while three agent
prompts (`implementer.md`, `test-engineer.md`, `cicd-engineer.md`) already instruct
"`Cargo.toml` → load `rust-development`" against a skill directory that does not exist. That
dangling reference is the single clearest signal in the whole inventory and is the anchor gap
this decision closes.

The shape question is not cosmetic. It determines whether the dangling reference self-resolves or
requires editing three agent files, where Cargo/workspace/toolchain knowledge lives relative to
language semantics, and whether Praxion's polyglot surface stays visually symmetric.

The polyglot skill template already formalizes *how* a language plugs into an existing skill
(create the leaf, add the row, update the description, leave the body alone). It does not say how
many top-level skills a language gets. That is the gap this record fills for Rust.

## Decision

Rust ships as **one unified `skills/rust-development/` skill**. Cargo, workspace layout, the
`[lints]` table, MSRV, feature flags, supply-chain tooling, and release automation live in a
`references/toolchain-and-workspace.md` leaf inside that skill, not in a separate
`rust-prj-mgmt` skill. Six reference leaves carry the depth; `assets/` carries the shipped
code-quality baselines (`rustfmt.toml`, `cargo-lints.toml`, `rust-toolchain.toml`) that
onboarding materializes into managed projects.

Two rules follow from this and bind future work:

1. **No `rust-prj-mgmt` skill is created**, now or as a matter of symmetry-restoration.
2. **`SKILL.md` body pressure is managed by progressive disclosure, not by splitting the skill.**
   Adding a reference leaf is the sanctioned response to growth.

## Considered Options

### Option 1 — Unified `skills/rust-development/` (chosen)

**Pros.** Closes the dangling reference with zero agent-file edits — the three prompts already
name this exact path. Keeps causally coupled knowledge colocated: feature flags change which code
compiles, MSRV changes which syntax is legal, and `[lints]` lives in `Cargo.toml` but configures
the compiler, so the "project management" material is not separable from language semantics in
Rust the way it is in Python or Node. One skill to discover, one activation description to tune.

**Cons.** Visual asymmetry with the two existing language pairs — a future reader may read it as
an oversight and try to "fix" it. Larger single skill; body pressure must be actively managed.

### Option 2 — Split `rust-development` + `rust-prj-mgmt`

**Pros.** Symmetric with both existing language pairs, which aids discoverability by pattern.
Each half stays small and sharply triggered. Supply chain / release / cross-compilation is a
plausibly separate audience (a CI author, a release manager) from type design and error hygiene.

**Cons.** The peer splits exist for a reason Rust does not share: `python-prj-mgmt` arbitrates
pixi vs uv, `node-prj-mgmt` arbitrates npm/pnpm/yarn/fnm. Cargo ships with the toolchain and has
no competitor, so `rust-prj-mgmt`'s thesis is one line. Requires editing three agent prompts to
add the second skill. Fragments content whose halves reference each other constantly.

### Option 3 — Unified skill plus a separate `rust-toolchain` skill

**Pros.** Splits on the axis that actually has mass (toolchain) rather than on the axis borrowed
from Python/Node (project management).

**Cons.** Invents a third naming pattern for the ecosystem to learn; still requires the three
agent edits; the toolchain/language boundary is exactly where the coupling argument in Option 1
bites hardest.

## Consequences

### Positive

- The dangling reference in three agent prompts resolves the moment the skill lands, with no
  prompt edits and therefore no risk of a partial edit leaving one agent broken.
- Toolchain and language guidance stay adjacent where their coupling is real.
- `assets/` gives onboarding a single source of truth for the Rust code-quality baseline, exactly
  as the Python and TypeScript assets do — the same install/never-overwrite contract, reused.
- Extension to a seventh reference leaf is additive and needs no structural decision.

### Negative

- Asymmetry with the Python/TS pairs is now a permanent explanation burden; mitigated by writing
  the rationale into the skill's Related Skills section rather than leaving it inferable.
- `SKILL.md` must stay under the 500-line target while covering both concerns; the six-leaf
  decomposition is the mechanism, and it puts real authoring discipline on the body.

### Neutral

- Adds one skill to the catalog and one frontmatter description to the startup surface (~1 line).
- No always-loaded token cost: skill bodies and leaves load on demand only.

## Disconfirmation

**Falsifier.** If Rust work in practice activates only the project-lifecycle material (CI
authoring, release, supply chain) and never the language material — or the reverse, consistently —
then the unified skill is loading dead weight on every activation and the split was correct.

**Steelmanned runner-up.** Option 2's strongest form is not the symmetry argument, it is the
audience argument: the person wiring a release pipeline and the person designing an error enum
are different people at different moments with different context budgets, and a skill that serves
both serves neither optimally. A split would let each half's activation description be sharp
("Cargo workspaces, MSRV, publishing" vs "type design, error hygiene, unsafe"), whereas one
description covering both is necessarily vaguer and will mis-trigger in both directions.

**Reversal trigger.** When `toolchain-and-workspace.md`, `project-scaffolding.md`, and
`essential-crates.md` collectively reach the point where a lifecycle-only consumer never opens a
language leaf, split then. Post-hoc splitting is mechanically cheap: move the leaves, create the
second skill, add three agent lines. Do not pre-split on speculation.

## Prior Decision

Re-affirms the polyglot skill template. That record formalizes the *intra-skill* extension
protocol (`contexts/` vs `references/`, the Language Contexts table, "the body is not modified")
and this decision applies it unchanged to Rust's leaves in other skills. It does not govern how
many top-level skills a language receives, so nothing in it is superseded — this record answers
an adjacent question the template deliberately left open.
