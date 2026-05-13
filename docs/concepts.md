---
diataxis: explanation
audience: developer
---

# Core Concepts

The building blocks of the Praxion ecosystem and how they compose into a layered system for AI-assisted development.

## What is Praxion?

Praxion is my vision for turning AI assistance into an agentic disciplined engineering system. There are many frameworks like this, but this is mine. I evolve it as I think I should, taking into account the fast evolution of technology these days. It tries to reflect how I want to build with what some define as `"intelligent systems"`: not as a loose collection of prompts or assistants, but as a structured layer of reusable expertise, specialized agents, commands, rules, and memory that work together to produce reliable, context-aware results. At its core, it operationalizes spec-driven development (SPECs) and context engineering (through skills, agents, rules, and commands) so that intent, constraints, and workflows are explicitly encoded and consistently executed. The project brings my conventions, workflows, and architectural thinking into the loop, enabling the assistant to operate with continuity, stronger judgment, and a clear understanding of how software should be designed, implemented, and evolved. I'm trying to make it compatible with **Claude Code**, **Claude Desktop**, and **Cursor**, although I mainly use CC.

The name Praxion comes from praxis, or the idea of turning knowledge into action, combined with `axon`, a suffix with influences from both neuroscience (axon, the structure responsible for transmitting signals,) and `-ion`, a system-oriented suffix that evokes motion, execution, and structure. It reflects the core intent of the project: not just to think with AI, but to operationalize that thinking into repeatable, high-quality engineering outcomes. I use Praxion as a representation of the bridge between cognition and implementation; that is, the helper that allows ideas to systematically evolve into working systems.

Without Praxion, an AI coding assistant starts each session from zero -- no knowledge of your coding conventions, no structured workflows, no ability to delegate complex tasks. With it, the assistant has domain expertise on demand, a pipeline of specialized agents for complex work, and conventions that enforce quality automatically.

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

**Examples:** `/co` (create a commit following project conventions), `/create-worktree` (set up an isolated git worktree), `/cajalogic` (manage persistent memory across sessions), `/onboard-project` (set up a new project for the ecosystem).

### Agents

Autonomous subprocesses that handle complex, multi-step tasks. Each agent runs in its own context window with a specific specialty, reads upstream documents, and writes structured output for downstream agents.

Agents communicate through shared documents in `.ai-work/<task-slug>/`, not through direct invocation. Each pipeline run gets its own task-scoped subdirectory (a kebab-case 2–4 word identifier generated at pipeline start). This forms a pipeline where each agent's output feeds the next stage. The assistant delegates to the right agent based on what you ask for -- or you can name agents explicitly.

**Examples:** `researcher` (codebase exploration, external docs), `systems-architect` (trade-off analysis, system design), `implementer` (step execution with self-review), `verifier` (post-implementation review against acceptance criteria).

### MCP Servers

External tool servers the assistant can call for capabilities beyond its built-in tools. MCP (Model Context Protocol) servers provide backend infrastructure like persistent memory and task lifecycle observability.

**Examples:** `memory` (structured persistence across sessions), `task-chronograph` (agent lifecycle event tracking).

## How They Work Together

The components form a layered architecture, from always-loaded directives down to delegated complex work:

![Praxion Component Layers — CLAUDE.md, Rules, Skills, Commands, Agents in descending load order](diagrams/concepts-component-layers/rendered/concepts-component-layers.svg)

**Rules vs. Skills:** Rules are brief, declarative, and auto-loaded -- they define *what* conventions to follow. Skills are richer, procedural, and loaded on demand -- they define *how* to do specific work. When deciding where knowledge belongs: if it's a constraint or convention that applies broadly, it's a rule. If it's a workflow or procedure for a specific domain, it's a skill.

**Commands vs. Agents:** Commands are user-invoked single actions (create a commit, scaffold a project). Agents are delegated multi-step processes that run autonomously (research a technology, design an architecture, implement a feature). Use commands for quick actions; use agents when the task requires exploration, planning, or multiple coordinated steps.

## The Agent Pipeline

For complex features, agents form a pipeline where each stage's output feeds the next (simplified below — the diagram omits the `context-engineer` / `interface-designer` shadow advisors, the `cicd-engineer` and `doc-engineer` parallel slots, and the `sentinel` / `architect-validator` audit roles; see [`agents/README.md`](../agents/README.md) for the full pipeline):

![Simplified agent pipeline (conceptual overview) — promethean → researcher → systems-architect → implementation-planner → implementer + test-engineer + doc-engineer → verifier. The full protocol including shadow advisors and parallel-execution semantics is in the agent-pipeline-flowchart.](diagrams/concepts-agent-pipeline/rendered/concepts-agent-pipeline.svg)

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

For the full spec-driven development methodology, see [Spec-Driven Development](spec-driven-development.md). For the decision audit trail using Architecture Decision Records, see [Decision Tracking](decision-tracking.md).

## Project Archetypes

The pipeline is shared, but the artifacts and rules it activates depend on the project's archetype. Three archetypes are recognized:

- **Traditional SWE** — the default. The full skill catalog applies (Python, API design, CI/CD, deployment, testing, refactoring, observability). Most Praxion projects fall here.
- **Agentic-AI apps** — agents-as-products. Activated when the codebase imports an agent SDK or builds MCP servers. Adds the `agentic-sdks`, `agent-evals`, `mcp-crafting`, and `communicating-agents` skills to the active set.
- **ML/AI training** — pre-training projects with compute budgets, eval thresholds, and iterative experiment loops. Activated when `train.py`, `prepare.py`, an ML framework dependency, or a `program.md` is detected. Adds the `ml-training`, `llm-training-eval`, `neo-cloud-abstraction`, and `experiment-tracking` skills, the three `rules/ml/` rules, and two slash commands (`/run-experiment`, `/check-experiment`). The `karpathy/autoresearch` project — which sits at the intersection of agentic-AI and ML training — is the canonical proof target. The full guide is [ML/AI Training Onramp](ml-training-onramp.md).

The `/onboard-project` command's Phase 8c detects ML signals and scaffolds the conventions automatically; non-ML projects skip Phase 8c silently. The architecture is open: a fourth archetype with its own skill cluster, rules, and onboarding scaffold is a future-compatible extension, not a special case.

## Architecture-as-Code and Documentation-as-Code

Praxion treats architecture as a machine-readable artifact that lives alongside the code it describes. The **Architecture-as-Code (AaC)** half encodes the structural model in a versioned, queryable form -- elements, relationships, deployment nodes, and fitness functions that agents can read, reason about, and validate automatically. The **Documentation-as-Code (DaC)** half ensures that authored rationale -- ADRs, architecture guides, concept documents -- evolves in the same commits as the structural model. Neither half degrades silently; they are versioned together and validated together.

This pairing is the cornerstone of Praxion's approach to context engineering. The global philosophy in `~/.claude/CLAUDE.md` names two principles that AaC+DaC directly operationalizes: **Context Engineering** ("architectural context is first-class; structural facts live in machine-readable models while rationale lives in authored narrative, both versioned together") and **Structural Beauty** ("the architecture you describe is the architecture you ship"). AaC+DaC is the mechanism that makes those principles enforceable rather than aspirational -- a fence convention keeps the model in sync with source, fitness functions detect drift, a pre-commit gate blocks golden-rule violations, and the sentinel audits traceability on every pipeline run.

For the full essay -- the two-halves design, the fence convention, the fitness function infrastructure, the architect-validator agent, and how the mechanisms compose -- see [docs/aac-dac.md](docs/aac-dac.md).
