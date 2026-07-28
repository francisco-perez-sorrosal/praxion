---
id: dec-288
title: upgrade_project_pins gains an in-place hub-SHA rewrite + add-caller-if-absent op; SHA resolved in the command layer, script deterministic given --hub-sha
status: accepted
category: architectural
date: 2026-07-27
summary: The existing-project upgrade path re-points a Praxion-authored ci-autofix caller's pinned hub @<40-hex> and adds the cross-model-review caller if absent. The hub SHA is resolved in the LLM/gh-capable /upgrade-project command layer and passed to the deterministic bash reconciler as --hub-sha (resolving in-script would depend on main's moving tip, breaking determinism); the rewrite edits only the SHA token on a uses:-line matching the Praxion-hub reusable-workflow shape, leaving foreign/hand-edited/self-host callers untouched.
tags: [ci-cd, self-healing-loop, fleet, upgrade, sha-pinning, github-actions, determinism, idempotency, cross-model-review, onboarding]
made_by: agent
agent_type: systems-architect
branch: worktree-p3b-fleet-install
pipeline_tier: standard
affected_files:
  - scripts/upgrade_project_pins.sh
  - commands/upgrade-project.md
  - scripts/test_upgrade_project_pins.py
  - scripts/CLAUDE.md
affected_reqs: [REQ-09, REQ-10, REQ-11, REQ-12, REQ-13, REQ-14]
re_affirms: dec-273
dissent: "A self-contained script that resolves its own hub SHA via gh would be one deterministic-looking place with no second layer to keep in sync; splitting resolution into the command layer means the SHA the operator sees resolved and the SHA the script writes can diverge if the command is edited without the script, and adds a gh dependency to a previously network-free command."
---

## Context

`dec-278` deferred fleet rollout of the P2 cross-model review gate; P3b closes that
deferral for **both** new onboards and already-onboarded projects. New onboards are
handled by extending `/onboard-project` sub-step 8e.8 (an existing, test-covered install
pattern). Already-onboarded projects are the hard half: they carry a materialized
`.github/workflows/ci-autofix.yml` caller pinned to an **old** hub `@<40-hex>` SHA (from
whenever they onboarded) and, typically, no `cross-model-review.yml` caller at all.

`scripts/upgrade_project_pins.sh` (wrapped by `/upgrade-project`) is the existing
deterministic, idempotent, **gate-free**, network-free reconciler that re-points the four
version-pinned surfaces a plugin bump invalidates (finalize-hook symlinks, the
observations merge driver, retired drivers, the manifest version stamp). It has never
touched `.github/workflows/` callers — a caller's version identity is a **cross-repo git
ref** (the hub SHA), a different class of pin from the local plugin-cache paths the
script reconciles today.

Two forces shape the design. (1) The script's contract is *deterministic given its
inputs* — resolving `gh api repos/.../commits/main --jq .sha` inside the script would make
its output depend on `main`'s moving tip. (2) An operator may have edited their caller
(watched-workflow list, comments, permissions) or may run a self-host / hand-rewritten
caller — the upgrade must never clobber those.

Activation: honest-uncertainty gate **fired** — ≥2 genuinely plausible designs on both
the resolution axis (in-script vs command-layer) and the rewrite axis (regenerate vs
edit-only-token). Stakes: privileged CI surface, but reversible per-repo and reusing the
audited `dec-273`/`dec-286` hub envelope. Lens set: Developer, Test, Operations,
Simplicity, Security. Tier-A Dialectical Inquiry run (below). Tier-B cross-model challenge
**declined**: the change is a deterministic, well-tested, per-repo-reversible reconciler
that invents no new trust boundary (it re-points to the same audited hub) — mirroring
`dec-286`'s own Tier-B decline for the same envelope.

## Decision

1. **SHA resolution in the command layer.** `/upgrade-project` resolves the current hub
   SHA the same way onboard 8e.8 does (`gh api repos/francisco-perez-sorrosal/praxion/commits/main --jq .sha`),
   validates it is a 40-hex commit, and forwards it to the script as `--hub-sha <SHA>`.
   The script never calls the network. Given a fixed `--hub-sha`, the script is fully
   deterministic and unit-testable with a fabricated SHA. When `--hub-sha` is absent, the
   script skips the caller surfaces entirely and reconciles the four pre-existing
   surfaces unchanged (backward compatible). When `gh` is unavailable in the command
   layer, the caller surfaces are skipped with an advisory and the core surfaces still
   reconcile.

2. **In-place rewrite edits only the SHA token; the `uses:`-line shape is the provenance
   signature.** A caller is treated as Praxion-authored-and-upgradable iff a line matches
   `uses:\s*francisco-perez-sorrosal/praxion/\.github/workflows/reusable-ci-autofix\.yml@[0-9a-f]{40}`.
   The script rewrites **only** that 40-hex token to the new SHA — everything else stays
   byte-for-byte. Idempotent by construction (no-op when the SHA already matches). A
   caller whose `uses:` does not match (foreign hub, a mutable tag/branch ref, a
   self-host local `./` ref, or a hand-rewritten body) is left untouched and reported.

