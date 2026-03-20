# Core Concepts

The building blocks of the ai-assistants ecosystem and how they compose into a layered system for AI-assisted development.

## What is ai-assistants?

A toolkit that enhances AI coding assistants (Claude Code, Claude Desktop, Cursor) with reusable expertise, automated agents, slash commands, and coding conventions. It provides a configuration layer that makes AI assistants more capable, consistent, and context-aware across projects.

Without ai-assistants, an AI coding assistant starts each session from zero -- no knowledge of your coding conventions, no structured workflows, no ability to delegate complex tasks. With it, the assistant has domain expertise on demand, a pipeline of specialized agents for complex work, and conventions that enforce quality automatically.

## The Building Blocks

### Rules

Domain knowledge loaded automatically by the assistant based on relevance. Rules are declarative constraints -- coding style, git conventions, coordination protocols -- that the assistant applies without explicit invocation.

Think of rules as encoding a senior developer's instincts. The assistant knows to use imperative mood in commit messages, to stage files by name rather than `git add -A`, and to match testing effort to risk -- because rules tell it so.

Rules are always-on background knowledge. They load when contextually relevant and cost minimal tokens when inactive.

**Examples:** `coding-style` (language-independent structural conventions), `git-conventions` (commit scope, staging discipline, message format), `readme-style` (documentation writing quality standards).

### Skills

Reusable knowledge modules loaded on demand when the task matches. Skills are deeper than rules -- they contain workflows, procedures, reference material, and best practices for a specific domain.

While a rule might say "use immutable data when possible," a skill provides the complete procedure for setting up a Python project with pixi, configuring ruff and mypy, and structuring tests with pytest.

Skills use **progressive disclosure**: metadata loads at activation time, full content on demand, and reference files only when deep detail is needed. This keeps token cost proportional to usage.

**Examples:** `python-development` (testing, type hints, tooling), `refactoring` (incremental improvement patterns), `spec-driven-development` (behavioral specifications for medium/large features), `cicd` (GitHub Actions, deployment strategies).

### Commands

Slash commands for frequent workflows. Invoke with `/<name>` (or `/i-am:<name>` in Claude Code plugin mode). Commands are user-initiated actions that automate repetitive tasks.

**Examples:** `/co` (create a commit following project conventions), `/create-worktree` (set up an isolated git worktree), `/memory` (manage persistent memory across sessions), `/onboard-project` (set up a new project for the ecosystem).

### Agents

Autonomous subprocesses that handle complex, multi-step tasks. Each agent runs in its own context window with a specific specialty, reads upstream documents, and writes structured output for downstream agents.

Agents communicate through shared documents in `.ai-work/`, not through direct invocation. This forms a pipeline where each agent's output feeds the next stage. The assistant delegates to the right agent based on what you ask for -- or you can name agents explicitly.

**Examples:** `researcher` (codebase exploration, external docs), `systems-architect` (trade-off analysis, system design), `implementer` (step execution with self-review), `verifier` (post-implementation review against acceptance criteria).

### MCP Servers

External tool servers the assistant can call for capabilities beyond its built-in tools. MCP (Model Context Protocol) servers provide backend infrastructure like persistent memory and task lifecycle observability.

**Examples:** `memory` (structured persistence across sessions), `task-chronograph` (agent lifecycle event tracking).

## How They Work Together

The components form a layered architecture, from always-loaded directives down to delegated complex work:

```text
CLAUDE.md             Always loaded. Global directives, methodology, personal info.
    |
    v
Rules                 Loaded when contextually relevant. Domain knowledge
    |                 (coding style, git conventions, coordination protocols).
    v
Skills                Activated for specific tasks. Expert workflows and procedures
    |                 (Python development, refactoring, CI/CD, spec-driven development).
    v
Commands              User-invoked. Quick actions for frequent workflows
    |                 (commits, worktrees, memory management, project scaffolding).
    v
Agents                Delegated. Complex multi-step work in isolated contexts
                      (research, architecture, implementation, testing, verification).
```

**Rules vs. Skills:** Rules are brief, declarative, and auto-loaded -- they define *what* conventions to follow. Skills are richer, procedural, and loaded on demand -- they define *how* to do specific work. When deciding where knowledge belongs: if it's a constraint or convention that applies broadly, it's a rule. If it's a workflow or procedure for a specific domain, it's a skill.

**Commands vs. Agents:** Commands are user-invoked single actions (create a commit, scaffold a project). Agents are delegated multi-step processes that run autonomously (research a technology, design an architecture, implement a feature). Use commands for quick actions; use agents when the task requires exploration, planning, or multiple coordinated steps.

## The Agent Pipeline

For complex features, agents form a pipeline where each stage's output feeds the next:

```text
promethean --> researcher --> systems-architect --> implementation-planner --> implementer    --> verifier
                                                                              test-engineer
                                                                              doc-engineer
```

1. **promethean** -- generates feature ideas from project state
2. **researcher** -- explores the codebase, evaluates technologies, gathers external information
3. **systems-architect** -- produces system design with trade-off analysis and behavioral specifications
4. **implementation-planner** -- decomposes the design into small, incremental steps
5. **implementer + test-engineer** -- execute steps in parallel on disjoint file sets (production code vs. test code); **doc-engineer** updates documentation when the planner assigns doc steps
6. **verifier** -- reviews the implementation against acceptance criteria

Supporting agents operate alongside the pipeline: **context-engineer** (manages context artifacts), **sentinel** (independent ecosystem health audits), **skill-genesis** (harvests patterns into reusable artifacts), **cicd-engineer** (CI/CD pipeline design).

For a full walkthrough with example prompts and outputs, see [Getting Started](getting-started.md).

## Process Scaling

The pipeline scales to task complexity. Not every task needs twelve agents:

| Task Complexity | What Happens |
|-----------------|--------------|
| **One-line fix** | Work directly. No agents, no planning documents. |
| **Small change** (2-3 files) | Optional researcher. Inline acceptance criteria. |
| **Medium feature** (4-8 files) | Full pipeline. Behavioral spec with requirement IDs. |
| **Large feature** (9+ files) | Full pipeline plus parallel execution, decision documentation, spec archival. |
| **Exploratory** | Timeboxed researcher. Decision captured, no implementation until resolved. |

The guiding principle: process overhead cannot be reclaimed. Default to the lighter option when uncertain -- process can always be added later.

For the full spec-driven development methodology, see [Spec-Driven Development](spec-driven-development.md). For the decision audit trail, see [Decision Tracking](decision-tracking.md).
