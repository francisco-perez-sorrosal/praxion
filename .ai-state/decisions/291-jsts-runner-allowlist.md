---
id: dec-291
title: Proceed with the JS/TS test-runner allowlist expansion for the same-repo fixer
status: accepted
category: architectural
date: 2026-07-28
summary: User-approved PROCEED (overriding the systems-architect's advisory DEFER) with the safe design — enum-selected runner, non-agent --ignore-scripts lockfile install, runner-only agent grant, policy sourced from the trusted default branch
tags: [ci, self-healing, autofix, security, supply-chain, allowlist, dependabot, user-override]
made_by: agent
agent_type: systems-architect
branch: worktree-autofix-fixer-hardening
pipeline_tier: standard
affected_files:
  - .github/workflows/reusable-ci-autofix.yml
  - .github/autofix-policy.yml
  - claude/project-baseline/ci-autofix/autofix-policy.yml.tmpl
  - tests/test_ci_autofix_hub_invariants.py
dissent: A --ignore-scripts install stops postinstall/lifecycle-script execution, but not a malicious test file or test-time config running arbitrary JS during the verification run itself — inside a contents:write + id-token:write job. DEFER would have avoided this residual test-time execution risk entirely.
---

## Context

The `autofix-same-repo-pr` fixer agent's `--allowedTools` grants Python test runners only (`Bash(uv run pytest:*)`, `Bash(python3 -m pytest:*)`, `Bash(pytest:*)`). On a JS/TS failure (e.g. the dashboard's vitest suite) the agent cannot run the tests to verify a candidate fix, so it iterates blind and exhausts `--max-turns` — the likely root cause of Bug A's live #48 instance. Bug A (`dec-290`) converts that thrash into a bounded, clean decline; this ADR is about whether to go further and let the fixer *verify* a JS/TS fix.

The load-bearing concern is that this job holds `contents: write` (to the PR head) + `id-token: write` (OIDC as the Claude app) and processes untrusted CI-log data. Any capability added here is added on a privileged surface. Running JS/TS tests requires installing JS deps, and JS `postinstall`/lifecycle scripts are a materially larger and more actively-exploited supply-chain surface than the Python path. On a Dependabot PR — the primary target — install executes the *changed* dependency's code in a higher-privilege context than the PR's own CI.

Two existing invariants shape the design space: (a) the governing policy is read in `classify` from the **trusted default-branch** checkout, not the PR head, so a malicious PR cannot alter the policy that governs its own fix; (b) `--allowedTools` must stay a single physical line or it is silently narrowed at runtime.

## Decision

**PROCEED with the safe design**, overriding the systems-architect's advisory DEFER. The user reviewed the DEFER recommendation and the full risk analysis below and explicitly chose to accept the residual supply-chain risk in exchange for closing the JS/TS capability gap now, alongside Bug A, in the same pipeline.

