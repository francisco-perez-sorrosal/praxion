# CI/CD Patterns and Examples

Complete workflow examples for common scenarios. All examples follow security best practices: SHA-pinned actions, least-privilege permissions, caching, timeouts, and concurrency control. Back to [SKILL.md](../SKILL.md).

> **Note**: Replace `<full-sha>` placeholders with actual commit SHAs from each action's repository. Use Dependabot to keep pinned SHAs current.

## Python CI

Full pipeline with ruff, mypy, pytest, and coverage.

```yaml
name: Python CI
on:
  push:
    branches: [main]
    paths: ['src/**', 'tests/**', 'pyproject.toml']
  pull_request:
    branches: [main]
    paths: ['src/**', 'tests/**', 'pyproject.toml']

permissions:
  contents: read

concurrency:
  group: python-ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
      - uses: actions/setup-python@<full-sha>
        with:
          python-version: '3.13'
      - run: pip install ruff
      - run: ruff check .
      - run: ruff format --check .

  typecheck:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
      - uses: actions/setup-python@<full-sha>
        with:
          python-version: '3.13'
          cache: 'pip'
      - run: pip install -e ".[dev]"
      - run: mypy src/

  test:
    needs: [lint, typecheck]
    runs-on: ubuntu-latest
    timeout-minutes: 15
    strategy:
      matrix:
        python-version: ['3.12', '3.13']
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
      - uses: actions/setup-python@<full-sha>
        with:
          python-version: ${{ matrix.python-version }}
          cache: 'pip'
      - run: pip install -e ".[dev]"
      - run: pytest --cov --cov-report=xml -x
      - uses: actions/upload-artifact@<full-sha>
        if: matrix.python-version == '3.13'
        with:
          name: coverage-report
          path: coverage.xml
          retention-days: 7
```

### Python with pixi

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
      - uses: prefix-dev/setup-pixi@<full-sha>
        with:
          cache: true
      - run: pixi run lint
      - run: pixi run typecheck
      - run: pixi run test
```

### Python with uv

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@<full-sha>
        with:
          enable-cache: true
      - run: uv run ruff check .
      - run: uv run mypy src/
      - run: uv run pytest --cov -x
```

## Node.js CI

```yaml
name: Node CI
on:
  push:
    branches: [main]
    paths: ['src/**', 'tests/**', 'package.json']
  pull_request:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: node-ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    strategy:
      matrix:
        node-version: [20, 22]
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
      - uses: actions/setup-node@<full-sha>
        with:
          node-version: ${{ matrix.node-version }}
          cache: 'npm'
      - run: npm ci
      - run: npm run lint
      - run: npm run typecheck
      - run: npm test -- --coverage
```

## Rust CI

```yaml
name: Rust CI
on:
  push:
    branches: [main]
    paths: ['src/**', 'Cargo.toml', 'Cargo.lock']
  pull_request:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: rust-ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  check:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
      - uses: dtolnay/rust-toolchain@stable
        with:
          components: rustfmt, clippy
      - uses: actions/cache@<full-sha>
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            target
          key: ${{ runner.os }}-cargo-${{ hashFiles('**/Cargo.lock') }}
          restore-keys: ${{ runner.os }}-cargo-
      - run: cargo fmt --check
      - run: cargo clippy -- -D warnings
      - run: cargo test
```

## Go CI

```yaml
name: Go CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: go-ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
      - uses: actions/setup-go@<full-sha>
        with:
          go-version-file: go.mod
          cache: true
      - uses: golangci/golangci-lint-action@<full-sha>
        with:
          version: latest
      - run: go test ./... -race -coverprofile=coverage.out
```

## Docker Build and Push

Multi-platform build with layer caching and registry push.

```yaml
name: Docker
on:
  push:
    tags: ['v*']

permissions:
  contents: read
  packages: write

jobs:
  build-push:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false

      - uses: docker/setup-qemu-action@<full-sha>

      - uses: docker/setup-buildx-action@<full-sha>

      - uses: docker/login-action@<full-sha>
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - uses: docker/metadata-action@<full-sha>
        id: meta
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha

      - uses: docker/build-push-action@<full-sha>
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

## Release Automation

Tag-triggered release with changelog and artifact upload.

```yaml
name: Release
on:
  push:
    tags: ['v*']

permissions:
  contents: write  # Create releases

