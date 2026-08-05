---
id: dec-294
title: Project-owned label-taxonomy manifest + additive-only reconciler (resolves #52)
status: accepted
category: architectural
date: 2026-07-28
summary: One-file baseline+additional label manifest, maintainer-owned, reconciled additively by a least-privilege hub reusable-workflow (SHA-pinned thin callers) that can define labels but never apply them; broad scope over the whole self-healing loop.
tags: [ci-cd, self-healing-loop, labels, taxonomy, github-actions, reconciler, fleet-rollout, onboarding, additive, least-privilege, governance, security]
made_by: agent
agent_type: systems-architect
branch: worktree-label-taxonomy-manifest
pipeline_tier: standard
affected_files:
  - .github/labels.yml
  - .github/workflows/reusable-labels-reconcile.yml
  - .github/workflows/labels-reconcile.yml
  - claude/project-baseline/labels/labels.yml.tmpl
  - claude/project-baseline/labels/labels-reconcile.yml.tmpl
  - commands/onboard-project.md
  - commands/upgrade-project.md
  - scripts/refresh_labels_baseline.py
  - scripts/upgrade_project_pins.sh
re_affirms: dec-281
dissent: 'A self-contained copied reconciler would carry ZERO cross-repo trust surface — no managed caller ever executes Praxion-controlled code, so a compromised hub commit cannot fan out `issues: write` across the whole fleet at once; for logic this trivial and stable, the hub''s propagation benefit may never be exercised while its supply-chain surface is real from day one.'
---

## Context

Issue #52 (`ecosystem-defect`, routed to `needs-adr` by the issue-autofix agent, cross-model-assessed `intake:defect`) reports that `gh issue create --label <name>` fails when a named label does not pre-exist in the target repo — GitHub's CLI does not auto-create labels the way the web "use this template" flow does. Multiple self-healing-loop surfaces silently assume their labels pre-exist:

- the managed-project reporter (`scripts/praxion_feedback/render.py::build_issue_labels` → `auto-filed`, `from-managed-project`, `category:<slug>`),
- the cross-model INTAKE gate (`issue-intake-assessment.yml`, whose `intake-assessment:*` / `intake:*` labels are documented only as "operator setup, not workflow code"),
- the cross-model review gate and ci-autofix hub (`cross-model-review:*`, `reviewed-by:<family>`, `autofix:declined`),
- the issue-autofix arming/triage labels (`ecosystem-feedback`, `needs-adr`, `triage:invalid`).

The #52 fixer (running without the Praxion plugin loaded) correctly classified this as a **taxonomy-ownership** decision, not a mechanical patch, and posted three candidate fixes. The user selected the fixer's **Option 2** (maintainer-owned manifest + reconciler) over Option 1 (reporter lazily seeds via `gh label create --force` — rejected: hands taxonomy control to the reporter, weakening the dec-281 arming-gate posture) and Option 3 (document + bootstrap script — rejected: no persistent diffable source of truth). The user's load-bearing requirement: **the target project owns its taxonomy**, starting from a common Praxion baseline, extensible per-project, expressed as a real configuration artifact in **one file**.

Research (`.ai-work/label-taxonomy-manifest/RESEARCH_FINDINGS.md`) established: 22 label literals (~20 non-GitHub-default) across the loop; 2 are live gaps on Praxion today (`reviewed-by:gemini`, `reviewed-by:composer`); no existing repo artifact expresses a "baseline list + project extension" merge shape; no existing reconciler touches live GitHub state (genuinely new mechanism type); `gh label create --force` is idempotent-safe; and GitHub's REST API places label *definition* and label *application* on structurally distinct endpoint families, so a reconciler built on `gh label *` is incapable — by construction — of ever applying a label to an issue.

## Decision

Ship three net-additive artifacts:

1. **A single-file, two-block manifest** `.github/labels.yml`: a Praxion-owned `baseline:` block and a project-owned `additional:` block, each a flat list of `{name, color, description}` entries. Family labels (`category:*`, `reviewed-by:*`, `intake:*`, `cross-model-review:*`, `intake-assessment:*`) are **pre-expanded to concrete entries**, grouped under comments that name the family and cite its enum source. **Broad scope**: the baseline declares every non-default self-healing-loop label, converging all four subsystems on one taxonomy authority. GitHub defaults (`bug`, `duplicate`) are intentionally excluded (always provisioned by GitHub; managing them would risk overwriting a project's own colors).

2. **An additive-only reconciler as a hub reusable-workflow + thin SHA-pinned callers** — mirroring the two existing self-healing-loop hubs (`reusable-ci-autofix.yml`, `reusable-cross-model-review.yml`). The **hub** `.github/workflows/reusable-labels-reconcile.yml` (`on: workflow_call` ONLY, top-level `permissions: {}`, its single job granting only `issues: write` + `contents: read`) checks out the caller repo's default branch, reads the manifest at the `manifest_path` input, and runs `gh label create <name> -c <color> -d <desc> --force` for every `baseline ++ additional` entry using the built-in `GITHUB_TOKEN` — **no external secret and no `secrets:` mapping** (the notable simplification vs. the two agent-driven hubs). A **thin caller** owns the real trigger (`push` to the manifest path on the default branch + `workflow_dispatch`) and the least-privilege `permissions:` ceiling: Praxion's own caller `.github/workflows/labels-reconcile.yml` pins the hub with a same-repo local `uses: ./.github/workflows/reusable-labels-reconcile.yml` (tracks HEAD — correct for the hub-developing repo), while every managed caller SHA-pins `{{PRAXION_HUB}}/.github/workflows/reusable-labels-reconcile.yml@{{HUB_SHA}}` (a resolved 40-hex SHA, never a mutable tag/branch). The hub is **NOT duplicated per project** — only the thin caller is installed downstream. **Additive-only**: the hub never deletes a label absent from the manifest, and — structurally, via the `gh label *` definition-endpoint surface — never applies a label to an issue/PR. The hub reusable-workflow choice buys the fleet automatic propagation of any future reconciler-logic fix via a single `/upgrade-project` SHA bump (the dec-288 pattern) and guarantees the reconcile logic can never drift between Praxion and its callers; it complies with dec-293 (which forbids a shared `./`-relative *composite action* inside a `workflow_call` hub — irrelevant here, since the hub inlines its loop rather than referencing a composite).

3. **Fleet wiring**: templates at `claude/project-baseline/labels/{labels.yml.tmpl, labels-reconcile.yml.tmpl}`; a new `/onboard-project` sub-step 8e.9 installs both under the same file-existence idempotency guard as 8e.8 (never overwrite); `/upgrade-project` gains a deterministic `refresh_labels_baseline.py` that replaces the `baseline:` block while preserving `additional:` verbatim — the mechanism by which Praxion's future baseline additions reach already-onboarded projects. A CI drift-gate test asserts the two enum-driven families (`_CATEGORY_CHOICES`, `reviewer_family`) are fully covered by the baseline.

The `reviewed-by:<family>` gap is closed by declaring **all three** enum values (`gpt`/`gemini`/`composer`) unconditionally in the baseline (drift-proof; harmless since unused definitions cost nothing), rather than deriving the concrete set from `autofix-policy.yml` at reconcile time (which would recouple and could re-open the failure on a future `reviewer_family` flip).

This ADR **re-affirms dec-281**: label *application* remains the human-only arming gate. The manifest declares `ecosystem-feedback`'s *existence* (so a human has it available to apply) without any code path capable of applying it.

## Considered Options

### Option A — Single-file two-block manifest + hub reusable-workflow reconciler (SHA-pinned thin callers), broad scope (CHOSEN)

- Pros: one diffable source of truth (user's explicit ask); broad scope converges all four subsystems and closes the intake gate's operator-setup gap; additive `--force` loop needs no diffing and is idempotent; **one central reconcile implementation** — a future logic fix propagates to the whole fleet via a single `/upgrade-project` SHA bump (dec-288 pattern) and the logic can never drift between Praxion and its callers; **structurally consistent with the two existing self-healing-loop hubs** (`reusable-ci-autofix.yml`, `reusable-cross-model-review.yml`) so a maintainer who understands one understands all three; baseline-refresh-on-upgrade propagates Praxion label additions; `ecosystem-feedback` invariant preserved by construction. **Simpler than the peer hubs** in one meaningful way: it uses the built-in `GITHUB_TOKEN` with no external secret, so it needs no `secrets:` mapping and no OIDC.
- Cons: SHA-pin/Actions-allowlist onboarding ceremony (one-time cost per caller) for what is today a trivial loop; adds a third hub reusable-workflow to the ecosystem's maintenance surface; introduces a cross-repo `workflow_call` trust edge — a compromised hub commit executes in every managed caller's context with `issues: write` (bounded: definition-endpoints only, never label application, never `contents: write`); a small structured-merge helper is still needed for baseline refresh; non-enum label literals can drift (mitigated by graceful fail-open + review).

### Option B — Self-contained copied reconciler workflow (no hub, no SHA pin)

- Pros: **zero cross-repo trust surface** — no managed caller ever executes Praxion-controlled code, so a compromised hub commit cannot fan out `issues: write` across the fleet; smallest onboarding footprint (no SHA-pin/allowlist step); for logic this trivial and stable there is effectively nothing to propagate, so "duplication" costs little; consistent with dec-293's controlled-duplication-over-shared-composite bias.
- Cons: the reconcile logic is copied per project, so any future logic fix (a dry-run mode, subtractive mode, per-family conditional, rate-limit backoff) must be re-shipped file-by-file via `/upgrade-project` and can silently drift between Praxion and stale installed copies; breaks structural consistency with the two existing hubs (three self-healing mechanisms, two shapes). Rejected: the user judged fleet-wide propagation + hub consistency worth the one-time pinning cost, and reconcilers accrete logic over time — the moment this one does, the copied-workflow choice has stranded every already-onboarded project on stale logic.

### Option C — Reporter lazily seeds labels via `gh label create --force` (the #52 fixer's Option 1)

- Pros: smallest diff; fixes the immediate reporter failure directly.
- Cons: hands taxonomy authority to the reporter (any category slug becomes a permanent upstream label) — the opposite of the user's requirement and at odds with dec-281's "arming labels are a controlled surface." Rejected by the user upfront.

### Option D — Two files (`labels.baseline.yml` overwritten on upgrade + `labels.additional.yml` project-owned)

- Pros: clean ownership; baseline refresh is a whole-file overwrite (no merge helper); mirrors the `rules/` two-location layering.
- Cons: violates the user's explicit "one file" requirement. Rejected on that constraint alone, though it is the natural runner-up to the single-file merge mechanics.

## Consequences

**Positive:**
- `gh issue create --label` and every self-healing-loop workflow's label-add are guaranteed to succeed on Praxion and any onboarded/forked project.
- Praxion's two live label gaps (`reviewed-by:{gemini,composer}`) close automatically on merge (push-on-manifest-path trigger).
- One maintainer-owned, diffable, PR-reviewable taxonomy; the intake gate's "operator setup" gap is subsumed.
- **One central reconcile implementation** — a future logic fix reaches the whole fleet via a single `/upgrade-project` SHA bump, and the reconcile logic can never drift between Praxion and its callers.
- **Structural consistency**: a third self-healing mechanism now follows the same hub+SHA-pinned-caller shape as ci-autofix and cross-model-review; the reconciler is the *simplest* of the three (built-in token, no external secret, no `secrets:` mapping, no OIDC).
- No new privileged CI surface beyond the least-privilege `issues: write` + `contents: read` grant; event-driven (no idle scheduled cost); the hub's top-level `permissions: {}` + per-job grant is the same least-privilege discipline the peer hubs use.
- dec-281's human-only arming invariant is strengthened (structurally re-affirmed, machine-checkable by a test).

**Negative / costs:**
- A new artifact type and convention (a labels manifest + reconciler hub + thin caller) enters the ecosystem — more surface to maintain, and a **third hub** to keep audited.
- A one-time SHA-pin/Actions-allowlist step is added to each caller's onboarding (mitigated: identical to the two hubs already installed by `/onboard-project`; `{{HUB_SHA}}` resolved at install time, bumped by `/upgrade-project`).
- A cross-repo `workflow_call` trust edge is introduced — a compromised Praxion hub commit runs in every managed caller's context with `issues: write` (bounded: `gh label *` definition-endpoints only, never label application, never `contents: write`; the same trust model the two existing hubs already carry with *broader* grants).
- Non-enum label literals rely on author discipline + review to stay in sync with the manifest (only the two enum-driven families are test-guarded).
- `/upgrade-project` gains a structured YAML-block merge (baseline refresh) — more than a SHA-token rewrite — in addition to the hub SHA bump.

## Disconfirmation

- **Falsifier:** This decision (the hub reusable-workflow) is wrong if, over the fleet's lifetime, the reconcile logic *never* changes AND no third GitHub-declarative-state consumer appears — because then the SHA-pin/Actions-allowlist ceremony bought a propagation guarantee that was never exercised, and a self-contained copy would have been strictly simpler with zero propagation cost incurred and zero cross-repo trust surface. It is also falsified if the cross-repo `workflow_call` trust edge turns out to be a *materially worse* blast radius than N independent copies — i.e., if a compromised or malicious Praxion hub commit fanning `issues: write` across every managed caller at once proves to be a real exploited/near-miss supply-chain risk that the copied-workflow approach structurally lacks. Independently, the whole feature is falsified if label literals drift from the manifest often enough that missing-label failures recur *despite* the manifest (a post-merge recurrence of a `gh ... --label` hard failure, or a workflow blocking on a manifest-absent label), which would indict the manifest concept regardless of reconciler mechanism.
- **Steelmanned runner-up (Option B, self-contained copied reconciler):** The reconciler is genuinely trivial and stable — ~15 lines of non-privileged `gh label create --force` over a flat manifest. A self-contained copy carries **zero cross-repo trust surface**: no managed caller ever executes Praxion-controlled code, so a compromised hub commit can't reach `issues: write` in every fleet repo simultaneously — a real supply-chain property the hub gives up from day one. The SHA-pin/allowlist onboarding step is friction the copy avoids entirely. And for logic this stable, "duplication" is nearly free because there is nothing to propagate: the propagation machinery the hub front-loads may sit unused for the feature's entire life. dec-293 chose exactly this — controlled duplication over a shared composite — for fleet logic that runs in caller context. The hub only wins *if* the reconciler accretes logic; if it never does, the copy was the simpler, safer choice all along.
- **Reversal trigger:** Revert to a self-contained copied reconciler (Option B) if any of: (a) the cross-repo `workflow_call` supply-chain surface proves to be a real exploited or near-miss risk — a compromised hub commit fanning out `issues: write` across the fleet; (b) after N months the hub's reconcile logic has never changed and no third GitHub-declarative-state consumer (branch protection, repo settings) has appeared, making the propagation benefit purely theoretical against a live trust surface; or (c) GitHub ships native label-manifest reconciliation, obsoleting the workflow entirely. Separately, if the `.github/labels.yml` two-block schema collides with an off-the-shelf label-sync action a project runs, namespace the path (`.github/praxion-labels.yml`).

## Prior Decision

Re-affirms **dec-281** ("Label application (ecosystem-feedback) is the HITL arming gate for issue autofix"). dec-281 established that *applying* the arming label is the human-only gate. This decision does not weaken that: the manifest declares the label's *existence* only, and the reconciler's tool surface (`gh label *` definition endpoints) is structurally incapable of *applying* any label to an issue/PR. A future supersession of dec-281 would require a change that lets automation apply arming labels — which this decision explicitly forecloses.
