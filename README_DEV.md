# Developer Guide

Contributor and developer documentation for Praxion. For installation and usage, see [`README.md`](README.md).

## Project Structure

```
CLAUDE.md                            # Project-level instructions (always loaded by Claude)
AGENTS.md                            # Thin adapter for AGENTS.md-aware agents
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
├── context-security-review/
├── data-modeling/
├── deployment/
├── doc-management/
├── external-api-docs/
├── hook-crafting/
├── id-decontamination/
├── llm-prompt-engineering/
├── mcp-crafting/
├── memory/
├── observability/
├── performance-architecture/
├── project-exploration/
├── python-development/
├── python-prj-mgmt/
├── refactoring/
├── roadmap-planning/
├── roadmap-synthesis/
├── rule-crafting/
├── skill-crafting/
├── software-planning/
├── spec-driven-development/
├── stakeholder-communications/
├── testing-strategy/
├── upstream-stewardship/
└── versioning/
commands/                            # Shared slash commands
├── CLAUDE.md                        # Command conventions (lazy loaded)
├── add-rules.md
├── clean-auto-memory.md
├── clean-work.md
├── co.md
├── cop.md
├── create-simple-python-prj.md
├── create-worktree.md
├── decontaminate-ids.md
├── eval.md
├── explore-project.md
├── full-security-scan.md
├── manage-readme.md
├── cajalogic.md
├── merge-worktree.md
├── onboard-project.md
├── refresh-skill.md
├── release.md
├── report-upstream.md
├── review-pr.md
├── roadmap.md
├── save-changes.md
├── sdd-coverage.md
├── star-repo.md
└── test.md
agents/                              # Shared agent definitions
├── CLAUDE.md                        # Agent conventions (lazy loaded)
├── promethean.md
├── researcher.md
├── systems-architect.md
├── interface-designer.md
├── implementation-planner.md
├── context-engineer.md
├── implementer.md
├── test-engineer.md
├── verifier.md
├── architect-validator.md
├── doc-engineer.md
├── sentinel.md
├── skill-genesis.md
├── cicd-engineer.md
└── roadmap-cartographer.md
rules/                               # Rules (installed to ~/.claude/rules/ or .cursor/rules/)
├── CLAUDE.md                        # Rule conventions (lazy loaded)
├── swe/
│   ├── adr-conventions.md
│   ├── agent-intermediate-documents.md
│   ├── coding-style.md
│   ├── memory-protocol.md
│   ├── swe-agent-coordination-protocol.md
│   ├── testing-conventions.md
│   └── vcs/
│       ├── git-conventions.md
│       └── pr-conventions.md       # Path-scoped: loads for PR-adjacent surfaces
└── writing/
    ├── diagram-conventions.md       # Path-scoped: loads only for diagram work
    └── readme-style.md              # Path-scoped: loads only for README files
hooks/                               # Hook scripts (auto-discovered by Claude Code)
├── hooks.json                       # Hook manifest (single source of truth)
├── _hook_utils.py
├── capture_memory.py
├── capture_session.py
├── check_code_quality.py
├── cleanup_gate.sh
├── commit_gate.sh
├── detect_duplication.py
├── format_python.py
├── inject_memory.py
├── memory_gate.py
├── precompact_state.py
├── promote_learnings.py
├── remind_adr.py
├── remind_memory.py
├── send_event.py
├── test_cleanup_gate.py
├── test_hook_utils.py
├── test_send_event.py
├── test_worktree_guard.py
├── validate_memory.py
└── worktree_guard.py
.claude-plugin/                      # Claude Code plugin manifest
├── CLAUDE.md                        # Plugin config conventions (lazy loaded)
├── plugin.json
└── PLUGIN_SCHEMA_NOTES.md
claude/config/                       # Claude personal config (symlinked to ~/.claude/)
├── README.md
├── CLAUDE.md
├── claude_desktop_config.json
├── userPreferences.txt
├── config_items.txt
├── stale_symlinks.txt
└── settings.local.json              # gitignored
codex/config/                        # Codex adapter sources, generators, and reference guidance
├── README.md
├── AGENTS.md.tmpl
├── userPreferences.txt
└── ...
cursor/config/                       # Cursor installer config
├── mcp.json.template
├── expected-mcp-servers.txt
├── export-cursor-commands.py
├── export-cursor-rules.py
└── README.md
scripts/                             # Utility scripts
├── CLAUDE.md                        # Script conventions (lazy loaded)
├── ccwt                             # Multi-worktree Claude session launcher
├── check_squash_safety.py           # Post-merge diagnostic: warn on .ai-state/ erasure from squash
├── chronograph-ctl                  # Task Chronograph dev helper (start/stop/status)
├── finalize_adrs.py                 # Promote draft ADRs to NNN at merge-to-main
├── git-finalize-hook.sh             # Multiplexed lifecycle dispatcher (post-merge/post-commit/post-checkout); post-merge runs reconcile -> finalize -> squash-safety
├── finalize_chain.sh                # Shared library sourced by git-finalize-hook.sh — path resolution, state-driven gates, three entry points
├── merge_driver_memory.py           # Custom merge driver for memory.json
├── merge_driver_observations.py     # Custom merge driver for observations.jsonl
├── migrate_worktree_home.sh         # Print migration commands for legacy .trees/ worktrees
├── phoenix-ctl                      # Phoenix observability daemon manager
├── reconcile_ai_state.py            # Reconcile .ai-state/ after worktree merges
├── regenerate_adr_index.py          # Regenerate DECISIONS_INDEX.md from ADR files
├── test_check_squash_safety.py      # Tests for squash-safety script
├── test_finalize_adrs.py            # Tests for finalize script
└── test_reconcile_ai_state.py       # Tests for reconcile script
docs/                                # Cross-cutting documentation
├── concepts.md
├── cursor-compat.md
├── decision-tracking.md              # Content updated to describe ADR system
├── external-api-docs.md
├── getting-started.md
├── memory-architecture.md
├── observability.md
└── spec-driven-development.md
task-chronograph-mcp/                # Pipeline observability MCP server
├── CLAUDE.md                        # MCP server dev conventions (lazy loaded)
└── ...
memory-mcp/                          # Persistent memory MCP server
├── CLAUDE.md                        # MCP server dev conventions (lazy loaded)
└── ...
eval/                                # Out-of-band quality evals (praxion-evals CLI)
├── pyproject.toml                   # Standalone uv project — not installed with plugin
├── src/praxion_evals/               # behavioral, harness, judges, tiers
└── tests/
.ai-state/                           # Persistent project intelligence (committed to git)
├── decisions/                       # Architecture Decision Records (ADR files)
│   ├── 001-skill-wrapper-over-mcp-server.md
│   ├── ...
│   └── DECISIONS_INDEX.md           # Auto-generated summary table
├── sentinel_reports/                # Timestamped audit reports + log
│   ├── SENTINEL_REPORT_*.md
│   └── SENTINEL_LOG.md
├── metrics_reports/                 # /project-metrics report triples + log
│   ├── METRICS_REPORT_*.{md,json}
│   └── METRICS_LOG.md
├── idea_ledgers/                    # Promethean ideation history
│   └── IDEA_LEDGER_*.md
└── ...
install.sh                           # Installer router
install_claude.sh                    # Claude Code / Desktop installer
install_cursor.sh                    # Cursor installer
install_codex.sh                     # Codex adapter installer (project-local)
Makefile                             # Development targets
```

