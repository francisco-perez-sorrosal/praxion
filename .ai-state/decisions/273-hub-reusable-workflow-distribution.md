---
id: dec-273
title: Distribute CI autofix machinery via hub reusable workflows + SHA-pinned per-repo callers + autofix-policy.yml
status: accepted
category: architectural
date: 2026-07-22
summary: Praxion distributes the self-healing CI/PR autofix machinery as hub reusable workflows (workflow_call) in the public Praxion repo, invoked by thin SHA-pinned per-repo caller templates that pass secrets by explicit mapping (never inherit) and are tuned by a per-repo autofix-policy.yml — chosen over fully-copied templates refreshed via the dec-271 manifest and over a GitHub App, because centralizing security-critical injection/sanitization logic in one audited hub with deliberate blast-radius-controlled per-repo upgrades beats N-copy logic duplication for a privileged surface.
tags: [ci-cd, autofix, github-actions, workflow-call, reusable-workflows, sha-pinning, self-healing-loop, distribution, fleet, security, onboarding]
made_by: agent
agent_type: systems-architect
branch: main
pipeline_tier: standard
affected_files:
  - .github/workflows/reusable-ci-autofix.yml
  - .github/workflows/ci-autofix.yml
  - claude/project-baseline/ci-autofix/ci-autofix.yml.tmpl
  - claude/project-baseline/ci-autofix/cross-model-review.yml.tmpl
  - claude/project-baseline/ci-autofix/autofix-policy.yml.tmpl
  - commands/onboard-project.md
  - commands/new-project.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07]
dissent: "SHA-pinned callers make every hub security fix a manual, per-repo pin-bump — a fleet member that never bumps stays on vulnerable logic; the copied-templates-via-dec-271-manifest runner-up would auto-deliver that fix to every unmodified copy. We accept manual bumps to gain deliberate, auditable, blast-radius-controlled upgrades and a single audited home for the injection/sanitization logic."
re_affirmed_by:
  - dec-286
  - dec-draft-b772d931
---

## Context

Praxion ships a first-iteration CI autofixer — `.github/workflows/ci-autofix.yml` (P0, ADR
`dec-272`): a `workflow_run`-triggered, SHA-pinned Claude agent that diagnoses from
sanitized failure logs read **as data**, opens a `ci-autofix/` fix PR (never pushes to `main`),
and carries layered loop prevention, a daily budget cap, and a sensitive-path tripwire. That
workflow lives only in the Praxion repo. The self-healing-loop brief (§4.1, §9 seed 2) requires
this machinery to become **installable into managed projects** while preserving per-project
ownership — the hard v1 requirement.