3. **Add-caller-if-absent, policy-gated, in the deterministic script.** When
   `.github/autofix-policy.yml` exists, its `review.cross_model_gate` is not `off`, and
   `.github/workflows/cross-model-review.yml` is absent, the script renders the shipped
   `cross-model-review.yml.tmpl` (fill `{{PRAXION_HUB}}` + the passed `{{HUB_SHA}}`, strip
   the doc-comment header — the template has no `{{WATCHED_WORKFLOWS}}`, so no detection is
   needed) and writes it. After any write, the script greps for a surviving `{{` and
   aborts loudly. Placing this in the script (not the command) keeps it subprocess-
   testable. The `CURSOR_API_KEY` print is surfaced by the command; never auto-injected.

4. **Manifest step preserves the conditional caller-set key.** Onboard records a
   caller-set key (e.g. `ci_autofix`) in the manifest `artifacts` object. The upgrade's
   manifest stamp changes from wholesale overwrite to a shallow merge
   (`.artifacts = (.artifacts + $expected)`): canonical core keys win (retired drivers
   still pruned), the conditional caller-set key is preserved; the idempotency check
   compares post-merge equality.

## Considered Options

### Resolution axis

**R1 — Resolve the hub SHA inside the script via `gh` (steelmanned runner-up).**
One self-contained place; no second layer to keep in sync; the operator runs one command
and the script does everything.
*Rejected:* the resolved SHA would be `main`'s tip at run time — the script's output
becomes non-deterministic, directly violating its `deterministic/idempotent/gate-free`
contract; adds a network + `gh` dependency to a previously network-free script; and makes
the reconciler untestable without either network or a `gh` stub.

**R2 — Resolve in the command layer, pass `--hub-sha` (chosen).**
Preserves the script's determinism/testability; mirrors onboard's own "LLM resolves,
mechanical layer renders" split; the network dependency lives where it already belongs
(`/upgrade-project` is an LLM-driven command that can already shell out).

### Rewrite axis

**W1 — Regenerate the whole caller from the template (overwrite).**
Simplest to write.
*Rejected:* clobbers every operator edit (watched-workflow list, comments, permission
tweaks) and cannot distinguish a self-host / hand-edited caller from a stock one —
violates the no-clobber constraint.

**W2 — Edit only the 40-hex token on a shape-matched `uses:` line (chosen).**
Never disturbs other caller content; self-host (`./` ref) and hand-edited/mutable-ref
callers fall out as "leave alone" for free; idempotent by construction.

## Consequences

**Positive:** the script keeps its audited contract (deterministic, gate-free,
network-free, LLM-free) and gains subprocess-level test coverage for every new behavior;
already-onboarded projects reach the current P3a+allowed_bots hub with a single
`/upgrade-project`; operator caller edits and self-host callers survive untouched; no new
trust boundary — the re-point targets the same audited hub as `dec-273`/`dec-286`.

**Negative / cost:** two layers now share the caller contract (`/upgrade-project` resolves
+ validates the SHA; the script rewrites) — a lock-step the `scripts/CLAUDE.md` entry must
document; `/upgrade-project` gains a `gh` dependency (degraded gracefully); the `uses:`
match pattern must move in lock-step with any future template restructure of the caller's
`uses:` line.

## Disconfirmation

- **Falsifier:** if a real managed project's `/upgrade-project` run either (a) leaves a
  stock Praxion caller un-upgraded because the `uses:`-shape match is too narrow, or (b)
  clobbers an operator's caller edit because the SHA-token rewrite bled beyond the single
  token, the "edit-only-the-token, shape-is-the-signature" premise is wrong and the
  rewrite must move to a structured YAML edit (a `yq`-based `uses:` surgical replace).
- **Steelmanned runner-up (Dialectical Inquiry):** R1 (resolve-in-script) is genuinely
  attractive — a single self-contained reconciler with no cross-layer contract is easier
  to reason about, and "the script fetches the current hub SHA" reads as exactly what an
  upgrade *should* do. If the script were allowed to be network-dependent, R1 would
  dominate: one command, one place, no `--hub-sha` plumbing, no lock-step note. The
  deciding factor is narrow but decisive: the script's *existing, relied-upon* contract is
  determinism (its tests assert idempotency and no-op second runs), and a moving-tip fetch
  breaks that at the root. So R2 wins **for this reconciler**; R1 would be correct only if
  the script's contract were redefined to permit network I/O — a larger change than P3b
  should make.
- **Reversal trigger:** if the command-layer/script split proves a maintenance burden
  (the two drift in practice), or if a future pass legitimately redefines the reconciler
  to allow network I/O, revisit and fold resolution back into the script (R1). If the
  `uses:`-shape signature misfires on real callers, promote the rewrite to a structured
  YAML edit.

## Prior Decision

Re-affirms `dec-273` (hub reusable-workflow distribution + SHA-pinned callers). This ADR
does not alter the distribution model — it adds the *upgrade* operation `dec-273`'s
"deliberate, auditable, blast-radius-controlled per-repo pin bump" always implied but
never mechanized. `dec-273`'s dissent (SHA-pinned callers make every hub fix a manual
per-repo bump) is directly mitigated here: `/upgrade-project` is now that bump, made
one-command and idempotent. It also closes the existing-project half of the rollout
`dec-278` deferred.
