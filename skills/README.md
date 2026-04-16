# Skills

Reusable skill modules for AI coding assistants. Each skill is a self-contained directory with a `SKILL.md` (Agent Skills standard). **Tool-agnostic:** compatible with Claude Code, Cursor, and other tools that support the standard; load automatically based on activation triggers.

## Available Skills

### AI Assistant Crafting

| Skill                               | Description                                                                                                                                                | When to Use                                                                                                              |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **[skill-crafting](skill-crafting/)**     | Creating and optimizing Agent Skills for Claude Code, Cursor, and other agents. Covers activation patterns, content structure, and progressive disclosure. | Creating new skills, updating/modernizing existing skills, debugging skill activation, understanding skill architecture. |
| **[agent-crafting](agent-crafting/)**     | Building custom agents (subagents) with prompt writing, tool configuration, and lifecycle management.                                                      | Building custom agents, designing agent workflows, spawning subagents, delegating tasks to agents.                       |
| **[command-crafting](command-crafting/)** | Creating slash commands with proper syntax, arguments, frontmatter, and best practices.                                                                    | Creating custom slash commands, debugging command behavior, converting prompts to reusable commands.                     |
| **[mcp-crafting](mcp-crafting/)**         | Building MCP servers in Python with FastMCP. Covers tools, resources, prompts, transports, testing, and deployment.                                        | Creating MCP servers, defining tools/resources, configuring transports, testing, integrating with Claude.                |
| **[rule-crafting](rule-crafting/)**       | Creating and managing rules — domain knowledge files eagerly loaded within scope (personal = all projects, project = that project).                        | Creating new rules, updating existing rules, debugging rule loading, organizing rule files, layer placement decisions.   |
| **[hook-crafting](hook-crafting/)**       | Creating, testing, and registering Claude Code hooks for automated code quality, observability, security gates, and workflow enforcement.                   | Creating new hooks, debugging hook execution, fixing hook registration, choosing between hook types, installer integration. |

### External Knowledge

| Skill | Description | When to Use |
| --- | --- | --- |
| **[external-api-docs](external-api-docs/)** | Retrieving current, curated API documentation for external libraries and SDKs. Covers search strategies, token-aware fetching, annotation persistence, and provider fallback hierarchy. Default provider: context-hub. | Writing code against an external API, debugging integration issues, evaluating SDK capabilities, looking up current endpoint signatures. |

### Platform Knowledge

| Skill | Description | When to Use |
| --- | --- | --- |
| **[claude-ecosystem](claude-ecosystem/)** | Anthropic Claude platform knowledge -- models, API features, SDKs, and documentation navigation. | Choosing models, using Messages API features, integrating Anthropic SDKs, navigating Anthropic docs. |
| **[agentic-sdks](agentic-sdks/)** | Building AI agents with OpenAI Agents SDK and Claude Agent SDK. Covers agent architecture, tools, multi-agent orchestration, safety, and MCP integration. Language modules for Python and TypeScript. | Building autonomous agents, choosing between agent frameworks, implementing multi-agent workflows, integrating tools or MCP servers. |
| **[communicating-agents](communicating-agents/)** | Agent-to-agent communication protocols for multi-agent interoperability. Covers A2A protocol -- Agent Cards, task-based messaging, discovery, streaming, and SDK implementation. Language modules for Python and TypeScript. | Building multi-agent systems across frameworks, exposing agents via A2A, implementing agent discovery, integrating A2A with AI frameworks. |

### Documentation

| Skill | Description | When to Use |
| --- | --- | --- |
| **[doc-management](doc-management/)** | Writing and maintaining project documentation (README.md, catalogs, architecture docs, changelogs). Covers cross-reference validation, catalog maintenance, and structural integrity. | Creating or reviewing project documentation, maintaining catalog READMEs, validating cross-references, ensuring documentation freshness. |

### Prompt Engineering

| Skill | Description | When to Use |
| --- | --- | --- |
| **[llm-prompt-engineering](llm-prompt-engineering/)** | End-user-facing prompt engineering — few-shot, chain-of-thought, structured output, prompt testing, injection hardening. Provider-agnostic; companion contexts for Python and TypeScript. | Writing or refining prompts, designing few-shot examples, enforcing structured output, testing prompt robustness, hardening against injection. |

### Planning & Communication

