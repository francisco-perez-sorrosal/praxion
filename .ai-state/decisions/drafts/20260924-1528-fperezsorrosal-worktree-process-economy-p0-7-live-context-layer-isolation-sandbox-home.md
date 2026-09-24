---
id: dec-draft-0cbab284
title: Context-layer isolation for live eval sessions via a per-session sandbox HOME and config dir, allowlisted env and --plugin-dir
status: proposed
category: implementation
date: 2026-09-24
summary: A headless `claude -p` session loads only a target checkout's context layer when HOME and CLAUDE_CONFIG_DIR point at a per-session sandbox populated by the target's own render_claude_md + link_rules, the read-only target copy is passed via --plugin-dir and --add-dir, MCP is emptied with --strict-mcp-config, and the environment is rebuilt from an allowlist with the runner's own interpreter first on PATH (so hook-delivered rules reach the session); auth rides on an env credential; out-of-sandbox tool_use paths are detected from telemetry. Proven live by nonces plus harness telemetry with a paired ambient control.
tags: [eval, context-layer, isolation, headless, claude-code-cli, sandbox, auth, process-economy, roadmap-p0-7]
made_by: agent
agent_type: systems-architect
branch: worktree-process-economy-p0-7-live
pipeline_tier: standard
affected_files:
  - eval/src/praxion_evals/live/session.py
  - eval/src/praxion_evals/live/materialize.py
---

## Context

The live context-layer scenario runner (dec-draft-2fdf564d) needs each headless session to load the **target** checkout's context layer — global CLAUDE.md, user-scope rules, hook-delivered rules, plugin agents/skills/commands/hooks — and nothing from the operator's environment, while keeping the operator's auth and never modifying their files. The operator's environment loads `~/.claude/CLAUDE.md` and `~/.claude/rules/*` (symlinks into the main checkout), nine enabled marketplace plugins, five MCP servers (four from plugins, one user-scoped), user `settings.json` hooks, and a `settings.json` `env` that exports `CLAUDE_PLUGIN_ROOT=/Users/fperez/dev/praxion` — which `hooks/inject_rules.py` uses to locate its manifest. The ambient `python3` also lacks PyYAML, so `inject_rules.py` skips the hook-delivered rules. Claude Code CLI 2.1.281.

## Decision

For every session (preflight and scenario), as built by `session.py` and `materialize.py`:

- `HOME=<session>/home`, `CLAUDE_CONFIG_DIR=<session>/home/.claude`, `TMPDIR=<session>/tmp`.
- The config dir is populated by the **target copy's own** primitives: `scripts/render_claude_md.py` (`render_claude_md` with `derive_defaults()`) renders the global CLAUDE.md, symlinked as `<config>/CLAUDE.md` exactly as the installer does; `lib/install_shared.sh::link_rules` installs the manifest's `install: symlink` rules (hook-deliver rules stay out, as in a real install, and arrive through the SessionStart hook); `settings.json` is `{}`.
- The target copy is **read-only on disk** and is passed with `--plugin-dir <copy>` and `--add-dir <copy>`. `--add-dir` is needed because the copy lies outside the session's cwd, so without it Praxion's progressive disclosure (skill references read by path) was denied in the recorded envelopes. The flag grants read **and** edit; the edit half is neutralized by the read-only copy, since a permission grant cannot override a filesystem permission.
- `--strict-mcp-config --mcp-config '{"mcpServers":{}}'`; `--permission-prompts none`. Spawn-selection sessions allowlist no tools, and every other scenario gets a narrow per-scenario allowlist.
- The environment is built from an allowlist (`PATH`, locale, `TERM`, `USER`, `LOGNAME`, `SHELL`, and the credential variables `ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_BASE_URL`) plus the side-effect-only hook kill switches (`PRAXION_DISABLE_AUTO_COMPLETE`, `PRAXION_DISABLE_OBSERVABILITY`, `PRAXION_DISABLE_HOOK_CHAIN_HEAL`, `PRAXION_DISABLE_SIDECAR_AUTOCOMMIT`) and harness noise switches (`CLAUDE_CODE_DISABLE_AUTO_MEMORY`, `DISABLE_AUTOUPDATER`, `PYTHONDONTWRITEBYTECODE`). Context-injecting hooks stay on.
- `PATH` is the operator's `PATH` with **the runner's own interpreter directory (`Path(sys.executable).parent`) prepended**. That interpreter imports PyYAML, because the graders need it, so hooks resolve a `python3` under which `inject_rules.py` delivers the hook-delivered rules. The preflight's fourth nonce, planted in a hook-delivered rule, must be echoed. A correctly installed operator session receives those rules; a baseline without them would measure a layer no real session runs. The ambient-interpreter defect itself is tracked separately as a fleet-wide ledger row.
- **Detection beyond prevention:** a Bash allowlist glob (`cat *`, `tail *`) cannot tell stdin from `~/.ssh/…`. Every tool_use input is therefore scanned for an absolute path outside the sandbox root and the copy, and any hit classifies the session as `isolation_breach` from telemetry.
- An env credential is required; the keychain OAuth entry is keyed to the config dir (docs, `authentication.md`), so it is deliberately not used.