## Per-Project Hook Opt-Outs

Seven env-var flags let a downstream project disable Praxion hooks that cost tokens or block behavior. Absence of the flag preserves default behavior — set to `1`, `true`, or `yes` in the target project's `.claude/settings.json` `env` block for Claude or `.codex/praxion/settings.json` `env` block for Codex.

| Flag | What it disables | When to use |
|------|------------------|-------------|
| `PRAXION_DISABLE_MEMORY_INJECTION` | `inject_memory.py` at SessionStart and SubagentStart | The only hook with meaningful prompt-token cost (~2k tokens per agent spawn). Set when the project has no curated memory worth injecting. |
| `PRAXION_DISABLE_MEMORY_GATE` | `memory_gate.py` (Stop) and `validate_memory.py` (SubagentStop) | Silences the "you must call remember()" blocker. No prompt-token impact — disables enforcement, not injection. |
| `PRAXION_DISABLE_OBSERVABILITY` | `send_event.py`, `capture_session.py`, `capture_memory.py` | Disables chronograph telemetry and `observations.jsonl` writes. Zero prompt-token impact; saves process-spawn time and local I/O. |
| `PRAXION_DISABLE_MEMORY_MCP` | Unified kill switch: implies `DISABLE_MEMORY_INJECTION` + `DISABLE_MEMORY_GATE`, and additionally injects a small "memory MCP disabled" notice so the assistant stops voluntary `remember()`/`recall()` calls driven by the `memory-protocol` rule. | Set when the project wants the memory MCP server's tools to remain nominally callable but behaviorally inert — e.g., during experiments, when memory.json has drifted schema, or when you simply do not want memory persistence for this project. |
| `PRAXION_DISABLE_PROCESS_INJECT` | `inject_process_framing.py` (UserPromptSubmit) | Disables the compact process-framing reminder that reinforces the tier selector and behavioral contract. No prompt-token impact; use when you want Codex or Claude to stay silent on that reminder. |
| `PRAXION_DISABLE_WORKTREE_GUARD` | `worktree_guard.py` (PreToolUse on `Write\|Edit\|NotebookEdit`) | Disables the cross-worktree write guard that blocks absolute paths resolving outside the session worktree into a sibling git tree. No prompt-token impact. Set when a workflow legitimately needs to edit the main repo or a sibling worktree from inside a linked worktree (rare; fail-open semantics mean the guard never wedges work — this flag silences the explicit block). |
| `PRAXION_DISABLE_RULE_INJECTION` | `inject_rules.py` (SessionStart) | Escape hatch for the per-project rules disable mechanism. Skips the hook entirely, so the 3 hook-deliver rules (`memory-protocol`, `agent-model-routing`, `vcs/git-conventions`) are absent from `additionalContext` AND no `claudeMdExcludes` reconciliation runs — existing entries from prior sessions remain in effect via Claude Code's native runtime, so previously-disabled symlinked rules stay disabled. Use when debugging the hook, or when a project wants hook-deliver rules out of all sessions without authoring a per-project disable list. See `docs/rules-taxonomy.md`. |

