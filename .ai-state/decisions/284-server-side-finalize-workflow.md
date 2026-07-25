---
id: dec-284
title: Server-side GitHub Actions finalize backstop for web-UI merges
status: accepted
category: architectural
date: 2026-07-24
summary: Add a push:main GitHub Actions workflow that reruns the on-main finalize composition and commits the promotion back with GITHUB_TOKEN, backstopping web-UI merges that client-side git hooks cannot reach.
tags: [ci, github-actions, finalize, hooks, adr, governance, dry, anti-recursion]
made_by: agent
agent_type: systems-architect
branch: worktree-finalize-hook-ci
pipeline_tier: standard
affected_files:
  - .github/workflows/finalize-adrs.yml
  - scripts/finalize_chain.sh
  - scripts/test_finalize_chain.py
  - tests/test_finalize_adrs_workflow_invariants.py
dissent: The local hook chain self-heals on the maintainer's next local git op (pull/checkout/commit), so a privileged server-side commit-back surface may be unnecessary complexity for a self-correcting, bounded-latency drift.
---

## Context

The `.ai-state/` finalize chain is a **client-side** git-hook chain: `git-finalize-hook.sh` (symlinked to `.git/hooks/{post-merge,post-commit,post-checkout}`) sources `finalize_chain.sh` and, on `main`, runs the composition `_finalize_chain_run_on_main` — `finalize_adrs.py --all` (promote `dec-draft-<hash>` → `dec-NNN`, rewrite cross-references, regenerate `DECISIONS_INDEX.md`; gated on drafts present) + `finalize_tech_debt_ledger.py --all` (collapse/migrate ledger rows; always) + `build_doc_manifest.py --root` (refresh the committed manifest; gated on a manifest existing). This mechanism is `dec-061` (ADR Finalize Protocol) and its tech-debt sibling.

