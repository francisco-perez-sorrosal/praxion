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

### Planning & Communication

| Skill | Description | When to Use |
| --- | --- | --- |
| **[roadmap-planning](roadmap-planning/)** | Roadmap planning, feature prioritization (RICE, MoSCoW, WSJF, Kano, ICE), dependency mapping, and backlog management. Integrates with promethean and spec-driven-development. | Prioritizing features, building roadmaps, managing backlogs, mapping dependencies, deciding what to build next. |
| **[stakeholder-communications](stakeholder-communications/)** | Developer-oriented communication patterns: technical status updates, RFC authoring, release announcements, demo scripts, and approval workflows. | Writing status reports, authoring RFCs, communicating releases or breaking changes, preparing demos, seeking technical approval. |

### Design & Architecture

| Skill | Description | When to Use |
| --- | --- | --- |
| **[api-design](api-design/)** | API-first design methodology covering REST, GraphQL, OpenAPI 3.1, versioning strategies, data contracts, and interface contracts. | Designing APIs, writing OpenAPI specs, choosing REST vs GraphQL, defining data or interface contracts, planning API versioning. |
| **[data-modeling](data-modeling/)** | Database and data model design covering relational schemas, NoSQL patterns, migrations (expand-contract), ORM patterns, and schema evolution. | Designing database schemas, choosing between relational and NoSQL, planning migrations, modeling entities and relationships. |
| **[performance-architecture](performance-architecture/)** | Performance as an architectural concern: caching strategies, benchmarking methodology, capacity planning, concurrency patterns, and scaling decisions. | Designing for performance, choosing caching strategies, sizing connection pools, planning capacity, setting up load testing. |

### Software Development

| Skill                                       | Description                                                                                                      | When to Use                                                                                             |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| **[python-development](python-development/)** | Modern Python development with type hints, testing patterns (pytest), and code quality tools (ruff, mypy).      | Writing Python code, implementing tests, configuring tooling, discussing language features.             |
| **[python-prj-mgmt](python-prj-mgmt/)**     | Python project management with pixi and uv. Defaults to **pixi** unless uv is explicitly requested.              | Setting up projects, managing dependencies, configuring environments, initializing new projects.        |
| **[refactoring](refactoring/)**             | Pragmatic refactoring emphasizing modularity, low coupling, high cohesion, and incremental improvement.          | Restructuring code, improving design, reducing coupling, organizing codebases, eliminating code smells. |
| **[code-review](code-review/)**             | Structured code review methodology with finding classification (PASS/FAIL/WARN), language adaptation, and report templates. | Reviewing code for convention compliance, post-implementation verification, reviewing PRs, ad-hoc quality assessments. |
| **[software-planning](software-planning/)** | Three-document planning model (IMPLEMENTATION_PLAN.md, WIP.md, LEARNINGS.md) for tracking work in small, known-good increments. | Starting significant software work, breaking down complex tasks, multi-step development efforts.        |
| **[spec-driven-development](spec-driven-development/)** | Behavioral specification format, complexity triage, requirement ID conventions, and traceability threading for medium/large features. Composes with software-planning. | Working on medium/large features that need behavioral specifications, requirement traceability, spec archival, or spec health monitoring. |
| **[agent-evals](agent-evals/)**             | Agent evaluation (evals) -- eval types, framework selection (Inspect AI, DeepEval, Promptfoo), golden datasets, LLM-as-judge, grader design, scoring, non-determinism, CI/CD integration. Python-focused. | Evaluating agent behavior, choosing eval frameworks, designing eval suites, building golden datasets, trajectory evaluation, eval-driven development. |
| **[cicd](cicd/)**                           | CI/CD pipeline design, GitHub Actions workflows, deployment strategies, caching, secrets management, and security hardening. | Creating CI/CD pipelines, writing GitHub Actions workflows, debugging workflow failures, optimizing pipeline performance. |

### Project

| Skill | Description | When to Use |
| --- | --- | --- |
| **[github-star](github-star/)** | Prompt the user to star the ai-assistants-cfg GitHub repository. | User invokes `/star-repo` or asks about starring the project. |
| **[memory](memory/)** | Persistent, structured memory system tracking user preferences, assistant learnings, project conventions, and relationship dynamics across sessions. | Remembering user preferences, storing project decisions, recalling past interactions, session context loading. |

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
