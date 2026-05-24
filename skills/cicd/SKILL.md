---
name: cicd
description: >
  CI/CD pipeline design and GitHub Actions workflow authoring: pipeline
  architecture, testing stages, deployment strategies, caching, secrets
  management, security hardening, performance optimization. Triggers: creating
  CI/CD pipelines, writing GitHub Actions workflows, configuring automated
  testing, setting up deployment automation, debugging workflow failures,
  optimizing pipeline performance, reviewing CI/CD config, designing deployment
  pipelines, implementing build automation.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
---

# CI/CD Pipeline Development

Comprehensive guidance for designing CI/CD pipelines and authoring GitHub Actions workflows following production-ready practices.

**Satellite files** (loaded on-demand):

- [references/github-actions.md](references/github-actions.md) -- workflow syntax, runners, action types, secrets, environments, security hardening, debugging
- [references/patterns-and-examples.md](references/patterns-and-examples.md) -- complete workflow examples for Python, Node, Rust, Go, Docker, release automation, and monorepo strategies
- [references/ml-experiment-ci.md](references/ml-experiment-ci.md) -- ML experiment CI patterns: eval-gated PRs, checkpoint artifact upload, baseline diffing, triggered dispatch, cost gating

## Core Principles

**Fast Feedback**: Pipeline should fail at the earliest possible stage. Run cheap checks (lint, format) before expensive ones (build, test, deploy). Every minute saved in feedback loops compounds across the team.

**Reproducibility**: Builds must be deterministic. Pin dependencies, pin action versions to full SHA, use lockfiles, and avoid mutable references (`@main`, `@latest`).

**Security by Default**: Least-privilege permissions, OIDC over long-lived tokens, secret rotation, supply chain verification. Security is not a phase -- it's a property of every stage.

**Incremental Optimization**: Start with a working pipeline, then optimize. Caching, parallelism, and conditional execution are high-leverage improvements to apply iteratively.

## Pipeline Architecture

### Standard Stages

```text
Lint/Format --> Build --> Unit Test --> Integration Test --> Deploy Staging --> E2E Test --> Deploy Production
```

Each stage should be independently runnable and fail-fast. Stages with no dependencies run in parallel.

### Stage Design Rules

- **Lint and format first** -- cheapest, fastest feedback. Catches 80% of issues in seconds
- **Build before test** -- compilation errors are cheaper to find than test failures
- **Unit tests before integration** -- fast, deterministic, high signal-to-noise
- **E2E tests after staging deploy** -- test the real environment, not a simulation
- **Deploy in stages** -- staging validates the artifact before production sees it

### When to Run What

| Trigger | Stages |
| --- | --- |
| Every push | Lint, format, unit tests |
| Pull request | Lint, format, build, unit + integration tests, critical E2E |
| Merge to main | Full pipeline including staging deploy + E2E |
| Nightly schedule | Full E2E suite, performance tests, security scans |
| Release tag | Full pipeline + production deploy |

## Branch Strategy

**Trunk-based development** is the recommended approach for CI/CD:

- All developers merge small, frequent updates to a single main branch
- Short-lived feature branches merged within a day
- Feature flags manage incomplete features in trunk
- Every commit to trunk is potentially deployable

Prerequisites: robust test suite, feature flag infrastructure, team discipline around small increments, fast CI pipeline.

## Deployment Strategies

| Strategy | Mechanism | Rollback | Risk | Cost | Best For |
| --- | --- | --- | --- | --- | --- |
| **Blue-green** | Two identical environments; instant traffic switch | Instant | Low | High (2x infra) | Large deploys needing instant rollback |
| **Canary** | Gradual traffic shift (5-10% start) | Fast (reduce %) | Very low | Medium | Continuous delivery with real-user validation |
| **Rolling** | Instance-by-instance replacement | Moderate | Medium | Low | Resource-constrained environments |
| **Feature flags** | Code-level toggle, independent of deploy | Instant (toggle) | Very low | None | Decoupling deployment from release |

Combine strategies: trunk-based development + feature flags + canary for small daily releases; blue-green for larger deployments.

## GitHub Actions Essentials

### Workflow Structure

YAML files in `.github/workflows/`. Triggered by events, contain jobs with steps.

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read  # Least-privilege default

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<full-sha>
      - run: echo "lint here"

  test:
    needs: lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<full-sha>
      - run: echo "test here"
