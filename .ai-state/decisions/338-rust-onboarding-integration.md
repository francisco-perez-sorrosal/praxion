---
id: dec-338
title: Rust onboarding lands as lettered sub-step 8e.2b with install-vs-print split and repo-local pre-commit hooks
status: accepted
category: architectural
date: 2026-08-30
summary: Add a lettered /onboard-project sub-step 8e.2b installing the Rust formatter, lint-policy and toolchain baselines from skills/rust-development/assets/, add Rust predicates to the pre-commit and Dependabot shipped templates with a repo-local (unpinned) Rust hook block, print rather than install policy-laden configs, and emit a named skip for the type-checker sub-step — rejecting both terminal-substep placement and renumbering.
tags: [onboarding, rust, cargo, shipped-templates, pre-commit, dependabot, code-quality-baseline, idempotency]
made_by: agent
agent_type: systems-architect
branch: worktree-data-structures-pillar
pipeline_tier: full
dissent: "A pinned upstream pre-commit repo gives hermetic, version-reproducible Rust hooks that do not depend on each contributor's local toolchain — the same property that makes the existing ruff hook reproducible — and repo-local system hooks trade that away for a class of contributor-machine failures."
affected_files:
  - skills/onboard-project/SKILL.md
  - skills/onboard-project/references/seed-pipeline.md
  - claude/project-baseline/pre-commit-config.yaml
  - claude/project-baseline/dependabot.yml.tmpl
  - skills/rust-development/assets/rustfmt.toml
  - skills/rust-development/assets/cargo-lints.toml
  - skills/rust-development/assets/rust-toolchain.toml
  - rules/swe/coding-style.md
affected_reqs: [REQ-05]
---

## Context

`/onboard-project` Phase 8e installs the code-quality baseline that makes the coding-style rule's
"every change must pass the linters/formatters/type-checks" mandate non-vacuous. Every one of its
sub-steps branches on Python-detected or JS/TS-detected. A codebase survey established the
consequence precisely: **a Rust-only project run through onboarding today receives zero linter
config, zero formatter config, zero type-check-equivalent config, and zero dependency-scanning
config**, because no sub-step's predicate ever fires for it. This is the single largest
onboarding-side hole in the Rust parity inventory.

Pre-flight stack detection already recognizes `Cargo.toml`. The gap was never detection — it is
that the detection result is never consumed downstream.

Three sub-questions had to be settled together, because they interact: where the new sub-step
sits in a heavily cross-referenced phase; which Rust configs are safe to install unconditionally
versus which encode project policy; and how the shipped pre-commit template expresses Rust hooks
given that this very file already carries a long comment documenting a costly version-skew
failure with its pinned Python hook.

## Decision

**Placement.** A new lettered sub-step **8e.2b — Rust formatter + linter + toolchain baseline**,
inserted immediately after the Python lint/format sub-step. Lettered insertion is the existing
idiom in this command (`5a`/`5b`, phases `8b`–`8e`, sub-step `8d.5b`) and avoids renumbering a
document other artifacts point into.

**Install vs print.** The sub-step **installs** the mechanical, policy-free baselines sourced
from `skills/rust-development/assets/`: `rustfmt.toml` (stable keys only), the `[lints.*]` block
(package form, or the workspace form plus member `lints.workspace = true` when a virtual root
manifest is detected), and `rust-toolchain.toml`. It **prints** guidance for policy-laden configs
— `cargo deny init` — and scaffolds no `clippy.toml` at all, because an unused config file is a
trap for later readers. This mirrors the existing precedent of printing the npm install command
rather than running it.

**Adjacent predicates.** The pre-commit sub-step gains a keep-or-strip predicate for a new
`# --- RUST` block; the dependency-scanning sub-step gains one for a `cargo` ecosystem block; the
type-checker sub-step gains an **explicit named skip** for Rust stating that the compiler is the
type checker and `[lints]` carries the policy, so the absence is visibly considered rather than
silently unhandled.

**Pre-commit hook style.** The Rust block uses `repo: local` with `language: system`
(`cargo fmt --all --`, `types: [rust]`, `pass_filenames: false`), with a commented-out clippy hook
as an opt-in. No external repository, therefore no `rev:` pin.

