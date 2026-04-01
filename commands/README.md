# Commands

Reusable slash commands for AI coding assistants. Each `.md` file becomes a `/command-name` invocable during interactive sessions. **Tool-agnostic:** compatible with Claude Code (plugin) and Cursor (exported as plain Markdown by `./install.sh cursor`).

## Available Commands

| Command | Description |
|---------|-------------|
| `/add-rules` | Copy rules into the current project for customization |
| `/clean-work` | Clean the `.ai-work/` directory after pipeline completion |
| `/co` | Create a commit for staged (or all) changes |
| `/cop` | Create a commit and push to remote |
| `/create-simple-python-prj` | Create a basic Python project with pixi or uv |
| `/create-worktree` | Create a new git worktree in `.trees/` |
| `/manage-readme` | Create or refine README.md files |
| `/memory` | Manage persistent memory (user prefs, assistant learnings, project conventions) |
| `/merge-worktree` | Merge a worktree branch back into current branch |
| `/onboard-project` | Onboard the current project for the Praxion plugin ecosystem |
| `/release` | Bump version, update changelog, and create a release tag |
| `/sdd-coverage` | Report spec-to-test and spec-to-code coverage for REQ IDs |
| `/star-repo` | Star the Praxion repo on GitHub |

## How Commands Work

- **Claude Code**: Loaded from plugin `commands/`, `.claude/commands/` (project), or `~/.claude/commands/` (personal). Invoke with `/` (plugin commands may be namespaced, e.g. `/i-am:co`).
- **Cursor**: Exported to `.cursor/commands/` or `~/.cursor/commands/` by `./install.sh cursor` (frontmatter stripped). Invoke with `/`.

For authoring guidance, see the [`command-crafting`](../skills/command-crafting/) skill.