| Skill | Description | When to Use |
| --- | --- | --- |
| **[roadmap-planning](roadmap-planning/)** | Roadmap planning, feature prioritization (RICE, MoSCoW, WSJF, Kano, ICE), dependency mapping, and backlog management. Integrates with promethean and spec-driven-development. | Prioritizing features, building roadmaps, managing backlogs, mapping dependencies, deciding what to build next. |
| **[roadmap-synthesis](roadmap-synthesis/)** | Ultra-in-depth project audit synthesized into a `ROADMAP.md` via a **project-derived evaluation lens set** (drawn from project values + domain constraints + exemplar sets: SPIRIT, DORA, SPACE, FAIR, CNCF Platform Maturity, or Custom), paradigm detection, and parallel-researcher fan-out. Produces a 10-section roadmap covering both **deficit repairs** (Weaknesses) and **forward lines of work** (Opportunities — new capabilities, strategic bets, evolution trends). Distinct from `roadmap-planning` (which sequences an existing backlog). | Producing a fresh `ROADMAP.md` from a full-project audit, running a "spring cleaning" or "state of the project" review, mapping the road ahead with opportunity-driven items alongside weakness-driven ones, conducting lens-based SDLC health audits for any project class. |
| **[stakeholder-communications](stakeholder-communications/)** | Developer-oriented communication patterns: technical status updates, RFC authoring, release announcements, demo scripts, and approval workflows. | Writing status reports, authoring RFCs, communicating releases or breaking changes, preparing demos, seeking technical approval. |

### Design & Architecture

| Skill | Description | When to Use |
| --- | --- | --- |
| **[api-design](api-design/)** | API-first design methodology covering REST, GraphQL, OpenAPI 3.1, versioning strategies, data contracts, and interface contracts. | Designing APIs, writing OpenAPI specs, choosing REST vs GraphQL, defining data or interface contracts, planning API versioning. |
| **[data-modeling](data-modeling/)** | Database and data model design covering relational schemas, NoSQL patterns, migrations (expand-contract), ORM patterns, and schema evolution. | Designing database schemas, choosing between relational and NoSQL, planning migrations, modeling entities and relationships. |
| **[deployment](deployment/)** | Application deployment: local Docker Compose, PaaS, cloud containers, Kubernetes, AI-native GPU platforms. Covers deployment primitives, Docker Compose patterns, dev-to-production spectrum, reverse proxy, secrets, AI/ML model serving. | Deploying an app, writing compose.yaml or Dockerfile, setting up a production server, choosing a hosting platform, configuring Caddy or nginx, deploying AI models. |
| **[observability](observability/)** | Application observability strategy: structured logging, metrics design, distributed tracing, alerting, SLI/SLO methodology, and OpenTelemetry instrumentation. | Adding observability, choosing logging/metrics/tracing strategies, designing alerts, defining SLIs and SLOs, instrumenting with OpenTelemetry. |
| **[performance-architecture](performance-architecture/)** | Performance as an architectural concern: caching strategies, benchmarking methodology, capacity planning, concurrency patterns, and scaling decisions. | Designing for performance, choosing caching strategies, sizing connection pools, planning capacity, setting up load testing. |

### Software Development