**Why a fourth flag?** The first three disable hook *side-effects* but cannot stop the assistant from voluntarily calling `remember()` because the always-loaded `rules/swe/memory-protocol.md` rule instructs it to. The MCP flag adds the missing piece: an assistant-observable signal injected at SessionStart/SubagentStart that triggers the rule's skip-all-operations exit clause. Without the notice, the rule's exit clause never fires.

Example `.claude/settings.json` for a project that wants Praxion skills/agents but **no memory** at all:

```json
{ "env": { "PRAXION_DISABLE_MEMORY_MCP": "1" } }
```

Example for finer-grained control — keep the gate blocker silent but continue injecting memory context:

```json
{ "env": { "PRAXION_DISABLE_MEMORY_GATE": "1" } }
```

Codex uses the same `env` shape in `.codex/praxion/settings.json`, so the same flags work there without touching `.claude/settings.json`.

The flags are read by each hook via `is_disabled()` in `hooks/_hook_utils.py`. To disable every Praxion hook at once, disable the plugin itself in `enabledPlugins`.

## Working on this Repo

- When adding or modifying skills, load the `skill-crafting` skill for spec compliance
- When adding or modifying commands, load the `command-crafting` skill
- When adding or modifying agents, load the `agent-crafting` skill
- When adding or modifying rules, load the `rule-crafting` skill
- Follow commit conventions in `rules/` (auto-loaded by Claude when relevant); for PR workflow (branch naming, `.ai-state/` safety, merge policy), see [`rules/swe/vcs/pr-conventions.md`](rules/swe/vcs/pr-conventions.md) — path-scoped, loads only on PR-adjacent surfaces
- Worktrees live under `.claude/worktrees/<name>/`. Pipeline worktrees use Claude Code's `EnterWorktree`; scratch worktrees use `/create-worktree` (both share the same home). Legacy `.trees/<name>/` remains readable during the deprecation window — run `scripts/migrate_worktree_home.sh` for per-worktree `git worktree move` commands
- **Never modify `~/.claude/plugins/cache/`** -- it contains installed copies that get overwritten on reinstall; always edit source files in this repo
- **Token budget**: Always-loaded content (CLAUDE.md files + rules) must stay under 25,000 tokens (~87,500 chars) as a failure-mode guardrail — the principle is that every always-loaded token must earn its attention share (applied in >30% of sessions, or unconditionally relevant). Before adding a new rule, apply the attention-relevance test first, then verify the budget. Prefer skills with reference files for procedural content; reserve rules for declarative domain knowledge. Rationale: `.ai-state/decisions/050-always-loaded-budget-revision.md`

