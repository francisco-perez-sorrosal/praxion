---
id: dec-358
title: praxion-sidecar link is the sole reconciler; doctor is read-only, network-free, and renders one shared check registry
status: accepted
category: behavioral
date: 2026-09-02
summary: The sidecar CLI splits repair from diagnosis — link reconciles all three projection surfaces idempotently, doctor never mutates and never touches the network, and status/doctor/--json/the SessionStart banner are four renderings of one ordered check registry. No doctor --fix, no link --check.
tags: [cli, sidecar-placement, reconciler, diagnostics, interface-design, tui, idempotency]
made_by: agent
agent_type: interface-designer
branch: worktree-sidecar-placement
pipeline_tier: full
affected_files:
  - scripts/praxion-sidecar
  - hooks/inject_sidecar_banner.py
  - scripts/finalize_chain.sh
  - .ai-work/sidecar-placement/INTERFACE_DESIGN.md
dissent: "A doctor --fix is what every operator's muscle memory expects from a doctor subcommand (brew, flutter, npm), and telling them to run a differently-named verb after every diagnosis adds a step to the most common recovery path in the whole CLI."
---

## Context

`praxion-sidecar` must answer two questions that look similar and are not:
*where does my project intelligence live and is it clean* (`status`), and *is
the projection correct and what exactly do I run to fix it* (`doctor`). It must
also **repair** the projection — the `.git/info/exclude` Praxion block, the
shadow symlinks, and the hook-chain registration — on demand, from a
`post-checkout` hook after `git worktree add`, and from a SessionStart self-heal
after a package manager re-points `core.hooksPath`.

Three failure modes shaped the decision:

- Praxion has already been bitten by a *second* repair path drifting from the
  first: the pre-fix Block D reconciler resolved `PLUGIN_ROOT` from a registry
  shape that never existed, so the gate silently skipped for every project that
  installed it (dec-355 / dec-356).
- A diagnostic that can mutate is a diagnostic operators stop trusting; a
  diagnostic that touches the network is one they cannot run offline, cannot run
  in a SessionStart hook, and which leaks the existence of a private sidecar to
  a remote host.
- `status` and `doctor` overlapping by ~80% invites two implementations of "is
  this healthy" that disagree in exactly the situations that matter.

The existing Praxion pattern already points the way: `upgrade_project_pins.sh`
applies and `--check` reports; `reconcile_aac_surfaces.py` takes
`--mode check|dry-run|apply`.

## Decision

1. **`link` is the only reconciler.** It reconciles all three projection
   surfaces from the manifest into the current checkout, is idempotent, and
   reports in the `upgrade_project_pins.sh` idiom (`Already linked — no
   changes.` / `Linked N surface(s) into <checkout>.`). Hooks call
   `praxion-sidecar link --quiet`.
2. **`doctor` never mutates and performs no network I/O.** Remote policy is
   evaluated by comparing configured URLs, never by contacting a host. There is
   no `doctor --fix`; almost every fix line is literally `praxion-sidecar link`.
3. **One check registry, four renderings.** `status`, `doctor`,
   `status --json` / `doctor --json`, and the SessionStart banner all evaluate
   the same ordered check list. There is exactly one implementation of "is this
   healthy".
4. **No `--check` on this CLI.** `doctor` *is* the check verb; `link --check`
   would be a third rendering of the same registry. `--dry-run` is available on
   every mutating verb.
5. **Two rows are read here and repaired elsewhere.** `hooks-path` and
   `hooks-chained` are repaired by `upgrade_project_pins.sh` (the P0 work) and
   only *read* by `doctor` — one repairer, two readers. They are also the only
   rows that apply under in-repo placement, which is why `doctor` runs on
   in-repo projects (exit `0`, two rows) rather than refusing.

## Considered Options

### A — `doctor --fix`

Pros: matches operator muscle memory from `brew doctor`, `flutter doctor`,
`npm doctor`; one command to diagnose and repair.
Cons: creates a second repair path beside `link`, which the hooks must call
anyway; the two drift the moment a new projection surface is added to one and
not the other — the dec-355 failure mode exactly; a `doctor` that can mutate
cannot be safely run from a SessionStart hook or a read-only CI check.

### B — `link --check`

Pros: mirrors `upgrade_project_pins.sh --check` literally.
Cons: a third rendering of the registry, with its own formatting to keep in
sync; leaves `doctor` and `link --check` answering the same question with two
outputs, which is precisely the divergence this decision exists to prevent.

### C — Reconciler / diagnostic pair with a shared registry (chosen)

Pros: one repairer, one registry, N thin renderings; `doctor` is safe to run
anywhere, offline, in a hook, in CI; adding a projection surface means one
registry row and one `link` branch, and every rendering updates for free.
Cons: the common recovery path is two commands (`doctor` then `link`) where
option A is one; `doctor` without `--fix` will read as an omission to some
operators until they read the fix lines.

## Consequences

**Positive.** A new projection surface is added in two places, not five. The
SessionStart banner and a CI gate consume the same verdicts a human sees.
`doctor` is safe by construction — read-only and offline — so it can be run on
a colleague's machine, in a sandbox, or on a project someone else onboarded.
P0's hook-chaining work gains a visible check surface before P1 exists.

**Negative.** The recovery path is two commands. `doctor` diverges from the
`brew doctor --fix`-style convention some operators expect, and the help text
carries the burden of making `link` discoverable. The registry becomes a
load-bearing internal structure that must be built before any rendering — an
ordering constraint the implementation plan has to honour.

## Disconfirmation

**Falsifier.** If telemetry or user reports show `doctor` being run repeatedly
without a following `link` — operators diagnosing and then not repairing —
the two-command path is failing in practice and `doctor --fix` (implemented as
a thin call into the same `link` code path, never a parallel implementation)
becomes the right call.

**Steelmanned runner-up.** Option A is genuinely better if `--fix` is
implemented as a *delegation* rather than a second implementation: `doctor
--fix` simply invokes `link`, so no drift is possible, and the operator gets
the one-command path their muscle memory expects. The reason to still decline
it now is smaller than it looks — it is mainly that a mutating `doctor` cannot
be the hook-safe, CI-safe, offline-safe read-only surface the banner needs, and
a `--fix` flag that most callers must be told never to pass is a trap in the
Bloch "hard to misuse" sense. If the falsifier fires, adding delegating `--fix`
is a small, safe change.

**Reversal trigger.** A third repair surface appearing (beyond `link` and
`upgrade_project_pins.sh`), or `hooks-path`/`hooks-chained` acquiring a third
reader, should prompt extracting the check registry into a shared module rather
than leaving it inside the CLI — at which point the reader/repairer split needs
re-examining as a whole.
