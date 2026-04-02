# Developer Guide

Contributor and developer documentation for Praxion. For installation and usage, see [`README.md`](README.md).

## Project Structure

```
CLAUDE.md                            # Project-level instructions (always loaded)
skills/                              # Shared skill modules (assistant-agnostic)
├── CLAUDE.md                        # Skill conventions (lazy loaded)
├── agent-crafting/
├── agent-evals/
├── agentic-sdks/
├── api-design/
├── cicd/
├── claude-ecosystem/
├── code-review/
├── command-crafting/
├── communicating-agents/
├── data-modeling/
├── doc-management/
├── external-api-docs/
├── github-star/
├── hook-crafting/
├── mcp-crafting/
├── memory/
├── performance-architecture/
├── python-development/
├── python-prj-mgmt/
├── refactoring/
├── roadmap-planning/
├── rule-crafting/
├── skill-crafting/
├── software-planning/
├── spec-driven-development/
└── stakeholder-communications/
commands/                            # Shared slash commands
├── CLAUDE.md                        # Command conventions (lazy loaded)
├── add-rules.md
├── clean-work.md
├── co.md
├── cop.md
├── create-simple-python-prj.md
├── create-worktree.md
├── manage-readme.md
├── memory.md
├── merge-worktree.md
├── onboard-project.md
├── sdd-coverage.md
└── star-repo.md
agents/                              # Shared agent definitions
├── CLAUDE.md                        # Agent conventions (lazy loaded)
├── promethean.md
├── researcher.md
├── systems-architect.md
├── implementation-planner.md
├── context-engineer.md
├── implementer.md
├── test-engineer.md
├── verifier.md
├── doc-engineer.md
├── sentinel.md
├── skill-genesis.md
└── cicd-engineer.md
rules/                               # Rules (installed to ~/.claude/rules/ or .cursor/rules/)
├── CLAUDE.md                        # Rule conventions (lazy loaded)
├── swe/
│   ├── agent-intermediate-documents.md
│   ├── coding-style.md
│   ├── adr-conventions.md
│   ├── swe-agent-coordination-protocol.md
│   └── vcs/
│       └── git-conventions.md
└── writing/
    └── readme-style.md              # Path-scoped: loads only for README files
.claude-plugin/                      # Claude Code plugin manifest
├── CLAUDE.md                        # Plugin config conventions (lazy loaded)
├── plugin.json
├── PLUGIN_SCHEMA_NOTES.md
└── hooks/                           # Plugin hook scripts
    ├── hooks.json
    ├── send_event.py
    ├── precompact_state.py
    ├── format_python.py
    ├── adr_reminder.py
    ├── check_code_quality.py
    └── commit_gate.sh
claude/config/                       # Claude personal config (symlinked to ~/.claude/)
├── README.md
├── CLAUDE.md
├── claude_desktop_config.json
├── userPreferences.txt
├── config_items.txt
├── stale_symlinks.txt
└── settings.local.json              # gitignored
cursor/config/                       # Cursor installer config
├── mcp.json.template
├── expected-mcp-servers.txt
├── export-cursor-commands.py
├── export-cursor-rules.py
└── README.md
scripts/                             # Utility scripts
├── CLAUDE.md                        # Script conventions (lazy loaded)
├── ccwt                             # Multi-worktree Claude session launcher
├── chronograph-ctl                  # Task Chronograph dev helper (start/stop/status)
├── phoenix-ctl                      # Phoenix observability daemon manager
└── regenerate_adr_index.py          # Regenerate DECISIONS_INDEX.md from ADR files
docs/                                # Cross-cutting documentation
├── concepts.md
├── cursor-compat.md
├── decision-tracking.md              # Content updated to describe ADR system
├── external-api-docs.md
├── getting-started.md
├── observability.md
└── spec-driven-development.md
task-chronograph-mcp/                # Pipeline observability MCP server
├── CLAUDE.md                        # MCP server dev conventions (lazy loaded)
└── ...
memory-mcp/                          # Persistent memory MCP server
├── CLAUDE.md                        # MCP server dev conventions (lazy loaded)
└── ...
.ai-state/                           # Persistent project intelligence (committed to git)
├── decisions/                       # Architecture Decision Records (ADR files)
│   ├── 001-skill-wrapper-over-mcp-server.md
│   ├── ...
│   └── DECISIONS_INDEX.md           # Auto-generated summary table
├── SENTINEL_REPORT_*.md
├── SENTINEL_LOG.md
└── ...
install.sh                           # Installer router
install_claude.sh                    # Claude Code / Desktop installer
install_cursor.sh                    # Cursor installer
Makefile                             # Development targets
```