## Design Intent

- **Assistant-agnostic shared assets**: `skills/`, `commands/`, `agents/`, and `rules/` live at the repo root, reusable across any AI assistant
- **AGENTS.md compatibility shim**: root `AGENTS.md` points AGENTS.md-aware tools to Praxion's canonical artifacts without copying their bodies
- **Assistant-specific config**: Personal settings live in config directories (`claude/config/` for Claude, `codex/config/` for Codex, `cursor/config/` for Cursor, future tool directories as needed)
- **Plugin distribution**: Skills, commands, and agents are installed via Claude Code's plugin system (`.claude-plugin/plugin.json`)
- **Personal config ownership**: `install_claude.sh` symlinks Claude config to `~/.claude/`; `install_codex.sh` installs project-local adapter surfaces under the target repo's `.codex/` and `.agents/`; shared `~/.codex/` user surfaces remain user-owned; `install_cursor.sh` symlinks skills and rules into `.cursor/` or `~/.cursor/`
- **Progressive disclosure**: Skills load metadata at startup, full content on activation, reference files on demand
- **CLAUDE.md stays lean**: Skills, commands, agents, and rules are auto-discovered by Claude via filesystem scanning -- listing them in `CLAUDE.md` wastes always-loaded tokens and creates a sync burden. `README.md` and per-directory READMEs serve as the human-facing catalogs
- **Nested CLAUDE.md for progressive disclosure**: Each artifact directory has its own `CLAUDE.md` with conventions specific to that directory. These are lazily loaded -- Claude reads them only when it accesses files in that directory, adding zero cost to sessions that don't touch the directory

## AGENTS.md and Codex Interop

`AGENTS.md` support is intentionally adapter-shaped. Praxion should not maintain
a second copy of Claude-facing guidance for Codex, Cursor, or any future
AGENTS.md-aware coding agent. The root `AGENTS.md` names the compatibility
contract and points agents back to canonical source artifacts.

`install_codex.sh` compiles a target project's `AGENTS.md` from two sources:

- the shared Praxion Codex baseline in `codex/config/AGENTS.md.tmpl`
- the project-local source template at `<project>/AGENTS.md.tmpl`

If `<project>/AGENTS.md.tmpl` is missing, the installer generates it once from
the project's root `CLAUDE.md` via the `adapt-claude-to-agents` skill workflow,
then compiles the final `AGENTS.md`. After that first install,
`AGENTS.md.tmpl` is the source to edit and `AGENTS.md` is compiled output.

By default the installer also adds generated Codex custom-agent wrappers under
the target project's `.codex/agents/`; those wrappers point back to canonical
`agents/*.md` files, translate Praxion's current routing table into Codex model
settings, and carry the source frontmatter contract instead of copying the full
body. It also generates Codex skill wrappers under the target project's
`.agents/skills/` directory, pointing back to canonical `skills/*/SKILL.md`
files while preserving the full skill description in the wrapper metadata.
Adapter fidelity matters here: preserve canonical Praxion wording for agent and
skill metadata. If Codex warns that skill descriptions were shortened to fit
its startup budget, accept that runtime warning instead of pre-trimming
generated wrappers.

When native Codex surfaces are installed, the compiled project `AGENTS.md` is
also the current consumer for the generated pipeline metadata. It points
AGENTS.md-aware tools to `.codex/praxion/pipeline_semantics.json` for task
sizing and delegation and to `.codex/praxion/model_routing.json` for Codex-side
routing, rather than asking Codex to reinterpret the Claude-only routing rule
directly.

For rules, the installer now generates a **Codex rules bridge** rather than a
lossy direct export to native `.codex/rules/`:

- `.codex/praxion/rules_manifest.json` indexes canonical Praxion rules
- `.codex/hooks/praxion-*.py` route always-on, prompt-scoped, and file-scoped
  rule matches back to canonical `rules/**/*.md`
- `.codex/hooks/praxion-*.py` also bridge the portable canonical hook families:
  process framing, subagent contract injection, memory gates, observability,
  Bash commit/cleanup gates, worktree guard, post-write quality checks, and
  precompact state snapshots
- `.codex/praxion/hook_runtime.py` runs canonical Praxion hook scripts with
  Codex-specific MCP tool names
- `.codex/hooks.json` registers those Praxion-managed hooks
- `.codex/config.toml` is updated surgically to enable `hooks = true`
  and remove deprecated `codex_hooks` entries

Codex hook registrations omit the Claude-style `async` field because current
Codex builds reject async hook handlers at startup. Observability hooks still
fan out through Codex's command-hook runner, and the wrappers fail open when
Chronograph or Phoenix is unavailable.

Codex still treats newly installed project-local hooks as reviewable security
surfaces, so a fresh target project may show pending hook review in `/hooks`
until the user approves those generated commands.

This is intentionally different from native Codex `.rules`, which remain the
surface for command approval / sandbox policy semantics. The Praxion rule
bridge preserves Claude-style semantic rule meaning without repurposing that
native Codex policy surface.

For MCP, `install_codex.sh` reuses the canonical `.claude-plugin/plugin.json`
`mcpServers` entries and writes the corresponding `memory` and
`task-chronograph` registrations into the target project's
`.codex/config.toml`. A project-local state file at
`.codex/praxion/mcp_state.json` tracks any original project-owned blocks so
uninstall can restore them without clobbering unrelated Codex config.

The installer still does not create `.ai-state/`; Claude project onboarding
owns that lifecycle. Codex memory hooks and file-backed observation capture
activate only when the target project already has `.ai-state/`. Current Codex
adapter status:

Rule pickup is automatic on every Codex install/check run: the bridge rescans
`rules/**/*.md` and rebuilds the manifest from source. New rules do not require
Python-side allowlist edits. When a rule needs an explicit Codex portability or
load override, add optional `codex:` frontmatter to the canonical rule file
instead of extending adapter code.

| Surface | Current Codex adapter status |
|---|---|
| `~/.codex/AGENTS.md` | User-owned global Codex baseline; Praxion does not install or overwrite it in the current project-local flow |
| `<project>/AGENTS.md.tmpl` | Project-local Codex source template; generated from `CLAUDE.md` on first install when missing |
| `commands/*.md` | `install_codex.sh` generates `praxion-command-<name>` wrappers under project `.agents/skills/` |
| `agents/*.md` | `install_codex.sh` generates thin `.codex/agents/*.toml` wrappers by default |
| `rules/**/*.md` frontmatter | `install_codex.sh` now generates a hook-backed rules bridge under `.codex/praxion/` plus `.codex/hooks.json`; native `.codex/rules` stays reserved for approval policy |
| `skills/*/SKILL.md` metadata | `install_codex.sh` generates project `.agents/skills/*` wrappers by default |
| MCP servers | `install_codex.sh` syncs canonical `.claude-plugin/plugin.json` `mcpServers` into project `.codex/config.toml`, with restore state under `.codex/praxion/mcp_state.json` |
| hooks | `install_codex.sh` now installs Praxion rule routing plus portable canonical hooks for process framing, subagent contract injection, memory gates, observability, Bash commit/cleanup gates, worktree guard, post-write quality checks, and precompact state snapshots; Claude marketplace auto-completion remains Claude-only |

Use this flow to test a pet project from a Praxion checkout:

```bash
./install.sh codex /path/to/pet-project --dry-run
./install.sh codex /path/to/pet-project
./install.sh codex /path/to/pet-project --check
./install.sh codex /path/to/pet-project --compat-only
```

Start a fresh Codex or AGENTS.md-aware agent session in the target project after
installing so startup discovery sees the generated `AGENTS.md`.

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

The token budget constraint (15,000 tokens for always-loaded content) drives a clear allocation strategy:

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

### LikeC4 Agent Skill (one-time, system-scope)

