# Commands

Reusable slash commands for AI coding assistants. Each `.md` file becomes a `/command-name` invocable during interactive sessions where the assistant supports slash commands. **Tool-agnostic:** compatible with Claude Code (plugin), Cursor (exported as plain Markdown by `./install.sh cursor`), and Codex (exposed as `praxion-command-<name>` skill wrappers by `./install.sh codex`).

## Available Commands

| Command | Description |
|---------|-------------|
| `/add-rules` | Copy rules into the current project for customization |
| `/clean-auto-memory` | Enumerate orphan Claude Code auto-memory directories for removed worktrees and help the user delete them |
| `/clean-work` | Clean the `.ai-work/` directory after pipeline completion |
| `/co` | Create a commit for staged (or all) changes |
| `/cop` | Create a commit and push to remote |
| `/create-simple-python-prj` | Create a basic Python project with pixi or uv |
| `/create-worktree` | Create a new git worktree in `.claude/worktrees/` |
| `/eval` | Run out-of-band quality evals (Tier 1 behavioral + regression). Opt-in, never hook-driven |
| `/explore-project` | Explore and understand an unfamiliar project's architecture, patterns, and workflow |
| `/full-security-scan` | Run a full-project security audit against all security-critical paths |
| `/landscape-refresh` | Bootstrap or refresh the project's landscape watchlist — flag stale entries (>90 days) and optionally re-validate URLs |
| `/manage-readme` | Create or refine README.md files |
| `/cajalogic` | Manage persistent memory (user prefs, assistant learnings, project conventions, observations) |
| `/check-experiment` | Poll an in-flight or report a completed ML training experiment |
| `/dashboard` | Launch the Praxion pipeline dashboard for the current project |
| `/decontaminate-ids` | Detect and remediate REQ/AC/step citations in the current project's source code |
| `/merge-worktree` | Merge a worktree branch back into current branch |
| `/new-project` | Scaffold a greenfield Claude-ready Python project and onboard it to Praxion |
| `/onboard-project` | Onboard the current project for the Praxion plugin ecosystem |
| `/project-coverage` | Run the project's canonical coverage target and render a terminal summary via the `test-coverage` skill |
| `/project-metrics` | Compute project complexity/health metrics (churn, complexity, coupling, hot-spots, trends) and write a timestamped report triple to `.ai-state/` |
| `/refresh-skill` | Refresh version-sensitive sections of a skill against current upstream documentation |
| `/release` | Bump version, update changelog, and create a release tag |
| `/report-upstream` | File a well-formed bug report on an upstream open-source project |
| `/praxion-complete-install` | Reconfigure or recover a marketplace-installed Praxion setup — symlink rules, CLI scripts, and optional context-hub MCP |
| `/praxion-complete-uninstall` | Reverse `/praxion-complete-install` — remove rule/script symlinks and optional context-hub MCP; plugin body is preserved |
| `/review-interface` | Run an interface design review on a file, PR, branch, or named surface via the interface-designer agent |
| `/review-pr` | Code review a pull request |
| `/dispatch-reworks` | Fan out `/resume-rework` into every rework worktree from `REWORK_MANIFEST.md` — background sessions by default, `--terminals` for visible windows |
| `/resume-rework` | Dispatch the appropriate agent for a rework worktree; cwd-driven auto-discovery of `VERIFIER_FINDINGS.md` (cite `commands/resume-rework.md`) |
| `/roadmap` | Produce a project-audited `ROADMAP.md` via a project-derived evaluation lens set (SPIRIT, DORA, SPACE, FAIR, CNCF Platform Maturity, or Custom) through the roadmap-cartographer agent; covers strengths, weaknesses, **opportunities (forward lines of work)**, phased improvements, and deprecations |
| `/run-experiment` | Dispatch an ML training experiment, validate compute budget, stream metrics, write `TRAINING_RESULTS.md` |
| `/save-changes` | Save current working changes to project memory with secret filtering |
| `/sdd-coverage` | Report spec-to-test and spec-to-code coverage for REQ IDs |
| `/skill-genesis` | Run the skill-genesis agent to autonomously harvest patterns from accumulated learnings (LEARNINGS.md, verification reports, memory entries, sentinel findings, ADRs); write a timestamped report to `.ai-state/skill_genesis_reports/` for later disposition via `/skill-genesis-review` |
| `/skill-genesis-review` | Disposition pending proposals from a skill-genesis report — batch multi-select presentation, append-only disposition log, execute approved memory entries, surface delegation handoffs |
| `/star-repo` | Star the Praxion repo on GitHub |
| `/test` | Auto-detect test framework and run tests |

## How Commands Work

- **Claude Code**: Loaded from plugin `commands/`, `.claude/commands/` (project), or `~/.claude/commands/` (personal). Invoke with `/` (plugin commands may be namespaced, e.g. `/i-am:co`).
- **Cursor**: Exported to `.cursor/commands/` or `~/.cursor/commands/` by `./install.sh cursor` (frontmatter stripped). Invoke with `/`.
- **Codex**: Exported to `.agents/skills/praxion-command-<name>/SKILL.md` by `./install.sh codex`. Invoke by asking Codex to run the Praxion command, e.g. `run /co with message ...`; the wrapper reads the canonical `commands/<name>.md` file before acting.

For authoring guidance, see the [`command-crafting`](../skills/command-crafting/) skill.
