---
name: project-exploration
description: >
  Systematic methodology for understanding unfamiliar software projects.
  Covers project characterization (language, framework, architecture pattern
  detection), codebase structure analysis, dependency mapping, development
  workflow discovery, and layered output from executive summary to deep dives.
  Use when joining a new project, exploring an unfamiliar codebase, needing a
  project overview, wanting to understand a project's architecture, or
  performing initial codebase orientation. Also activates for project
  understanding, codebase walkthrough, code exploration, project analysis,
  and developer onboarding to a codebase.
allowed-tools: [Read, Glob, Grep, Bash(git:*), Bash(wc:*), Bash(find:*)]
compatibility: Claude Code
---

# Project Exploration

Methodology for understanding any software project you encounter -- from a tiny CLI tool to a massive monorepo. The `/explore-project` command drives the exploration workflow; this skill provides the analysis methodology that any agent or command can reference.

**Satellite files** (loaded on-demand):

- [references/analysis-checklists.md](references/analysis-checklists.md) -- detailed per-phase checklists with specific files, patterns, and tool invocations
- [references/framework-signatures.md](references/framework-signatures.md) -- recognition patterns for common frameworks organized by language ecosystem
- [references/architecture-patterns.md](references/architecture-patterns.md) -- architecture pattern identification guide with Mermaid diagram templates

## Gotchas

- **Source code is always the source of truth.** When documentation conflicts with code, the code is correct. Flag every discrepancy -- it's either a bug or stale documentation. Never trust docs over code.
- **README.md may be stale.** Cross-reference README claims against actual project state: does the described build command work? Do the documented APIs exist? A README that says "Python 3.8+" while `pyproject.toml` requires `>=3.12` is a signal.
- **CI/CD config is the most honest documentation.** Workflow files reveal the real build, test, and deploy process -- what actually runs, not what someone wrote in a guide months ago.
- **Don't try to read everything.** For projects over 100 files, reading all source is counterproductive. Prioritize entry points, configuration, and module boundaries. Sample representative files from each module.
- **Monorepos need territory mapping first.** Don't apply single-project analysis to a monorepo. Identify sub-projects/packages first, then analyze each territory independently.
- **Lock files reveal the real dependency graph.** `package-lock.json`, `uv.lock`, `Cargo.lock`, `go.sum` show transitive dependencies. `pyproject.toml`/`package.json` show only direct ones.

## Project Characterization

Before analysis, classify the project along three dimensions that determine the analysis strategy. Detection should be automatic from filesystem signals -- no user input required.

### Detection Sequence

Scan these config files in order to identify the project's ecosystem:

| Signal File | Ecosystem | Build/Package Tool |
|------------|-----------|-------------------|
| `pyproject.toml` | Python | uv, poetry, setuptools, flit, hatch |
| `pixi.toml` | Python/Conda | pixi |
| `setup.py` / `setup.cfg` | Python (legacy) | setuptools |
| `package.json` | JavaScript/TypeScript | npm, pnpm, yarn, bun |
| `Cargo.toml` | Rust | cargo |
| `go.mod` | Go | go modules |
| `pom.xml` / `build.gradle` | Java/Kotlin | Maven, Gradle |
| `Gemfile` | Ruby | Bundler |
| `mix.exs` | Elixir | Mix |
| `CMakeLists.txt` / `Makefile` | C/C++ | CMake, Make |
| `*.sln` / `*.csproj` | C#/.NET | dotnet |
| `deno.json` | Deno/TypeScript | deno |

Multiple hits indicate a polyglot project. Prioritize by where the main entry point lives.

### Dimension 1: Project Size

| Tier | Signal | Analysis Strategy |
|------|--------|-------------------|
| **Small** | < 50 files | Single-pass comprehensive scan. Read all source files. One-shot executive summary. |
| **Medium** | 50-500 files | Structured scan. Focus on entry points, config, module boundaries. Sample representative files per module. |
| **Large** | 500+ files | Sampling strategy. Map module boundaries first. Analyze 2-3 key modules deeply. Use file counts and directory names for the rest. |
| **Monorepo** | Multiple package manifests (e.g., multiple `package.json`, workspace config, multiple `go.mod`) | Territory mapping first. List all sub-projects with one-line descriptions. Ask the developer which territory to explore. Then apply the appropriate tier to that territory. |

Detect size: `find . -type f -not -path './.git/*' -not -path './node_modules/*' -not -path './.venv/*' -not -path './vendor/*' -not -path './target/*' -not -path './dist/*' -not -path './build/*' | wc -l`

Detect monorepo: multiple package manifests at different directory levels, or workspace config (`workspaces` in package.json, `[tool.uv.workspace]` in pyproject.toml, `Cargo.toml` with `[workspace]`).

