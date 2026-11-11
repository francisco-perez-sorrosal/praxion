---
id: dec-draft-cd95f438
title: "The plugin's likec4 MCP server runs only where its workspace holds a model"
status: proposed
category: architectural
date: 2026-11-11
summary: "A launcher, scripts/likec4_mcp_gate.py, becomes the plugin's likec4 server entry: it runs npx -y @likec4/mcp, the command the plugin ran before, only when LIKEC4_WORKSPACE (docs/diagrams/) under the project directory holds a .c4 file, and otherwise answers MCP itself with no instructions and no tools, so a project with no model stops paying about 1,330 tokens of instructions and 460 of tool names per session."
tags: [startup-context-diet, catalogue, mcp, likec4, project-scope, managed-projects]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - scripts/likec4_mcp_gate.py
  - scripts/test_likec4_mcp_gate.py
  - .claude-plugin/plugin.json
  - skills/likec4-diagramming/SKILL.md
  - scripts/CLAUDE.md
affected_reqs: []
---

## Context

The startup-context diet's catalogue item asks to scope likec4 to the projects that use it. Until now the plugin started `npx -y @likec4/mcp` in every session of every project. The server reads a single workspace, `LIKEC4_WORKSPACE`, which the plugin sets to `docs/diagrams/`. Where that workspace holds no `.c4` source, the server answers every query with nothing. It still puts its instructions and its twenty tool names into the session.

Measured on 2026-11-11 with the free `count_tokens` endpoint, from the server's own `initialize` and `tools/list` replies: 3,646 characters of instructions, 1,326 tokens, plus 462 tokens of deferred tool names. The spike of 2026-10-11 read 1,332 for the instructions.

On this machine, 8 of 21 managed projects carry `.c4` sources, every one of them under `docs/diagrams/`: praxion, knotica, knotica-okf, cv-forge, sandbook, sandbook-int4-shims, burstworks and francisco. The other 13, and every unmanaged directory, pay for a server that serves nothing.

## Decision

`.claude-plugin/plugin.json` starts the `likec4` server as `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/likec4_mcp_gate.py`, with the same `LIKEC4_WORKSPACE`. The gate reads the project directory: `CLAUDE_PROJECT_DIR`, which Claude Code exports to stdio MCP servers, else the working directory.

- **When the workspace under it holds a `.c4` file** (skipping `.git`, `node_modules`, `.venv`), the gate execs `npx -y @likec4/mcp`. Behaviour is byte for byte what it was.
- **Otherwise** it serves MCP itself as a connected server with no instructions and no tools. It answers `initialize`, `tools/list` and `ping`, and gives method-not-found for anything else.

The gate is stdlib-only, in Python 3.7 syntax, and not executable, so the installer never links it onto PATH. The `likec4-diagramming` skill says the server starts only where a model exists, and its existing fallback, direct `.c4` reads, covers a project's first model until the next session.

## Considered Options

### Leave the server global
Rejected. It costs about 1.8K tokens in every session of 13 of 21 managed projects and in every unmanaged directory, for no capability there.

### Exit at once when there is no model
Rejected. Claude Code shows a server that exits as failed, which means a failed-server notice in most projects. A connected, empty server is silent.

### Move the server out of the plugin into each project's own `.mcp.json`, written by onboarding when the project adopts LikeC4
Rejected for now. Managed projects lag on features. Every project that uses LikeC4 today would lose the server on the update until it re-onboards. A project `.mcp.json` server also asks for approval once per project. The gate needs no migration: evidence in the project decides.

### Detect any `.c4` file anywhere in the project
Rejected. The server reads only its workspace, so a model elsewhere (a test fixture, for instance) would start a server that still serves nothing. The gate reads exactly what the server reads.

## Consequences

- A session in a project with no model loses about 1,330 tokens of instructions and 460 of tool names. A session in a project with a model receives the same server as before.
- A project's first `.c4` source gets the MCP tools from the next session. Until then the skill reads `.c4` files directly, which it already did whenever the server was absent.
- One more launcher sits between the plugin and the LikeC4 server, so a change to the server's command or workspace convention now has two sites: `plugin.json`'s `env` and the gate's default. The tests pin both.
- The gate adds one bounded directory walk at session start. It runs under whichever `python3` is on PATH, as the hooks do.

## Disconfirmation

- **Falsifier:** a session in a project whose `docs/diagrams/` holds a `.c4` file connects to the `likec4` server with fewer than twenty tools, or a session in a project without one still lists `mcp__plugin_praxion_likec4__*` tools. Either means the gate misjudges where the server has a workspace.
- **Steelmanned runner-up:** onboarding writes the server into the projects that use LikeC4. The project then declares what it uses, which is data, not detection, and the plugin carries no launcher. It loses because a lagging managed project would silently lose the tools until re-onboarded, and because a project-scoped server needs a per-project approval the plugin server does not.
- **Reversal trigger:** Claude Code gains a per-project switch for a plugin's MCP server, or a `paths`-style activation for one. Either would carry the same scope without a launcher, and this gate should then be retired.