## Working on this Repo

- When adding or modifying skills, load the `skill-crafting` skill for spec compliance
- When adding or modifying commands, load the `command-crafting` skill
- When adding or modifying agents, load the `agent-crafting` skill
- When adding or modifying rules, load the `rule-crafting` skill
- Follow commit conventions in `rules/` (auto-loaded by Claude when relevant)
- **Never modify `~/.claude/plugins/cache/`** -- it contains installed copies that get overwritten on reinstall; always edit source files in this repo
- **Token budget**: Always-loaded content (CLAUDE.md files + rules) must stay under 8,500 tokens (~29,750 chars). Before adding a new rule, verify the budget. Prefer skills with reference files for procedural content; reserve rules for declarative domain knowledge

## Design Intent

- **Assistant-agnostic shared assets**: `skills/`, `commands/`, `agents/` live at the repo root, reusable across any AI assistant
- **Assistant-specific config**: Personal settings live in config directories (`claude/config/` for Claude, `cursor/config/` for Cursor)
- **Plugin distribution**: Skills, commands, and agents are installed via Claude Code's plugin system (`.claude-plugin/plugin.json`)
- **Symlink for personal config**: `install_claude.sh` symlinks Claude config to `~/.claude/`; `install_cursor.sh` symlinks skills and rules into `.cursor/` or `~/.cursor/`
- **Progressive disclosure**: Skills load metadata at startup, full content on activation, reference files on demand
- **CLAUDE.md stays lean**: Skills, commands, agents, and rules are auto-discovered by Claude via filesystem scanning -- listing them in `CLAUDE.md` wastes always-loaded tokens and creates a sync burden. `README.md` and per-directory READMEs serve as the human-facing catalogs
- **Nested CLAUDE.md for progressive disclosure**: Each artifact directory has its own `CLAUDE.md` with conventions specific to that directory. These are lazily loaded -- Claude reads them only when it accesses files in that directory, adding zero cost to sessions that don't touch the directory

## Progressive Disclosure and Satellite Files

Skills, agents, and rules each have a distinct execution model that determines how they load, resolve file references, and interact with the sandbox. Understanding these differences is essential for deciding where to place content and how to structure large instruction sets.

### Nested CLAUDE.md Files

Claude Code discovers CLAUDE.md files through a bidirectional directory walk:
- **Upward (eager)**: At session start, walks from cwd to the filesystem root, loading every CLAUDE.md found
- **Downward (lazy)**: Subdirectory CLAUDE.md files load only when Claude reads files in that directory

This project uses nested CLAUDE.md files as a progressive disclosure layer between the always-loaded root `CLAUDE.md` and the on-demand crafting skills. Each artifact directory (`agents/`, `skills/`, `commands/`, `rules/`, etc.) has its own `CLAUDE.md` with:
- Directory-specific conventions (structure, naming, registration)
- Pointers to the relevant crafting skill for detailed guidance
- Gotchas and constraints unique to that artifact type

These files are Claude-facing (loaded into context on demand). The existing `README.md` files in each directory remain the human-facing catalogs. Both complement each other — READMEs tell humans what exists, CLAUDE.md files tell Claude how to work there.

CLAUDE.md files survive compaction (re-injected after `/compact`), so once loaded they persist for the session.

### Execution Models

