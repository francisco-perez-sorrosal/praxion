# Agent Instructions for Praxion

Praxion is a meta-project for building and governing other projects through
reusable agentic coding artifacts. It is mainly developed and operated through
Claude today, but its shared assets are intended to be reusable across agentic
coding frameworks such as Codex, Cursor, and Claude.

This file is an adapter for agents that understand `AGENTS.md`. It must avoid
textual redundancy with the existing Praxion guidance. The source of truth
remains the repository artifacts: `CLAUDE.md`, `rules/`, `skills/`, `commands/`,
`agents/`, hooks, MCP servers, and `.ai-state/`.

## Reading Order

1. Read `CLAUDE.md` first for Praxion-specific baseline context.
2. Read relevant always-on rules in `rules/**/*.md` that do not have `paths:`
   frontmatter when the work depends on project conventions.
3. Read path-scoped rules when touching matching files.
4. Load `skills/<name>/SKILL.md` when the task matches the skill description or
   the user names the skill.
5. Load skill references only on demand.
6. Treat `commands/*.md` and `agents/*.md` as executable workflow specs, not as
   Codex-native slash commands or subagents unless a Codex bridge explicitly
   implements that mapping.

## Operating Contract

Follow Praxion's behavioral contract from
`rules/swe/agent-behavioral-contract.md`:

- Surface Assumptions.
- Register Objection.
- Stay Surgical.
- Simplicity First.

For task sizing, follow `rules/swe/swe-agent-coordination-protocol.md`.
Default to the lowest process tier that fits the request. Use the existing
Praxion worktree home, `.claude/worktrees/<slug>/`, for isolated work.

## Interop Boundaries

- Do not duplicate existing Praxion guidance here. Point to source artifacts and
  load them on demand.
- Do not duplicate large rule, skill, command, or agent bodies into Codex files.
  Link to the existing artifacts and load them progressively.
- Preserve canonical wording when adapting Praxion skills or agents to another
  tool. Do not truncate, summarize, or rewrite source text unless a hard
  platform constraint makes that unavoidable.
- For Codex skill wrappers specifically, preserve the full canonical skill
  `description` metadata. Codex may warn that descriptions were shortened to
  fit its startup skill budget; accept that runtime warning rather than
  pre-trimming Praxion's source descriptions or generated wrappers.
- Do not modify `~/.claude/plugins/cache/`; edit source files in this repo.
- Keep assistant-specific configuration in assistant-specific directories.
  Shared assets remain at the repository root.
- Preserve the token-budget discipline for always-loaded guidance. Add detail to
  skills or references instead of this file when possible.

## Compatibility Contract

`AGENTS.md` is a compatibility shim, not a parallel instruction corpus. Its job
is to make the existing Praxion artifacts discoverable to agents that support
the `AGENTS.md` protocol, and to name the adapter seams for artifacts that are
not natively understood.

Directly reusable by AGENTS.md-aware coding agents without a tool-specific
installer:

- `AGENTS.md` as the entrypoint adapter.
- `CLAUDE.md` as project baseline context, read by reference.
- `rules/**/*.md` as conventions, loaded by reading the relevant files.
- `skills/*/SKILL.md` and skill references as progressive-disclosure guidance.
- `commands/*.md` as canonical slash-command workflow specs, exposed to Codex
  through generated `praxion-command-<name>` skill wrappers when installed.
- Human-facing docs such as `README.md`, `README_DEV.md`, and `docs/`.
- Source code, tests, hooks, scripts, MCP server source, and `.ai-state/` data
  as normal repository files.

Requires an adapter or tool-specific installer before it becomes native in a
given agentic coding framework:

- `agents/*.md` -> framework-specific subagent registration that preserves
  Praxion pipeline semantics.
- `rules/**/*.md` frontmatter -> path matcher and rule loader.
- `skills/*/SKILL.md` metadata -> skill discovery and activation bridge.
- MCP server manifests/source -> target framework MCP config writer.
- hooks -> target framework lifecycle hook integration.
- Assistant-specific config under `claude/`, `cursor/`, or future
  tool-specific directories.

## Verification

Use the verification path documented in `CLAUDE.md` for the files touched. For
changes to shipped blocks or onboarding behavior, run:

- `python3 scripts/sync_canonical_blocks.py --check`

For Python behavior, run the relevant pytest target from `CLAUDE.md` or
`README_DEV.md`.


<!-- PRAXION:AGENTS_ADAPTER:START -->
## Praxion Adapter

This project uses Praxion guidance through AGENTS.md-compatible tooling.
Praxion's source artifacts are canonical; this block is only a pointer.

Praxion source:

```text
/Users/fperez/dev/praxion
```

When working in this project:

1. Read `/Users/fperez/dev/praxion/AGENTS.md` for the compatibility contract.
2. Read `/Users/fperez/dev/praxion/CLAUDE.md` for Praxion baseline context.
3. Load relevant rules from `/Users/fperez/dev/praxion/rules/` by reading the files.
4. Load matching skills from `/Users/fperez/dev/praxion/skills/<name>/SKILL.md` and
   skill references only when needed.
5. Treat `/Users/fperez/dev/praxion/commands/*.md` and `/Users/fperez/dev/praxion/agents/*.md` as
   workflow specs unless this agentic framework has a native adapter for them.

Always-on Praxion stance:

- Surface Assumptions.
- Register Objection.
- Stay Surgical.
- Simplicity First.

Task sizing:

- Direct: single-file fix, config, doc, typo.
- Lightweight: 2-3 files, one behavior, clear scope.
- Standard: 4-8 files, 2-4 behaviors, architectural decisions.
- Full: 9+ files, 5+ behaviors, cross-cutting work.
- Spike: exploratory, uncertain outcome.

Praxion agents available through Codex custom-agent wrappers when the native
adapter is installed: promethean, researcher, systems-architect,
implementation-planner, context-engineer, implementer, test-engineer, verifier,
architect-validator, doc-engineer, sentinel, skill-genesis, cicd-engineer, and
roadmap-cartographer.

Praxion skills are exposed to Codex through project-local `.agents/skills`
wrapper skills. Load matching skills on demand; canonical skill files remain
the source of truth.

Do not copy Praxion rules, skills, commands, or agents into this file. Keep this
adapter small and update Praxion at the source.
<!-- PRAXION:AGENTS_ADAPTER:END -->