Evidence (four live probes, $0.72 total, plus seven recorded envelopes at $2.00): the isolated run echoed every planted nonce on the surfaces it could reach (global CLAUDE.md template, an always-loaded rule, a plugin agent description). Its `init` event listed only the target copy plus two builtins and zero MCP servers, with `apiKeySource: ANTHROPIC_API_KEY`. Its debug log never referenced the real `~/.claude`, and the real `~/.claude/projects` and `history.jsonl` were untouched. The paired ambient run over the **same** planted copy echoed only the plugin nonce and listed nine extra plugins and five MCP servers. A subagent (`praxion:implementer`) spawned inside the sandbox echoed nonces from its own body, a preloaded skill, the rule and the global CLAUDE.md. The hook-delivered nonce was absent under the ambient interpreter (`PyYAML not available; skipping rule injection`), which motivated the PATH prepend.

## Considered Options

### Option 1 — sandbox HOME + config dir, target-installed user scope, runner interpreter first on PATH (chosen)

Pros: one structural boundary; the target's layer lands at the same scopes as a real install, via the target's own install code, hook-delivered rules included; every Claude Code write (sessions, `.claude.json`, plugin data) and every hook that hard-codes `$HOME/.claude` lands in the sandbox. Cons: requires an env credential; hooks run under the runner's interpreter rather than the operator's ambient one, so the sandbox deliberately does **not** reproduce the ambient PyYAML defect — the measured layer is the one a correctly installed session receives.

### Option 1b — same sandbox, operator's PATH unchanged

Rejected at the architecture checkpoint: it reproduced the ambient interpreter defect, so hook-delivered rules never reached the session and the baseline measured a layer no correctly installed session runs.

### Option 2 — `--setting-sources project,local` + `--add-dir` + `--plugin-dir`, real HOME

Pros: keeps OAuth. Cons: `~/.claude.json` (user MCP servers) is read regardless of setting sources; transcripts land in the real `~/.claude/projects`; `hooks/auto_complete_install.py` resolves `$HOME/.claude` directly and can relink the real global CLAUDE.md; the target's CLAUDE.md loads as an additional-directory file, not at user scope. Four enumerated closures instead of one boundary.

### Option 3 — `--bare`

Pros: purpose-built for scripted calls. Cons: skips CLAUDE.md discovery, hooks and plugin discovery and offers only Bash/read/edit tools, removing the agent roster and hook-delivered context that are part of the layer under test; OAuth never read.

### Option 4 — `--safe-mode`

Rejected: disables CLAUDE.md, skills, plugins and hooks — the layer itself.

### Option 5 — Claude Agent SDK `query()`

Pros: typed messages; already a dependency of the eval package. Cons: runs its own bundled CLI version rather than the operator's; merges rather than replaces the environment; the task requires verbatim `claude -p` envelopes as test fixtures.

## Consequences

Positive: isolation is structural, provable per run (four nonces, including the hook-delivered surface), and robust to future hooks that write under `$HOME`. Out-of-sandbox reads are caught from telemetry even where an allowlist glob cannot prevent them. The operator's configuration, installed plugin cache and transcripts are never touched.

Negative: operators who authenticate only through the keychain must supply `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) or an API key; spend on this machine is API-metered. The measured layer assumes a PyYAML-capable hook interpreter, which the operator's ambient environment does not currently provide. The mechanism depends on CLI semantics for `CLAUDE_CONFIG_DIR`, `--plugin-dir`, `--add-dir` and `--strict-mcp-config` that a future release could change — the per-run nonce preflight is the tripwire.
