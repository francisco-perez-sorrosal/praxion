# ai-assistants

Configuration repository for AI coding assistants. Centralizes settings, skills, commands, agents, and rules in one **tool-agnostic** repo. Compatible with **Claude Desktop**, **Claude Code**, and **Cursor**; each tool uses its own install path (see Installation below).

## Installation

The main entry point is `install.sh`, which routes to `install_claude.sh` (Claude Code/Desktop) or `install_cursor.sh` (Cursor). Run the interactive installer — it walks through each choice, defaulting to the recommended option at each step.

```bash
./install.sh                    # Claude Code (default)
./install.sh desktop            # Claude Desktop
./install.sh cursor             # Cursor → user profile ~/.cursor/
./install.sh cursor /path/repo  # Cursor → per-project at /path/repo/.cursor/
./install.sh cursor --check     # Verify Cursor install (user profile)
./install.sh cursor /path --check  # Verify Cursor install (per-project)
./install.sh code --dry-run     # Dry-run: show what would be installed (Claude Code)
./install.sh cursor --dry-run   # Dry-run: show what would be installed (Cursor)
./install.sh --check            # Verify installation health (code or desktop)
./install.sh --uninstall        # Remove installation (code or desktop)
```

For **Claude Code vs Cursor** differences (formats, discovery paths), see [docs/cursor-compat.md](docs/cursor-compat.md).