Register the LikeC4 DSL Agent Skill for in-editor `.c4` file guidance — see [`docs/architecture-diagrams.md#ai-tooling`](docs/architecture-diagrams.md#ai-tooling).

### Session-scoped local testing

For active development on Praxion itself, launch Claude Code with the working tree as the plugin source:

```bash
praxion-claude-dev       # installed by install.sh at ~/.local/bin/praxion-claude-dev
# equivalent to: claude --plugin-dir /path/to/Praxion --settings <session-overlay> --dangerously-skip-permissions
```

The working-tree copy is loaded via `--plugin-dir`, and a session-scoped `--settings` overlay disables the marketplace-installed `i-am@bit-agora` for the session. Without the overlay, the user-settings line `"i-am@bit-agora": true` in `enabledPlugins` force-enables the marketplace copy alongside the working tree (per Claude Code docs, force-enables override `--plugin-dir`'s shadowing) — so `/context` would load both copies and double the skill, agent, and command tokens. The overlay flips that one entry to `false` for the session only; your global `~/.claude/settings.json` is untouched, so non-Praxion sessions still get the marketplace copy as usual.

Edits to skills, commands, agents, or hooks are live. Run `/reload-plugins` inside the session to re-read them without relaunching; a full restart is only needed when `plugin.json` itself changes.

The launcher passes `--dangerously-skip-permissions` by default because dev loops against your own working tree rarely benefit from per-tool prompts. When you do want them — e.g., to test a hook's permission behavior — launch with `PRAXION_DEV_SAFE=1 praxion-claude-dev`.

Personal config and rules are **not** plugin-scoped — they're handled separately by `install.sh code` (clone-based) or `/praxion-complete-install` (marketplace-only). Running `praxion-claude-dev` does not touch them.

### Updating the plugin cache

After modifying the plugin manifest or adding new components, update the installed copy:

```bash
./install.sh code              # Re-run installer (marketplace install)
claude plugin install i-am@bit-agora --scope user   # Or install directly from the marketplace
```

### Local-edit testing workaround

`./install.sh code` performs a marketplace fetch — local file edits in the worktree do not propagate to the installed plugin cache. When iterating on files Claude Code resolves through `${CLAUDE_PLUGIN_ROOT}` (hook scripts, `hooks/hooks.json`, plugin-cache-resolved commands), copy edited files directly into the cache:

```bash
# Example: a notification-hook edit
cp hooks/notify_bg_session_state.py ~/.claude/plugins/cache/bit-agora/i-am/0.2.0/hooks/

# Example: a hooks.json registration change
cp hooks/hooks.json ~/.claude/plugins/cache/bit-agora/i-am/0.2.0/

# Verify the cache copy matches the worktree
diff hooks/notify_bg_session_state.py ~/.claude/plugins/cache/bit-agora/i-am/0.2.0/hooks/notify_bg_session_state.py
```

The version in the cache path (`0.2.0/`) comes from `.claude-plugin/plugin.json`. After a plugin version bump, the cache directory name changes — re-run `./install.sh code` once, then resume the `cp` workflow against the new version directory.

Scripts invoked from the worktree directly (e.g., `scripts/dispatch-reworks`) do not need this — they run from the worktree's own path. Only files Claude Code resolves through the installed plugin cache need the copy.

This is a documented workaround tracked as `td-036` in `.ai-state/TECH_DEBT_LEDGER.md`. A first-class `bash install.sh --dev-link` mode is the long-term resolution.

### Verifying changes

- `./install.sh --check` — confirms all symlinks, plugin, hooks, and permissions are healthy
- `/context` inside Claude Code — shows which skills and reference files are loaded in the current context window
- `claude plugin list` — verifies the plugin is registered and its version

## Plugin Development

The plugin manifest lives in `.claude-plugin/plugin.json`. Key constraints:

- See `.claude-plugin/PLUGIN_SCHEMA_NOTES.md` for validator constraints
- The plugin is distributed via the [`bit-agora`](https://github.com/francisco-perez-sorrosal/bit-agora) GitHub marketplace
- When installed, commands are namespaced as `/i-am:<name>`

### Plugin cache contains the full repo

When `claude plugin install i-am@bit-agora` runs, Claude Code clones the entire Praxion repo at the marketplace-pinned tag into `~/.claude/plugins/cache/bit-agora/i-am/<version>/`. The plugin mechanism only **loads** what `plugin.json` declares (skills, commands, agents, hooks, MCP servers) — but the rest of the repo (rules, CLI scripts, `install.sh`, `lib/`, `memory-mcp/`, `task-chronograph-mcp/`, `eval/`, etc.) sits on disk unused by the loader.

`/praxion-complete-install` relies on this. It resolves `${CLAUDE_PLUGIN_ROOT}` (set by Claude Code) and invokes the cached `install.sh` with `--complete-install`, which symlinks `${CLAUDE_PLUGIN_ROOT}/rules/` → `~/.claude/rules/` and `${CLAUDE_PLUGIN_ROOT}/scripts/` → `~/.local/bin/`. Source and destination are both local; no network, no extra clone.

### Marketplace-only install flow (internal architecture)

The three system-level surfaces (rules, scripts, context-hub MCP) that the plugin mechanism doesn't cover are handled transparently via a first-session auto-completion hook:

- `hooks/auto_complete_install.py` — SessionStart hook that detects missing surfaces and completes setup automatically on first session. Uses sensible defaults from `git config` (name, email) with optional operator override via single prompt.
- `install_claude.sh::complete_install_from_plugin()` — the underlying logic (shared with explicit re-invocation). Prompts per-surface for consent, reuses `link_rules()` from `lib/install_shared.sh` and the same filter predicate as `relink_all()` for scripts, delegates to `prompt_chub_mcp()` for the MCP entry.
- `commands/praxion-complete-install.md` — optional slash command for explicit re-invocation. Resolves `CLAUDE_PLUGIN_ROOT` and invokes `install.sh code --complete-install` from the cache.

The inverse pair (`complete_uninstall_from_plugin()` + `/praxion-complete-uninstall`) removes only symlinks whose target begins with the plugin cache path. Hand-installed rules/scripts from other sources are left alone.

### Two install modes coexist

| Target | Install Command | Plugin body source | Rules + scripts source | Flow |
|---|---|---|---|---|
| **Clone-based (full)** | `./install.sh code` | Local checkout | Local checkout | One-step installer; no follow-up needed |
| **Marketplace (plugin only)** | `claude plugin install i-am@bit-agora` | Plugin cache | Plugin cache via auto-completion hook | Auto-completes on first session (no manual step required) |
| **Marketplace (explicit reconfigure)** | `/praxion-complete-install` | Plugin cache | Plugin cache | Optional: re-invoke for reconfiguration/recovery/re-link |

For live-edit development on Praxion itself, use `praxion-claude-dev` (a thin wrapper around `claude --plugin-dir`) to launch a session that loads the plugin directly from the working tree — see [Session-scoped local testing](#session-scoped-local-testing).

### Post-update refresh

`claude plugin update i-am` replaces the cache directory entirely. Existing symlinks in `~/.claude/rules/` and `~/.local/bin/` continue pointing to the old cache version. Refresh by either:
- Start a fresh Claude Code session (triggers auto-completion automatically), OR
- Explicitly run `/praxion-complete-install` to re-link against the new version, OR
- For clone-based installs: run `./install.sh code --relink`

No automatic refresh hook exists today because Claude Code doesn't expose a PostPluginUpdate event — filed as a watch-item for when that API lands.

### Uninstall ordering

Always run `/praxion-complete-uninstall` **before** `claude plugin uninstall i-am`. Reversing the order leaves dangling symlinks pointing at a deleted cache directory. The complete-uninstall still cleans them up correctly in that case (filter by `target begins with ${CLAUDE_PLUGIN_ROOT}` — absent target doesn't matter, the link itself gets removed), but the right-order path avoids the intermediate broken state.

## Quality Evals

Quality measurement for agent pipelines that runs **separately from pipeline execution**, not as part of it. No hook triggers evals automatically; no agent ever calls them while a pipeline is in flight (binding constraint: [`dec-040`](.ai-state/decisions/040-eval-framework-out-of-band.md)). The framework lives in `eval/` as a standalone `uv` project and is **not** bundled with the plugin.

### Tiers

| Command | Tier | Purpose |
|---------|------|---------|
| `/eval` | 1 | Filesystem-only artifact manifest check — confirms every expected deliverable for the pipeline's tier was produced under `.ai-work/<task-slug>/`. Pure filesystem read; no LLM call. |
| `/eval-praxion` | 2 | LLM-as-judge semantic quality gate over completed `.ai-state/` artifacts. Family 1: pipeline-outcome fidelity (ADR structure, supersession reciprocity, traceability). Family 2: behavioral-contract adherence (BC-tag coverage in `VERIFICATION_REPORT.md`). Reports land in `.ai-state/praxion_eval_reports/`. |

The `regression` sub-package was retired in the praxion-self-eval-v1 pipeline. Baselines were keyed by `task_slug`, but Praxion slugs are one-shot — each feature generates a unique slug with no second run to compare against. The entire broken-by-design surface (448 LOC) was removed. The broader regression-mode redesign (tier/shape-keyed envelope baselines over a Phoenix corpus) remains deferred; see `eval/EVAL_PLAN.md`.

### When to run

- **`/eval`** — after any pipeline run to confirm the agent produced the full artifact set for its tier.
- **`/eval-praxion`** — after a multi-ADR pipeline or for periodic quality review; requires `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY`.

### Examples

```sh
/i-am:eval                                                           # list tier status
/i-am:eval behavioral --task-slug architecture-doc                   # verify deliverables
/i-am:eval behavioral --task-slug architecture-doc --tier full       # include ARCHITECTURE.md + docs/architecture.md recency
/i-am:eval-praxion                                                   # LLM-as-judge over main HEAD
```

### Benefits

- **Catches silent pipeline skips.** When a subagent reports "complete" but didn't actually write the deliverable, `/eval behavioral` flags the missing file. The verifier alone has false-positive failure modes; behavioral is an independent cross-check.
- **Semantic quality gate.** `/eval-praxion` surfaces ADR reasoning gaps and behavioral-contract omissions that mechanical checks cannot detect.
- **Zero pipeline overhead.** Binding constraint in `dec-040`: eval code never runs inside a pipeline, so bugs in the eval framework cannot break agent work.

### Scope

Currently Praxion-internal: `/i-am:eval` and `/i-am:eval-praxion` resolve `Bash(uv run ...)` in their `allowed-tools` frontmatter, which requires the `eval/` project on disk. When the plugin is installed in another project, the commands are exposed but invocation fails — there is no `eval/` directory and no `praxion-evals` binary on the path.

Making the tooling portable would require bundling `eval/` inside the plugin or publishing `praxion-evals` to PyPI. Not in scope today — open an issue if you need to consume it downstream.

## Releases

Versioning is managed by [Commitizen](https://commitizen-tools.github.io/commitizen/) with conventional commits. The version lives in `pyproject.toml` `[tool.commitizen].version` and is synced to `memory-mcp/pyproject.toml`, `task-chronograph-mcp/pyproject.toml`, `eval/pyproject.toml`, and `.claude-plugin/plugin.json` via `version_files`.

### Day-to-day development

Push to `main` with conventional commit messages (`feat:`, `fix:`, etc.). No CI runs on push. Between releases, every version file equals the last released stable; the version string changes only when `cz bump` runs at release time.

### Creating a release (manual, from GitHub UI)

1. Go to **Actions → Release → Run workflow**
2. Click **Run workflow**

Commitizen computes the proper semver bump from all conventional commits since the last tag, rewrites every `version_files` target in one operation, generates `CHANGELOG.md`, creates a git tag, and publishes a GitHub release. The bump level depends on commit types: `fix:` → patch, `feat:` → minor, breaking change → major (`major_version_zero = true` keeps `feat!` at MINOR while pre-1.0).

### Manual version operations

```bash
# Check current version
cz version --project

# Preview what the next bump would produce (dry-run, no changes)
cz bump --dry-run --yes
```

## References

- [Claude Code Plugins](https://code.claude.com/docs/en/plugins)
- [Claude Code Sub-agents](https://code.claude.com/docs/en/sub-agents)
- [Agent Skills Best Practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices.md)
- [bendrucker/claude config](https://github.com/bendrucker/claude/blob/main/.claude/)
- [citypaul/.dotfiles claude config](https://github.com/citypaul/.dotfiles/blob/main/claude)
