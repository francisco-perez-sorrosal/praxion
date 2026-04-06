# Analysis Checklists

Detailed per-phase checklists for project exploration. Each phase lists what to look for, where to look, and what to output. Back-reference: [../SKILL.md](../SKILL.md)

## Phase 1: First Impressions

**Goal**: Identify the project and establish basic facts in under 30 seconds.

### What to Look For

- [ ] Project name and one-sentence purpose
- [ ] Primary language(s) and framework(s)
- [ ] License type
- [ ] Project age (first commit date)
- [ ] Recent activity (last commit date, commit frequency)
- [ ] Size metrics (file count, rough LOC)
- [ ] Documentation presence and quality signals
- [ ] AI-specific context files (CLAUDE.md, AGENTS.md, .cursorrules)

### Where to Look

| Target | Tool | Command/Pattern |
|--------|------|----------------|
| Project identity | Read | `README.md` (first 50 lines) |
| AI context | Read | `CLAUDE.md`, `AGENTS.md` |
| Config files | Glob | `*.toml`, `*.json`, `*.yaml`, `*.yml` at root |
| License | Read | `LICENSE`, `LICENSE.md`, `COPYING` |
| Directory structure | Bash | `ls -la` at project root |
| Ignored paths | Read | `.gitignore` |
| File count | Bash | `find . -type f -not -path './.git/*' -not -path './node_modules/*' -not -path './.venv/*' -not -path './vendor/*' -not -path './target/*' -not -path './dist/*' -not -path './build/*' \| wc -l` |
| History depth | Bash | `git log --oneline --all \| wc -l` |
| Recent commits | Bash | `git log --oneline -10` |
| First commit | Bash | `git log --reverse --format="%ai" \| head -1` |
| Contributors | Bash | `git shortlog -sn --all \| head -10` |

### What to Output

- Project name, purpose (one sentence), and type classification
- Tech stack: language(s), framework(s), key dependencies
- Size tier classification (small/medium/large/monorepo)
- Documentation quality classification (rich/adequate/sparse/misleading)
- License type
- Age and activity summary

## Phase 2: Architecture Discovery

**Goal**: Map how the code is organized, how parts relate, and produce a Mermaid diagram.

### What to Look For

- [ ] Entry points (where execution starts)
- [ ] Module/package boundaries
- [ ] Dependency direction between modules
- [ ] Core abstractions (key types, interfaces, traits)
- [ ] Data flow (input sources, transformations, output sinks)
- [ ] External system integrations (databases, APIs, queues)
- [ ] Architecture pattern (monolith, microservices, plugin, etc.)
- [ ] Documentation-code drift in architectural claims

### Where to Look

| Target | Tool | Command/Pattern |
|--------|------|----------------|
| Entry points | Glob | `**/main.*`, `**/index.*`, `**/app.*`, `cmd/*`, `bin/*` |
| Module boundaries | Bash | `ls -d src/*/` or equivalent top-level source dirs |
| Package structure | Glob | `**/package.json`, `**/pyproject.toml`, `**/Cargo.toml` (nested) |
| Import graph | Grep | `^import `, `^from .* import`, `require(`, `use ` patterns |
| Core types | Grep | `^class `, `^struct `, `^interface `, `^trait `, `^type ` patterns |
| Database connections | Grep | `DATABASE_URL`, `SQLALCHEMY`, `prisma`, `mongoose`, `diesel` |
| API definitions | Glob | `**/openapi.*`, `**/*.proto`, `**/schema.graphql` |
| Service boundaries | Glob | `**/Dockerfile`, `**/docker-compose.*`, `**/k8s/` |
| Architecture claims | Read | README.md architecture section, `docs/architecture*` |

### Mermaid Diagram Generation

After identifying modules and their relationships:

1. **List all top-level modules** (directories under `src/`, top-level packages, service directories)
2. **Trace dependency direction** from imports/requires between modules
3. **Identify external systems** (databases, message queues, external APIs)
4. **Select the matching architecture pattern template** from [architecture-patterns.md](architecture-patterns.md)
5. **Fill in actual names** from the project
6. **Limit to 10-12 nodes** for readability -- group related files into their parent module

Verify the diagram against code: every arrow should correspond to an actual import or call. **Source code is the truth** -- if the README describes a different architecture than what the imports reveal, diagram what the code actually shows and flag the discrepancy.

### What to Output

- Module map with one-line descriptions
- Entry points with their roles
- Architecture pattern identification with rationale
- Dependency direction summary
- Mermaid architecture diagram
- Any doc-code discrepancies found

## Phase 3: Development Workflow

**Goal**: Answer "How do I build, test, and contribute?"

### What to Look For