Rationale for DEFER (superseded by the user's PROCEED override below):
- Bug A already closes the actual defect (stranding + idempotency). With it in place, a JS/TS max-turns thrash costs one bounded 30-turn decline, then the label suppresses re-trigger — the expensive-re-trigger problem is solved regardless of this ADR.
- The value of proceeding is bounded (JS/TS declines become JS/TS fixes); the cost is a trust expansion on a privileged surface that only a live dogfood can validate (structural tests are blind to CLI-runtime + permission behavior). Bundling that validation cycle with Bug A would delay the low-risk fix.
- Separation of concerns: do not mix a privileged-surface capability change into a smaller behavior fix.

**User override:** the systems-architect's DEFER recommendation above was reviewed and explicitly overridden by the user in favor of PROCEED, accepting the residual risk in the `dissent:` line, because (a) Bug A ships in the same pipeline so any JS/TS-runner failure still degrades to a bounded clean decline rather than a stranded PR, and (b) the Python fixer already installs and executes Dependabot-bumped Python deps in this exact privileged job, so the enum-gated `--ignore-scripts` JS/TS runner reaches parity with a risk the loop already carries rather than introducing a new risk class.

The vetted design (PROCEED, chosen):
1. **Enum selector** in policy (`provider.js_test_runner: off | vitest | jest | npm-test | pnpm-test`, default `off`) — never a free-form command string templated into the allowlist. `classify` maps the enum to two fixed strings via a hardcoded table.
2. **Non-agent install step** running `npm ci --ignore-scripts` (or `pnpm install --frozen-lockfile --ignore-scripts`) from the lockfile in the PR-head checkout — `--ignore-scripts` disables the postinstall lifecycle-script class entirely; the agent's allowlist never grants an install command.
3. **Runner-only agent grant** (`Bash(./node_modules/.bin/vitest run:*)`) appended as one token on the existing single allowlist line; empty when the selector is `off` (byte-identical to today).
4. Install/runner strings resolved from the trusted default-branch policy read; per-repo opt-in.

## Considered Options

### Option 1 — DEFER; ship Bug A alone (steelmanned runner-up — not chosen)

- Pros: the real defect ships fast and low-risk; no privileged-surface trust expansion rides along; JS/TS degrades to a clean decline (graceful, not a regression); a follow-up would get its own dedicated dogfood cycle.
- Cons: JS/TS PRs get declines, not verified fixes — a real, asymmetric capability gap accepted by choosing PROCEED instead.

### Option 2 — PROCEED with the safe design (chosen)

- Pros: closes the capability gap; `--ignore-scripts` neutralizes the biggest JS-vs-Python asymmetry, reaching parity with the risk the Python path already carries; enum + trusted-default-branch policy make the grant injection-safe by construction; ships alongside Bug A so JS/TS failures still degrade to a clean decline rather than a stranded PR.
- Cons: still expands a privileged surface; residual risk = a malicious test file's *runtime* code executing during the test run in a `contents:write`+`id-token:write` job (not eliminated by `--ignore-scripts`); needs its own live dogfood before full trust.

### Option 3 — PROCEED naively (agent-driven install-and-test grant)

- Rejected: agent-chosen install on a privileged job that processes untrusted logs is the worst injection posture — no `--ignore-scripts` discipline, no non-agent boundary.

## Consequences

- Positive (PROCEED): closes the JS/TS capability gap in the same pipeline as Bug A; one classifier table + two `classify` outputs + one non-agent install step + one templated allowlist token; no new job, no privilege change, no push/merge grant; enum + trusted-default-branch design keeps the tool-grant boundary injection-safe.
- Negative (PROCEED): the privileged surface (`contents: write` + `id-token: write`) now also executes JS/TS test-time code for opted-in repos; the residual test-time-execution risk (see `dissent:` above) is accepted, not eliminated, and must be validated by its own live dogfood (see Disconfirmation) before broader fleet rollout.
- Reversible: Option 1 (DEFER) remains available — the `provider.js_test_runner` policy key can be flipped back to `off` per-repo (or the feature pulled entirely) without touching Bug A.

## Disconfirmation

- **Falsifier**: a live dogfood on a real JS/TS PR shows `--ignore-scripts` install still permits attacker-controlled code execution during the verification run (a malicious test file, a test-time config hook, a build step the runner needs) that reaches beyond the sandboxed job — this disproves PROCEED and should trigger an immediate revert to `off`. Conversely, if JS/TS Dependabot traffic turns out to be a small fraction of traffic and the capability gap causes little toil, that would have favored DEFER instead.
- **Steelmanned runner-up (Option 1, DEFER)**: DEFER would have shipped Bug A alone, kept the privileged surface's blast radius unchanged, and pushed the trust-expansion decision to a dedicated follow-up with its own focused dogfood cycle — cleaner separation of concerns, and no risk of the two changes' failure modes compounding in one pipeline. The user weighed this against the immediate value of closing the capability gap and chose PROCEED with full knowledge of this trade-off.
- **Reversal trigger**: revisit toward DEFER/off if the live dogfood on a JS/TS PR shows the `--ignore-scripts` non-agent install + runner-only grant does not produce a clean verified-fix-or-decline cycle, or if any test-time code execution reaches outside the expected sandbox — flip `provider.js_test_runner` back to `off` (per-repo, reversible) and re-open this ADR.

## Prior Decision

Extends the fix-commit envelope established by dec-286 (single job owns the security controls) and dec-283 (sensitive-path deny-by-default), and pairs with `dec-290` (Bug A) — Bug A's finalize/decline step is what makes accepting this residual risk tractable: any JS/TS-runner failure converges to a bounded clean decline rather than a stranded or thrashing PR. This entry amends the systems-architect's original DEFER recommendation in place (still `status: proposed`, not yet finalized) to record the user's explicit PROCEED override at the implementation-planning stage, per direct user instruction.