**Config directories** — Installer resources live in tool-specific dirs so scripts stay clean and you can edit config without touching code:
- **claude/config/** — Personal config files (CLAUDE.md, userPreferences.txt, claude_desktop_config.json) and lists (config_items.txt, stale_symlinks.txt). Install links these into `~/.claude/`. See [claude/config/README.md](claude/config/README.md).
- **cursor/config/** — MCP template and expected servers: mcp.json.template (placeholders `{{MCP_ROOT}}`, `{{AGENTS_DIR_ABS}}`, `{{MEMORY_FILE}}`) and expected-mcp-servers.txt for `--check`. See [cursor/config/README.md](cursor/config/README.md).

### Claude Code (`./install.sh` or `./install.sh code`)

| Step | What | Interactive? |
|------|------|-------------|
| 1 | Personal config (CLAUDE.md, userPreferences.txt, settings.local.json) → `~/.claude/` | No — always installed |
| 2 | Rules → `~/.claude/rules/` (auto-loaded by Claude when relevant) | No — always installed |
| 3 | i-am plugin via [`bit-agora`](https://github.com/francisco-perez-sorrosal/bit-agora) marketplace (scope: user or project) | Yes — recommended |
| 4 | Task Chronograph hooks (agent lifecycle observability) | Yes — recommended |
| 5 | Claude Desktop config link to official Desktop location | Yes — skip by default |

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

Skills, commands, and agents are Claude Code features — run `./install.sh code` for the full feature set.

### Cursor (`./install.sh cursor`)

Installs skills, rules, commands, and MCP into Cursor’s discovery paths. Run from **this repo** (ai-assistants) root.

**Two targets:**

| Target | Command | Result |
|--------|---------|--------|
| **User profile (default)** | `./install.sh cursor` or `make install-cursor` | Installs into `~/.cursor/`. Skills, rules, commands, and MCP are available in **every** Cursor project. |
| **Per project** | `./install.sh cursor /path/to/your/repo` | Installs into `/path/to/your/repo/.cursor/`. Only that project sees these artifacts when opened in Cursor. The path must be an existing directory. |

Direct script usage (same repo root):

```bash
./install_claude.sh code                  # Claude Code (bypass router)
./install_claude.sh desktop --check       # Claude Desktop health check
./install_cursor.sh              # user profile ~/.cursor/
./install_cursor.sh /path/to/repo # that repo’s .cursor/
./install_cursor.sh --check       # Cursor health check
./install_cursor.sh --dry-run     # Cursor dry-run (or use install.sh cursor --dry-run)
```
All three install paths support the same flags: `--check`, `--dry-run`, `--uninstall`.

**What gets installed**

| What | How |
|------|-----|
| Skills | Symlinks to this repo’s `skills/<name>/`. |
| Rules | Symlinks to this repo's `rules/` (preserving directory structure). |
| Commands | Exported from `commands/*.md` (frontmatter stripped to plain Markdown). |
| MCP | `mcp.json` with task-chronograph, memory, and **sub-agents** ([sub-agents-mcp](https://github.com/shinpr/sub-agents-mcp)); server paths always point at **this repo** (override with `CURSOR_REPO_ROOT`). |

MCP: task-chronograph and memory require `uv`; sub-agents requires **Node/npx**. Re-run the install after cloning this repo or when you want to refresh. For **per-project** installs, the target repo’s `.cursor/` is usually gitignored so each clone runs the installer; for **user profile**, `~/.cursor/` is persistent.

**Agents prerequisite**: sub-agents-mcp uses `cursor-agent` as its backend. Run `cursor-agent login` to authenticate before using agents in Cursor.

**Agents** — Installed with the rest: one script configures [sub-agents-mcp](https://github.com/shinpr/sub-agents-mcp) so Cursor uses this repo’s `agents/*.md`. Run `./install.sh cursor` (or `make install-cursor`); agents appear in Cursor once the MCP server is running. Requires Node/npx.

**Dry-run** — See what would be installed without writing: `./install.sh code --dry-run`, `./install.sh cursor --dry-run`, or `make dry-run-cursor` (and `make dry-run` for Claude Code).

**Verification** — Run a health check:

```bash
./install.sh cursor --check           # user profile ~/.cursor/
./install.sh cursor /path/to/repo --check   # per-project
```

The check verifies `skills/`, `rules/`, `commands/`, and `mcp.json` (with task-chronograph, memory, sub-agents). In Cursor, confirm **Settings → Tools & MCP** lists the MCP servers.

### User preferences (Claude Desktop / iOS)

On devices without filesystem access (e.g., Claude iOS app) or when using Claude Desktop without the CLI, paste the following into the **User Preferences** field in Claude's settings:

```text
Read the user preferences from https://raw.githubusercontent.com/francisco-perez-sorrosal/ai-assistants-cfg/main/claude/config/userPreferences.txt and follow them before any other interaction
```

This tells Claude to fetch and apply the adaptive precision mode instructions at the start of each conversation.

## Getting Started

For a walkthrough of developing a small application using the agent pipeline — from ideation through implementation and verification — see [docs/getting-started.md](docs/getting-started.md).

## Spec-Driven Development

For medium and large features, the pipeline activates spec-driven development -- behavioral specifications with requirement IDs threaded through architecture, planning, testing, and verification. Small tasks skip specs entirely; the pipeline scales proportionally.

See [docs/spec-driven-development.md](docs/spec-driven-development.md) for the spec format, traceability flow, and comparison with spec-only tools.

## Skills

Reusable knowledge modules loaded automatically based on context. See [`skills/README.md`](skills/README.md) for the full catalog.

| Category | Skills |
|----------|--------|
| AI Assistant Crafting | skill-crafting, agent-crafting, command-crafting, mcp-crafting, rule-crafting |
| Platform Knowledge | claude-ecosystem, agentic-sdks, communicating-agents |
| Documentation | doc-management |
| Software Development | python-development, python-prj-mgmt, refactoring, code-review, software-planning, spec-driven-development, cicd |
| Project | memory, github-star |

## Commands

Slash commands invoked with `/<name>`. In Claude Code (plugin) use `/i-am:<name>`; in Cursor they are exported to `.cursor/commands/`. See [`commands/README.md`](commands/README.md) for details.

| Command | Description |
|---------|-------------|
| `/add-rules [names... \| all]` | Copy rules into the current project for customization |
| `/co` | Create a commit for staged (or all) changes |
| `/cop` | Create a commit and push to remote |
| `/create-worktree [branch]` | Create a new git worktree in `.trees/` |
| `/merge-worktree [branch]` | Merge a worktree branch back into current branch |
| `/create-simple-python-prj [name] [desc] [pkg-mgr] [dir]` | Scaffold a Python project (defaults: pixi, `~/dev`) |
| `/manage-readme [file-paths...]` | Create or refine README.md files with precision-first style |
| `/clean-work` | Clean the `.ai-work/` directory after pipeline completion |
| `/memory` | Manage persistent memory (user prefs, learnings, conventions) |
| `/onboard-project` | Onboard the current project to work with the ai-assistants ecosystem |
| `/star-repo` | Star the ai-assistants-cfg repo on GitHub |

See [`commands/README.md`](commands/README.md) for the full list and authoring guidance.

## Agents

Twelve autonomous agents for complex, multi-step tasks; each runs in its own context with skills and scoped tools. Available in Claude Code (plugin) and Cursor (via sub-agents-mcp). See [`agents/README.md`](agents/README.md) for the pipeline diagram and usage patterns.

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

## Rules

Domain knowledge files loaded by the assistant within scope (personal = all projects, project = that project). Compatible with Claude and Cursor; see [`rules/README.md`](rules/README.md) for the full catalog, writing guidelines, and the rules-vs-skills decision model.

---

For contributor and developer documentation, see [`README_DEV.md`](README_DEV.md).