jobs:
  release:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
          fetch-depth: 0  # Full history for changelog

      - name: Generate changelog
        id: changelog
        run: |
          PREV_TAG=$(git describe --tags --abbrev=0 HEAD^ 2>/dev/null || echo "")
          if [ -n "$PREV_TAG" ]; then
            CHANGES=$(git log "$PREV_TAG"..HEAD --pretty=format:"- %s" --no-merges)
          else
            CHANGES=$(git log --pretty=format:"- %s" --no-merges)
          fi
          {
            echo "changes<<EOF"
            echo "$CHANGES"
            echo "EOF"
          } >> "$GITHUB_OUTPUT"

      - uses: softprops/action-gh-release@<full-sha>
        with:
          body: |
            ## Changes
            ${{ steps.changelog.outputs.changes }}
          generate_release_notes: true
```

## Multi-Platform Matrix Build

```yaml
name: Cross-Platform
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  build:
    runs-on: ${{ matrix.os }}
    timeout-minutes: 20
    strategy:
      fail-fast: false  # Don't cancel other OS builds on failure
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        include:
          - os: ubuntu-latest
            artifact-name: linux
          - os: macos-latest
            artifact-name: macos
          - os: windows-latest
            artifact-name: windows
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
      - run: echo "Build for ${{ matrix.artifact-name }}"
      - uses: actions/upload-artifact@<full-sha>
        with:
          name: build-${{ matrix.artifact-name }}
          path: dist/
          retention-days: 7
```

## Dynamic Matrix

Generate matrix values at runtime based on changed files or configuration.

```yaml
jobs:
  detect:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    outputs:
      matrix: ${{ steps.set-matrix.outputs.matrix }}
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
      - id: set-matrix
        run: |
          # Generate matrix from directory structure, config file, or changed paths
          MATRIX=$(find packages -maxdepth 1 -mindepth 1 -type d -printf '"%f",' | sed 's/,$//')
          echo "matrix={\"package\":[$MATRIX]}" >> "$GITHUB_OUTPUT"

  build:
    needs: detect
    runs-on: ubuntu-latest
    timeout-minutes: 15
    strategy:
      matrix: ${{ fromJSON(needs.detect.outputs.matrix) }}
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
      - run: echo "Building ${{ matrix.package }}"
```

## Monorepo Path Filtering

Job-level filtering using `dorny/paths-filter` (avoids the "required check doesn't run" problem with workflow-level path filters).

```yaml
name: Monorepo CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  changes:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    outputs:
      frontend: ${{ steps.filter.outputs.frontend }}
      backend: ${{ steps.filter.outputs.backend }}
      infra: ${{ steps.filter.outputs.infra }}
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
      - uses: dorny/paths-filter@<full-sha>
        id: filter
        with:
          filters: |
            frontend:
              - 'frontend/**'
              - 'shared/**'
            backend:
              - 'backend/**'
              - 'shared/**'
            infra:
              - 'infra/**'
              - 'terraform/**'

  frontend:
    needs: changes
    if: needs.changes.outputs.frontend == 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
      - run: echo "Build and test frontend"

  backend:
    needs: changes
    if: needs.changes.outputs.backend == 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false
      - run: echo "Build and test backend"
```

## Caching Patterns

### Language-Specific Dependency Caching

```yaml
# Python (pip)
- uses: actions/setup-python@<full-sha>
  with:
    python-version: '3.13'
    cache: 'pip'

# Node.js (npm)
- uses: actions/setup-node@<full-sha>
  with:
    node-version: 22
    cache: 'npm'

# Node.js (pnpm)
- uses: pnpm/action-setup@<full-sha>
  with:
    version: 9
- uses: actions/setup-node@<full-sha>
  with:
    node-version: 22
    cache: 'pnpm'

# Go (built-in)
- uses: actions/setup-go@<full-sha>
  with:
    go-version-file: go.mod
    cache: true

# Rust (manual)
- uses: actions/cache@<full-sha>
  with:
    path: |
      ~/.cargo/registry
      ~/.cargo/git
      target
    key: ${{ runner.os }}-cargo-${{ hashFiles('**/Cargo.lock') }}

# Docker layer caching (BuildKit)
- uses: docker/build-push-action@<full-sha>
  with:
    cache-from: type=gha
    cache-to: type=gha,mode=max
```

### Custom Cache with Fallback

```yaml
- uses: actions/cache@<full-sha>
  with:
    path: |
      ~/.cache/custom-tool
      .build-cache
    key: ${{ runner.os }}-custom-${{ hashFiles('config.lock') }}-${{ github.sha }}
    restore-keys: |
      ${{ runner.os }}-custom-${{ hashFiles('config.lock') }}-
      ${{ runner.os }}-custom-
```

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
