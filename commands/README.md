# Commands

Reusable slash commands for AI coding assistants. Each `.md` file becomes a `/command-name` invocable during interactive sessions. **Tool-agnostic:** compatible with Claude Code (plugin) and Cursor (exported as plain Markdown by `./install.sh cursor`).

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
| `/manage-readme` | Create or refine README.md files |
| `/cajalogic` | Manage persistent memory (user prefs, assistant learnings, project conventions, observations) |
| `/merge-worktree` | Merge a worktree branch back into current branch |
| `/new-project` | Scaffold a greenfield Claude-ready Python project and onboard it to Praxion |
| `/onboard-project` | Onboard the current project for the Praxion plugin ecosystem |
| `/project-coverage` | Run the project's canonical coverage target and render a terminal summary via the `test-coverage` skill |
| `/refresh-skill` | Refresh version-sensitive sections of a skill against current upstream documentation |
| `/release` | Bump version, update changelog, and create a release tag |
| `/report-upstream` | File a well-formed bug report on an upstream open-source project |
| `/review-pr` | Code review a pull request |
| `/roadmap` | Produce a project-audited `ROADMAP.md` via a project-derived evaluation lens set (SPIRIT, DORA, SPACE, FAIR, CNCF Platform Maturity, or Custom) through the roadmap-cartographer agent; covers strengths, weaknesses, **opportunities (forward lines of work)**, phased improvements, and deprecations |
| `/save-changes` | Save current working changes to project memory with secret filtering |
| `/sdd-coverage` | Report spec-to-test and spec-to-code coverage for REQ IDs |
| `/star-repo` | Star the Praxion repo on GitHub |
| `/test` | Auto-detect test framework and run tests |

## How Commands Work

- **Claude Code**: Loaded from plugin `commands/`, `.claude/commands/` (project), or `~/.claude/commands/` (personal). Invoke with `/` (plugin commands may be namespaced, e.g. `/i-am:co`).
- **Cursor**: Exported to `.cursor/commands/` or `~/.cursor/commands/` by `./install.sh cursor` (frontmatter stripped). Invoke with `/`.

For authoring guidance, see the [`command-crafting`](../skills/command-crafting/) skill.
