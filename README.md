# Praxion

[Version](https://github.com/francisco-perez-sorrosal/Praxion/releases/latest)
[Release Date](https://github.com/francisco-perez-sorrosal/Praxion/releases/latest)
[License](LICENSE)
[Last Commit](https://github.com/francisco-perez-sorrosal/Praxion/commits/main)

**A structured layer of reusable expertise, specialized agents, commands, rules, and memory that operationalizes spec-driven development and context engineering into reliable, context-aware results**.

This is my vision for turning AI assistance into a disciplined engineering system. There are many frameworks like this, but this is mine; It's my orchestration of established engineering conventions, workflows, and architectural thinking into the assistant's loop so it operates with continuity and stronger judgment.

Every non-trivial feature starts from a behavioral spec with traceable requirements that thread through architecture, planning, implementation, and verification.

The name comes from *praxis* (knowledge into action) combined with *axon* (signal transmission), representing the bridge between cognition and implementation.

Compatible with **Claude Code** (mainly), **Claude Desktop**, and **Cursor**.

## What You Get

- **36 skills** covering Python, API design, CI/CD, deployment, observability, refactoring, spec-driven development, external API docs, security review, testing strategy, test coverage, roadmap synthesis, and more -- loaded automatically when the task matches
- **13 specialized agents** that collaborate on complex features (research, architecture, planning, implementation, testing, verification, roadmap cartography)
- **29 slash commands** for daily workflows -- commits, worktrees, memory management, project scaffolding, testing, releases, code review, roadmap generation, metrics
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

Every artifact added must justify its token cost; every artifact removed is a gift to every project that consumes Praxion. Always-loaded content (CLAUDE.md files + unscoped rules) ships into the first 25,000 tokens of every session — a failure-mode guardrail, not a target. `paths:` scoping and progressive-disclosure skills keep that ceiling inviolate.

### Measure before optimizing

Don't guess what improves output quality — measure it. The eval framework (ROADMAP Phase 3), sentinel audits, and the memory MCP observation store turn intuition-driven tuning into evidence-driven design.

### Standards convergence is an opportunity

MCP, AGENTS.md, and A2A under the Linux Foundation's AAIF let Praxion's patterns reach beyond any single assistant. Cross-tool portability to Cursor, Claude Desktop, and the next wave of agentic tooling is intentional.

### Curiosity over dogma

Agent Teams, HTTP hooks, MCP Gateways, and other emerging patterns may reshape assumptions. Keep the architecture open — track known limitations in `[CLAUDE.md](CLAUDE.md#known-claude-code-limitations)` and revisit when fixes ship.

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

### Onboard a project

Two distinct paths, picked by what's already in the directory. Both converge on the same Praxion-aware end state — same `.gitignore` block, same `.ai-state/` skeleton, same git hooks, same `CLAUDE.md` blocks.


| Starting point                   | Entry point                                                                 | Companion doc                                                      |
| -------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| **Empty directory** (greenfield) | `./new_project.sh <name>` then `/new-project` inside the launched session   | [Greenfield Project Onboarding](docs/greenfield-onboarding.md)     |
| **Existing project** (has code)  | `/onboard-project` inside an active Claude Code session at the project root | [Existing-Project Onboarding](docs/existing-project-onboarding.md) |


The greenfield flow ends by chaining to `/onboard-project` so there is one source of truth for what "Praxion-onboarded" means. `/onboard-project` runs nine phases with `AskUserQuestion` gates between them — including an opt-in **Phase 8 architecture baseline** that delegates to `systems-architect` to produce `.ai-state/ARCHITECTURE.md` + `docs/architecture.md` from the existing codebase (high leverage: every later sentinel audit, feature pipeline, and Memory MCP recall benefits from those docs landing on day one).

For a pipeline walkthrough -- from ideation through implementation and verification -- see [Getting Started](docs/getting-started.md).

## What's Included

### Skills

Reusable knowledge modules loaded automatically based on context. See `[skills/README.md](skills/README.md)` for the full catalog with descriptions and activation triggers.


| Category                 | Skills                                                                                                                                                                                         |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AI Assistant Crafting    | skill-crafting, agent-crafting, command-crafting, mcp-crafting, rule-crafting, hook-crafting                                                                                                   |
| External Knowledge       | external-api-docs                                                                                                                                                                              |
| Platform Knowledge       | claude-ecosystem, agentic-sdks, communicating-agents, llm-prompt-engineering                                                                                                                   |
| Planning & Communication | roadmap-planning, roadmap-synthesis, stakeholder-communications                                                                                                                                |
| Design & Architecture    | api-design, data-modeling, deployment, observability, performance-architecture                                                                                                                 |
| Documentation            | doc-management                                                                                                                                                                                 |
| Software Development     | python-development, python-prj-mgmt, project-exploration, refactoring, code-review, software-planning, spec-driven-development, agent-evals, cicd, testing-strategy, test-coverage, versioning |
| Security                 | context-security-review                                                                                                                                                                        |
| OSS Contribution         | upstream-stewardship                                                                                                                                                                           |
| Project                  | memory, id-decontamination                                                                                                                                                                     |


### Commands

Slash commands invoked with `/<name>`. In Claude Code plugin mode, use `/i-am:<name>`. See `[commands/README.md](commands/README.md)` for the full list.


| Command                       | Description                                                                                                                                                                              |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/co`                         | Create a commit for staged (or all) changes                                                                                                                                              |
| `/cop`                        | Create a commit and push to remote                                                                                                                                                       |
| `/create-worktree`            | Create a new git worktree under `.claude/worktrees/` (legacy `.trees/` accepted by `/merge-worktree` during deprecation — run `scripts/migrate_worktree_home.sh` for migration commands) |
| `/merge-worktree`             | Merge a worktree branch back into current branch; runs `.ai-state/` reconciliation and finalizes any draft ADRs                                                                          |
| `/clean-auto-memory`          | Opt-in cleanup of orphan Claude Code auto-memory directories for removed worktrees                                                                                                       |
| `/create-simple-python-prj`   | Scaffold a Python project (defaults: pixi, `~/dev`)                                                                                                                                      |
| `/add-rules`                  | Copy rules into the current project for customization                                                                                                                                    |
| `/manage-readme`              | Create or refine README.md files                                                                                                                                                         |
| `/clean-work`                 | Clean the `.ai-work/` directory after pipeline completion                                                                                                                                |
| `/decontaminate-ids`          | Detect and remediate REQ/AC/step citations in project source code                                                                                                                        |
| `/cajalogic`                  | Manage persistent memory (user prefs, learnings, conventions, observations)                                                                                                              |
| `/onboard-project`            | Onboard the current project to work with the ecosystem                                                                                                                                   |
| `/sdd-coverage`               | Report spec-to-test and spec-to-code coverage for REQ IDs                                                                                                                                |
| `/full-security-scan`         | Run a full-project security audit against all security-critical paths                                                                                                                    |
| `/release`                    | Bump version, update changelog, and create a release tag                                                                                                                                 |
| `/test`                       | Auto-detect test framework and run tests                                                                                                                                                 |
| `/explore-project`            | Explore and understand an unfamiliar project's architecture, patterns, and workflow                                                                                                      |
| `/roadmap`                    | Produce a lens-audited `ROADMAP.md` for the current project with both deficit repairs (Weaknesses) and forward lines of work (Opportunities) via a project-derived evaluation lens set   |
| `/report-upstream`            | File a well-formed bug report on an upstream open-source project                                                                                                                         |
| `/review-pr`                  | Code review a pull request                                                                                                                                                               |
| `/save-changes`               | Save current working changes to project memory with secret filtering                                                                                                                     |
| `/star-repo`                  | Star the Praxion repo on GitHub                                                                                                                                                          |
| `/project-metrics`            | Compute project complexity/health metrics (churn, complexity, coupling, hot-spots, trends) and write a timestamped report triple to `.ai-state/`                                         |
| `/project-coverage`           | Run the project's canonical coverage target and render a terminal summary via the `test-coverage` skill                                                                                  |
| `/eval`                       | Run out-of-band quality evals (Tier 1 behavioral + regression) — opt-in, never hook-driven                                                                                               |
| `/new-project`                | Scaffold a greenfield Claude-ready Python project and onboard it to Praxion                                                                                                              |
| `/refresh-skill`              | Refresh version-sensitive sections of a skill against current upstream documentation                                                                                                     |
| `/praxion-complete-install`   | Finish a marketplace-only Praxion install — symlink rules, CLI scripts, and optional context-hub MCP                                                                                     |
| `/praxion-complete-uninstall` | Reverse `/praxion-complete-install` — remove rule/script symlinks and optional MCP                                                                                                       |


**Deep dive:** `/new-project` **(greenfield)**

The bash wrapper `new_project.sh <name> [target-dir]` lays a pre-Claude scaffold (`.git/` repo, AI-assistants `.gitignore` block, empty `.claude/`), validates host prereqs, then `exec`s an interactive Claude Code session seeded with the `/new-project` command body. Inside that session, Claude:

1. Asks one content question: what to build (default: a mini Claude Agent SDK + FastAPI coding agent with web UI)
2. Prints an orchestrator preamble so you learn the model before watching it execute
3. Runs the **Standard-tier seed pipeline** with phase gates and per-subagent sub-gates (researcher → systems-architect → implementation-planner → implementer + test-engineer → verifier) so you preview each agent's outputs before they appear
4. Runs `/init` once the codebase exists (so `CLAUDE.md` describes reality), then idempotently appends three Praxion blocks: Agent Pipeline, Compaction Guidance, Behavioral Contract
5. Generates a per-run `onboarding_for_mushi_busy_ppl.md` trail map with file inventory + lesson ladder
6. Recommends `/onboard-project` for the remaining surfaces (git hooks, merge drivers, `.ai-state/` skeleton, `.claude/settings.json` toggles), then `/co` to commit

Smooth-integration contract: the seed pipeline writes `.ai-state/ARCHITECTURE.md` + `docs/architecture.md` as part of the systems-architect's full delegation checklist, so `/onboard-project`'s Phase 8 (Architecture Baseline) becomes a no-op when chained — no double-architect overhead.

Optional `PRAXION_NEW_PROJECT_EDITOR=cursor|code|claude-desktop|none` picks the editor surface the scaffold opens in so you can watch `.ai-work/` and `.ai-state/` populate as the pipeline runs.

See [Greenfield Project Onboarding](docs/greenfield-onboarding.md) for the full transcript, troubleshooting, and design rationale.



**Deep dive:** `/onboard-project` **(existing project)**

Phased, idempotent retrofit for a repo that already has code. Each phase pauses with an `AskUserQuestion` gate that explains *what* and *why* before any write occurs. **Run all rest** (one-way) skips remaining gates.


| Phase | Action                                                                                                                                                                                 |
| ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0     | Pre-flight diagnostic (writes nothing — prints stack detection + plugin scope + prior-onboarding signals)                                                                              |
| 1     | Append the canonical 10-line AI-assistants block to `.gitignore`                                                                                                                       |
| 2     | Create `.ai-state/` skeleton — `decisions/drafts/`, `DECISIONS_INDEX.md`, `TECH_DEBT_LEDGER.md`, `calibration_log.md`                                                                  |
| 3     | Append `.gitattributes` entries + register Python semantic merge drivers via `git config`                                                                                              |
| 4     | Install `pre-commit` (id-citation discipline) + `post-merge` (ADR finalize + tech-debt dedupe + squash safety) hooks                                                                   |
| 5     | Multi-select `.claude/settings.json` toggles for memory MCP injection / memory gate / memory MCP / observability                                                                       |
| 6     | Append three blocks to `CLAUDE.md`: Agent Pipeline + Compaction Guidance + Behavioral Contract                                                                                         |
| 7     | Print install commands for missing companion CLIs (`chub`, `scc`, `uv`) — advisory only                                                                                                |
| 8     | **Architecture baseline (opt-in, default-yes)** — delegate to `systems-architect` in baseline-audit mode → `.ai-state/ARCHITECTURE.md` + `docs/architecture.md` (+ optional ADR draft) |
| 9     | Print summary, stage modified files (no commit)                                                                                                                                        |


Every phase has an idempotency predicate — re-runs on an already-onboarded project are no-ops. The command never auto-commits. Phase 4 is skipped if the `i-am` plugin is not installed (the hooks need its `scripts/` directory). Phase 8 is skipped if either architecture doc already exists (e.g., produced by a prior seed pipeline or onboard run).

If the directory looks like a freshly-scaffolded greenfield project (`.git/` + AI-assistants `.gitignore` + empty `.claude/` + no source tree), the command aborts with a redirect to `/new-project`.

See [Existing-Project Onboarding](docs/existing-project-onboarding.md) for the full nine-phase contract, the architecture-baseline rationale, and troubleshooting.



### Agents

Thirteen autonomous agents for complex, multi-step tasks. See `[agents/README.md](agents/README.md)` for the pipeline diagram and usage patterns.


| Agent                    | Description                                                                                                                                                                                                                                                       |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `promethean`             | Feature-level ideation from project state                                                                                                                                                                                                                         |
| `researcher`             | Codebase exploration, external docs, alternative evaluation                                                                                                                                                                                                       |
| `systems-architect`      | Trade-off analysis, system design                                                                                                                                                                                                                                 |
| `implementation-planner` | Step decomposition, execution supervision                                                                                                                                                                                                                         |
| `context-engineer`       | Context artifact auditing, optimization, ecosystem management                                                                                                                                                                                                     |
| `implementer`            | Step execution with skill-augmented coding and self-review                                                                                                                                                                                                        |
| `test-engineer`          | Complex test design, test suite refactoring, testing infrastructure                                                                                                                                                                                               |
| `verifier`               | Post-implementation review against acceptance criteria                                                                                                                                                                                                            |
| `doc-engineer`           | Documentation quality management (READMEs, catalogs, changelogs)                                                                                                                                                                                                  |
| `sentinel`               | Independent ecosystem quality auditor                                                                                                                                                                                                                             |
| `skill-genesis`          | Post-pipeline learning harvest and artifact proposal                                                                                                                                                                                                              |
| `cicd-engineer`          | CI/CD pipeline design, GitHub Actions, deployment automation                                                                                                                                                                                                      |
| `roadmap-cartographer`   | Project-level audit through a project-derived lens set (SPIRIT, DORA, SPACE, FAIR, CNCF Platform Maturity, or Custom) synthesized into a grounded `ROADMAP.md` covering strengths, weaknesses, **opportunities (forward lines of work)**, and phased improvements |


### Rules

Domain knowledge files loaded by the assistant within scope (personal = all projects, project = that project). See `[rules/README.md](rules/README.md)` for the full catalog and the rules-vs-skills decision model.

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


| Tool                | Purpose                                               |
| ------------------- | ----------------------------------------------------- |
| `remember`          | Store a curated memory with type, importance, summary |
| `search`            | Multi-term ranked search with Markdown summaries      |
| `browse_index`      | Full memory index as compact Markdown-KV              |
| `timeline`          | Chronological view of observations                    |
| `session_narrative` | Structured summary of a session                       |
| `consolidate`       | Merge, archive, or update entries atomically          |


**Configuration** (per project, in `.ai-state/`):


| File                 | Purpose                        | Git        |
| -------------------- | ------------------------------ | ---------- |
| `memory.json`        | Curated memories (schema v2.0) | Committed  |
| `observations.jsonl` | Observation log (append-only)  | Committed  |
| `*.lock`             | File locks for concurrency     | Gitignored |


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


| Step | What                                                                                                                      | Interactive?           |
| ---- | ------------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| 1    | Personal config (CLAUDE.md, userPreferences.txt, settings.local.json) to `~/.claude/`                                     | No -- always installed |
| 2    | Rules to `~/.claude/rules/` (auto-loaded by Claude when relevant)                                                         | No -- always installed |
| 3    | i-am plugin via `[bit-agora](https://github.com/francisco-perez-sorrosal/bit-agora)` marketplace (scope: user or project) | Yes -- recommended     |
| 4    | Task Chronograph hooks (agent lifecycle observability)                                                                    | Yes -- recommended     |
| 5    | CLI scripts (ccwt — multi-worktree Claude sessions) to `~/.local/bin/`                                                    | No -- always installed |
| 6    | External API docs ([context-hub](https://github.com/andrewyng/context-hub) MCP — curated API docs for 600+ libraries)     | Yes -- recommended     |
| 7    | Phoenix observability daemon (persistent trace backend at `http://localhost:6006`)                                        | Yes -- recommended     |
| 7    | Claude Desktop config link to official Desktop location                                                                   | Yes -- skip by default |


When installed as a plugin, commands are namespaced: `/co` becomes `/i-am:co`. Plugin permissions for skill reference files are auto-configured at Step 3. See `[README_DEV.md](README_DEV.md#progressive-disclosure-and-satellite-files)` for how progressive disclosure works with plugin-installed skills.

**Developing on Praxion itself?** After the standard install, use `praxion-claude-dev` (placed at `~/.local/bin/` by `install.sh`) to launch a Claude Code session that loads the plugin directly from your working tree — edits to skills, commands, agents, or hooks are live, and `/reload-plugins` picks them up without restarting. See `[README_DEV.md](README_DEV.md#session-scoped-local-testing)` for the full dev workflow.

**Manual plugin install** (marketplace-only, without cloning):

```bash
claude plugin marketplace add francisco-perez-sorrosal/bit-agora
claude plugin install i-am@bit-agora --scope user
```

This installs the plugin body only (skills, commands, agents, hooks, MCP servers). The Claude Code plugin mechanism does not natively cover rules (auto-loaded globally) or CLI scripts on `$PATH`. To finish the setup, start a Claude Code session and run:

```
/praxion-complete-install
```

The command prompts for consent before each system-level change (rules in `~/.claude/rules/`, scripts in `~/.local/bin/`, context-hub MCP in `~/.claude.json`). Idempotent — safe to re-run.

**No additional download needed.** `claude plugin install` already fetched the *full Praxion repo* at the marketplace-pinned tag into `~/.claude/plugins/cache/bit-agora/i-am/<version>/`. The plugin mechanism only *loads* skills, commands, agents, hooks, and MCP servers from it, but the rest of the repo — rules, CLI scripts, `install.sh` itself — is already on disk in the cache. `/praxion-complete-install` symlinks from that cache; it does not clone, download, or require internet access.

**Refresh after plugin update.** When you run `claude plugin update i-am`, the cache directory is replaced with the new version. Existing symlinks in `~/.claude/rules/` and `~/.local/bin/` now point at the previous cache dir which no longer exists. Re-run `/praxion-complete-install` to refresh them against the new version.

**Uninstall order matters.** If you want to remove Praxion completely, run `/praxion-complete-uninstall` **first**, then `claude plugin uninstall i-am`. Doing the reverse order leaves dangling symlinks that target a deleted cache directory. If that happens, `/praxion-complete-uninstall` will still clean them up (it filters by "target begins with plugin cache path"; an absent target doesn't matter, the link itself gets removed).

### Claude Desktop (`./install.sh desktop`)

Links `claude_desktop_config.json` to the official Desktop location:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

Skills, commands, and agents are Claude Code features -- run `./install.sh code` for the full feature set.

### Cursor (`./install.sh cursor`)

Installs skills, rules, commands, and MCP into Cursor's discovery paths. Two targets:


| Target                     | Command                             | Result                                                                          |
| -------------------------- | ----------------------------------- | ------------------------------------------------------------------------------- |
| **User profile (default)** | `./install.sh cursor`               | Installs into `~/.cursor/`. Available in every Cursor project.                  |
| **Per project**            | `./install.sh cursor /path/to/repo` | Installs into `/path/to/repo/.cursor/`. Only that project sees these artifacts. |


**What gets installed:**


| What     | How                                                                                                      |
| -------- | -------------------------------------------------------------------------------------------------------- |
| Skills   | Symlinks to this repo's `skills/<name>/`                                                                 |
| Rules    | Symlinks to this repo's `rules/` (preserving directory structure)                                        |
| Commands | Exported from `commands/*.md` (frontmatter stripped to plain Markdown)                                   |
| MCP      | `mcp.json` with task-chronograph, memory, and [sub-agents-mcp](https://github.com/shinpr/sub-agents-mcp) |


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

For contributor and developer documentation, see `[README_DEV.md](README_DEV.md)`.