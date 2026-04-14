# Praxion

[![Version](https://img.shields.io/github/v/release/francisco-perez-sorrosal/Praxion?style=flat-square&label=version)](https://github.com/francisco-perez-sorrosal/Praxion/releases/latest)
[![Release Date](https://img.shields.io/github/release-date/francisco-perez-sorrosal/Praxion?style=flat-square)](https://github.com/francisco-perez-sorrosal/Praxion/releases/latest)
[![License](https://img.shields.io/github/license/francisco-perez-sorrosal/Praxion?style=flat-square)](LICENSE)
[![Last Commit](https://img.shields.io/github/last-commit/francisco-perez-sorrosal/Praxion?style=flat-square)](https://github.com/francisco-perez-sorrosal/Praxion/commits/main)

**A structured layer of reusable expertise, specialized agents, commands, rules, and memory that operationalizes spec-driven development and context engineering into reliable, context-aware results**.

This is my vision for turning AI assistance into a disciplined engineering system. There are many frameworks like this, but this is mine; It's my orchestration of established engineering conventions, workflows, and architectural thinking into the assistant's loop so it operates with continuity and stronger judgment.

Every non-trivial feature starts from a behavioral spec with traceable requirements that thread through architecture, planning, implementation, and verification.

The name comes from *praxis* (knowledge into action) combined with *axon* (signal transmission), representing the bridge between cognition and implementation.

Compatible with **Claude Code** (mainly), **Claude Desktop**, and **Cursor**.

## What You Get

- **34 skills** covering Python, API design, CI/CD, deployment, observability, refactoring, spec-driven development, external API docs, security review, testing strategy, roadmap synthesis, and more -- loaded automatically when the task matches
- **13 specialized agents** that collaborate on complex features (research, architecture, planning, implementation, testing, verification, roadmap cartography)
- **20 slash commands** for daily workflows -- commits, worktrees, memory management, project scaffolding, testing, releases, code review, roadmap generation
- **Coding rules** auto-loaded by context -- coding style, git conventions, documentation standards, agent coordination
- **MCP servers** for persistent memory and agent lifecycle observability

## Core Concepts

The ecosystem has five building blocks that layer from always-on background knowledge down to delegated complex work.

- **Rules** -- Domain knowledge loaded automatically by relevance. Declarative constraints (coding style, git conventions) the assistant applies without explicit invocation.
- **Skills** -- Reusable knowledge modules loaded on demand. Deeper than rules: workflows, procedures, and reference material for specific domains (Python development, refactoring, CI/CD).
- **Commands** -- Slash commands for frequent workflows. User-invoked quick actions (`/co` for commits, `/create-worktree` for git worktrees, `/cajalogic` for cross-session memory).
- **Agents** -- Autonomous subprocesses for complex multi-step tasks. Each runs in its own context with a specialty (research, architecture, implementation, testing, verification). They communicate through shared documents, forming a pipeline.
- **MCP Servers** -- External tool servers for capabilities like persistent memory and task observability.

For a full explanation of how these compose -- including the layered architecture, rules-vs-skills decision model, and agent pipeline flow -- see [Core Concepts](docs/concepts.md).

## Guiding Principles

Five durable principles shape how Praxion evolves, extending the global philosophy in `~/.claude/CLAUDE.md`.

### Token budget is a first-class constraint

Every artifact added must justify its token cost; every artifact removed is a gift to every project that consumes Praxion. Always-loaded content (CLAUDE.md files + unscoped rules) ships into the first 15,000 tokens of every session — `paths:` scoping and progressive-disclosure skills keep that ceiling inviolate.

### Measure before optimizing

Don't guess what improves output quality — measure it. The eval framework (ROADMAP Phase 3), sentinel audits, and the memory MCP observation store turn intuition-driven tuning into evidence-driven design.

### Standards convergence is an opportunity

MCP, AGENTS.md, and A2A under the Linux Foundation's AAIF let Praxion's patterns reach beyond any single assistant. Cross-tool portability to Cursor, Claude Desktop, and the next wave of agentic tooling is intentional.

### Curiosity over dogma

Agent Teams, HTTP hooks, MCP Gateways, and other emerging patterns may reshape assumptions. Keep the architecture open — track known limitations in [`CLAUDE.md`](CLAUDE.md#known-claude-code-limitations) and revisit when fixes ship.

### Behavioral contract over polite compliance

A disciplined assistant is not a polite one. When the user's direction collides with the philosophy, the assistant surfaces the collision instead of quietly executing around it. Four named behaviors define this contract, extending the `Understand, Plan, Verify` methodology with an explicit operational stance every agent is held to:

- **Surface Assumptions** — name every assumption before acting on it; ask when ambiguity could produce the wrong artifact
- **Register Objection** — when a request violates scope, structure, or evidence, flag the conflict with a reason before complying or before declining
- **Stay Surgical** — touch only what the change requires; if the change grew mid-execution, stop and re-scope instead of silently expanding
- **Simplicity First** — prefer the smallest solution that meets the behavior; treat every added line, file, or dependency as a claim that must earn its place

The contract is a first-class operational pillar. It is enforced through an always-loaded rule, self-tests at agent runtime, and named failure-mode tags in verification reports — not left to each agent's interpretation of the philosophy.

For phase-by-phase execution guidance, see [ROADMAP §Guiding Principles for Execution](ROADMAP.md#guiding-principles-for-execution).

## Quick Start

```bash
git clone https://github.com/francisco-perez-sorrosal/Praxion.git
cd Praxion
./install.sh            # Claude Code (default)
./install.sh --check    # Verify installation
```

For other targets: `./install.sh desktop` (Claude Desktop), `./install.sh cursor` (Cursor). See [Installation](#installation) for details.

For a pipeline walkthrough -- from ideation through implementation and verification -- see [Getting Started](docs/getting-started.md).

## What's Included

### Skills

Reusable knowledge modules loaded automatically based on context. See [`skills/README.md`](skills/README.md) for the full catalog with descriptions and activation triggers.

| Category | Skills |
|----------|--------|
| AI Assistant Crafting | skill-crafting, agent-crafting, command-crafting, mcp-crafting, rule-crafting, hook-crafting |
| External Knowledge | external-api-docs |
| Platform Knowledge | claude-ecosystem, agentic-sdks, communicating-agents |
| Planning & Communication | roadmap-planning, roadmap-synthesis, stakeholder-communications |
| Design & Architecture | api-design, data-modeling, deployment, observability, performance-architecture |
| Documentation | doc-management |
| Software Development | python-development, python-prj-mgmt, project-exploration, refactoring, code-review, software-planning, spec-driven-development, agent-evals, cicd, testing-strategy, versioning |
| Security | context-security-review |
| OSS Contribution | upstream-stewardship |
| Project | memory, github-star |

### Commands

Slash commands invoked with `/<name>`. In Claude Code plugin mode, use `/i-am:<name>`. See [`commands/README.md`](commands/README.md) for the full list.

| Command | Description |
|---------|-------------|
| `/co` | Create a commit for staged (or all) changes |
| `/cop` | Create a commit and push to remote |
| `/create-worktree` | Create a new git worktree in `.trees/` |
| `/merge-worktree` | Merge a worktree branch back into current branch |
| `/create-simple-python-prj` | Scaffold a Python project (defaults: pixi, `~/dev`) |
| `/add-rules` | Copy rules into the current project for customization |
| `/manage-readme` | Create or refine README.md files |
| `/clean-work` | Clean the `.ai-work/` directory after pipeline completion |
| `/cajalogic` | Manage persistent memory (user prefs, learnings, conventions, observations) |
| `/onboard-project` | Onboard the current project to work with the ecosystem |
| `/sdd-coverage` | Report spec-to-test and spec-to-code coverage for REQ IDs |
| `/full-security-scan` | Run a full-project security audit against all security-critical paths |
| `/release` | Bump version, update changelog, and create a release tag |
| `/test` | Auto-detect test framework and run tests |
| `/explore-project` | Explore and understand an unfamiliar project's architecture, patterns, and workflow |
| `/roadmap` | Produce a lens-audited `ROADMAP.md` for the current project with both deficit repairs (Weaknesses) and forward lines of work (Opportunities) via a project-derived evaluation lens set |
| `/report-upstream` | File a well-formed bug report on an upstream open-source project |
| `/review-pr` | Code review a pull request |
| `/save-changes` | Save current working changes to project memory with secret filtering |
| `/star-repo` | Star the Praxion repo on GitHub |

### Agents

Thirteen autonomous agents for complex, multi-step tasks. See [`agents/README.md`](agents/README.md) for the pipeline diagram and usage patterns.

| Agent | Description |
|-------|-------------|
| `promethean` | Feature-level ideation from project state |
| `researcher` | Codebase exploration, external docs, alternative evaluation |
| `systems-architect` | Trade-off analysis, system design |
| `implementation-planner` | Step decomposition, execution supervision |
| `context-engineer` | Context artifact auditing, optimization, ecosystem management |
| `implementer` | Step execution with skill-augmented coding and self-review |
| `test-engineer` | Complex test design, test suite refactoring, testing infrastructure |
| `verifier` | Post-implementation review against acceptance criteria |
| `doc-engineer` | Documentation quality management (READMEs, catalogs, changelogs) |
| `sentinel` | Independent ecosystem quality auditor |
| `skill-genesis` | Post-pipeline learning harvest and artifact proposal |
| `cicd-engineer` | CI/CD pipeline design, GitHub Actions, deployment automation |
| `roadmap-cartographer` | Project-level audit through a project-derived lens set (SPIRIT, DORA, SPACE, FAIR, CNCF Platform Maturity, or Custom) synthesized into a grounded `ROADMAP.md` covering strengths, weaknesses, **opportunities (forward lines of work)**, and phased improvements |

### Rules

Domain knowledge files loaded by the assistant within scope (personal = all projects, project = that project). See [`rules/README.md`](rules/README.md) for the full catalog and the rules-vs-skills decision model.

### Observability

Agent pipeline tracing via OpenTelemetry and [Arize Phoenix](https://github.com/Arize-ai/phoenix). Every session -- pipeline runs, native Claude Code agents, tool calls -- is traced and persisted. One Phoenix instance serves all projects on the machine with per-project isolation.

```bash
phoenix-ctl install    # Install daemon (~300MB, starts on login)
open http://localhost:6006  # Trace UI
```

See [Observability](docs/observability.md) for the full guide: architecture, multi-project workflow, configuration, and troubleshooting.

### Memory

Dual-layer persistent memory that gives every agent cross-session knowledge about the project. Curated memories (facts, decisions, gotchas) live in `memory.json`; automatic observations (tool events, session lifecycle) accumulate in `observations.jsonl`. Both live in each project's `.ai-state/` directory and are committed to git.

**Setup**: Memory activates automatically per project. The first `remember()` call or tool event creates `.ai-state/memory.json` and `.ai-state/observations.jsonl`. No manual initialization required.

**How agents use it**:

1. At agent spawn, the `inject_memory.py` hook injects a Markdown summary of all curated entries into the agent's context -- no tool call needed
2. During work, agents call `remember()` when they discover something that applies beyond the current task (guided by the always-loaded `memory-protocol.md` rule)
3. Tool events are captured automatically to the observation log by the `capture_memory.py` hook
4. At agent completion, `validate_memory.py` warns if LEARNINGS.md was written without `remember()`

**Key tools**:

| Tool | Purpose |
|------|---------|
| `remember` | Store a curated memory with type, importance, summary |
| `search` | Multi-term ranked search with Markdown summaries |
| `browse_index` | Full memory index as compact Markdown-KV |
| `timeline` | Chronological view of observations |
| `session_narrative` | Structured summary of a session |
| `consolidate` | Merge, archive, or update entries atomically |

**Configuration** (per project, in `.ai-state/`):

| File | Purpose | Git |
|------|---------|-----|
| `memory.json` | Curated memories (schema v2.0) | Committed |
| `observations.jsonl` | Observation log (append-only) | Committed |
| `*.lock` | File locks for concurrency | Gitignored |

See [Memory Architecture](docs/memory-architecture.md) for the full guide: dual-layer design, data model, enforcement hooks, concurrency model, and scaling strategy.

## Installation

The main entry point is `install.sh`, which routes to `install_claude.sh` (Claude Code/Desktop) or `install_cursor.sh` (Cursor). The interactive installer walks through each choice, defaulting to the recommended option at each step.

```bash
./install.sh                    # Claude Code (default)
./install.sh desktop            # Claude Desktop
./install.sh cursor             # Cursor (user profile ~/.cursor/)
./install.sh cursor /path/repo  # Cursor (per-project at /path/repo/.cursor/)
./install.sh --check            # Verify installation health
./install.sh --uninstall        # Remove installation
./install.sh code --dry-run     # Dry-run: show what would be installed
```

### Claude Code (`./install.sh` or `./install.sh code`)

| Step | What | Interactive? |
|------|------|-------------|
| 1 | Personal config (CLAUDE.md, userPreferences.txt, settings.local.json) to `~/.claude/` | No -- always installed |
| 2 | Rules to `~/.claude/rules/` (auto-loaded by Claude when relevant) | No -- always installed |
| 3 | i-am plugin via [`bit-agora`](https://github.com/francisco-perez-sorrosal/bit-agora) marketplace (scope: user or project) | Yes -- recommended |
| 4 | Task Chronograph hooks (agent lifecycle observability) | Yes -- recommended |
| 5 | CLI scripts (ccwt — multi-worktree Claude sessions) to `~/.local/bin/` | No -- always installed |
| 6 | External API docs ([context-hub](https://github.com/andrewyng/context-hub) MCP — curated API docs for 600+ libraries) | Yes -- recommended |
| 7 | Phoenix observability daemon (persistent trace backend at `http://localhost:6006`) | Yes -- recommended |
| 7 | Claude Desktop config link to official Desktop location | Yes -- skip by default |

When installed as a plugin, commands are namespaced: `/co` becomes `/i-am:co`. Plugin permissions for skill reference files are auto-configured at Step 3. See [`README_DEV.md`](README_DEV.md#progressive-disclosure-and-satellite-files) for how progressive disclosure works with plugin-installed skills.

**Manual plugin install** (without the interactive installer):

```bash
claude plugin marketplace add francisco-perez-sorrosal/bit-agora
claude plugin install i-am@bit-agora --scope user
```

### Claude Desktop (`./install.sh desktop`)

Links `claude_desktop_config.json` to the official Desktop location:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

Skills, commands, and agents are Claude Code features -- run `./install.sh code` for the full feature set.

### Cursor (`./install.sh cursor`)

Installs skills, rules, commands, and MCP into Cursor's discovery paths. Two targets:

| Target | Command | Result |
|--------|---------|--------|
| **User profile (default)** | `./install.sh cursor` | Installs into `~/.cursor/`. Available in every Cursor project. |
| **Per project** | `./install.sh cursor /path/to/repo` | Installs into `/path/to/repo/.cursor/`. Only that project sees these artifacts. |

**What gets installed:**

| What | How |
|------|-----|
| Skills | Symlinks to this repo's `skills/<name>/` |
| Rules | Symlinks to this repo's `rules/` (preserving directory structure) |
| Commands | Exported from `commands/*.md` (frontmatter stripped to plain Markdown) |
| MCP | `mcp.json` with task-chronograph, memory, and [sub-agents-mcp](https://github.com/shinpr/sub-agents-mcp) |

**Agents prerequisite**: sub-agents-mcp uses `cursor-agent` as its backend. Run `cursor-agent login` to authenticate before using agents in Cursor.

**Verification:**

```bash
./install.sh cursor --check           # user profile
./install.sh cursor /path --check     # per-project
```

For **Claude Code vs Cursor** format differences (discovery paths, command export, MCP config), see [docs/cursor-compat.md](docs/cursor-compat.md).

### User Preferences (Claude Desktop / iOS)

On devices without filesystem access (e.g., Claude iOS app) or when using Claude Desktop without the CLI, paste the following into the **User Preferences** field in Claude's settings:

```text
Read the user preferences from https://raw.githubusercontent.com/francisco-perez-sorrosal/Praxion/main/claude/config/userPreferences.txt and follow them before any other interaction
```

**Config directories** -- Installer resources live in tool-specific dirs:

- **claude/config/** -- Personal config files (CLAUDE.md, userPreferences.txt, claude_desktop_config.json) and lists. See [claude/config/README.md](claude/config/README.md).
- **cursor/config/** -- MCP template and expected servers. See [cursor/config/README.md](cursor/config/README.md).

## Advanced Topics

- **[Memory Architecture](docs/memory-architecture.md)** -- Dual-layer memory system: curated JSON + observation JSONL, enforcement hooks, concurrency model, temporal consistency, scaling strategy, and agent integration.
- **[External API Docs](docs/external-api-docs.md)** -- Retrieve current, curated API documentation for external libraries (Stripe, OpenAI, AWS, etc.) during development. Setup guide, workflow examples, and the annotation learning loop.
- **[Spec-Driven Development](docs/spec-driven-development.md)** -- Behavioral specifications with requirement IDs for medium/large features. The pipeline scales proportionally: small tasks skip specs; substantive features get full traceability.
- **[Decision Tracking](docs/decision-tracking.md)** -- Architecture Decision Records (ADRs) in `.ai-state/decisions/` capture decisions from AI-assisted sessions. Agents write structured Markdown files with YAML frontmatter, with a lightweight reminder hook for architectural commits.
- **[Claude Code vs Cursor](docs/cursor-compat.md)** -- Format differences, discovery paths, and adaptation details for each tool.
- **[Core Concepts](docs/concepts.md)** -- Deep explanation of the building blocks, the layered architecture, and the agent pipeline.
- **[Claude Ecosystem Learning Resources](docs/claude-ecosystem-learning-resources.md)** -- Curated external guides covering Claude models, cowork patterns, practical workflows, setup strategies, and domain applications. Recommended for new users and skill authors.



---

For contributor and developer documentation, see [`README_DEV.md`](README_DEV.md).
