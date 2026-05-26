# GitHub Actions Reference

Deep reference for GitHub Actions workflow syntax, runners, action types, secrets management, security hardening, and debugging. Back to [SKILL.md](../SKILL.md).

## Workflow Syntax

### Complete Workflow Structure

```yaml
name: CI Pipeline
run-name: ${{ github.actor }} -- CI run

on:
  push:
    branches: [main, 'release/**']
    paths: ['src/**', 'tests/**']
    paths-ignore: ['docs/**']
  pull_request:
    branches: [main]
    types: [opened, synchronize, reopened]
  schedule:
    - cron: '0 6 * * 1'  # Every Monday at 06:00 UTC
  workflow_dispatch:
    inputs:
      environment:
        description: 'Target environment'
        required: true
        default: 'staging'
        type: choice
        options: [staging, production]
  workflow_call:
    inputs:
      version:
        required: true
        type: string
    secrets:
      deploy_token:
        required: true

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

env:
  NODE_ENV: production

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    environment: staging
    outputs:
      version: ${{ steps.version.outputs.value }}

    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
        python-version: ['3.12', '3.13']
        exclude:
          - os: macos-latest
            python-version: '3.12'
        include:
          - os: ubuntu-latest
            python-version: '3.13'
            coverage: true
      fail-fast: true
      max-parallel: 4

    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false

      - name: Set version
        id: version
        run: echo "value=$(cat VERSION)" >> "$GITHUB_OUTPUT"

      - name: Conditional step
        if: matrix.coverage == true
        run: echo "Running with coverage"
```

### Expressions and Contexts

```yaml
# Status check functions
if: success()         # Previous steps succeeded (default)
if: failure()         # Any previous step failed
if: always()          # Run regardless of status
if: cancelled()       # Workflow was cancelled

# Context references
${{ github.event_name }}          # Event that triggered the workflow
${{ github.ref_name }}            # Branch or tag name
${{ github.sha }}                 # Full commit SHA
${{ github.actor }}               # User who triggered the workflow
${{ secrets.MY_SECRET }}          # Repository/org/environment secret
${{ vars.MY_VARIABLE }}           # Repository/org variable
${{ env.MY_ENV }}                 # Environment variable
${{ needs.job_id.outputs.key }}   # Output from a dependent job
${{ steps.step_id.outputs.key }}  # Output from a previous step
${{ matrix.os }}                  # Current matrix value
${{ runner.os }}                  # Runner OS (Linux, macOS, Windows)

# Useful expressions
${{ contains(github.event.head_commit.message, '[skip ci]') }}
${{ startsWith(github.ref, 'refs/tags/v') }}
${{ github.event.pull_request.draft == false }}
${{ toJSON(github.event) }}       # Debug: dump entire event payload
${{ hashFiles('**/package-lock.json') }}  # Content hash for cache keys
${{ fromJSON(needs.setup.outputs.matrix) }}  # Dynamic matrix
```

### Outputs Between Steps and Jobs

```yaml
jobs:
  setup:
    runs-on: ubuntu-latest
    outputs:
      should-deploy: ${{ steps.check.outputs.deploy }}
    steps:
      - id: check
        run: |
          # Single value
          echo "deploy=true" >> "$GITHUB_OUTPUT"
          # Multiline value
          {
            echo "changelog<<EOF"
            cat CHANGELOG.md
            echo "EOF"
          } >> "$GITHUB_OUTPUT"

  deploy:
    needs: setup
    if: needs.setup.outputs.should-deploy == 'true'
    runs-on: ubuntu-latest
    steps:
      - run: echo "Deploying..."
```

## Runners

### GitHub-Hosted Runners

| Runner | vCPU | RAM | Storage | Notes |
| --- | --- | --- | --- | --- |
| `ubuntu-latest` | 4 | 16 GB | 14 GB SSD | Default choice |
| `ubuntu-24.04` | 4 | 16 GB | 14 GB SSD | Pin for reproducibility |
| `macos-latest` | 3-4 | 14 GB | 14 GB SSD | More expensive per-minute |
| `windows-latest` | 2 | 7 GB | 14 GB SSD | Most expensive |
| `ubuntu-latest-arm` | 4 | 16 GB | 14 GB SSD | ARM64, free for public repos |

**Larger runners** (Team/Enterprise): up to 64 vCPU, GPU runners available.

**ARM64 runners** (public preview 2025): Cobalt 100 processors, ~40% CPU improvement. Free for public repos. All official actions compatible; verify community actions.

**Best practice**: Pin to specific OS version (e.g., `ubuntu-24.04`) instead of `ubuntu-latest` for build reproducibility.

### Self-Hosted Runners

- Full control over hardware, OS, and software
- No per-minute billing (but infrastructure costs)
- **Not recommended for public repos** -- arbitrary code execution risk from fork PRs
- Third-party managed alternatives: RunsOn, Blacksmith, Namespace, WarpBuild