### Dimension 2: Project Type

| Type | Detection Signals | Analysis Emphasis |
|------|------------------|-------------------|
| **Web application** | Framework config (Django, Rails, Express, Next.js), `routes/`, `views/`, `pages/`, `api/` directories | Request lifecycle, routing, middleware, data layer, rendering |
| **CLI tool** | `main()` with arg parsing, `cmd/` directory, `click`/`argparse`/`clap`/`cobra` imports | Command structure, argument dispatch, output formatting |
| **Library/SDK** | Public exports, `src/lib.rs`, `index.ts` re-exports, `__init__.py` with `__all__` | Public API surface, extension points, internal vs external boundaries |
| **Data pipeline** | DAG definitions, scheduler config, `tasks/`/`pipelines/`/`dags/` directories | Pipeline stages, data transformations, scheduling, storage |
| **Infrastructure** | Terraform/Pulumi files, Dockerfiles, k8s manifests, deployment configs | Resource definitions, deployment topology, configuration management |
| **AI/ML project** | Model definitions, training loops, datasets, `models/`, `training/` directories | Model architecture, training pipeline, evaluation, data preprocessing |
| **Microservices** | Multiple Dockerfiles, service directories, API gateway config, proto/OpenAPI files | Service boundaries, communication patterns, shared contracts |
| **Compiler/Language** | `lexer/`, `parser/`, `ast/`, `codegen/` directories, grammar files | Processing pipeline stages, AST representation, optimization passes |
| **Mixed/Unclear** | No strong signals for any single type | Apply general analysis; let Phase 2 reveal the structure |

### Dimension 3: Documentation Quality