A **GitHub web-UI merge runs server-side**, where those client-side hooks cannot fire (issue #45). Draft ADRs land on `main` un-promoted, the index is un-regenerated, cross-references dangle, and ledger/manifest reconciliation is skipped — until the maintainer's *next local* git op fires the chain. The drift is self-healing but of unbounded latency, and it defeats the purpose of the automation for a contributor who merges exclusively through the web UI.

Grounding facts verified from primary GitHub documentation (RESEARCH_FINDINGS.md): a `git push` authenticated with the default `GITHUB_TOKEN` does **not** re-trigger a `push`-triggered workflow (structural anti-recursion, `push` is not in the documented exception set); `main` currently carries **no branch protection and no rulesets** (live `gh api` check) and Praxion is a **personal user-account** repo; `.github/workflows/release.yml` already demonstrates the raw-`git`-steps commit-back idiom in this repo.

## Decision

Add a server-side GitHub Actions workflow `.github/workflows/finalize-adrs.yml`, triggered on `push` to `main`, that reruns the **full on-main finalize composition** and commits the promotion back to `main` using the default `GITHUB_TOKEN`. It is an **additive backstop**: the local hook chain is untouched and remains the primary path.

Two structural sub-decisions define the shape:

1. **Full composition symmetry.** The workflow mirrors the entire `_finalize_chain_run_on_main` composition (all three finalizers), not ADR-only — a web-UI merge strands all three, so an ADR-only fix would leave a narrower version of the same bug. It does **not** mirror the outer post-merge steps `reconcile_ai_state.py` (local merge-conflict settling, N/A to a server-produced tree) or `check_squash_safety.py` (a local-developer diagnostic, non-actionable in CI).
2. **Single source of truth.** The workflow sources `finalize_chain.sh` and calls a new thin public entry point `finalize_chain_run_on_main` (wrapping the existing private composition) rather than re-listing the steps in YAML — one authoritative definition of ordering/gating, shared by hooks and workflow. The only difference between the two callers is the error-handling policy, expressed as a single `FINALIZE_CHAIN_STRICT` env flag: fail-loud for CI (a finalizer's non-zero exit fails the job before commit-back), non-blocking for the hooks (unchanged warn-and-continue, exit 0).

Operational specifics: `on: push: branches: [main]` with **no `paths:` filter** (rely on the scripts' own state-driven gates + a `git status --porcelain` commit-gate for no-empty-commits); `concurrency: group: ${{ github.workflow }}-${{ github.ref }}`, `cancel-in-progress: false`; `permissions: {}` at workflow level + `contents: write` only on the pushing job; every `uses:` SHA-pinned; `github-actions[bot]` identity; imperative commit message with **no** AI-authorship trailer; no `pull_request_target`; no agent/`claude-code-action` step.

**Scope: Praxion-only, dogfood-first.** Fleet propagation to managed projects is deferred (see Consequences).

## Considered Options

### Option 1 — Server-side `push:main` workflow, commit-back with `GITHUB_TOKEN` (chosen)

- **Pros:** Reaches web-UI merges (the only path the hooks miss). `GITHUB_TOKEN` anti-recursion is structurally airtight per primary docs — no `[skip ci]` hack, terminates naturally. Zero new secrets/App registration. Mirrors the existing `release.yml` commit-back precedent. Full symmetry + DRY reuse of the existing composition means near-zero net logic.
- **Cons:** Introduces one new privileged surface (`contents: write` push to `main`). Latent fragility if branch protection with "no bypass" is later added (see Reversal trigger). Needs PyYAML in CI for the manifest step.

### Option 2 — Pre-merge required status check that finalizes on the PR branch

- **Pros:** No push-to-main; finalize happens before the merge lands, so `main` is never in a dangling state.
- **Cons:** **NNN assignment is intrinsically a merge-to-main operation** — the next sequential `dec-NNN` is only well-defined against `main`'s committed `decisions/` set *at merge time*. On a PR branch, two concurrent PRs would each compute the same next NNN → collision on merge. `finalize_adrs.py` is designed to run *at* merge-to-main, not before; a pre-merge check can validate draft well-formedness but cannot safely assign NNN. Weak on the core operation. Rejected.

### Option 3 — Squash-time / merge-queue finalize

- **Pros:** A single controlled integration point.
- **Cons:** Merge queue is not configured (added infra). Squash merges **erase** `.ai-state/` entries — `dec-059` (squash-safety) exists precisely because squash is dangerous for `.ai-state/`; building finalize on the squash path fights an existing guard. Disproportionate to the problem. Rejected.

### Option 4 — Accept + document (rely on the next local git op)

- **Pros:** Zero new surface, zero new failure modes. The local hook chain **does** eventually finalize on the maintainer's next local `pull`/`checkout`/`commit` — the drift is self-healing with bounded (if unpredictable) latency.
- **Cons:** Leaves `main` in a dangling state (un-promoted drafts, stale index, dangling cross-refs) for an arbitrary interval; defeats the automation for web-UI-only contributors. This is the status-quo bug. The strongest runner-up (see Disconfirmation) but does not actually close #45.

## Consequences

**Positive:**
- Web-UI merges reach the same finalizer as local git ops — #45 closed for Praxion.
- One authoritative composition definition; hooks and workflow cannot drift.
- Local hook behavior byte-for-byte unchanged (`FINALIZE_CHAIN_STRICT` defaults off).
- Fail-loud: a broken finalize surfaces in the Actions run and never commits corrupt state to `main`.
- Reuses `dec-024` SHA-pinning + `release.yml` commit-back conventions — no new patterns.

**Negative / accepted:**
- One new privileged `contents: write` surface on `main`.
- CI depends on PyYAML (one `pip install`).
- Latent branch-protection fragility (see Reversal trigger) — deliberately not solved now.

**Deferred (out of scope):** Fleet propagation to managed projects via `/onboard-project` + `claude/canonical-blocks/` + `/new-project` is deferred, mirroring `dec-278`'s deferred fleet-install pattern. Reason: user projects vary in default-branch protection, org-vs-personal ownership (which changes the token/bypass calculus), and CI availability; propagating an unproven privileged-push workflow fleet-wide is premature. A follow-on task installs it downstream once proven on Praxion.

**Relationship to prior decisions:** Extends `dec-061` (ADR Finalize Protocol) by adding a server-side backstop to the same mechanism; does not supersede or alter it. Follows `dec-024` (CI SHA-pinning) and the `release.yml` commit-back idiom.

## Disconfirmation

**Activation:** yes — honest-uncertainty gate fires (a genuine runner-up exists) and `category: architectural`. Dialectical-inquiry sub-step performed (steelmanned runner-up below). Tier-B cross-model challenge **not** invoked: blast radius is contained (idempotent, advisory-locked, fail-loud, unprotected personal repo) and the anti-recursion property is airtight from primary docs — the decision does not meet the Tier-B stakes bar (security / one-way-door / user-visible-breaking with residual uncertainty).

- **Falsifier — what evidence would make this decision wrong:** If GitHub's documented anti-recursion behavior did not hold — i.e., a `GITHUB_TOKEN`-authenticated push to `main` *did* re-trigger the `push` workflow — the design would loop. (Primary docs state it does not; a live dogfood confirms.) Equally, if `finalize_adrs.py` were not idempotent, a queued concurrent run could double-promote. (The script holds an advisory lock and no-ops when there is nothing to promote.)
- **Steelmanned runner-up — Option 4 (accept + document):** The local hook chain is *state-driven* and self-healing: the maintainer's very next local `git pull`/`checkout`/`commit` fires `post-merge`/`post-checkout`/`post-commit`, which finalizes any drafts that landed via the web UI. The drift is therefore bounded-latency and self-correcting — not permanent. Against that, this ADR adds a *new privileged commit-back surface* (a `contents: write` push to `main` from CI), a new failure mode (R2/R4), and latent branch-protection fragility (R1), all to eliminate a delay that a single local git op already erases. For a solo maintainer who runs local git ops regularly, the marginal value over "do nothing" is small, and the simplest-thing-that-works principle argues for Option 4. The chosen option wins only because web-UI-*only* workflows (and future multi-contributor use) can leave the drift un-healed for arbitrarily long, and closing #45 means the mechanism should not depend on a subsequent *local* action at all.
- **Reversal trigger:** If **branch protection with "do not allow bypassing" is ever enabled on `main`**, `GITHUB_TOKEN` pushes will start failing (its pseudo-identity is not addable to a ruleset bypass-actor list). At that point the design must be revisited: switch to a GitHub App installation token + a ruleset bypass-actor entry — and critically, **re-derive the anti-recursion property**, because App/PAT-token pushes *do* re-trigger `push` workflows (the free `GITHUB_TOKEN` guard is lost), requiring an explicit loop-guard (a commit-author / actor check). Do not pre-build this; it is inert today.