**Companion CLIs.** Phase 7 gains one Rust row (`cargo-nextest`) plus an explicit sentence
recording that there is deliberately no Rust package-manager row, because Cargo ships with the
toolchain and has no analogue to the Python `uv` recommendation.

## Considered Options

### Option 1 — Lettered sub-step 8e.2b (chosen)

**Pros.** No renumbering. Keeps the lint/format concern grouped where a reader expects it. Matches
four existing lettered-insertion precedents in the same command.

**Cons.** Adds a second lettered level to the sub-step numbering.

### Option 2 — Terminal sub-step appended after the existing nine

**Pros.** Strictly append-only; zero risk of disturbing existing numbering or cross-references.

**Cons.** Scatters the lint/format concern across the phase, so a reader scanning for "where does
formatting get installed" finds Python early, JS/TS early, and Rust last, after unrelated CI and
label sub-steps.

### Option 3 — Renumber so Rust becomes a peer sub-step and JS/TS shifts down

**Pros.** Cleanest final numbering; three peer language sub-steps in a row.

**Cons.** A gratuitous breaking change to a heavily cross-referenced document for a cosmetic gain.
Every existing reference to the shifted sub-steps would need auditing.

### On the pre-commit hook style — pinned upstream repo vs `repo: local`

A pinned third-party Rust pre-commit repo would give hermetic, reproducible hooks independent of
the contributor's local toolchain. It was rejected because this exact template already carries an
extended comment documenting the cost of that model for Python: two independently-versioned
formatters never converge, the commit never settles, and pre-commit's stash/restore around each
failed attempt can silently revert uncommitted work. A `repo: local` hook runs the project's own
`cargo fmt` — the same binary the developer and CI use — so the skew class cannot arise. Its
failure mode ("cargo: command not found") is loud and self-explanatory.

## Consequences

### Positive

- A Rust-only project stops receiving nothing from the phase whose stated purpose is making the
  code-quality mandate real.
- The `cargo` Dependabot block is the cheapest item in the entire parity inventory — the
  ecosystem is natively supported upstream and unused.
- Zero renumbering; every existing cross-reference into Phase 8e stays valid.
- The named type-checker skip converts a silent absence into a documented, considered non-action.
- No external `rev:` pin means no Rust pin-drift checker is needed by construction.

### Negative

- The `repo: local` hooks require `cargo` on PATH at commit time and fail when it is missing.
  Accepted deliberately: a loud, obvious failure beats a silent version-skew class.
- Sub-step numbering grows a second lettered level.
- Two shipped templates and one command gain Rust-conditional branches that must be kept in sync
  with the paired greenfield command.

### Neutral

- The four canonical `CLAUDE.md` blocks are untouched, so the shipped-block sync check is
  unaffected — but it must be run as an acceptance gate rather than assumed.

## Disconfirmation

**Falsifier.** If `repo: local` + `language: system` hooks prove unreliable across contributor
machines for reasons other than "Rust is not installed" — differing toolchain channels producing
different formatting, say — then the hermeticity argument wins and a pinned upstream repo was
right despite its drift class.

**Steelmanned runner-up.** The pinned-repo case is stronger than the rejection above concedes.
Pre-commit's whole value proposition is that the hook environment is reproducible and does not
depend on what the contributor happens to have installed; `repo: local` opts out of that
guarantee entirely. The Python skew incident that motivates the rejection was caused by *two*
declared ruff versions disagreeing, which is an author error the tooling can detect — not an
inherent property of pinned repos. A pinned Rust repo plus a pin-coherence check would get both
reproducibility and safety.

**Reversal trigger.** The first report of a `repo: local` Rust hook producing different output
than the project's CI `cargo fmt --check`, or the appearance of a Rust pre-commit repo whose
hooks resolve the project's own toolchain rather than shipping their own.

## Relationship to the sibling skill-shape decision

This record supersedes nothing and re-affirms nothing. It is a **complementary sibling** of the
draft authored in the same pipeline that creates `skills/rust-development/` and establishes its
`assets/` directory as the source of truth. That decision settles *where the Rust baselines live*;
this one settles *when and how onboarding materializes them*. Neither constrains the other's
answer, so no supersession or re-affirmation cross-reference is warranted — recording one would
falsely flip the sibling's status at finalize.
