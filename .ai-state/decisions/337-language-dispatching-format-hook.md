---
id: dec-337
title: One language-dispatching format hook over a shared tool registry, replacing the Python-only format hook
status: accepted
category: architectural
date: 2026-08-30
summary: Generalize hooks/format_python.py into hooks/format_code.py backed by a new hooks/_lang_tools.py extension-to-tool registry consumed by both the PostToolUse formatter and the commit-gate quality check — rejecting parallel per-language hook files, because ~80% of the existing hook body is language-neutral and duplicating it a second and third time is a DRY violation by construction.
tags: [hooks, rust, polyglot, dry, registry, posttooluse, commit-gate, refactoring]
made_by: agent
agent_type: systems-architect
branch: worktree-data-structures-pillar
pipeline_tier: full
dissent: "Parallel per-language hooks are trivially independent — a broken Rust hook cannot regress Python formatting, each file's blast radius is exactly one language, and the registry's argv-builder indirection is real complexity bought for only two rows."
affected_files:
  - hooks/_lang_tools.py
  - hooks/format_code.py
  - hooks/format_python.py
  - hooks/hooks.json
  - hooks/check_code_quality.py
  - hooks/test_format_code.py
  - hooks/test_lang_tools.py
  - skills/context-security-review/references/hook-safety-contract.md
affected_reqs: [REQ-06, REQ-07]
---

## Context

Praxion runs three live hooks that act on source files, and all three are Python-only:
`format_python.py` (PostToolUse `Write|Edit`, runs `ruff format`), `check_code_quality.py`
(commit gate, filters staged files to `*.py`), and `detect_duplication.py` (Python AST analysis).
Neither TypeScript nor Rust has any equivalent, so formatting enforcement in a Praxion session is
Python-privileged: a `.py` write is formatted automatically, a `.rs` write is not.

Closing this for Rust forces a shape decision that the codebase survey explicitly escalated
rather than defaulting: grow parallel per-language hook files, or generalize into one
language-dispatching hook.

The relevant measurement: `format_python.py` is 77 lines. Roughly 60 of them are language-neutral
machinery — parse stdin JSON, extract `file_path`, snapshot before, run the tool, snapshot after,
count changed lines, emit an `additionalContext` report, exit 0 unconditionally. Roughly 15 are
Python-specific — the `.py` suffix test and the `ruff` / `uv run ruff` / `pixi run ruff`
resolution ladder.

A second forcing detail surfaced during design: Rust's per-file formatter invocation is not a
straight substitution. Bare `rustfmt` on a single file defaults to edition 2015 unless given
`--edition` or a discoverable `rustfmt.toml` that sets one, so modern syntax fails to parse. The
Rust entry needs a *builder*, not a static command.

## Decision

Introduce `hooks/_lang_tools.py`: a registry mapping file extension to a language entry
(tool resolver, argv builder, staged-file predicate). Rename `hooks/format_python.py` to
`hooks/format_code.py` and reimplement its language-specific 15 lines as a registry lookup;
repoint the PostToolUse `Write|Edit` registration in `hooks/hooks.json`. Extend
`hooks/check_code_quality.py` to consume the same registry for its staged-file branch.

The registry ships with **exactly two rows**: `.py` → `ruff format`, `.rs` → `rustfmt` with an
`--edition` resolved from the nearest `rustfmt.toml` / `Cargo.toml`, defaulting to the current
edition. TypeScript is deliberately **not** added — it is a one-row addition when its own task
arrives, not speculative generality now.

Two contracts are preserved verbatim from the existing hook and are non-negotiable:

- **Silent no-op when the tool is absent.** A resolver returning nothing produces exit 0 and no
  output. The hook never blocks a write.
- **Byte-identical Python behavior.** Pinned by a characterization test written *before* the
  refactor and required to pass unchanged after it.

Two scope boundaries are drawn explicitly:

- **Clippy is excluded from the commit gate.** Only `cargo fmt --check` runs there. Lint is a
  merge-stage cost; a multi-second lint on a pre-tool commit gate trains people to disable the
  gate, which loses the fast check too.
- **`detect_duplication.py` gains no Rust branch.** Rust AST duplication analysis needs a Rust
  parser dependency, which is disproportionate to the value.

## Considered Options

### Option 1 — Parallel per-language hooks (`format_rust.py` beside `format_python.py`)

**Pros.** Maximum independence: a defect in the Rust hook cannot regress Python formatting. No
rename, so no ripple into `hooks.json` or the hook-safety register. Each file is readable in
isolation with no indirection.

**Cons.** Copies ~60 lines of identical machinery a second time now and a third time when
TypeScript lands, which is precisely the "same pattern appears three times, refactor immediately"
threshold the coding-style rule names — reached by construction rather than by accident. Three
registrations to keep consistent. `check_code_quality.py` would still have to re-derive tool
resolution independently, so the duplication is wider than the format hooks alone.

### Option 2 — One language-dispatching hook over a shared registry (chosen)

**Pros.** One enforcement path, one test surface, one place a language is added. Expresses
per-language argv quirks (Rust's `--edition`) cleanly instead of forcing a lowest-common-
denominator shell-out. `check_code_quality.py` reuses the registry rather than duplicating
resolution. Adding TypeScript later is one row plus one test.

**Cons.** A rename that ripples to `hooks/hooks.json` and the hook-safety register — a stale
registration would silently disable Python formatting too, which is worse than the gap being
closed. Introduces one layer of indirection for a two-row table.

### Option 3 — Defer hooks entirely; document the gap

**Pros.** Zero risk to a working Python path. Keeps this task purely additive.

**Cons.** Leaves the single most visible day-to-day asymmetry between a Python and a Rust project
in a Praxion session unaddressed, in a task whose entire purpose is removing that asymmetry. A
documented gap with no owner and no trigger tends to stay a gap.

## Consequences

### Positive

- `.rs` writes are formatted on the same surface `.py` writes are — the observable symmetry the
  parity goal asks for.
- Adding TypeScript becomes a one-row change rather than a third 60-line copy.
- Tool resolution is stated once and consumed by both the formatter and the commit gate.

### Negative

- A rename with two known downstream references; both are enumerated in the plan so neither
  desynchronizes silently, but the risk is real and the mitigation is discipline, not mechanism.
- Regression risk to a hook that runs on every Write/Edit for every Praxion user. Bounded by the
  characterization-test-first ordering, which is why the refactor and the Rust row are separate
  steps that must not be merged.

### Neutral

- One new module in `hooks/`; the Hooks component row in the architecture doc is unchanged
  (hook files are enumerated by filesystem scan, not listed individually).

## Disconfirmation

**Falsifier.** If a third language cannot be expressed as a registry row without widening the
entry shape — for example, one whose formatter must be invoked project-wide rather than per-file —
then the shared abstraction was fitted to two accidentally-similar cases and parallel hooks were
right.

**Steelmanned runner-up.** Option 1's strongest argument is not simplicity, it is blast radius.
These hooks run on *every* Write and Edit for every user of the plugin; a defect is not a failing
test, it is a broken editing loop in the field. Parallel files make the failure domain exactly
one language by construction, with no shared code path to reason about. That is a genuinely
better safety property, and it is bought at the price of duplication that a careful reader can
tolerate in 60-line files.

**Reversal trigger.** The first language whose entry does not fit `(resolver, argv builder,
staged predicate)` without widening the shape. At that point, stop extending the registry and
split rather than generalizing further.