## Action Types

### Composite Actions

Bundle multiple steps into a reusable unit. No separate runtime -- steps run on the caller's runner.

```yaml
# .github/actions/setup-python-env/action.yml
name: 'Setup Python Environment'
description: 'Install Python and dependencies'
inputs:
  python-version:
    description: 'Python version'
    required: false
    default: '3.13'
runs:
  using: 'composite'
  steps:
    - uses: actions/setup-python@<full-sha>
      with:
        python-version: ${{ inputs.python-version }}
        cache: 'pip'
    - run: pip install -r requirements.txt
      shell: bash
```

### Reusable Workflows

Standardize entire pipelines. Invoked at the job level with `workflow_call`.

```yaml
# .github/workflows/reusable-ci.yml
name: Reusable CI
on:
  workflow_call:
    inputs:
      python-version:
        required: true
        type: string
    secrets:
      codecov-token:
        required: false

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<full-sha>
      - uses: actions/setup-python@<full-sha>
        with:
          python-version: ${{ inputs.python-version }}
      - run: pytest --cov
```

```yaml
# Caller workflow
jobs:
  ci:
    uses: ./.github/workflows/reusable-ci.yml
    with:
      python-version: '3.13'
    secrets: inherit  # Pass all secrets (or list individually)
```

### Comparison

| Aspect | Composite Action | Reusable Workflow |
| --- | --- | --- |
| Scope | Steps within a job | Entire workflow (multiple jobs) |
| Runner | Inherits caller's runner | Each job specifies its own |
| Secrets | Accesses caller's secrets | Must be explicitly passed or use `secrets: inherit` |
| Invocation | `steps[].uses` | `jobs.<id>.uses` |
| Best for | Step bundles, team-internal reuse | Pipeline standardization across repos |

## Secrets Management

### OIDC for Cloud Authentication

Eliminates long-lived credentials. The workflow requests a short-lived token from the cloud provider.

```yaml
permissions:
  id-token: write   # Required for OIDC
  contents: read

steps:
  - uses: aws-actions/configure-aws-credentials@<full-sha>
    with:
      role-to-assume: arn:aws:iam::123456789012:role/github-actions
      aws-region: us-east-1
```

Supported providers: AWS, Azure, GCP, HashiCorp Vault.

### Environment Protection Rules

```yaml
jobs:
  deploy-prod:
    environment:
      name: production
      url: https://example.com
    runs-on: ubuntu-latest
```

Configure in repository settings:
- **Required reviewers** -- up to 6 per environment
- **Wait timers** -- 1 min to 30 days (does not consume billable minutes)
- **Deployment branches** -- restrict which branches can deploy
- **Self-review prevention** -- prevent the deployer from approving their own deploy

Note: On Free/Pro/Team plans, protection rules only available for public repos.

### Secret Best Practices

- Use OIDC over long-lived tokens for all cloud providers
- Rotate remaining secrets every 30-90 days
- Use descriptive naming: `AWS_PROD_ACCESS_KEY`, `STAGING_DB_PASSWORD`
- Scope org secrets to specific repos (avoid all-repo access)
- Use `GITHUB_TOKEN` (auto-generated, scoped, short-lived) whenever possible
- Non-sensitive config goes in GitHub Variables (`vars.*`), not secrets

## Security Hardening

### GITHUB_TOKEN Permissions

```yaml
# Workflow-level: deny by default
permissions: {}

jobs:
  build:
    permissions:
      contents: read      # Read repo code
      packages: write     # Push to GitHub Packages
      id-token: write     # OIDC authentication
```

Always start with empty permissions and add only what's needed per job.

### Third-Party Action Security

**Pin to full SHA** -- the only immutable reference:

```yaml
# Correct -- immutable
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2

# Dangerous -- tags can be force-pushed
- uses: actions/checkout@v4

# Very dangerous -- mutable branch reference
- uses: actions/checkout@main
```

**The tj-actions/changed-files incident (March 2025, CVE-2025-30066)**: Attackers compromised a maintainer's PAT, retroactively modified all version tags to point to malicious code that dumped CI secrets from runner memory into logs. Affected 23,000+ repos in 15 hours. SHA pinning is the only defense against tag tampering.

**Mitigation**:
- Pin all actions to full SHA
- Use Dependabot to get update PRs for pinned actions
- Fork critical third-party actions for additional control
- Use `step-security/harden-runner` to audit action behavior

### Repository Rulesets

Replace deprecated "required workflows". Organization-level mandatory checks enforced via repository rules. Require specific workflows to pass before merge.

### Workflow Security Checklist