| Artifact | Loading | Path Resolution | Satellite Files Cross-Project? | Strategy |
|----------|---------|-----------------|-------------------------------|----------|
| **Skills** | Lazy — metadata at startup, full SKILL.md on activation, reference files on demand | Base path injected on activation; LLM resolves relative refs to absolute paths | Yes | Use `references/` subdirectories freely |
| **Agents** | Eager — full `.md` definition loaded into the sub-agent's CLAUDE.md at spawn | CWD is the project root; `Read` resolves against CWD, not plugin cache | No | Keep definitions self-contained |
| **Rules** | Eager within scope — all personal rules load every session; project rules load in that project; `paths`-filtered rules load only for matching files | No path context; raw markdown appended to system prompt | No | Keep rules self-contained and concise (share token budget with CLAUDE.md) |

**Skills** are the only artifact type that supports progressive disclosure across projects. When Claude Code activates a skill, it provides the skill's absolute directory path (the "base path"), allowing the LLM to resolve relative references to satellite files regardless of where the skill is installed — project directory, personal `~/.claude/skills/`, or plugin cache.

**Agents** receive their entire definition as part of the sub-agent's system prompt at spawn time. The sub-agent's working directory is the project root, not the plugin cache. Any `Read` calls resolve against the project, so references to sibling files in the plugin cache fail silently. Keep agent definitions self-contained. If content is too large, compress it (tables over prose, remove redundancy) or split into independent agent files by domain.

