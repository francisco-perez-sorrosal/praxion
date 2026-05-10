# Codex Config

Codex-specific adapter sources live here. Shared Praxion artifacts remain
canonical at the repository root; files in this directory generate or install
Codex-native surfaces from those sources.

## Agent Export

`export-codex-agents.py` converts `agents/*.md` into Codex custom-agent TOML
files under a target `.codex/agents/` directory.

The exporter preserves:

- `name`
- `description`
- translated `model` / `model_reasoning_effort` values from the canonical
  Praxion routing table
- a thin `developer_instructions` wrapper that tells Codex to read the
  canonical Praxion agent file before acting and carries the source
  frontmatter contract as a compact capsule

The source frontmatter capsule preserves Claude-specific tool, hook,
permission, memory, background, max-turn, and skill semantics that Codex
does not model natively in the wrapper TOML.

## Skill Export

`export-codex-skills.py` converts `skills/*/SKILL.md` into Codex skill wrappers
under a target `.agents/skills/` directory.

The exporter preserves:

- the canonical skill name
- the full canonical description
- a thin wrapper body that points back to the canonical Praxion skill file

It intentionally does not copy canonical skill bodies into the wrapper. Codex
loads the wrapper at startup and can read the canonical skill on activation.

## Command-Skill Export

`export-codex-command-skills.py` converts `commands/*.md` into Codex skill
wrappers under the same target `.agents/skills/` directory.

The exporter preserves:

- the canonical slash-command description
- the canonical command name as a `praxion-command-<name>` skill
- a thin wrapper body that points back to the canonical Praxion command file
- argument-substitution guidance for `$ARGUMENTS` and positional arguments

It intentionally does not copy canonical command bodies into the wrapper. Codex
gets a documented project-skill activation surface while Praxion keeps
`commands/*.md` as the single source of truth.

## Rules Bridge

`export-codex-rules-bridge.py` generates the Praxion-managed Codex rules bridge
under a target project's `.codex/` directory.

Generated surfaces:

- `.codex/praxion/rules_manifest.json` -- canonical rule index derived from
  `rules/**/*.md`
- `.codex/praxion/rules_lookup.py` -- helper for matching always-on,
  prompt-scoped, and path-scoped Praxion rules
- `.codex/praxion/hook_runtime.py` -- helper for running canonical Praxion hook
  scripts with Codex-specific runtime environment
- `.codex/hooks/praxion-session-start.py` -- injects always-on Praxion rule
  context at session start
- `.codex/hooks/praxion-memory-session-start.py` -- injects curated memory
  context when the target project already has `.ai-state/`
- `.codex/hooks/praxion-memory-stop.py` -- enforces the memory gate with Codex
  MCP tool names
- `.codex/hooks/praxion-observability-session-start.py` -- records session
  lifecycle events and context-surface measurements
- `.codex/hooks/praxion-observability-stop.py` -- records session stop events
- `.codex/hooks/praxion-user-prompt-submit.py` -- routes prompt-matched rules
- `.codex/hooks/praxion-process-framing-user-prompt-submit.py` -- injects
  Praxion process framing for non-trivial prompts
- `.codex/hooks/praxion-subagent-pre-tool-use.py` -- injects the Praxion
  behavioral contract into host-native subagent prompts
- `.codex/hooks/praxion-commit-*-pre-tool-use.py` -- runs canonical Bash
  commit gates for quality, ADR reminders, memory reminders, and ID citation
  discipline
- `.codex/hooks/praxion-cleanup-learnings-pre-tool-use.py` -- warns before
  cleanup deletes unpromoted `.ai-work/**/LEARNINGS.md` content
- `.codex/hooks/praxion-worktree-guard-pre-tool-use.py` -- blocks
  cross-worktree file writes from linked git worktrees
- `.codex/hooks/praxion-pre-tool-use.py` -- routes file-scoped rules before
  mutating file tool activity
- `.codex/hooks/praxion-observability-pre-tool-use.py` -- forwards tool-start
  events to Praxion observability
- `.codex/hooks/praxion-observability-post-tool-use.py` -- forwards tool-result
  events and captures memory observations
- `.codex/hooks/praxion-format-python-post-tool-use.py` -- runs canonical
  Python auto-formatting after file writes/edits
