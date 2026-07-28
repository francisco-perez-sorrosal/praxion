---
id: dec-292
title: PM-aware JS/TS install via default-branch lockfile detection + install-failure-degrades-to-decline
status: accepted
category: architectural
date: 2026-07-28
summary: Supersede dec-291's install-derivation — decouple the package manager (detected from the trusted default-branch lockfile, provisioned via corepack) from the js_test_runner enum, and make the install step continue-on-error + gate the fixer so an install failure degrades to Bug A's green clean decline
tags: [ci, self-healing, autofix, security, supply-chain, package-manager, pnpm, corepack, dependabot, robustness]
made_by: agent
agent_type: systems-architect
branch: worktree-autofix-pm-detect
pipeline_tier: standard
supersedes: dec-291
affected_files:
  - .github/workflows/reusable-ci-autofix.yml
  - .github/autofix-policy.yml
  - claude/project-baseline/ci-autofix/autofix-policy.yml.tmpl
  - dashboard_app/package-lock.json
  - tests/test_ci_autofix_hub_invariants.py
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-09]
dissent: Lockfile detection reads the trusted default-branch tree, but it makes the installer implicit — a repo with two lockfiles relies on documented precedence rather than an explicit admin declaration; an explicit provider.js_package_manager key would be more auditable at the cost of drift and config surface.
---

## Context

The #48 live dogfood of dec-290/291 confirmed Bug A's clean-decline works but exposed three runtime defects in dec-291's JS/TS install path — all invisible to the 62 structural tests, visible only at runtime:

1. **Package-manager mismatch.** dec-291's `JS_RUNNER_TABLE` coupled *test runner* and *package manager* into one enum row: `vitest → ("npm ci", "./node_modules/.bin/vitest run")`. Praxion's `dashboard_app` uses pnpm (`packageManager: pnpm@11.0.9`, `pnpm-lock.yaml`). `npm ci` latched onto a **stale leftover `dashboard_app/package-lock.json`** and failed `EUSAGE` (lockfile out of sync with `package.json`).
2. **Install failure fails the job (AC-1 regression).** The install step lacked `continue-on-error`, so its failure made the job **red** instead of degrading to Bug A's **green** clean decline — making a decline indistinguishable from a crash.
3. **Stale `dashboard_app/package-lock.json`** — a pre-pnpm leftover that `npm ci` latched onto.

dec-291's own Disconfirmation named a reversal trigger: *"revisit toward DEFER/off if the live dogfood shows the install + runner grant does not produce a clean verified-fix-or-decline cycle."* The dogfood fired it. But the failure is not the *decision* (PROCEED with the safe JS/TS-runner design) — it is the *mechanism* (enum-coupled installer; non-resilient install step). This ADR corrects the mechanism and re-affirms the decision.

Two invariants from dec-291 shape the fix: (a) the policy is read in `classify` from the **trusted default-branch** checkout, not the PR head; (b) `--allowedTools` must stay one physical line. The classify job already checks out the default branch at repo root before reading the policy — so lockfile *detection* can ride the same trusted checkout at zero additional trust cost.

## Decision

**Supersede dec-291's install-derivation and install-step robustness.** Keep everything else dec-291 decided (PROCEED with the JS/TS runner; enum-selected runner; non-agent `--ignore-scripts` install; runner-only agent grant; policy sourced from the trusted default branch).

1. **Decouple package manager from test runner.** The `js_test_runner` enum keeps selecting the **runner** (`js_test_grant` byte-identical to dec-291). The **installer** is derived from the package manager **detected from the default-branch lockfile** in `classify`, via a closed table:
   - `pnpm-lock.yaml` → `corepack enable && pnpm install --frozen-lockfile`
   - `yarn.lock` → `corepack enable && yarn install --frozen-lockfile`
   - `package-lock.json` (or none) → `npm ci`
   - fixed precedence pnpm > yarn > npm; fail-safe default npm.
   Detection reads only lockfile **presence** in the trusted default-branch tree — a closed-table lookup key, never file content templated into a command. Injection-safe by construction, the same trust source as the policy read. `--ignore-scripts` is still appended by the (non-agent) install step; each table row keeps the install verb as its tail so the appended flag binds.