**Rules** are injected as inline text — Claude never sees a file path or directory context for them. The `install.sh` installer symlinks rule `.md` files to `~/.claude/rules/` but explicitly skips `references/` subdirectories. Reference files never reach the rules directory. Rules that need supporting material can point to skill reference files (the skill's base path makes them resolvable), but the rule itself must be self-contained.

### Security and Permissions

All artifact types execute within Claude Code's shared sandbox. The permission model applies uniformly:

- **Read access** is the default. Skills, agents, and rules can all trigger `Read` tool calls against project files without approval.
- **Write access** requires user approval (or `acceptEdits` permission mode for agents). The `allowed-tools` field in skill frontmatter pre-approves specific tools but does not bypass filesystem path restrictions.
- **Plugin cache reads** require explicit directory whitelisting. Skill reference files installed via the plugin system live in `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/...` — outside the project directory. Without a wildcard allowlist, Claude prompts for permission on every reference file read, and plugin version changes invalidate prior approvals.

Add the wildcard allowlist to grant read access across plugin updates:

```json
// In ~/.claude/settings.json or ~/.claude/settings.local.json
{
  "permissions": {
    "additionalDirectories": ["~/.claude/plugins/**"]
  }
}
```

The installer (`install.sh`) configures this automatically during plugin installation.

### Structuring Large Instruction Sets

The token budget constraint (8,500 tokens for always-loaded content) drives a clear allocation strategy:

| Content Type | Where to Put It | Why |
|---|---|---|
| Global directives, short conventions | Root `CLAUDE.md` | Always loaded — keep lean |
| Directory-specific conventions, registration gotchas | Subdirectory `CLAUDE.md` | Lazy loaded — zero cost until Claude enters the directory |
| Domain knowledge, constraints, reference material | Rules | Eagerly loaded within scope — keep concise (shares token budget with root CLAUDE.md) |
| Multi-step workflows, procedures with code | Skills | Lazy-loaded with progressive disclosure — satellite files absorb depth |
| Sub-agent behavior definitions | Agents | Loaded at spawn — self-contained by necessity |

Best practices for keeping the core small:

1. **Favor skills for complex workflows.** A skill's three-tier loading (metadata -> instructions -> references) keeps startup cost at ~100 tokens per skill while allowing thousands of tokens on demand.
2. **Use reference files for depth, not breadth.** Each reference file should cover one coherent topic. Keep references one level deep from `SKILL.md` — avoid nested chains.
3. **Reserve rules for declarative knowledge.** Rules state what should be true, not how to do it. If you find yourself writing steps, it belongs in a skill.
4. **Compress agent definitions aggressively.** Tables, bullet lists, and imperative statements over prose. Agents cannot offload to satellite files, so every token counts.
5. **Do not duplicate across layers.** If a rule covers commit conventions, the commit skill should not repeat them — Claude loads both when relevant.

### Decision Framework: Rules vs Skills vs Agent Instructions

| Question | If Yes | Use |
|----------|--------|-----|
| Must Claude always know this, every session? | Yes | `CLAUDE.md` |
| Is this domain knowledge Claude should apply contextually? | Yes | Rule |
| Is this a multi-step workflow or procedure? | Yes | Skill |
| Does this define a sub-agent's role and behavior? | Yes | Agent definition |
| Does it need satellite files for depth? | Yes | Skill (only artifact type that supports them cross-project) |

See [`rules/README.md`](rules/README.md#rules-vs-skills-vs-claudemd) for the detailed comparison table with concrete examples.

### Debugging

Run `/context` inside Claude Code to inspect which skills and reference files are loaded in the current context window. Use this to verify progressive disclosure is working correctly after installation.

### Sources

- [Extend Claude with skills](https://code.claude.com/docs/en/skills) — official docs; see "Add supporting files" for the satellite file pattern
- [Inside Claude Code Skills](https://mikhail.io/2025/10/claude-code-skills/) — Mikhail Shilkov's reverse-engineering showing base path injection on skill activation
- [Claude Code memory](https://code.claude.com/docs/en/memory#rules) — official docs; rules are loaded inline with no path context
- [Reddit: Claude Code plugin permissions](https://www.reddit.com/r/ClaudeAI/) — plugin cache permission issues with `additionalDirectories` workaround

## How Rules Interact with Commands

Rules do **not** need to be referenced from slash commands. When `/co` triggers a commit workflow, Claude automatically loads relevant rules from `~/.claude/rules/` based on the task context -- no explicit binding required.

Commands can use **semantic hints** to help Claude disambiguate when multiple overlapping rules exist:

```
"Commit following our conventional commits standard."
```

Never reference rule filenames directly in commands -- filenames have no special meaning to the command system.

See [`rules/README.md`](rules/README.md) for the full rule specification, writing guidelines, and the rules-vs-skills-vs-CLAUDE.md decision model.

## Development Setup

For user-facing installation instructions, see [`README.md`](README.md#installation).

### Local testing (recommended for development)

Load the plugin directly from the cloned repo for a single session. Changes to skills, commands, and agents are reflected immediately — no reinstall needed.

```bash
claude --plugin-dir /path/to/Praxion
```

Personal config and rules are **not** loaded. Use `./install.sh` if you also need those.

### Updating the plugin cache

After modifying the plugin manifest or adding new components, update the installed copy:

```bash
./install.sh                   # Re-run installer, choose "Install plugin" at Step 3
claude plugin install i-am@bit-agora --scope user   # Or install directly
```

### Verifying changes

- `./install.sh --check` — confirms all symlinks, plugin, hooks, and permissions are healthy
- `/context` inside Claude Code — shows which skills and reference files are loaded in the current context window
- `claude plugin list` — verifies the plugin is registered and its version

## Plugin Development

The plugin manifest lives in `.claude-plugin/plugin.json`. Key constraints:

- See `.claude-plugin/PLUGIN_SCHEMA_NOTES.md` for validator constraints
- The plugin is distributed via the [`bit-agora`](https://github.com/francisco-perez-sorrosal/bit-agora) GitHub marketplace
- When installed, commands are namespaced as `/i-am:<name>`

## References

- [Claude Code Plugins](https://code.claude.com/docs/en/plugins)
- [Claude Code Sub-agents](https://code.claude.com/docs/en/sub-agents)
- [Agent Skills Best Practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices.md)
- [bendrucker/claude config](https://github.com/bendrucker/claude/blob/main/.claude/)
- [citypaul/.dotfiles claude config](https://github.com/citypaul/.dotfiles/blob/main/claude)
