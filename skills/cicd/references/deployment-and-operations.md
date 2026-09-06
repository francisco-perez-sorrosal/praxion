# CI/CD Deployment and Operations Examples

Complete workflow examples for the deploy-and-operate half of a pipeline: environment-protected deployments, Railway deploys, scheduled maintenance, PR validation, and a reusable composite setup action. Build, test, release, matrix, monorepo, and caching examples live in [patterns-and-examples.md](patterns-and-examples.md). All examples follow the same security baseline: SHA-pinned actions, least-privilege permissions, timeouts, and concurrency control. Back to [SKILL.md](../SKILL.md).

> **Note**: Replace `<full-sha>` placeholders with actual commit SHAs from each action's repository. Use Dependabot to keep pinned SHAs current.

## Deployment with Environment Protection

```yaml
name: Deploy
on:
  push:
    branches: [main]

permissions:
  contents: read
  id-token: write  # OIDC

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
      - run: echo "Run tests"

  deploy-staging:
    needs: test
    runs-on: ubuntu-latest
    timeout-minutes: 15
    environment:
      name: staging
      url: https://staging.example.com
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
      - uses: aws-actions/configure-aws-credentials@<full-sha>
        with:
          role-to-assume: ${{ vars.AWS_ROLE_STAGING }}
          aws-region: us-east-1
      - run: echo "Deploy to staging"

  smoke-test:
    needs: deploy-staging
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - run: curl -f https://staging.example.com/health

  deploy-production:
    needs: smoke-test
    runs-on: ubuntu-latest
    timeout-minutes: 15
    environment:
      name: production
      url: https://example.com
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
      - uses: aws-actions/configure-aws-credentials@<full-sha>
        with:
          role-to-assume: ${{ vars.AWS_ROLE_PRODUCTION }}
          aws-region: us-east-1
      - run: echo "Deploy to production"
```

## Railway Deploy
<!-- last-verified: 2026-08-05 -->

Railway ships no first-party GitHub Action — the official pattern is the CLI container image plus a project-scoped `RAILWAY_TOKEN` secret. Prefer Railway's built-in GitHub autodeploy with "Wait for CI" (holds the deploy until checks pass) when the repo is linked; deploy from Actions only when the pipeline must own the deploy step (monorepo carve-outs, promotion after gates).

```yaml
name: Deploy to Railway
on:
  push:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: railway-deploy-${{ github.ref }}
  cancel-in-progress: false  # never cancel a deploy mid-flight

jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    container: ghcr.io/railwayapp/cli:latest
    env:
      RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
      - run: railway up --service "${{ vars.RAILWAY_SERVICE_ID }}" --detach
```

- `RAILWAY_TOKEN` is project- and environment-scoped — one secret per target environment. Use `RAILWAY_API_TOKEN` only for account-level operations.
- `--detach` returns after upload; drop it to stream build logs into the job at the cost of runner minutes.
- The remote Railway MCP server is OAuth-only and cannot authenticate in CI — the CLI is the only headless path.
- Target-side configuration (environments, PR environments, config-as-code, auth matrix): deployment skill → [railway.md](../../deployment/references/railway.md).

## Scheduled Maintenance

```yaml
name: Maintenance
on:
  schedule:
    - cron: '0 6 * * 1'  # Monday 06:00 UTC

permissions:
  contents: read
  security-events: write

jobs:
  security-scan:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
      - name: Run security audit
        run: echo "Run dependency audit, SAST, secret scan"

  dependency-check:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
      - name: Check for outdated dependencies
        run: echo "Check outdated deps"

  performance-test:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
      - name: Run performance benchmarks
        run: echo "Run benchmarks, compare with baseline"
```

## PR Validation

```yaml
name: PR Checks
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]

permissions:
  contents: read
  pull-requests: read

concurrency:
  group: pr-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  validate:
    if: github.event.pull_request.draft == false
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false

      - name: Check PR title format
        run: |
          TITLE="${{ github.event.pull_request.title }}"
          if ! echo "$TITLE" | grep -qE '^(feat|fix|refactor|docs|test|chore):'; then
            echo "::error::PR title must follow conventional commits format"
            exit 1
          fi

      - name: Check PR size
        run: |
          ADDITIONS=${{ github.event.pull_request.additions }}
          DELETIONS=${{ github.event.pull_request.deletions }}
          TOTAL=$((ADDITIONS + DELETIONS))
          if [ "$TOTAL" -gt 1000 ]; then
            echo "::warning::Large PR ($TOTAL lines changed). Consider breaking into smaller PRs."
          fi
```

## Composite Action: Reusable Setup

```yaml
# .github/actions/project-setup/action.yml
name: 'Project Setup'
description: 'Standard project setup with caching'
inputs:
  python-version:
    description: 'Python version'
    default: '3.13'
  install-dev:
    description: 'Install dev dependencies'
    default: 'true'
outputs:
  cache-hit:
    description: 'Whether cache was hit'
    value: ${{ steps.cache.outputs.cache-hit }}
runs:
  using: 'composite'
  steps:
    - uses: actions/setup-python@<full-sha>
      with:
        python-version: ${{ inputs.python-version }}
        cache: 'pip'
      id: cache
    - run: |
        if [ "${{ inputs.install-dev }}" = "true" ]; then
          pip install -e ".[dev]"
        else
          pip install -e .
        fi
      shell: bash
```

Usage in workflows:

```yaml
steps:
  - uses: actions/checkout@<full-sha>
    with:
      persist-credentials: false
  - uses: ./.github/actions/project-setup
    with:
      python-version: '3.13'
  - run: pytest
```