The single open falsifier for this decision (brief §9.2: "cross-repo `workflow_call` limits or
private-repo friction at fleet scale") was closed by dedicated research
(`.ai-work/p1-installable-core/RESEARCH_FINDINGS.md`, verdict **viable-with-caveats**): a private
managed repo **can** call a reusable workflow in Praxion's public repo with **no hub-side grant**
(Q1a/Q1c); the nesting/count ceilings (10 levels / 50 workflows, Q2a/Q2b) sit far above this
1–2-level, 2-workflow topology; SHA-pinning `workflow_call` refs is **GitHub's own documented
recommendation** (Q3b). Two operational — not architectural — frictions surfaced: (1) a caller
repo's org/enterprise **Actions allowlist** may need a one-time entry for Praxion's hub
(Q4b, caller-side only, outside Praxion's control); (2) **`secrets: inherit` is same-org/enterprise
only** and silently no-ops cross-org (Q5b) — so caller templates **must** use explicit `secrets:`
mapping (Q5c/Q5d).

## Decision

Distribute the machinery as **hub reusable workflows + SHA-pinned per-repo callers + a per-repo
`autofix-policy.yml`**:

1. **Hub** (public Praxion repo): `.github/workflows/reusable-ci-autofix.yml` with
   `on: workflow_call`, generalizing every concern of the shipped `ci-autofix.yml`. Its
   caller-facing interface is **minimal**: one optional `policy_path` input (default
   `.github/autofix-policy.yml`) and one **explicitly-declared** required secret
   (`CLAUDE_CODE_OAUTH_TOKEN`). Every per-repo tunable (budget cap, attempt cap, sensitive paths,
   surface toggle, fixer model, auto-commit tiers) is read from the caller's checked-out
   `autofix-policy.yml`; every event-intrinsic value (failed-run id, conclusion, head branch,
   **default branch** — no longer hardcoded `main`) is read from the `github.event` context that
   propagates into the called workflow. `reusable-cross-model-review.yml` (the Cursor gate) is
   designed now (§4.2) but **built in P2**.

2. **Caller templates** in `claude/project-baseline/ci-autofix/`: `ci-autofix.yml.tmpl` (built in
   P1), `cross-model-review.yml.tmpl` (P2 placeholder), `autofix-policy.yml.tmpl` (built in P1).
   Each caller is **thin in logic, explicit in privilege**: it carries the `workflow_run` trigger
   (whose `workflows:` list GitHub requires to be a static literal — the one per-repo value that
   cannot be sourced from the policy file), the **least-privilege `permissions:` ceiling**, the
   **explicit `secrets:` mapping** (never `inherit`), and a **full-commit-SHA-pinned `uses:`** to
   the hub. Upgrades are deliberate per-repo SHA-pin bumps.

3. **`autofix-policy.yml`** (per-repo, brief §4.3) is the single home for per-repo behavior. The
   reusable workflow reads it from the checked-out caller repo. `watched_workflows` is documentary
   there; the caller's static `on.workflow_run.workflows` trigger list is authoritative (GitHub
   constraint).

4. **Praxion is caller #1**: `.github/workflows/ci-autofix.yml` refactors into a thin caller of
   the hub (same-repo local `uses: ./.github/workflows/reusable-ci-autofix.yml`), using the
   **same explicit `secrets:` mapping** managed projects use so the cross-org path is exercised on
   Praxion itself. All P0 logic moves down into the reusable workflow unchanged; Praxion dogfoods
   before any managed project.

5. **Onboarding** (`/onboard-project` new phase + `/new-project` mirror): install the caller +
   policy templates using the **file-existence idempotency pattern** already used for
   `dependabot.yml.tmpl` (never overwrite), record them in the **onboard manifest**
   `.ai-state/.praxion-onboard.json` artifact inventory, and **PRINT — never auto-inject** — both
   the secrets setup (`gh secret set CLAUDE_CODE_OAUTH_TOKEN`) and the one-time caller-org
   **Actions-allowlist** instruction from the research.

All P0 security invariants are preserved verbatim in the reusable workflow: never `track_progress`
(bug #860); `pull_request_target` banned; every `uses:` SHA-pinned; least-privilege job
permissions; untrusted CI-log text fetched/sanitized in a non-agent step and read as data; the
P2 reviewer job gets **no `contents: write`**; the gate fails open; no AI authorship in commits.

## Considered Options

### Option A — Hub reusable workflows + SHA-pinned callers + policy file (chosen)
- **Pros:** the security-critical logic (log sanitization, data-not-instructions posture, budget
  cap, sensitive-path tripwire, loop prevention) lives in **one audited hub** — a fix is authored
  once; upgrades are **deliberate, auditable, blast-radius-controlled** (a bad hub change reaches a
  repo only when it chooses to bump; Praxion dogfoods first); the caller carries no copied logic,
  so per-repo audit surface is tiny; SHA-pinning is GitHub's own recommendation; research confirms
  zero hub-side friction and structural headroom.
- **Cons:** a hub security fix does not reach a fleet member until its operator bumps the SHA pin
  (manual discipline); a one-time caller-org Actions-allowlist entry may be needed (outside
  Praxion's control); explicit `secrets:` mapping is marginally more verbose than `inherit` (which
  cannot be relied on cross-org anyway).

### Option B — Fully-copied workflow templates refreshed via the dec-271 manifest (steelmanned runner-up)
- **Pros:** reuses **already-built** machinery — dec-271's block-history manifest +
  `refresh_claude_blocks.py` classification (`absent`/`current`/`stale`/`modified`,
  refuse-to-clobber) delivers self-healing refresh with **no per-repo pin bumps**; the full
  workflow logic is **visible and auditable inside each repo**; a self-contained copied workflow
  calls **nothing external**, so it needs **no `workflow_call` allowlist entry** (sidesteps the
  one operational friction Option A carries) and has **no runtime dependency** on Praxion's repo
  visibility or availability.
- **Cons:** the injection/sanitization/tripwire logic is **duplicated N times**, so a security fix
  must re-propagate to every copy — and the dec-271 refresh **refuses to touch a locally-modified
  copy**, leaving it frozen on old (possibly vulnerable) logic; **auto-refresh is worse for a
  *bad* change** (it reaches all unmodified copies automatically — the opposite of Option A's
  deliberate-bump containment); larger per-repo audit surface; and dec-271's mechanism is
  **CLAUDE.md-block-specific today** — extending `REFRESHABLE_SLUGS` + `refresh_claude_blocks.py`
  to hash standalone `.github/workflows/*.yml` file bodies is real new implementation cost the
  runner-up must pay that Option A avoids.

### Option C — GitHub App minting/owning the workflows
- **Pros:** short-lived installation tokens (the least-privilege auth story); centralized
  fleet control; natively solves the *separate* cross-repo issue-filing auth problem the healing
  sidecar faces (brief §5 / ADR seed 3).
- **Cons:** disproportionate for P1 — turns Praxion (a plugin/library) into an **operated service**
  with a hosted webhook endpoint, token-minting infra, availability SLA, and its own security
  surface; does **not** remove the need for per-repo `CLAUDE_CODE_OAUTH_TOKEN` / `CURSOR_API_KEY`
  (those authenticate the *agents*, not the GitHub API); still needs *something* in each repo to
  trigger. Rejected for P1 as the wrong instrument for *workflow distribution*; it is the correct
  future instrument for the healing sidecar's cross-repo issue **filing**, a different problem.

## Consequences

- **Positive:** managed projects gain the full hardened autofixer by installing a thin caller +
  policy; the privileged, injection-exposed logic has one audited home; upgrades are deliberate and
  their blast radius is bounded; Praxion is caller #1 and validates the cross-org secrets path on
  itself; the design forward-links cleanly to P2 (`reusable-cross-model-review.yml` + its caller)
  and P3 (policy `surfaces.pr_checks`/`dependabot`/`fork_prs`) without rework; it builds directly
  on `dec-272` (the P0 shipped workflow) — that ADR's Consequences already named this
  fixer "caller #1 of the hub."
- **Negative / cost:** fleet upgrade discipline is now a human responsibility (mitigated by
  Praxion-dogfoods-first + a documented pin-bump path; measurable at P6); a one-time
  caller-org-allowlist step may block onboarding on locked-down orgs (mitigated by an explicit
  printed instruction + pre-flight check, never auto-injected); `watched_workflows` is duplicated
  between the caller's static trigger and the policy file (GitHub constraint, kept in sync at
  install); the caller is not *purely* minimal — it must carry the least-privilege `permissions:`
  ceiling (a feature, not a bug: each repo *sees* exactly what it grants).

## Disconfirmation

- **Falsifier:** the original falsifier (cross-repo `workflow_call` limits / private-repo
  friction) is **retired** by research. The refined falsifier: org-level Actions **allowlist**
  friction (Q4b) proves **common** across the fleet — its admins routinely refuse or forget to add
  Praxion's hub, blocking onboarding on a step outside Praxion's control — **or** measured evidence
  over P6 shows hub security fixes routinely fail to reach the fleet because operators don't bump
  SHA pins. Either makes the self-contained, allowlist-free, auto-refreshing copied-templates
  design preferable.
- **Steelmanned runner-up:** **Option B** — fully-copied templates refreshed via the dec-271
  manifest. It reuses machinery Praxion **already ships**, needs **no external call** (hence no
  allowlist entry and no runtime dependency on Praxion), keeps every repo's logic locally
  auditable, and **auto-delivers** fixes to unmodified copies without any operator action. It wins
  the moment allowlist friction is common **or** manual pin-bump discipline demonstrably fails —
  i.e., when refresh **autonomy** matters more than logic **centralization**.
- **Reversal trigger:** (a) org-Actions-allowlist friction blocks onboarding on a material
  fraction of managed projects, **or** (b) P6 metrics show hub security fixes lag the fleet because
  SHA pins aren't bumped. Either promotes copied-templates-via-manifest from runner-up to design
  and justifies the dec-271→standalone-file generalization then. A single GitHub App (Option C)
  should be re-opened only if the *healing sidecar* (brief §5) needs unattended cross-repo issue
  filing — a distinct problem from workflow distribution.

## Prior Decision

Builds directly on `dec-272` (P0 shipped `ci-autofix.yml`). This ADR does **not**
supersede or re-affirm it — it **generalizes** the shipped workflow into the hub the P0 ADR's
Consequences already anticipated ("this fixer is caller #1 of the hub `reusable-ci-autofix.yml`
(P1)"). The P0 design and all its invariants are preserved unchanged inside the reusable workflow.
