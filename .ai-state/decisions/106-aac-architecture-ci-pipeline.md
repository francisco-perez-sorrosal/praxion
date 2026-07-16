---
id: dec-106
title: Architecture CI pipeline — three parallel jobs invoking architect-validator on architectural-touch PRs
status: accepted
category: architectural
date: 2026-05-01
summary: 'Ship .github/workflows/architecture.yml with three parallel jobs (regenerate-and-diff, fitness-functions, dsl-validate); dsl-validate invokes the architect-validator agent via anthropics/claude-code-action; path-filter triggers prevent non-architectural PRs from running; mechanical fence check runs first to fail fast and avoid agent API spend.'
tags: [aac, dac, ci, github-actions, architect-validator, fitness, claude-code-action, gate, pre-merge]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - .github/workflows/architecture.yml
  - agents/cicd-engineer.md
re_affirms: dec-108
re_affirmed_by:
  - dec-108
---

## Context

`dec-100` chartered the `architect-validator` agent with a `--mode=pre-merge` invocation path and explicitly named the `cicd-engineer` as the author of the GitHub Actions workflow that invokes the validator: "the validator performs the reasoning; the harness manages the gate logic." `dec-101` chartered the architectural fitness functions infrastructure (`fitness/import-linter.cfg`, `fitness/tests/`) and committed to running them in CI. `dec-094` and `dec-098` together commit to the regenerate-and-diff property: committed renders must match what `likec4 gen` + `d2` produce from the source `.c4`.

V1 shipped the agents, the validator script, and the fitness infrastructure but did not ship the workflow. Without the workflow, `--mode=pre-merge` is unreachable from CI; fitness regressions are caught only by manual `pytest` runs; render drift is invisible until a human runs the diagram hook locally. The workflow is the missing harness.

## Decision

Ship `.github/workflows/architecture.yml` with three jobs running in parallel:

1. **`regenerate-and-diff`** — checks out the PR head, installs `likec4` + `d2`, runs the existing `scripts/diagram-regen-hook.sh`, and runs `git diff --exit-code -- docs/diagrams/`. Exits non-zero if the committed renders disagree with the freshly-generated ones.
2. **`fitness-functions`** — runs `uv run pytest fitness/tests/ -q` and `uv run lint-imports --config fitness/import-linter.cfg --no-cache`. Both must pass.
3. **`dsl-validate`** — runs `python scripts/aac_fence_validator.py` over every `**/ARCHITECTURE.md` and `docs/architecture.md` (mechanical check, fast-fail), then invokes the `architect-validator` agent in `--mode=pre-merge` via `anthropics/claude-code-action@v1` with the PR number passed in the prompt.

**Triggers**: `pull_request` and `push` to `main`, restricted by `paths:` to architectural-touch globs:
- `docs/diagrams/**`
- `**/*.c4`
- `**/ARCHITECTURE.md`
- `docs/architecture.md`
- `.ai-state/decisions/**`
- `fitness/**`
- `scripts/aac_fence_validator.py`
- `scripts/check_aac_golden_rule.py`

**Security/hardening conventions**:
- `permissions: {}` at workflow level; jobs add only what they need (`contents: read` for all; `id-token: write` for `dsl-validate` if `claude-code-action` requires it for OIDC).
- All actions pinned to full SHA, reusing the same SHAs already in `.github/workflows/test.yml` and `.github/workflows/claude-code-review.yml`.
- `timeout-minutes` on every job (10 for regenerate-and-diff and fitness-functions; 15 for dsl-validate to allow agent latency).
- `concurrency: { group: architecture-${{ github.ref }}, cancel-in-progress: true }`.

**Source-of-truth split**:
- Mechanical reasoning (path-pair existence, fence balance, attribute presence, render diff, fitness suite outcomes) lives in CI scripts.
- Structural reasoning (model↔code drift, ADR↔model drift, generated-region drift) lives in the `architect-validator` agent invoked in `dsl-validate`.

**No update to `skills/cicd/SKILL.md`** — the skill is generic CI/CD knowledge; AaC-specific patterns belong with AaC artifacts. `agents/cicd-engineer.md` Phase 1 gains a single bullet pointing to the new workflow as a reference pattern.

## Considered Options

### Option 1 — Sequential jobs with `needs:` chain

**Pros:** One feedback at a time; lower runner cost when jobs share intermediate state.