| Quality | Detection Signals | Strategy Adjustment |
|---------|------------------|---------------------|
| **Rich** | README > 100 lines, CONTRIBUTING.md exists, `docs/` directory with content, inline doc comments | Summarize existing docs. Focus analysis on gaps and undocumented areas. Cross-check doc claims against code for drift. |
| **Adequate** | README exists with setup instructions, some inline comments | Generate missing context from code analysis. Note what's documented vs inferred. |
| **Sparse** | README < 20 lines or absent, no `docs/`, minimal comments | Heavy code-first analysis. The exploration output itself becomes the primary documentation. Note the gap explicitly. |
| **Misleading** | Docs exist but conflict with code (API signatures differ, described features don't exist, build instructions fail) | **Source code wins.** Flag every discrepancy. This is one of the highest-value outputs -- the developer needs to know what to distrust. |

## Analysis Framework

Four phases of progressive depth. Phases 1-3 always run for the executive summary. Phase 4 runs on request for deep dives.

### Phase 1: First Impressions

**Goal**: Answer "What is this project and what does it do?" in under 30 seconds.

**Analyze**:
- `README.md` -- project purpose, setup instructions, usage examples (verify against code)
- `CLAUDE.md` / `AGENTS.md` -- AI-specific project context
- Project config files -- detected in characterization step
- `LICENSE` -- licensing model
- `.gitignore` -- what the project considers generated/private
- Top-level directory structure -- module organization at a glance
- `git log --oneline -10` -- recent activity and commit style
- `git log --oneline --all | wc -l` -- project history depth

**Output**: Project identity (name, purpose, age), tech stack, size metrics, license.

### Phase 2: Architecture Discovery

**Goal**: Answer "How is the code organized and how do parts relate?"

**Analyze**:
- **Entry points**: `main.*`, `index.*`, `app.*`, `cmd/*`, `bin/*` -- where execution starts
- **Module boundaries**: Top-level directories under `src/`, package directories, Go packages
- **Dependency direction**: Import/require patterns -- which modules depend on which
- **Key abstractions**: Core types, interfaces, traits, protocols -- the project's vocabulary
- **Data flow**: How data enters (APIs, CLI, files), transforms, and exits (responses, output, storage)
- **Architecture pattern**: Match against known patterns (see [references/architecture-patterns.md](references/architecture-patterns.md))

**Produce a Mermaid architecture diagram** showing:
- Main modules/packages as nodes
- Dependency arrows between them
- External systems (databases, APIs, message queues) as separate nodes
- Data flow direction

Use the pattern-specific Mermaid templates from [references/architecture-patterns.md](references/architecture-patterns.md). Fill in actual module names discovered during analysis. Keep diagrams readable -- max 10-12 nodes. For large projects, create a high-level diagram of module groups, not individual files.

**Output**: Module map, entry points, architecture pattern, dependency direction, Mermaid diagram.

### Phase 3: Development Workflow

**Goal**: Answer "How do I build, test, and contribute to this project?"

**Analyze**:
- **Build system**: How to build/run the project (from config files and CI)
- **Test framework**: What test runner, where tests live, how to run them
- **CI/CD**: What `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile` reveal about the real process
- **Code quality**: Linter configs (`.eslintrc`, `ruff.toml`, `.golangci.yml`), formatter configs, type checking
- **Git conventions**: Commit message patterns from `git log --format="%s" -20`, branch naming, PR templates
- **Development setup**: `.env.example`, `docker-compose.yml`, devcontainer config

**Output**: Build/test/lint commands, CI pipeline summary, contribution workflow.

### Phase 4: Deep Dives (On Request)

**Goal**: Answer specific questions about targeted areas.

This phase runs only when the developer requests a focused exploration (`/explore-project <area>`) or during guided mode. Common deep dive targets:

- **Specific module**: Internal structure, public API, key algorithms, test coverage
- **Data model**: Schema definitions, ORM models, database migrations, entity relationships
- **API surface**: Endpoints, request/response shapes, authentication, versioning
- **Security model**: Authentication flow, authorization checks, secrets management, trust boundaries
- **Error handling**: Error types, recovery strategies, logging patterns, user-facing messages
- **Performance**: Hot paths, caching layers, connection pooling, async patterns
- **Historical context**: `git log --follow <file>` for key files, major refactors, architectural pivots

## Executive Summary Template

Use this template for the default mode output. Fill in from Phase 1-3 findings:

```
## Project: {name}

**Purpose**: {one-sentence description of what the project does and for whom}
**Type**: {project type} ({domain})
**Size**: ~{LOC estimate} LOC | {file count} files | {module count} modules
**Stack**: {primary language(s)} | {framework(s)} | {key dependencies}
**Architecture**: {pattern} -- {one-line explanation}

{Mermaid architecture diagram from Phase 2}

**Build**: `{build command}` ({build tool})
**Test**: `{test command}` ({test framework}) | Tests in `{test location}`
**Lint**: `{lint command}` ({linter})
**Entry points**:
- `{path}` -- {brief description}
- `{path}` -- {brief description}

**Key patterns**: {2-3 notable code patterns or conventions}
**Documentation**: {quality tier} -- {one-line assessment}
**Gotchas**: {1-3 non-obvious things a new developer should know}
```

## Guided Exploration Protocol

For interactive mode (`/explore-project guide`), follow this flow:

1. **Run Phase 1** and present the executive overview (condensed, ~10 lines)
2. **Ask the developer**: "Which area would you like to explore next?"
   - Offer options: Architecture (Phase 2), Development workflow (Phase 3), or a specific module/area (Phase 4)
3. **Present one phase at a time**, waiting for developer direction between each
4. **Within Phase 2**, break into sub-steps:
   - Module map and entry points first
   - Dependency graph and architecture pattern second
   - Mermaid diagram third
   - After each: "Want me to go deeper on any of these modules?"
5. **Within Phase 4**, let the developer name the target area
6. **After each phase**, offer: "What would you like to explore next? Or ask any question about what we've covered."

The developer controls pace and depth. Never present all phases at once. Each response should introduce fewer than 7 new concepts before pausing.

## Adaptation Rules

Adjust analysis strategy based on the three classification dimensions:

### By Project Size

- **Small**: Phases 1-3 in a single pass. Read all files. No sampling needed. Executive summary may be shorter since there's less to cover.
- **Medium**: Structured analysis with clear phase boundaries. Sample 3-5 representative files per module instead of reading all.
- **Large**: Start with module-level overview (directory names, file counts, README per module). Deep dive only into modules the developer cares about. The Mermaid diagram should show module groups, not individual files.
- **Monorepo**: Present territory map first. After developer selects a territory, reclassify that territory's size and apply the matching strategy.

### By Project Type

Reorder Phase 2 analysis emphasis based on type:

| Type | Phase 2 Lead With | Phase 2 Emphasize |
|------|-------------------|-------------------|
| Web app | Routing and request lifecycle | Middleware stack, data layer, rendering |
| CLI | Command dispatch structure | Argument parsing, output formatting |
| Library | Public API surface | Extension points, versioning strategy |
| Pipeline | DAG/stage structure | Data transformations, scheduling |
| Infrastructure | Resource topology | Configuration management, state |
| AI/ML | Model architecture | Training loop, data pipeline, evaluation |
| Microservices | Service boundary map | Communication patterns, shared contracts |

### By Documentation Quality

- **Rich/Adequate**: Cross-reference docs against code. Summarize what exists. Focus exploration on gaps and undocumented patterns. Flag any doc-code drift.
- **Sparse/Absent**: The exploration output IS the documentation. Be more thorough in Phase 1-3. Note the documentation gap in the executive summary.
- **Misleading**: This is the highest-value scenario. For every finding, explicitly state whether it's from docs or from code. Flag discrepancies prominently: "README says X, but code shows Y -- trust the code."