- [ ] `permissions: {}` at workflow level with per-job grants
- [ ] All actions pinned to full SHA
- [ ] `persist-credentials: false` in `actions/checkout`
- [ ] `timeout-minutes` set on all jobs
- [ ] No `pull_request_target` without careful review
- [ ] Secrets never echoed or logged
- [ ] OIDC configured for cloud provider authentication
- [ ] Dependabot configured for action version updates

## Artifacts

### Sharing Data Between Jobs

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo "build output" > dist/app.js
      - uses: actions/upload-artifact@<full-sha>
        with:
          name: build-output
          path: dist/
          retention-days: 7
          compression-level: 6  # 0 for pre-compressed files

  deploy:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@<full-sha>
        with:
          name: build-output
          path: dist/
```

**Tips**:
- Set `retention-days` to minimize storage costs
- Use `compression-level: 0` for already-compressed files
- Use `overwrite: true` to replace artifacts with the same name
- Tar files before upload to preserve permissions
- For large artifacts, consider external storage (S3, Azure Blob)

## Debugging and Troubleshooting

### Debug Logging

```yaml
# Enable for a single run via env
env:
  ACTIONS_STEP_DEBUG: true
  ACTIONS_RUNNER_DEBUG: true
```

Or set repository variables `ACTIONS_STEP_DEBUG = true` for all runs.

### Local Testing

**`nektos/act`** -- run workflows locally in Docker:
```bash
# Run default event (push)
act

# Run specific workflow
act -W .github/workflows/ci.yml

# Run specific job
act -j test

# With secrets
act --secret-file .env.secrets
```

Catches configuration errors and validates step execution order. Not a full GitHub runner replica -- some features differ.

**`actionlint`** -- static analysis for workflow YAML:
```bash
# Install
brew install actionlint

# Lint all workflows
actionlint

# Lint specific file
actionlint .github/workflows/ci.yml
```

Catches syntax errors, expression mistakes, unused variables, runner compatibility issues.

### Interactive Debugging

```yaml
# SSH into a running workflow for live debugging
- uses: mxschmitt/action-tmate@<full-sha>
  if: failure()  # Only on failure
  with:
    limit-access-to-actor: true  # Restrict to workflow triggerer
```

### Common Issues

| Issue | Cause | Fix |
| --- | --- | --- |
| Workflow doesn't trigger | Path/branch filter mismatch | Check `on.push.paths` and `on.push.branches` filters |
| Required check blocks merge | Path-filtered workflow doesn't run for some PRs | Use `dorny/paths-filter` at job level instead |
| `workflow_dispatch` inputs not accessible | Wrong context reference | Use `github.event.inputs.*` for dispatch, `inputs.*` for `workflow_call` |
| Concurrency not working on reusable workflows | Concurrency defined in caller | Define concurrency in the called workflow, not the caller |
| Self-hosted runner not picking up jobs | Runner labels mismatch | Verify `runs-on` matches runner label configuration |
| Cache miss despite same lockfile | OS or runner change | Include `runner.os` in cache key |
| Action fails after update | Tag-based pinning | Pin to full SHA; use Dependabot for controlled updates |

## Cost Optimization

### Billing Model

- **Public repos**: Standard runners free, unlimited minutes
- **Private repos**: Monthly included minutes, then pay per minute
- **Multipliers**: macOS = 10x, Windows = 2x, larger runners = variable

### Cost Reduction Strategies

1. Cache dependencies aggressively (reduces minutes per run)
2. Cancel redundant runs with `concurrency` groups
3. Run expensive tests only on merge to main, not every push
4. Use ARM64 runners when compatible (free for public, cheaper for private)
5. Set short `retention-days` on artifacts to reduce storage costs
6. Use path filters to skip workflows when irrelevant files change
7. Set `timeout-minutes` to prevent runaway jobs burning minutes

## Supply Chain Security

### Artifact Attestations (GA 2024)

```yaml
permissions:
  id-token: write
  attestations: write

steps:
  - uses: actions/attest-build-provenance@<full-sha>
    with:
      subject-path: dist/app.tar.gz
```

- Generates SLSA build provenance with Sigstore signing
- Public repos: Sigstore Public Good Instance + immutable transparency log
- Private repos: GitHub's Sigstore instance (no transparency log)
- Also available: `actions/attest-sbom` for Software Bill of Materials

### SLSA Levels

| Level | Requirement |
| --- | --- |
| **1** | Build process fully scripted, provenance metadata generated |
| **2** | Builds on hosted platform, provenance cryptographically signed |
| **3** | Isolated environments, no external influence, non-reusable |

GitHub Actions with attestation actions achieves SLSA Level 2 out of the box.

## GitHub Actions Metrics (2025)

Available on Free, Pro, and Team plans:

- **Usage metrics**: Minutes consumed per workflow, runner OS distribution, resource-intensive jobs
- **Performance metrics**: Job run times, queue times, failure rates
- Available at organization and repository levels

Use these to identify optimization targets: slowest workflows, most resource-hungry jobs, highest failure rates.