```

### Key Concepts

- **Jobs** run in parallel by default on separate runners. Use `needs` for sequential execution
- **Steps** within a job run sequentially on the same runner
- **Matrix strategy** runs a job across multiple configurations (OS, language version)
- **Concurrency** controls prevent redundant runs: `concurrency: { group: ${{ github.ref }}, cancel-in-progress: true }`

### Event Triggers

| Event | Use Case |
| --- | --- |
| `push` / `pull_request` | Standard CI (branch/path filters available) |
| `schedule` | Nightly builds, periodic security scans |
| `workflow_dispatch` | Manual trigger with custom inputs |
| `workflow_call` | Reusable workflow invocation |
| `release` | Release automation |
| `repository_dispatch` | External event trigger via API |

--> See [references/github-actions.md](references/github-actions.md) for complete workflow syntax, runner types, action types, and advanced configuration.

## Caching and Performance

**Caching is the highest-leverage optimization** -- up to 80% build time reduction.

### Dependency Caching

Setup actions handle caching natively:
```yaml
- uses: actions/setup-python@<full-sha>
  with:
    python-version: '3.13'
    cache: 'pip'
```

For custom caches, use `actions/cache` with lockfile-based keys:
```yaml
- uses: actions/cache@<full-sha>
  with:
    path: ~/.cache/pip
    key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements.txt') }}
    restore-keys: ${{ runner.os }}-pip-
