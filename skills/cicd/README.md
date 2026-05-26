# cicd

CI/CD pipeline design and GitHub Actions workflow authoring. Covers pipeline architecture, testing stages, deployment strategies, caching, secrets management, security hardening, and performance optimization for production-ready pipelines.

## When to Use

- Creating or reviewing CI/CD pipelines or GitHub Actions workflows
- Configuring automated testing stages (lint, build, unit, integration, E2E)
- Setting up deployment automation (staging, production, release tagging)
- Debugging workflow failures or optimizing pipeline performance
- Implementing security hardening (action pinning, OIDC, least-privilege tokens)
- Designing caching strategies to reduce build times
- Choosing deployment strategies (blue-green, canary, rolling, feature flags)

## Activation

Activates automatically when working on `.github/workflows/` files or discussing CI/CD pipeline design, GitHub Actions, deployment automation, or build optimization.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core principles, pipeline architecture, deployment strategies, security hardening, caching, DORA metrics, anti-patterns, pre-merge checklist |
| `references/github-actions.md` | GitHub Actions workflow syntax, runners, action types, secrets management, security hardening, debugging |
| `references/patterns-and-examples.md` | Complete workflow examples for Python, Node, Rust, Go, Docker, release automation, and monorepo strategies |
| `references/ml-experiment-ci.md` | ML experiment CI patterns: eval-gated PRs, checkpoint artifact upload, baseline diffing, triggered dispatch, cost gating |

## Related Skills

- [`deployment`](../deployment/) -- deployment targets and platform configuration that CI/CD pipelines automate
- [`observability`](../observability/) -- DORA metrics complement application SLIs; monitoring deployed pipelines
- [`performance-architecture`](../performance-architecture/) -- performance regression detection patterns for CI pipelines
- [`python-development`](../python-development/) -- pytest patterns and linting configuration for CI steps
- [`python-prj-mgmt`](../python-prj-mgmt/) -- pixi/uv dependency installation commands for CI workflows