- [ ] Build command and build system
- [ ] Test framework and how to run tests
- [ ] Test location and naming conventions
- [ ] Linting and formatting tools and their configs
- [ ] Type checking setup
- [ ] CI/CD pipeline stages
- [ ] Development environment setup (containers, venvs, env files)
- [ ] Git conventions (commit style, branch naming, PR templates)
- [ ] Contributor documentation

### Where to Look

| Target | Tool | Command/Pattern |
|--------|------|----------------|
| Build system | Read | `Makefile`, `justfile`, `Taskfile.yml`, `package.json` scripts |
| Test framework | Glob | `**/pytest.ini`, `**/jest.config.*`, `**/vitest.config.*`, `**/.rspec` |
| Test files | Glob | `**/test_*`, `**/*_test.*`, `**/*.test.*`, `**/*.spec.*`, `tests/` |
| Linter config | Glob | `**/ruff.toml`, `**/.eslintrc*`, `**/.golangci.yml`, `**/biome.json` |
| Formatter config | Glob | `**/.prettierrc*`, `**/rustfmt.toml`, `**/.editorconfig` |
| Type checking | Glob | `**/tsconfig.json`, `**/mypy.ini`, `**/pyrightconfig.json` |
| CI workflows | Glob | `.github/workflows/*`, `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci/config.yml` |
| Dev environment | Glob | `.env.example`, `docker-compose*.yml`, `.devcontainer/` |
| Commit style | Bash | `git log --format="%s" -20` |
| PR templates | Glob | `.github/PULL_REQUEST_TEMPLATE*` |
| Contributor docs | Read | `CONTRIBUTING.md`, `docs/contributing*` |

### What to Output

- Build command(s) with prerequisites
- Test command(s) with test framework name
- Lint/format/type-check commands
- CI pipeline summary (what runs, in what order)
- Development setup steps
- Git conventions summary (commit style, branch naming)

## Phase 4: Deep Dives

**Goal**: Provide focused analysis on developer-specified areas.

### Common Deep Dive Targets

#### Data Model
- [ ] ORM models or schema definitions
- [ ] Database migrations
- [ ] Entity relationships
- [ ] Validation rules

| Target | Tool | Command/Pattern |
|--------|------|----------------|
| Models | Glob | `**/models.*`, `**/models/`, `**/schema.*`, `**/entities/` |
| Migrations | Glob | `**/migrations/`, `**/alembic/`, `**/prisma/migrations/` |
| Schema files | Glob | `**/*.sql`, `**/schema.prisma`, `**/schema.graphql` |

#### API Surface
- [ ] Route definitions and HTTP methods
- [ ] Request/response types
- [ ] Authentication/authorization middleware
- [ ] API versioning strategy

| Target | Tool | Command/Pattern |
|--------|------|----------------|
| Routes | Grep | `@app.route`, `router.get`, `@GetMapping`, `#[get(` |
| OpenAPI | Glob | `**/openapi.*`, `**/swagger.*` |
| Auth middleware | Grep | `authenticate`, `authorize`, `jwt`, `bearer`, `oauth` |

#### Security Model
- [ ] Authentication flow (how users prove identity)
- [ ] Authorization checks (how permissions are enforced)
- [ ] Secrets management (env vars, vaults, config)
- [ ] Input validation and sanitization
- [ ] Trust boundaries between components

| Target | Tool | Command/Pattern |
|--------|------|----------------|
| Auth config | Grep | `AUTH_`, `JWT_SECRET`, `SESSION_`, `OAUTH_` |
| Permission checks | Grep | `is_admin`, `has_permission`, `@requires_auth`, `authorize` |
| Secret refs | Grep | `SECRET`, `API_KEY`, `TOKEN`, `PASSWORD` (in config, not source) |

#### Performance Characteristics
- [ ] Caching layers and strategies
- [ ] Connection pooling
- [ ] Async/concurrent patterns
- [ ] Known hot paths (from comments, benchmarks, profiling config)

| Target | Tool | Command/Pattern |
|--------|------|----------------|
| Cache config | Grep | `redis`, `memcached`, `cache`, `@cached`, `lru_cache` |
| Connection pools | Grep | `pool_size`, `max_connections`, `connection_pool` |
| Async patterns | Grep | `async def`, `await`, `tokio::spawn`, `Promise.all` |
| Benchmarks | Glob | `**/bench*`, `**/benchmark*`, `**/*.bench.*` |

#### Historical Context
- [ ] Major refactors (large diffs, directory renames)
- [ ] Architectural pivots visible in git history
- [ ] Who wrote the foundational code (for context, not blame)
- [ ] Files with highest churn

| Target | Tool | Command/Pattern |
|--------|------|----------------|
| File history | Bash | `git log --follow --oneline {file}` |
| High-churn files | Bash | `git log --format=format: --name-only \| sort \| uniq -c \| sort -rn \| head -20` |
| Major refactors | Bash | `git log --diff-filter=R --summary \| head -50` |
| Key contributors | Bash | `git shortlog -sn -- {path}` |