**Cons:** Slowest feedback. The three jobs are genuinely independent (no shared state): render-diff inspects `docs/diagrams/`; fitness inspects code imports + AST; dsl-validate inspects markdown fences + the validator agent. Forcing serial execution doubles or triples wall-clock with no logic gain. Rejected.

### Option 2 — Three parallel jobs (chosen)

**Pros:** Fastest feedback. Failures isolate cleanly to one job. Matches the existing `test.yml` matrix-style parallelism.

**Cons:** Three runner-minutes per architectural PR. The path-filter trigger keeps the cost bounded (only architectural PRs incur it).

### Option 3 — Workflow replicates the agent's checks in pure CI scripts

**Pros:** No API spend per PR.

**Cons:** Duplicates the agent's reasoning logic in shell scripts; the agent definition becomes the canonical reference and the workflow becomes a stale cousin. Violates `dec-100`'s split. Rejected.

### Option 4 — Workflow only runs the agent (no mechanical checks)

**Pros:** Single source of truth; one job.

**Cons:** Every architectural PR consumes Opus-class API budget for checks that a Python script can do mechanically (fence balance, attribute presence, render diff). Wasteful. Rejected.

### Option 5 — Hybrid: agent invoked only on PR explicitly labeled `aac-deep-validate`

**Pros:** Lowest API cost.

**Cons:** Defeats the gate property. Contributors can avoid the agent's reasoning by not adding the label. Rejected.

## Consequences

**Positive:**

- `architect-validator --mode=pre-merge` becomes reachable from CI; v1.1 closes dec-100's harness gap.
- Three independent failure modes surface cleanly: render drift, fitness regression, structural drift. Each has its own log and resolution path.
- Path-filter trigger keeps the workflow off non-architectural PRs; cost is bounded.
- Mechanical fence check runs first inside `dsl-validate`, fail-fast before the API spend.
- Reusable as a template by user projects via `/onboard-project` (deferred — see Operational below).

**Negative:**

- Adds Anthropic API cost per architectural PR. Mitigated by trigger filtering and fail-fast ordering.
- Requires the `ANTHROPIC_API_KEY` secret to be configured. Same precondition as the existing `claude-code-review.yml` workflow; not a new dependency.
- A PR that touches one architectural-trigger path triggers all three jobs. Acceptable; the alternative (per-job path filtering) creates required-checks fragility (a job that doesn't run cannot pass; required checks must always run).

**Operational:**

- The workflow file ships with all action SHAs pre-pinned to the values currently used in `.github/workflows/test.yml` and `.github/workflows/claude-code-review.yml`. Future bumps go through Dependabot.
- `agents/cicd-engineer.md` Phase 1 ("Read existing workflows") naturally surfaces this workflow when an agent is asked about CI patterns; no other prompt change is needed.
- The workflow is **Praxion-author-only** at v1.1. `/onboard-project` does not install it in user projects — that is a v2 deferral until the AaC fence convention has at least one consumer-project trial run.
- Library-version verification: GitHub Actions itself has no version (it is the runner). Action versions reuse the SHAs already pinned in the project; no new pin is introduced. `anthropics/claude-code-action@v1` is the moving-target pin from the existing workflow — kept consistent rather than version-locking, because the existing workflow demonstrates that policy.
- **Doc-feedback-loop note**: when implementing this workflow, the implementer should run `chub_search` for `claude-code-action` and submit `chub_feedback` per `external-api-docs` Step 5 if the curated docs differ from the current action surface. The architect-validator's invocation pattern is novel enough to be worth feedback.

## Prior Decision

This ADR re-affirms `dec-108` (the golden-rule enforcement hook, sibling draft). The CI workflow and the commit-time hook share `scripts/check_aac_golden_rule.py` as substrate but operate at different lifecycle points; they remain two ADRs because they have distinct surfaces and triggers. The CI workflow does **not** invoke `check_aac_golden_rule.py` directly — instead, it relies on the contributor's pre-commit hook to have caught the violation locally; the CI's three jobs cover the *post-commit* drift surfaces (render diff, fitness, fence/structural). If contributors disable their pre-commit hook, the golden-rule violation surfaces at PR time via the regenerate-and-diff job (renders re-generated will differ from committed) and via `dsl-validate` (fence validator catches fence-interior edits if the source did not change).
