---
diataxis: how-to
audience: developer
---

# Claude Code vs Cursor: differences

This doc explains how the same repo artifacts (skills, rules, commands, agents, MCP) are used by **Claude Code** and **Cursor**. For installation and configuration, see the main [README.md](../README.md). The top-level `install.sh` routes to `install_claude.sh` (code/desktop) or `install_cursor.sh` (cursor).

## Discovery and format

| Aspect | Claude Code | Cursor |
|--------|-------------|--------|
| **Skills** | Plugin install copies repo into `~/.claude/plugins/cache/...`; skills discovered from plugin dir. Same [Agent Skills](https://agentskills.io) format: folder with `SKILL.md` + optional `references/`, `scripts/`, `assets/`. | Discovers from `.cursor/skills/` or `.claude/skills/` (project) and `~/.cursor/skills/` or `~/.claude/skills/` (user). Same SKILL.md format; no conversion. |
| **Rules** | Symlinked from repo `rules/` to `~/.claude/rules/`; Claude loads by relevance. Plain or frontmatter `.md`. | Symlinked from repo `rules/` to `.cursor/rules/` (or `~/.cursor/rules/`). Cursor loads `.md` files by relevance; optional frontmatter (`description`, `globs`, `alwaysApply`) enables “Apply Intelligently”. |
| **Commands** | One `.md` per command with **YAML frontmatter** (`description`, `allowed-tools`, `argument-hint`); slash name = filename stem. Plugin namespaces: `/i-am:co`. | **Plain Markdown only** — no frontmatter. Discovers from `.cursor/commands/` or `~/.cursor/commands/`. So repo `commands/*.md` must be **exported** (frontmatter stripped) for Cursor. |
| **Agents** | First-class plugin agents: `agents/*.md` with frontmatter (`name`, `description`, `tools`, `skills`) + body. Invoked by name or delegation. | One path: [sub-agents-mcp](https://github.com/shinpr/sub-agents-mcp). Install-cursor writes `mcp.json` with `AGENTS_DIR` = this repo’s `agents/`, `AGENT_TYPE=cursor`. Agent filename = agent name; files use frontmatter + body (sub-agents-mcp uses body). |
| **MCP servers** | Defined in plugin `plugin.json` with `${CLAUDE_PLUGIN_ROOT}`; Claude Code resolves to plugin cache path. | Defined in `.cursor/mcp.json` (or UI) with **absolute paths** (or path from run dir). No plugin root variable; path must point at this repo or install location. |

## What’s portable as-is

- **Skills:** Content is portable. Only the **discovery path** differs (plugin cache vs `.cursor/skills/` or `.claude/skills/`).
- **Rules:** Content is portable. Symlinked from the same source files for both tools. Cursor can optionally use frontmatter for “Apply Intelligently” — add it to source rules when needed.
- **Repo as source of truth:** Both tools consume from the same repo; no duplication of skill or rule content.

## What needs adaptation at install time

- **Commands:** Cursor cannot use frontmatter; an export step produces plain `.cursor/commands/*.md` from `commands/*.md`.
- **MCP:** Cursor needs a generated `.cursor/mcp.json` with concrete paths (e.g. repo root) instead of `${CLAUDE_PLUGIN_ROOT}`.
- **Agents:** Cursor gets them via sub-agents-mcp only. Install-cursor configures it; no second option. Agent files stay as-is (frontmatter + body); sub-agents-mcp uses filename as name.

## Prerequisites

- **Claude Code**: `claude` CLI installed. Plugin permissions auto-configured by installer.
- **Cursor (agents)**: sub-agents-mcp requires Node/npx and `cursor-agent login` for authentication. Run `cursor-agent login` before using agents in Cursor.
- **MCP servers**: task-chronograph and memory require `uv`; sub-agents requires `npx`.

## Summary

Same artifacts, different discovery and config: Claude Code uses the plugin system and `~/.claude/`; Cursor uses `.cursor/` (or `~/.cursor/`) and generated/exported files. The repo stays tool-agnostic; configuration is in the [README](../README.md).
