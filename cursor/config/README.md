# Cursor installer config

Resources used by `install_cursor.sh` (and the main installer when targeting Cursor).

- **mcp.json.template** — Template for `.cursor/mcp.json`. Placeholders are replaced at install time:
  - `{{MCP_ROOT}}` — Repo root (or `CURSOR_REPO_ROOT`) used for task-chronograph MCP paths.
  - `{{AGENTS_DIR_ABS}}` — Absolute path to this repo's `agents/` (for sub-agents-mcp).

- **expected-mcp-servers.txt** — One server name per line. Used by `--check` to verify that `mcp.json` contains these MCP servers.

- **export-cursor-commands.py** — Exports `commands/*.md` to `.cursor/commands/` (frontmatter stripped to plain Markdown). Invoked by `install_cursor.sh` with `repo_root` and `out_dir`.

- **export-cursor-rules.py** — Optional utility for exporting rules with Cursor-specific frontmatter (`description`, `alwaysApply`). Not used by the default installer (which symlinks rules directly), but available for users who want "Apply Intelligently" metadata added to rule copies.
