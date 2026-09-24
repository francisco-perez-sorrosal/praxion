---
id: dec-draft-0cbab284
title: Context-layer isolation for live eval sessions via a per-session sandbox HOME and config dir, allowlisted env and --plugin-dir
status: proposed
category: implementation
date: 2026-09-24
summary: A headless `claude -p` session loads only a target checkout's context layer when HOME and CLAUDE_CONFIG_DIR point at a per-session sandbox populated by the target's own render_claude_md + link_rules, the target copy is passed via --plugin-dir, MCP is emptied with --strict-mcp-config, and the environment is rebuilt from an allowlist; auth rides on an env credential (ANTHROPIC_API_KEY outranks OAuth). Proven live by nonces plus harness telemetry with a paired ambient control.
tags: [eval, context-layer, isolation, headless, claude-code-cli, sandbox, auth, process-economy, roadmap-p0-7]
made_by: agent
agent_type: systems-architect
branch: worktree-process-economy-p0-7-live
pipeline_tier: standard
affected_files:
  - scripts/render_claude_md.py
  - lib/install_shared.sh
  - hooks/auto_complete_install.py
  - hooks/_hook_utils.py
---

## Context

The live context-layer scenario runner (dec-draft-2fdf564d) needs each headless session to load the **target** checkout's context layer — global CLAUDE.md, user-scope rules, plugin agents/skills/commands/hooks — and nothing from the operator's environment, while keeping the operator's auth and never modifying their files. The operator's environment loads `~/.claude/CLAUDE.md` and `~/.claude/rules/*` (symlinks into the main checkout), nine enabled marketplace plugins, five MCP servers (four from plugins, one user-scoped), user `settings.json` hooks, and a `settings.json` `env` that exports `CLAUDE_PLUGIN_ROOT=/Users/fperez/dev/praxion` — which `hooks/inject_rules.py` uses to locate its manifest. Claude Code CLI 2.1.281.

## Decision

For every session (preflight and scenario):

- `HOME=<session>/home`, `CLAUDE_CONFIG_DIR=<session>/home/.claude`, `TMPDIR=<session>/tmp`.
- The config dir is populated by the **target copy's own** primitives: `scripts/render_claude_md.py` (`render_claude_md` with `derive_defaults()`) renders the global CLAUDE.md, symlinked as `<config>/CLAUDE.md` exactly as the installer does; `lib/install_shared.sh::link_rules` installs the manifest's `install: symlink` rules (hook-deliver rules stay out, as in a real install); `settings.json` is `{}`.
- `--plugin-dir <target copy>`; `--strict-mcp-config --mcp-config '{"mcpServers":{}}'`.
- The environment is built from an allowlist (`PATH`, locale, `TERM`, `USER`, `LOGNAME`, `SHELL`, and the credential variables `ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_BASE_URL`) plus the side-effect-only hook kill switches (`PRAXION_DISABLE_AUTO_COMPLETE`, `PRAXION_DISABLE_OBSERVABILITY`, `PRAXION_DISABLE_HOOK_CHAIN_HEAL`, `PRAXION_DISABLE_SIDECAR_AUTOCOMMIT`) and harness noise switches (`CLAUDE_CODE_DISABLE_AUTO_MEMORY`, `DISABLE_AUTOUPDATER`, `PYTHONDONTWRITEBYTECODE`). Context-injecting hooks stay on.
- An env credential is required; the keychain OAuth entry is keyed to the config dir (docs, `authentication.md`), so it is deliberately not used.

Evidence (four live probes, $0.72 total): the isolated run echoed 3/3 planted nonces (global CLAUDE.md template, an always-loaded rule, a plugin agent description), its `init` event listed only the target copy plus two builtins and zero MCP servers with `apiKeySource: ANTHROPIC_API_KEY`, its debug log never referenced the real `~/.claude`, and the real `~/.claude/projects` and `history.jsonl` were untouched. The paired ambient run over the **same** planted copy echoed only the plugin nonce — the global and rule nonces were absent because the main checkout's files loaded instead — and listed nine extra plugins and five MCP servers. A subagent (`praxion:implementer`) spawned inside the sandbox echoed nonces from its own body, a preloaded skill, the rule and the global CLAUDE.md.

## Considered Options

### Option 1 — sandbox HOME + config dir, target-installed user scope (chosen)

Pros: one structural boundary; the target's layer lands at the same scopes as a real install, via the target's own install code; every Claude Code write (sessions, `.claude.json`, plugin data) and every hook that hard-codes `$HOME/.claude` lands in the sandbox. Cons: requires an env credential; hooks run under the operator's `PATH`, so an interpreter defect there (observed: no PyYAML, so hook-delivered rules are skipped) is reproduced rather than masked.

### Option 2 — `--setting-sources project,local` + `--add-dir` + `--plugin-dir`, real HOME

Pros: keeps OAuth. Cons: `~/.claude.json` (user MCP servers) is read regardless of setting sources; transcripts land in the real `~/.claude/projects`; `hooks/auto_complete_install.py` resolves `$HOME/.claude` directly and can relink the real global CLAUDE.md; the target's CLAUDE.md loads as an additional-directory file, not at user scope. Four enumerated closures instead of one boundary.

### Option 3 — `--bare`

Pros: purpose-built for scripted calls. Cons: skips CLAUDE.md discovery, hooks and plugin discovery and offers only Bash/read/edit tools, removing the agent roster and hook-delivered context that are part of the layer under test; OAuth never read.

### Option 4 — `--safe-mode`

Rejected: disables CLAUDE.md, skills, plugins and hooks — the layer itself.

### Option 5 — Claude Agent SDK `query()`

Pros: typed messages; already a dependency of the eval package. Cons: runs its own bundled CLI version rather than the operator's; merges rather than replaces the environment; the task requires verbatim `claude -p` envelopes as test fixtures.

## Consequences

Positive: isolation is structural, provable per run, and robust to future hooks that write under `$HOME`. The operator's configuration, installed plugin cache and transcripts are never touched.

Negative: operators who authenticate only through the keychain must supply `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) or an API key; spend on this machine is API-metered. The mechanism depends on CLI semantics for `CLAUDE_CONFIG_DIR`, `--plugin-dir` and `--strict-mcp-config` that a future release could change — the per-run nonce preflight is the tripwire.