```

### Performance Optimization Checklist

1. **Cache dependencies** -- lockfile-keyed, with fallback restore keys
2. **Parallelize independent jobs** -- lint, build, test as separate jobs
3. **Use path filters** -- only run workflows when relevant files change
4. **Cancel redundant runs** -- `concurrency` with `cancel-in-progress`
5. **Set timeouts** -- override the 6-hour default (30 min usually sufficient)
6. **Conditional execution** -- `if` conditions to skip unnecessary steps
7. **Use ARM64 runners** -- free for public repos, ~40% CPU improvement

Cache limit: 10 GB per repository. Artifacts default retention: 90 days (configurable 1-90).

## Secrets and Security

### Secret Hierarchy (precedence order)

1. **Environment secrets** (highest) -- scoped to deployment environments
2. **Repository secrets** -- available to all workflows in a repo
3. **Organization secrets** (lowest) -- shared across repos with policy-based access

### Security Hardening

| Practice | Implementation |
| --- | --- |
| **Pin actions to SHA** | `uses: actions/checkout@<full-sha>` -- tags can be tampered (CVE-2025-30066) |
| **Least-privilege token** | `permissions: {}` at workflow level, add only what's needed |
| **OIDC for cloud auth** | `id-token: write` + provider configuration -- no long-lived credentials |
| **Restrict pull_request_target** | Runs with write permissions on forked PRs -- use with extreme caution |
| **Set short timeouts** | `timeout-minutes: 30` on jobs |
| **Disable persist-credentials** | `persist-credentials: false` in `actions/checkout` unless needed |

### Supply Chain Security

- **SLSA framework**: Build provenance via `actions/attest-build-provenance`
- **Artifact attestations**: Cryptographically link artifacts to build metadata (Sigstore)
- **Dependabot**: Auto-updates dependencies, flags vulnerabilities
- **Secret scanning + push protection**: Blocks commits containing secrets

--> See [references/github-actions.md](references/github-actions.md) for OIDC configuration, environment protection rules, and the tj-actions incident analysis.

## Reusability Patterns

Three mechanisms for code reuse in GitHub Actions:

| Type | Scope | Best For |
| --- | --- | --- |
| **Composite action** | Steps within a job | Packaging reusable step sequences |
| **Reusable workflow** | Entire workflow (multiple jobs) | Standardizing pipelines across repos |
| **Custom action** (JS/Docker) | Single step with complex logic | Marketplace distribution, complex processing |

**Guidance**: Composite actions for team-internal reuse (flexible, composable). Reusable workflows for organizational standardization (opinionated, less flexible). Custom actions for complex logic or marketplace distribution.

--> See [references/github-actions.md](references/github-actions.md) for syntax details and comparison.

## Observability

### DORA Metrics

The standard for measuring DevOps performance:

- **Deployment frequency** -- how often code deploys to production (elite: multiple/day)
- **Lead time for changes** -- commit to production (elite: under 1 hour)
- **Change failure rate** -- % of deploys causing failures (elite: 0-15%)
- **Mean time to restore** -- recovery time after failure (elite: under 1 hour)

GitHub Actions provides built-in usage and performance metrics on all plans (since 2025).

## Anti-Patterns

| Anti-Pattern | Fix |
| --- | --- |
| **Pinning to `@main`/`@v1`** -- mutable references allow supply chain attacks | Pin to full SHA; use Dependabot for update PRs |
| **Overly permissive token** -- `permissions: write-all` or no permissions block | Set `permissions: {}` at workflow level, add specific permissions per job |
| **Monolithic pipeline** -- single job doing lint+build+test+deploy | Split into parallel jobs with `needs` for dependencies |
| **No caching** -- downloading dependencies on every run | Cache with lockfile-keyed `actions/cache` or setup action built-in caching |
| **Long-lived secrets** -- static API keys that never rotate | Use OIDC for cloud providers; rotate remaining secrets every 30-90 days |
| **No concurrency control** -- redundant runs stacking up | Add `concurrency` with `cancel-in-progress: true` |
| **6-hour default timeout** -- wasteful when jobs hang | Set `timeout-minutes` on every job (30 min default) |
| **Path filters on required checks** -- blocks merging when workflow doesn't run | Use `dorny/paths-filter` at job level instead of workflow-level path triggers |
| **Secrets in logs** -- `echo $SECRET` or debug output leaking credentials | Never echo secrets; use `::add-mask::` for dynamic values |
| **Testing only on PR** -- main branch can still break | Run full pipeline on merge to main, not just on PR |

## Integration with Other Skills

- **[Python Development](../python-development/SKILL.md)** -- pytest patterns, ruff/mypy configuration for CI steps
- **[Python Project Management](../python-prj-mgmt/SKILL.md)** -- pixi/uv commands for dependency installation in CI workflows
- **[Observability](../observability/SKILL.md)** -- application metrics and SLIs that complement DORA pipeline metrics

## Essential Marketplace Actions

| Category | Action | Purpose |
| --- | --- | --- |
| Core | `actions/checkout` | Clone repository |
| Core | `actions/cache` | Dependency/build caching |
| Core | `actions/upload-artifact` / `download-artifact` | Share data between jobs |
| Languages | `actions/setup-node`, `setup-python`, `setup-go`, `setup-java` | Language environment |
| Docker | `docker/build-push-action`, `docker/setup-buildx-action` | Container builds |
| Security | `actions/attest-build-provenance` | SLSA attestations |
| Security | `step-security/harden-runner` | Runner hardening |
| Filtering | `dorny/paths-filter` | Job-level path filtering |
| Release | `softprops/action-gh-release` | GitHub release creation |
| Linting | `rhysd/actionlint` | Workflow YAML validation |
| Debugging | `mxschmitt/action-tmate` | SSH into runner |

## Resources

- [GitHub Actions Workflow Syntax](https://docs.github.com/actions/reference/workflow-syntax-for-github-actions) -- complete YAML reference
- [GitHub Security Hardening](https://docs.github.com/en/actions/reference/security/secure-use) -- security best practices
- [GitHub OIDC](https://docs.github.com/en/actions/concepts/security/openid-connect) -- cloud authentication without secrets
- [SLSA Framework](https://slsa.dev/) -- supply chain security levels
- [DORA Metrics](https://dora.dev/guides/dora-metrics/) -- DevOps performance measurement
- [nektos/act](https://github.com/nektos/act) -- run workflows locally
- [rhysd/actionlint](https://github.com/rhysd/actionlint) -- static analysis for workflow YAML

## Pre-Merge Checklist

Before merging CI/CD configuration changes:

- [ ] Actions pinned to full SHA (not tags or branches)
- [ ] `permissions` block set with least-privilege scope
- [ ] Secrets used via environment or repository secrets (not hardcoded)
- [ ] `timeout-minutes` set on all jobs
- [ ] Concurrency group configured for PR workflows
- [ ] Caching enabled for dependencies
- [ ] Path filters applied where appropriate
- [ ] `actionlint` passes on all workflow files
- [ ] Test the workflow with `act` or a dry-run branch before merging