- `.codex/hooks/praxion-detect-duplication-post-tool-use.py` -- runs canonical
  intra-file duplication detection after file writes/edits
- `.codex/hooks/praxion-observability-subagent-start.py` -- records subagent
  lifecycle start events when Codex emits them
- `.codex/hooks/praxion-memory-subagent-stop.py` -- enforces subagent memory
  validation with Codex MCP tool names when Codex emits the event
- `.codex/hooks/praxion-observability-subagent-stop.py` -- records subagent
  lifecycle stop events when Codex emits them
- `.codex/hooks/praxion-precompact-state.py` -- writes `.ai-work/` pipeline
  state snapshots before compaction when Codex emits the event
- `.codex/praxion/hook_registrations.json` -- expected Praxion hook
  registrations for merge/check logic

Codex does not currently accept an `async` field in `.codex/hooks.json`.
The exporter therefore omits `async` from all hook registrations, including
observability hooks. Codex launches multiple matching command hooks
concurrently at runtime, so the unsupported field is not needed to preserve
non-blocking fan-out behavior.

This bridge intentionally does **not** export semantic Praxion Markdown rules
into `.codex/rules/`. Native Codex `.rules` remain reserved for command
approval / sandbox policy semantics.

The bridge also does **not** create `.ai-state/`. Claude project onboarding
owns that lifecycle; generated Codex memory hooks and file-backed observation
capture activate against an existing `.ai-state/` directory.

The Claude marketplace auto-completion hook is intentionally not bridged to
Codex because its job is to repair `~/.claude` plugin surfaces. Codex installs
use `install_codex.sh` instead.

Rule pickup is dynamic: every exporter run rescans `rules/**/*.md`. The bridge
does not depend on a hardcoded Python allowlist for new rules. Automatic Codex
classification is derived from the canonical rule source, with optional
rule-local `codex:` frontmatter for exceptions:

```yaml
---
codex:
  portability: portable
  load: always_on
---
```

## Config and Hook Registration

`manage-codex-rules-bridge.py` installs, checks, and uninstalls the
Praxion-managed Codex rule bridge state in a target project:

- ensures `.codex/config.toml` has `hooks = true` and removes deprecated
  `codex_hooks` entries during install
- merges Praxion-managed hook registrations into `.codex/hooks.json`
- preserves non-Praxion Codex config and hook entries
- removes only Praxion-managed entries during uninstall

All Praxion-managed rule-bridge assets are prefixed `praxion-` or live under
`.codex/praxion/` so ownership remains explicit and uninstall stays surgical.

## MCP Adapter

`manage-codex-mcp.py` installs, checks, and uninstalls the Praxion-managed
Codex MCP adapter in the shared Codex user config:

- reads the canonical `mcpServers` definitions from `.claude-plugin/plugin.json`
- writes the corresponding `memory` and `task-chronograph` entries into
  `~/.codex/config.toml` as `mcp_servers.*` tables with concrete repo-root
  paths
- preserves unrelated Codex config sections and non-Praxion MCP entries
- tracks installed Praxion projects in `~/.codex/praxion/mcp_state.json`
- restores any pre-existing user server blocks when the last Praxion-installed
  project is uninstalled

This shared-config ownership model is intentional: the rules bridge is
project-local under the target repo's `.codex/`, but Codex MCP registration is
managed through the shared user config surface.

## Pipeline Adapter

`export-codex-pipeline-adapter.py` generates Codex adapter metadata from
Praxion's canonical coordination and model-routing rules.

Generated surfaces:

- `.codex/praxion/pipeline_semantics.json` -- process-tier, agent-flow, and
  shared-document metadata derived from
  `rules/swe/swe-agent-coordination-protocol.md`
- `.codex/praxion/model_routing.json` -- Praxion agent tier routes derived from
  `rules/swe/agent-model-routing.md`, translated to Codex model classes without
  pinning decaying model IDs

The adapter metadata is intentionally machine-readable and pointer-based. It
does not copy canonical agent, rule, or planning bodies; Codex orchestration
must still read the canonical Praxion source files before acting.

Current consumer: the installed project `AGENTS.md` adapter block points
AGENTS.md-aware main sessions at these files when present, so task sizing,
delegation, and model routing stay in the Codex adapter layer.