| Skill                                       | Description                                                                                                      | When to Use                                                                                             |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| **[project-exploration](project-exploration/)** | Systematic methodology for understanding unfamiliar software projects. Covers project characterization, codebase structure analysis, dependency mapping, development workflow discovery, and layered output. | Joining a new project, exploring an unfamiliar codebase, needing a project overview, understanding a project's architecture, initial codebase orientation. |
| **[python-development](python-development/)** | Modern Python development with type hints, testing patterns (pytest), and code quality tools (ruff, mypy).      | Writing Python code, implementing tests, configuring tooling, discussing language features.             |
| **[python-prj-mgmt](python-prj-mgmt/)**     | Python project management with pixi and uv. Defaults to **pixi** unless uv is explicitly requested.              | Setting up projects, managing dependencies, configuring environments, initializing new projects.        |
| **[refactoring](refactoring/)**             | Pragmatic refactoring emphasizing modularity, low coupling, high cohesion, and incremental improvement.          | Restructuring code, improving design, reducing coupling, organizing codebases, eliminating code smells. |
| **[code-review](code-review/)**             | Structured code review methodology with finding classification (PASS/FAIL/WARN), language adaptation, and report templates. | Reviewing code for convention compliance, post-implementation verification, reviewing PRs, ad-hoc quality assessments. |
| **[software-planning](software-planning/)** | Three-document planning model (IMPLEMENTATION_PLAN.md, WIP.md, LEARNINGS.md) for tracking work in small, known-good increments. | Starting significant software work, breaking down complex tasks, multi-step development efforts.        |
| **[spec-driven-development](spec-driven-development/)** | Behavioral specification format, complexity triage, requirement ID conventions, and traceability threading for medium/large features. Composes with software-planning. | Working on medium/large features that need behavioral specifications, requirement traceability, spec archival, or spec health monitoring. |
| **[agent-evals](agent-evals/)**             | Agent evaluation (evals) -- eval types, framework selection (Inspect AI, DeepEval, Promptfoo), golden datasets, LLM-as-judge, grader design, scoring, non-determinism, CI/CD integration. Python-focused. | Evaluating agent behavior, choosing eval frameworks, designing eval suites, building golden datasets, trajectory evaluation, eval-driven development. |
| **[cicd](cicd/)**                           | CI/CD pipeline design, GitHub Actions workflows, deployment strategies, caching, secrets management, and security hardening. | Creating CI/CD pipelines, writing GitHub Actions workflows, debugging workflow failures, optimizing pipeline performance. |
| **[context-security-review](context-security-review/)** | Security review methodology for Claude Code plugin ecosystems covering context artifact injection, hook compromise, dependency supply chain, secrets exposure, and GitHub Actions security. | Reviewing PRs for security issues, conducting security audits, verifying agent permissions, reviewing hook scripts, checking for secrets. |
| **[testing-strategy](testing-strategy/)** | Language-agnostic testing methodology covering test strategy selection, test pyramid, mocking philosophy, fixture patterns, property-based testing, and coverage philosophy. Language-specific references via progressive disclosure. | Choosing test strategies, designing test architecture, deciding what to mock, writing fixtures, adding property-based tests, planning coverage. |

### OSS Contribution

| Skill | Description | When to Use |
| --- | --- | --- |
| **[upstream-stewardship](upstream-stewardship/)** | Methodology for responsibly reporting bugs and contributing fixes to upstream open-source projects. Covers deduplication, sanitization, template compliance, and responsible disclosure. | Filing upstream issues, reviewing bug report drafts, discovering upstream bugs during development, contributing fixes to dependencies. |

### Project

| Skill | Description | When to Use |
| --- | --- | --- |
| **[github-star](github-star/)** | Prompt the user to star the Praxion GitHub repository. | User invokes `/star-repo` or asks about starring the project. |
| **[memory](memory/)** | Persistent, structured memory system tracking user preferences, assistant learnings, project conventions, and relationship dynamics across sessions. | Remembering user preferences, storing project decisions, recalling past interactions, session context loading. |
| **[versioning](versioning/)** | Version bumping, changelog generation, release automation, and tool detection for multi-file projects. Breaking change guidelines for textual/config ecosystems. | Bumping versions, generating changelogs, configuring release automation, choosing versioning tools, defining breaking changes. |

## How Skills Work

Skills are loaded automatically when the assistant detects a matching context based on each skill's `description` field in its frontmatter. You can also reference them explicitly (e.g., "load the `refactoring` skill").

### Activation

- **Automatic**: The tool matches your task context against skill `description` triggers
- **Explicit**: Reference a skill by name in conversation or from project instructions (`CLAUDE.md`, `AGENTS.md`, etc.)

### Structure

Each skill directory contains at minimum a `SKILL.md` with:

- **Frontmatter**: `name`, `description`, `allowed-tools`, and other metadata
- **Content**: Domain-specific guidance, patterns, and workflows

Larger skills use **progressive disclosure** with supporting files (`REFERENCE.md`, `EXAMPLES.md`, `BEST-PRACTICES.md`) loaded only when needed, keeping the context window efficient.

### Storage Locations

- **This repository**: `skills/` at the root (source of truth)
- **Claude Code**: Plugin install copies to cache; also `.claude/skills/` (project), `~/.claude/skills/` (personal)
- **Cursor**: `.cursor/skills/` or `.claude/skills/` (project), `~/.cursor/skills/` or `~/.claude/skills/` (personal). Install via `./install.sh cursor`
