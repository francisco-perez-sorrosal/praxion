# Praxion

Praxion is my vision for turning AI assistance into an agentic disciplined engineering system. There are many frameworks like this, but this is mine. I evolve it as I think I should, taking into account the fast evolution of technology these days. It tries to reflect how I want to build with what some define as `"intelligent systems"`: not as a loose collection of prompts or assistants, but as a structured layer of reusable expertise, specialized agents, commands, rules, and memory that work together to produce reliable, context-aware results. At its core, it operationalizes spec-driven development (SPECs) and context engineering (through skills, agents, rules, and commands) so that intent, constraints, and workflows are explicitly encoded and consistently executed. The project brings my conventions, workflows, and architectural thinking into the loop, enabling the assistant to operate with continuity, stronger judgment, and a clear understanding of how software should be designed, implemented, and evolved. I'm trying to make it compatible with **Claude Code**, **Claude Desktop**, and **Cursor**, although I mainly use CC.

The name Praxion comes from praxis, or the idea of turning knowledge into action, combined with `axon`, a suffix with influences from both neuroscience (axon, the structure responsible for transmitting signals,) and `-ion`, a system-oriented suffix that evokes motion, execution, and structure. It reflects the core intent of the project: not just to think with AI, but to operationalize that thinking into repeatable, high-quality engineering outcomes. I use Praxion as a representation of the bridge between cognition and implementation; that is, the helper that allows ideas to systematically evolve into working systems.

## What You Get

- **24 skills** covering Python, API design, CI/CD, refactoring, spec-driven development, and more -- loaded automatically when the task matches
- **12 specialized agents** that collaborate on complex features (research, architecture, planning, implementation, testing, verification)
- **12 slash commands** for daily workflows -- commits, worktrees, memory management, project scaffolding
- **Coding rules** auto-loaded by context -- coding style, git conventions, documentation standards, agent coordination
- **MCP servers** for persistent memory and agent lifecycle observability

## Core Concepts

The ecosystem has five building blocks that layer from always-on background knowledge down to delegated complex work.

- **Rules** -- Domain knowledge loaded automatically by relevance. Declarative constraints (coding style, git conventions) the assistant applies without explicit invocation.
- **Skills** -- Reusable knowledge modules loaded on demand. Deeper than rules: workflows, procedures, and reference material for specific domains (Python development, refactoring, CI/CD).
- **Commands** -- Slash commands for frequent workflows. User-invoked quick actions (`/co` for commits, `/create-worktree` for git worktrees, `/memory` for cross-session persistence).
- **Agents** -- Autonomous subprocesses for complex multi-step tasks. Each runs in its own context with a specialty (research, architecture, implementation, testing, verification). They communicate through shared documents, forming a pipeline.
- **MCP Servers** -- External tool servers for capabilities like persistent memory and task observability.

For a full explanation of how these compose -- including the layered architecture, rules-vs-skills decision model, and agent pipeline flow -- see [Core Concepts](docs/concepts.md).

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
| AI Assistant Crafting | skill-crafting, agent-crafting, command-crafting, mcp-crafting, rule-crafting |
| Platform Knowledge | claude-ecosystem, agentic-sdks, communicating-agents |
| Planning & Communication | roadmap-planning, stakeholder-communications |
| Design & Architecture | api-design, data-modeling, performance-architecture |
| Documentation | doc-management |
| Software Development | python-development, python-prj-mgmt, refactoring, code-review, software-planning, spec-driven-development, agent-evals, cicd |
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
| `/memory` | Manage persistent memory (user prefs, learnings, conventions) |
| `/onboard-project` | Onboard the current project to work with the ecosystem |
| `/sdd-coverage` | Report spec-to-test and spec-to-code coverage for REQ IDs |
| `/star-repo` | Star the Praxion repo on GitHub |

### Agents

Twelve autonomous agents for complex, multi-step tasks. See [`agents/README.md`](agents/README.md) for the pipeline diagram and usage patterns.

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

### Rules

Domain knowledge files loaded by the assistant within scope (personal = all projects, project = that project). See [`rules/README.md`](rules/README.md) for the full catalog and the rules-vs-skills decision model.

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
| 5 | Claude Desktop config link to official Desktop location | Yes -- skip by default |

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

- **[Spec-Driven Development](docs/spec-driven-development.md)** -- Behavioral specifications with requirement IDs for medium/large features. The pipeline scales proportionally: small tasks skip specs; substantive features get full traceability.
- **[Decision Tracking](docs/decision-tracking.md)** -- Machine-readable audit log of decisions from AI-assisted sessions. Dual-path capture (agents write directly + commit-time hook safety net) with tier-aware gating.
- **[Claude Code vs Cursor](docs/cursor-compat.md)** -- Format differences, discovery paths, and adaptation details for each tool.
- **[Core Concepts](docs/concepts.md)** -- Deep explanation of the building blocks, the layered architecture, and the agent pipeline.

---

For contributor and developer documentation, see [`README_DEV.md`](README_DEV.md).