2. **Provision pnpm/yarn via `corepack enable`** (bundled with the runner's pre-installed Node) — **no new `uses:` action to SHA-pin** on the privileged surface, fleet-uniform across pnpm/yarn-berry via each repo's `packageManager` pin, and correct whether or not pnpm is pre-installed on `ubuntu-latest`. `COREPACK_ENABLE_DOWNLOAD_PROMPT=0` prevents a non-TTY prompt hang.

3. **Install failure degrades to a green decline.** Add `id: js_install` + `continue-on-error: true` to the install step and gate the fixer on `steps.js_install.outcome != 'failure'` (`'skipped'`/`'success'` pass → Python path unchanged; `'failure'` skips the fixer → finalize declines → job exits 0). Bug A parity.

4. **Delete the stale `dashboard_app/package-lock.json`.**

No new policy key is required — detection removes config surface rather than adding it. No new job, no permission change, no runner-grant change, `--allowedTools` unchanged.

## Considered Options

### Option 1 — Lockfile detection + corepack (chosen)

- Pros: zero-config fleet correctness; injection-safe by construction (trusted default-branch presence-check → closed table); self-correcting on npm→pnpm migration; no new SHA-pinned action; correct under both hypotheses about the runner's pnpm state; install failure degrades to a green decline.
- Cons: installer is implicit (relies on documented precedence when two lockfiles coexist); adds filesystem-probing to the embedded classify script; yarn-berry flag semantics differ from classic (out of scope; pnpm is the live target).

### Option 2 — Explicit `provider.js_package_manager` policy key + `pnpm/action-setup` (steelmanned runner-up — not chosen)

- Pros: fully explicit and auditable — the admin declares the PM, no filesystem probing; `pnpm/action-setup` is the battle-tested canonical provisioner and reads the `packageManager` pin directly.
- Cons: re-introduces the *same class of defect* one layer up — a policy key that says `npm` while the repo migrated to pnpm drifts silently, exactly the mismatch #48 hit; adds config surface every managed repo must set correctly; `action-setup` is a **new third-party action on a `contents:write + id-token:write` surface** that must be SHA-pinned and maintained, and it only handles pnpm (yarn needs a different mechanism), so it is not fleet-uniform. The auditability gain is real but is outweighed by the drift risk and the new privileged-surface action.

### Option 3 — Keep the enum coupling, only fix Praxion's row to `pnpm install` (rejected)

- Rejected: hardcoding `pnpm` into the `vitest` row fixes Praxion but bakes the runner↔PM conflation deeper into the fleet contract — the next repo with `jest` + pnpm, or `vitest` + yarn, hits the identical bug. Treats the symptom, not the coupling.

## Consequences

- Positive: the installer matches the repo's real package manager fleet-wide with no config; install failures are green declines, not red jobs (strictly safer than dec-291); no new action, permission, or job; the runner grant and non-agent `--ignore-scripts` boundary are untouched, so dec-291's injection posture is preserved or improved.
- Negative: the embedded classify script grows a small detection function (still un-unit-testable in isolation — tested via YAML-string/exec assertions, unchanged from dec-291); yarn-berry repos are not fully covered (documented caveat); a repo with two committed lockfiles depends on precedence rather than an explicit declaration (the `dissent:` line).
- Reversible: `provider.js_test_runner: off` still disables the whole path per-repo (unchanged from dec-291); the corepack choice can be swapped for `pnpm/action-setup` without touching the detection logic.
- Residual supply-chain risk is **unchanged** from dec-291: test-time code still executes during the verification run in a `contents:write + id-token:write` job; `--ignore-scripts` still closes install-time lifecycle execution; no new risk class is introduced.

## Disconfirmation

- **Falsifier**: the re-triggered #48 dogfood (post-merge) again ends in a **failure** conclusion — e.g. corepack cannot provision `pnpm@11.0.9` on `ubuntu-latest` (no bundled corepack, or a blocked registry fetch), or `pnpm install --frozen-lockfile` fails on an in-sync lockfile, or the `continue-on-error` + fixer-gate still lets a red status escape. Any of these disproves this design and points back toward `pnpm/action-setup` (for provisioning) or `off` (to disable).
- **Steelmanned runner-up (Option 2)**: an explicit `provider.js_package_manager` key + SHA-pinned `pnpm/action-setup` would make the installer auditable and use the canonical provisioner, trading the drift risk for a hard admin declaration — defensible if fleet repos rarely migrate PMs and administrators prefer explicit over inferred. It was rejected because the drift failure mode is the very bug #48 exposed and because it adds a new action to a privileged surface; if PM drift proves rare and detection edge-cases proliferate, revisit toward the explicit key.
- **Reversal trigger**: revisit toward `pnpm/action-setup` if a future `ubuntu-latest` image drops bundled corepack or corepack provisioning proves flaky in CI; revisit toward the explicit `js_package_manager` key if lockfile detection produces a wrong installer on any real fleet repo (e.g. a monorepo with per-package lockfiles under one `js_project_dir`).

## Prior Decision

Supersedes **dec-291** (*Proceed with the JS/TS test-runner allowlist expansion for the same-repo fixer*). dec-291's headline decision is **re-affirmed**, not reversed: PROCEED with the JS/TS runner using the safe design — enum-selected runner, non-agent `--ignore-scripts` lockfile install, runner-only agent grant, policy sourced from the trusted default branch, residual test-time-execution risk accepted. This ADR corrects only the two mechanism defects the #48 dogfood exposed: (1) the installer is decoupled from the runner enum and detected from the default-branch lockfile (provisioned via corepack), replacing dec-291's enum-coupled `npm ci`; (2) the install step becomes `continue-on-error` with a fixer gate so an install failure degrades to Bug A's green decline instead of failing the job. Pairs with dec-290 (Bug A — the decline mechanism this fix routes install failures into) and extends the fix-commit envelope of dec-286 and the sensitive-path deny-by-default of dec-283, all unchanged.
