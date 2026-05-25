# Cross-Agent Portability

The [Agent Skills standard](https://agentskills.io) is an open format adopted by 25+ AI development tools. A well-authored skill works across all of them without modification — if you avoid tool-specific assumptions in the SKILL.md body.

## Adopters

Claude Code, Claude (claude.ai), Cursor, VS Code / GitHub Copilot, OpenAI Codex, Gemini CLI, Roo Code, Goose, Amp, Factory, Databricks, Spring AI, TRAE, Letta, Firebender, OpenCode, Autohand, Mux, Piebald, Agentman, Command Code, Mistral Vibe, Ona, VT Code, and others.

See [agentskills.io](https://agentskills.io/home) for the current list.

## Skill Discovery Paths

Each tool scans its own directories for `SKILL.md` files. The standard does not mandate a single path — it defines the format, and tools choose where to look.

| Tool | Discovery Path(s) |
| --- | --- |
| Claude Code | `~/.claude/skills/<name>/SKILL.md` (personal), `.claude/skills/<name>/SKILL.md` (project), nested `.claude/skills/` in subdirectories (monorepo) |
| Cursor | `.cursor/rules/` (`.mdc` files) plus Agent Skills `SKILL.md` via `.claude/skills/`. Reads `name`, `description`, `paths`, `disable-model-invocation`, `metadata` natively. |
| Codex CLI | `.agents/skills/` (walks parent dirs to repo root), `~/.agents/skills/`, `/etc/codex/skills/`. Reads only `name` + `description` from SKILL.md; invocation policy, tool deps, and UI metadata live in a sibling `agents/openai.yaml`. |
| VS Code / Copilot | `.github/copilot-instructions.md` (project instructions), plus Agent Skills via `.claude/skills/` |
| Gemini CLI | `GEMINI.md` (project instructions), plus Agent Skills via `.claude/skills/` |

**Tip**: Most tools that adopted the standard look for skills in `.claude/skills/` at the project root. Placing skills there maximizes cross-tool discovery.

## What's Portable vs. Tool-Specific

### Portable (works everywhere)

- **SKILL.md format**: YAML frontmatter (`name`, `description`, `license`, `compatibility`, `metadata`) + markdown body
- **Directory structure**: `scripts/`, `references/`, `assets/` subdirectories
- **Markdown body content**: Instructions, examples, workflows, checklists
- **Progressive disclosure**: Metadata at startup, full SKILL.md on activation, reference files on demand

### Tool-Specific (may vary or be ignored)

- **`allowed-tools`**: Tool names differ across agents (Claude Code uses `Read`, `Bash`, `Edit`; other tools may use different names). The field is experimental per the spec.
- **`compatibility`**: Use this to indicate when a skill targets a specific tool: `compatibility: Designed for Claude Code (or similar products)`
- **MCP tool names** (`ServerName:tool_name`): Only relevant to tools with MCP support
- **Claude-Code-only extensions**: `when_to_use`, `user-invocable`, `context: fork`, `agent`, `model`, `effort`, `argument-hint`, `arguments`, `hooks`, string substitutions (`$ARGUMENTS`, `$0`, `${CLAUDE_SESSION_ID}`) — Claude Code features, not part of the open standard. (`paths` and `disable-model-invocation` are *not* Claude-only — Cursor reads them natively; see the discovery table above.)

### Writing for Maximum Portability

- Keep the SKILL.md body in standard markdown — avoid tool-specific syntax
- Put tool-specific instructions behind a clear heading (e.g., `## Claude Code Usage`) so other agents can skip them
- Use `compatibility` in frontmatter to signal tool requirements rather than embedding assumptions in the body
- Prefer prose instructions and examples over tool-specific commands when possible
- Test with at least two different agents if portability matters for your use case

## Skills vs. Project Instruction Files

Skills (SKILL.md) and project instruction files (CLAUDE.md, AGENTS.md, GEMINI.md, .cursorrules) serve different purposes:

| Aspect | Skills (SKILL.md) | Project Instructions (CLAUDE.md, etc.) |
| --- | --- | --- |
| **Scope** | Modular, task-specific capability | Project-wide context and conventions |
| **Loading** | On-demand when relevant to the task | Always loaded at session start |
| **Portability** | Cross-agent via the open standard | Tool-specific format |
| **Reuse** | Shareable across projects | Tied to one project |

`AGENTS.md` is an emerging convention for universal project instructions (not part of the Agent Skills standard). If you need both project-wide instructions and reusable skills, use `AGENTS.md` for the former and `.claude/skills/` for the latter.
