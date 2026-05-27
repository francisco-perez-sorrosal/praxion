# Praxion

[![License](https://img.shields.io/github/license/francisco-perez-sorrosal/Praxion)](LICENSE)
[![Release](https://img.shields.io/github/v/release/francisco-perez-sorrosal/Praxion)](https://github.com/francisco-perez-sorrosal/Praxion/releases/latest)
[![Last Commit](https://img.shields.io/github/last-commit/francisco-perez-sorrosal/Praxion)](https://github.com/francisco-perez-sorrosal/Praxion/commits/main)

**A structured layer of reusable expertise — skills, agents, commands, rules, and memory — that operationalizes spec-driven development and context engineering into reliable, context-aware results.**

This is my vision for turning AI assistance into a disciplined engineering system. There are many frameworks like this, but this one is mine: an orchestration of established engineering conventions, workflows, and architectural thinking into the assistant's loop, so it operates with continuity and stronger judgment.

Every non-trivial feature starts from a behavioral spec with traceable requirements that thread through architecture, planning, implementation, and verification.

The name combines *praxis* (knowledge into action) and *axon* (signal transmission) — the bridge between cognition and implementation.

Compatible with **Claude Code** (primary), **Claude Desktop**, **Cursor**, and AGENTS.md-aware agents such as **Codex**.

## Contents

- [What You Get](#what-you-get)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
- [Guiding Principles](#guiding-principles)
- [What's Included](#whats-included)
- [Installation](#installation)
- [Documentation](#documentation)

## What You Get

- **49 skills** — Python, API design, CI/CD, deployment, observability, refactoring, spec-driven development, security review, testing, ML/AI training, web/TUI/API interface design, and more. Loaded automatically when the task matches.
- **15 specialized agents** — research, architecture, interface design, planning, implementation, testing, verification, structural validation, roadmap cartography. They collaborate on complex features through a shared-document pipeline.
- **39 slash commands** — commits, worktrees, memory management, project scaffolding, testing, releases, code review, roadmap generation, metrics, ML experiment dispatch.
- **20 rules** — coding style, git conventions, documentation standards, agent coordination. Auto-loaded by context.
- **MCP servers** — persistent cross-session memory and agent-lifecycle observability.
- **Architecture-as-Code + Documentation-as-Code stack** — fence convention, fitness functions, golden-rule pre-commit gate, `architect-validator` agent, architecture CI workflow, REQ↔architecture traceability, periodic `sentinel` audit, Diátaxis-aligned doc taxonomy. See [docs/aac-dac.md](docs/aac-dac.md) for how the mechanisms compose.

## Quick Start

```bash
git clone https://github.com/francisco-perez-sorrosal/Praxion.git
cd Praxion
./install.sh            # Claude Code (default)
./install.sh --check    # Verify installation
```

Other targets: `./install.sh desktop` (Claude Desktop), `./install.sh cursor` (Cursor), `./install.sh codex /path/repo` (Codex / AGENTS.md-aware agents). See [Installation](#installation) for the per-target detail.

### Onboard a Project

Two entry points, picked by what is already in the directory. Both converge on the same Praxion-aware end state — identical `.gitignore` block, `.ai-state/` skeleton, git hooks, and `CLAUDE.md` blocks.

| Starting point                   | Entry point                                                                 | Companion doc                                                      |
| -------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| **Empty directory** (greenfield) | `./new_project.sh <name>`, then `/new-project` inside the launched session  | [Greenfield Project Onboarding](docs/greenfield-onboarding.md)     |
| **Existing project** (has code)  | `/onboard-project` inside a Claude Code session at the project root         | [Existing-Project Onboarding](docs/existing-project-onboarding.md) |

The greenfield flow ends by chaining to `/onboard-project`, so there is one source of truth for what "Praxion-onboarded" means. `/onboard-project` runs ten idempotent phases with `AskUserQuestion` gates — including an opt-in architecture baseline that produces `.ai-state/DESIGN.md` + `docs/architecture.md` from the existing codebase. For a pipeline walkthrough from ideation through verification, see [Getting Started](docs/getting-started.md).

## Core Concepts

The ecosystem has five building blocks that layer from always-on background knowledge down to delegated complex work.

- **Rules** — domain knowledge loaded automatically by relevance. Declarative constraints (coding style, git conventions) the assistant applies without explicit invocation.
- **Skills** — reusable knowledge modules loaded on demand. Deeper than rules: workflows, procedures, and reference material for specific domains.
- **Commands** — slash commands for frequent workflows. User-invoked quick actions (`/co` for commits, `/create-worktree` for git worktrees, `/cajalogic` for cross-session memory).
- **Agents** — autonomous subprocesses for complex multi-step tasks. Each runs in its own context with a specialty and communicates through shared documents, forming a pipeline.
- **MCP servers** — external tool servers for capabilities like persistent memory and task observability.

For the layered architecture, the rules-vs-skills decision model, and the agent pipeline flow, see [Core Concepts](docs/concepts.md).

### Project Archetypes

Praxion manages three project archetypes through one shared pipeline:

- **Traditional SWE** — the default; covered by the full skill catalog.
- **Agentic-AI apps** — agents-as-products; activated by `agentic-sdks`, `agent-evals`, `mcp-crafting`, `communicating-agents`.
- **ML/AI training** — pre-training projects with compute budgets, eval thresholds, and experiment loops; activated by `ml-training`, `llm-training-eval`, `neo-cloud-abstraction`, `experiment-tracking`. Run `/run-experiment` to dispatch a training run, `/check-experiment` to poll one. See the [ML/AI Training Onramp](docs/ml-training-onramp.md).

Orthogonal to the archetypes, **hackathon mode** is a project-scoped opt-in that replaces the 5-tier process selector with a flexible-entry **Hackathon Spine**: a fixed-order pipeline you enter at any stage by describing what you need in natural language, move around in freely mid-task, and exit. Test/SDD/ADR ceremony is relaxed for proof-of-concept work; the behavioral contract and the verifier remain. Enabled via `/onboard-project` Phase 5b or `/new-project --hackathon`; day-to-day launch is `scripts/praxion-hackathon`. Component map: [Architecture Guide §11](docs/architecture.md#11-hackathon-mode).

## Guiding Principles

Five durable principles shape how Praxion evolves, extending the global philosophy in `~/.claude/CLAUDE.md`.

- **Token budget is a first-class constraint.** Always-loaded content (CLAUDE.md files + unscoped rules) ships into the first 25,000 tokens of every session — a failure-mode guardrail, not a target. `paths:` scoping and progressive-disclosure skills keep that ceiling inviolate.
- **Measure before optimizing.** Don't guess what improves output quality — measure it. The eval framework, sentinel audits, and the memory observation store turn intuition-driven tuning into evidence-driven design.
- **Standards convergence is an opportunity.** MCP, AGENTS.md, and A2A let Praxion's patterns reach beyond any single assistant. Cross-tool portability to Cursor, Claude Desktop, and the next wave of agentic tooling is intentional.
- **Curiosity over dogma.** Emerging patterns may reshape assumptions. Keep the architecture open — known limitations are tracked in [`CLAUDE.md`](CLAUDE.md#known-claude-code-limitations) and revisited when fixes ship.
- **Behavioral contract over polite compliance.** A disciplined assistant is not a polite one. When the user's direction collides with the philosophy, the assistant surfaces the collision instead of quietly executing around it.

The behavioral contract is a first-class operational pillar — enforced through an always-loaded rule, agent-runtime self-tests, and named failure-mode tags in verification reports. Four named behaviors define it:

- **Surface Assumptions** — name every assumption before acting; ask when ambiguity could produce the wrong artifact.
- **Register Objection** — when a request violates scope, structure, or evidence, flag the conflict with a reason before complying or declining.
- **Stay Surgical** — touch only what the change requires; if scope grew mid-execution, stop and re-scope.
- **Simplicity First** — prefer the smallest solution that meets the behavior; every added line, file, or dependency must earn its place.

## What's Included

### Skills

Reusable knowledge modules loaded automatically based on context. See [skills/README.md](skills/README.md) for the full catalog with activation triggers.

| Category                 | Skills                                                                                                                                                                                        |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AI Assistant Crafting    | skill-crafting, agent-crafting, command-crafting, mcp-crafting, rule-crafting, hook-crafting                                                                                                   |
| External Knowledge       | external-api-docs                                                                                                                                                                             |
| Platform Knowledge       | claude-ecosystem, agentic-sdks, communicating-agents, llm-prompt-engineering                                                                                                                  |
| Planning & Communication | roadmap-planning, roadmap-synthesis, stakeholder-communications                                                                                                                               |
| Design & Architecture    | api-design, data-modeling, deployment, observability, performance-architecture                                                                                                                |
| ML/AI Training           | ml-training, llm-training-eval, neo-cloud-abstraction, experiment-tracking                                                                                                                    |
| Documentation            | doc-management                                                                                                                                                                                |
| Software Development     | python-development, python-prj-mgmt, project-exploration, refactoring, code-review, software-planning, spec-driven-development, agent-evals, cicd, testing-strategy, test-coverage, versioning |
| Security                 | context-security-review                                                                                                                                                                       |
| OSS Contribution         | upstream-stewardship                                                                                                                                                                          |
| Project                  | memory, id-decontamination                                                                                                                                                                    |

### Commands

39 slash commands invoked with `/<name>` (`/i-am:<name>` in Claude Code plugin mode). Frequently used:

- `/co`, `/cop` — create a commit (and push)
- `/create-worktree`, `/merge-worktree` — git worktree lifecycle
- `/onboard-project`, `/new-project` — bring a project into the ecosystem
- `/roadmap` — produce a lens-audited `ROADMAP.md`
- `/project-metrics`, `/eval-praxion` — health metrics and out-of-band quality evals
- `/run-experiment`, `/check-experiment` — ML training experiment dispatch

See [commands/README.md](commands/README.md) for the complete list with descriptions.

> [!NOTE]
> **Commands are skills now (in Claude Code).** Claude Code [merged custom slash commands into skills](https://code.claude.com/docs/en/skills) — a `commands/<name>.md` file and a `skills/<name>/SKILL.md` directory both produce `/<name>`, and Claude Code already surfaces Praxion's commands through the skill system. Praxion keeps its slash commands as single-file `commands/*.md` because that directory is the **assistant-agnostic source** `install.sh` exports to Cursor and Codex (which don't share the merge). Rule of thumb: author a `commands/*.md` file for a portable single-file workflow; reach for a `skills/<name>/` directory when it needs bundled scripts/references or should auto-load. See the [`command-crafting`](skills/command-crafting/SKILL.md) skill for the decision.

### Agents

15 autonomous agents for complex, multi-step tasks, organized by pipeline role. See [agents/README.md](agents/README.md) for the pipeline diagram and usage patterns.

| Role            | Agents                                                                              |
| --------------- | ----------------------------------------------------------------------------------- |
| Ideation        | `promethean` — feature-level ideation from project state                            |
| Research & design | `researcher`, `systems-architect`, `interface-designer`, `context-engineer`       |
| Planning        | `implementation-planner` — step decomposition and execution supervision             |
| Build           | `implementer`, `test-engineer`, `doc-engineer`                                      |
| Verification    | `verifier`, `architect-validator` — acceptance review and code↔DSL↔ADR validation   |
| Independent     | `sentinel` (ecosystem audit), `skill-genesis` (learning harvest), `roadmap-cartographer`, `cicd-engineer` |

`skill-genesis` runs as an autonomous, on-demand learning-harvest report writer (invoked via `/skill-genesis`); proposals are dispositioned later via `/skill-genesis-review`.

### Rules

Domain knowledge files loaded by the assistant within scope (personal = all projects, project = that project). See [rules/README.md](rules/README.md) for the full catalog and the rules-vs-skills decision model.

### Observability

Agent pipeline tracing via OpenTelemetry and [Arize Phoenix](https://github.com/Arize-ai/phoenix). Every session — pipeline runs, native Claude Code agents, tool calls — is traced and persisted. One Phoenix instance serves all projects on the machine with per-project isolation.

```bash
phoenix-ctl install         # Install daemon (~300MB, starts on login)
open http://localhost:6006  # Trace UI
```

See [Observability](docs/observability.md) for architecture, multi-project workflow, configuration, and troubleshooting.

### Memory

Dual-layer persistent memory gives every agent cross-session knowledge about the project. Curated memories (facts, decisions, gotchas) live in `memory.json`; automatic observations (tool events, session lifecycle) accumulate in `observations.jsonl`. Both live in each project's `.ai-state/` directory and are committed to git.

Memory activates automatically per project — the first `remember()` call or tool event creates the files. At agent spawn, a hook injects a Markdown summary of curated entries into the agent's context; during work, agents call `remember()` for cross-task discoveries; tool events are captured automatically.

See [Memory Architecture](docs/memory-architecture.md) for the dual-layer design, data model, enforcement hooks, and concurrency model.

## Installation

The main entry point is `install.sh`, which routes to `install_claude.sh` (Claude Code/Desktop), `install_cursor.sh` (Cursor), or `install_codex.sh` (Codex / AGENTS.md-aware agents). The interactive installer defaults to the recommended option at each step.

```bash
./install.sh                    # Claude Code (default)
./install.sh desktop            # Claude Desktop
./install.sh cursor             # Cursor (user profile ~/.cursor/)
./install.sh cursor /path/repo  # Cursor (per-project at /path/repo/.cursor/)
./install.sh codex /path/repo   # Codex / AGENTS.md-aware agents
./install.sh --check            # Verify installation health
./install.sh --uninstall        # Remove installation
./install.sh code --dry-run     # Show what would be installed
```

### Claude Code

`./install.sh` (or `./install.sh code`) walks through seven steps:

| Step | What                                                                                                                      | Interactive?           |
| ---- | ------------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| 1    | Personal config (CLAUDE.md, userPreferences.txt, settings.local.json) to `~/.claude/`                                     | No — always installed  |
| 2    | Rules to `~/.claude/rules/` (auto-loaded when relevant)                                                                   | No — always installed  |
| 3    | i-am plugin via [bit-agora](https://github.com/francisco-perez-sorrosal/bit-agora) marketplace (scope: user or project)   | Yes — recommended      |
| 4    | Task Chronograph hooks (agent lifecycle observability)                                                                    | Yes — recommended      |
| 5    | CLI scripts (`ccwt` — multi-worktree Claude sessions) to `~/.local/bin/`                                                  | No — always installed  |
| 6    | External API docs ([context-hub](https://github.com/andrewyng/context-hub) MCP — curated docs for 600+ libraries)         | Yes — recommended      |
| 7    | Phoenix observability daemon (persistent trace backend at `http://localhost:6006`)                                        | Yes — recommended      |

When installed as a plugin, commands are namespaced: `/co` becomes `/i-am:co`.

> [!TIP]
> Developing on Praxion itself? After the standard install, use `praxion-claude-dev` (placed at `~/.local/bin/`) to launch a session that loads the plugin from your working tree — edits to skills, commands, agents, and hooks are live. See [README_DEV.md](README_DEV.md#session-scoped-local-testing).

<details>
<summary><strong>Marketplace plugin install</strong> (Claude Code only)</summary>

```bash
claude plugin marketplace add francisco-perez-sorrosal/bit-agora
claude plugin install i-am@bit-agora --scope user
```

Praxion auto-completes setup on the first Claude Code session — rules are symlinked to `~/.claude/rules/`, CLI scripts to `~/.local/bin/`, no manual step required. `claude plugin install` fetches the full repo at the marketplace-pinned tag into `~/.claude/plugins/cache/`; auto-completion symlinks from that cache without cloning or network access.

**After plugin updates** — `claude plugin update i-am` leaves existing symlinks pointing at the old version. Start a fresh session (auto-completion refreshes them) or run `/praxion-complete-install`.

**Uninstall order** — run `/praxion-complete-uninstall` **first**, then `claude plugin uninstall i-am`. The reverse order leaves dangling symlinks (still cleanable by `/praxion-complete-uninstall`).

To reconfigure personal settings or recover from corruption, `/praxion-complete-install` is idempotent and prompts before each system-level change.

</details>

### Claude Desktop

`./install.sh desktop` links `claude_desktop_config.json` to the official Desktop location (`~/Library/Application Support/Claude/` on macOS, `~/.config/Claude/` on Linux). Skills, commands, and agents are Claude Code features — run `./install.sh code` for the full feature set.

### Cursor

`./install.sh cursor` installs skills, rules, commands, and MCP into Cursor's discovery paths — either the user profile (`~/.cursor/`, default) or per-project (`./install.sh cursor /path/to/repo` → `/path/to/repo/.cursor/`). Skills and rules are symlinked to this repo; commands are exported as plain Markdown; `mcp.json` registers task-chronograph, memory, and [sub-agents-mcp](https://github.com/shinpr/sub-agents-mcp).

> [!NOTE]
> Agents in Cursor use `cursor-agent` as the sub-agents-mcp backend — run `cursor-agent login` before using them.

Verify with `./install.sh cursor --check` (add a path for per-project). For Claude Code vs Cursor format differences, see [docs/cursor-compat.md](docs/cursor-compat.md).

### Codex / AGENTS.md-Aware Agents

`./install.sh codex /path/repo` compiles the target project's `AGENTS.md` from the shared Praxion Codex philosophy plus a project adapter, and manages project-local adapter surfaces under `.codex/` and `.agents/` (thin agent/skill/command wrappers that point back to canonical Praxion sources, plus a rules bridge).

```bash
./install.sh codex /path/to/repo --dry-run
./install.sh codex /path/to/repo
./install.sh codex /path/to/repo --check
```

`AGENTS.md.tmpl` is the editable source; `AGENTS.md` is compiled output. If the template is missing, the installer generates it once from the project's `CLAUDE.md`. Start a fresh Codex session after installation so the new `AGENTS.md` loads. Claude project onboarding owns `.ai-state/` creation — the Codex adapter installs memory and observability hooks but they activate only once `.ai-state/` exists. See [codex/config/README.md](codex/config/README.md) for the adapter mechanics.

### User Preferences (Claude Desktop / iOS)

On devices without filesystem access, paste this into the **User Preferences** field in Claude's settings:

```text
Read the user preferences from https://raw.githubusercontent.com/francisco-perez-sorrosal/Praxion/main/claude/config/userPreferences.txt and follow them before any other interaction
```

Installer resources live in tool-specific config directories: [claude/config/](claude/config/README.md), [codex/config/](codex/config/README.md), [cursor/config/](cursor/config/README.md).

## Documentation

- **[Core Concepts](docs/concepts.md)** — the building blocks, the layered architecture, and the agent pipeline.
- **[Memory Architecture](docs/memory-architecture.md)** — dual-layer memory: curated JSON + observation JSONL, enforcement hooks, concurrency model, scaling strategy.
- **[External API Docs](docs/external-api-docs.md)** — retrieve current API documentation for external libraries during development.
- **[Spec-Driven Development](docs/spec-driven-development.md)** — behavioral specifications with requirement IDs for medium/large features.
- **[Decision Tracking](docs/decision-tracking.md)** — Architecture Decision Records in `.ai-state/decisions/` capturing decisions from AI-assisted sessions.
- **[Claude Code vs Cursor](docs/cursor-compat.md)** — format differences, discovery paths, and adaptation details.
- **[Claude Ecosystem Learning Resources](docs/claude-ecosystem-learning-resources.md)** — curated external guides for new users and skill authors.

For in-flight tech debt see [`.ai-state/TECH_DEBT_LEDGER.md`](.ai-state/TECH_DEBT_LEDGER.md); for strategic horizons and ideation, see the most recent ledger under [`.ai-state/idea_ledgers/`](.ai-state/idea_ledgers/).

---

For contributor and developer documentation, see [README_DEV.md](README_DEV.md).
