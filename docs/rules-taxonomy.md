---
diataxis: reference
audience: developer
---

# Rules Taxonomy and Disable Guide

Every Praxion-onboarded project inherits a curated set of rules: coding style, behavioral contract, agent coordination protocol, ADR conventions, and more. Some are always-loaded (cost tokens on every session); others load only when their trigger paths are read. This guide explains how rules are categorized, how the per-project disable mechanism reaches each category, and how to measure the cost of your choices.

## Two-Channel Delivery, One Disable List

Praxion delivers rules through two channels. The per-project `.claude/praxion-rules.yaml` disable list reaches **both** — different mechanism under the hood, single YAML interface.

| Channel | Delivery | Disable mechanism |
|---------|----------|-------------------|
| **Hook-deliver** | Body shipped at SessionStart via `additionalContext` JSON from `inject_rules.py` | Filtered out of `additionalContext` when in the YAML disable list |
| **Symlink** | File installed to `~/.claude/rules/<id>.md`; Claude Code's native runtime loads it (unconditionally for always-on rules; on matching `Read` for path-scoped rules) | Portable glob (`**/.claude/rules/<id>.md`) reconciled into `claudeMdExcludes` in `.claude/settings.json`; Claude Code's runtime skips the file |

Together the two mechanisms give the YAML uniform reach: **any rule named in the disable list is guaranteed not to load**. The one exception is core rules (`core: true`) — they remain non-disableable, and attempts to disable them emit a stderr warning.

## Three Categories of Rules

### 1. Core Rules (non-disableable, always-loaded)

Five rules encode Praxion's operating contract. They are **immune to the disable mechanism** — attempting to disable one emits a stderr warning and the rule remains loaded.

| ID | Rule file | Purpose | Token cost |
|----|-----------|---------|------------|
| `CLAUDE` | `rules/CLAUDE.md` | Agent reading order + build/test/lint + repo layout | ~640 tokens |
| `swe/adr-conventions` | `rules/swe/adr-conventions.md` | Architecture Decision Record format, lifecycle, finalize protocol | ~3115 tokens |
| `swe/agent-behavioral-contract` | `rules/swe/agent-behavioral-contract.md` | Four non-negotiable behaviors: Surface Assumptions, Register Objection, Stay Surgical, Simplicity First | ~375 tokens |
| `swe/agent-intermediate-documents` | `rules/swe/agent-intermediate-documents.md` | `.ai-work/` and `.ai-state/` document locations, lifetimes, task-slug convention | ~3200 tokens |
| `swe/swe-agent-coordination-protocol` | `rules/swe/swe-agent-coordination-protocol.md` | Agent pipeline, tier table, delegation checklists, parallel execution | ~4245 tokens |

**Total core tokens:** ~11,575

### 2. Always-Loaded Hook-Deliver Rules (disableable, biggest token savings)

Three rules ship at SessionStart and contribute to the always-loaded token baseline. Disabling them via the YAML filters them out of `additionalContext` — the most direct way to reclaim always-loaded tokens.

| ID | Rule file | Purpose | Token cost | Typical disabler |
|----|-----------|---------|------------|------------------|
| `swe/memory-protocol` | `rules/swe/memory-protocol.md` | Memory MCP usage, recall, remember, conflict resolution | ~1500 tokens | Projects with `PRAXION_DISABLE_MEMORY_MCP=1` or no memory MCP server |
| `swe/agent-model-routing` | `rules/swe/agent-model-routing.md` | Claude model tier routing table, per-agent allocation | ~2300 tokens | Projects using default model routing only |
| `swe/vcs/git-conventions` | `rules/swe/vcs/git-conventions.md` | Commit scope, message format, secrets discipline | ~1300 tokens | Projects with different VCS policy or no Git |

**Total hook-deliver tokens reclaimable:** ~5,100

### 3. Path-Scoped Rules (disableable, declarative-only — zero baseline cost)

Fourteen rules load only when their `paths:` frontmatter matches a `Read` target. They cost **zero tokens at SessionStart** regardless of whether they appear in the YAML disable list.

| Category | Rule ID(s) | Activation pattern | Purpose |
|----------|------------|-------------------|---------|
| **SWE** | `swe/coding-style` | `.py`, `.ts`, `.rs`, `.go`, etc. | Language-specific code formatting |
| | `swe/id-citation-discipline` | Source files in language extensions | REQ-to-code traceability conventions |
| | `swe/shipped-artifact-isolation` | Rules, skills, commands, agents | Constraints on project-portable artifacts |
| | `swe/staleness-policy` | `skills/**/SKILL.md` | Skill freshness conventions |
| | `swe/testing-conventions` | Test code, test files | Testing strategy and terminology |
| | `swe/vcs/pr-conventions` | `.github/`, PR-adjacent surfaces | Pull request workflow and merge policy |
| **ML/AI** | `ml/eval-driven-verification` | Training plans, `runs/`, `experiments/` | ML eval-driven acceptance criteria |
| | `ml/experiment-tracking-conventions` | `runs/`, `experiments/`, `program.md` | Experiment tracking tool conventions |
| | `ml/gpu-budget-conventions` | Training steps, WIP.md, `program.md` | GPU compute budget enforcement |
| **Writing** | `writing/aac-dac-conventions` | `ARCHITECTURE.md`, `*.c4` | Architecture-as-Code fence conventions |
| | `writing/diagram-conventions` | `docs/**`, READMEs, design docs | Diagram toolchain and layout rules |
| | `writing/html-output-conventions` | `dashboard_app/**`, doc manifests | HTML output generation |
| | `writing/readme-style` | `**/README.md`, `**/README_DEV.md` | Markdown writing quality and structure |

**Why disable a path-scoped rule?** Path-scoping itself is a cost control — adding a path-scoped rule to the disable list yields no SessionStart token savings. The reason to disable is **declarative**: you want a guarantee that the rule never applies in this project, even if a trigger file (e.g., a generically-named `prepare.py` in a non-ML project) is added later for unrelated reasons. The disable list translates to a `claudeMdExcludes` entry in `.claude/settings.json`, and Claude Code's runtime then skips the rule on every matching Read.

## Creating a Project Disable List

### Step 1: Create `.claude/praxion-rules.yaml`

Create a YAML file in your project (committed to git, since the derived `.claude/settings.json` is also committed and team-shared):

```yaml
# .claude/praxion-rules.yaml — Project-local rule configuration
#
# Optional file. If absent, all rules load (backward compatible).
# Schema version 1 only.

version: 1

# Disable specific rules by ID. fnmatch globs supported (e.g., ml/*).
disable:
  - swe/memory-protocol  # Project sets PRAXION_DISABLE_MEMORY_MCP=1

# Or disable all rules in a category with globs
# disable:
#   - ml/*                # Not an ML project — guaranteed never to fire
#   - writing/*           # Project uses a different documentation standard
```

### Step 2: Understand the Behavior

- **No config file** → all rules load (backward compatible; no settings.json mutation)
- **Empty `disable:` list** → all rules load (same)
- **`disable: [swe/memory-protocol]`** → suppressed from `additionalContext` at SessionStart (reclaims ~1.5k always-loaded tokens)
- **`disable: [ml/*]`** → 3 `**/.claude/rules/ml/*.md` patterns written to `claudeMdExcludes`; ML rules guaranteed not to load even if trigger files appear (no SessionStart token savings — path-scoped rules already cost zero baseline)
- **Attempting `disable: [swe/agent-behavioral-contract]`** → stderr warning emitted, rule stays loaded (core protection)

The hook is **idempotent**: it recomputes the derived `claudeMdExcludes` on every SessionStart, replacing only Praxion-managed entries (those whose pattern starts with `**/.claude/rules/`) and preserving any other `claudeMdExcludes` entries you added by hand. Removing an entry from the YAML cleans up the corresponding `claudeMdExcludes` entry on the next session.

### Step 3: Measure the Effect

Use `measure_context_surface.py` to see the always-loaded token delta:

```bash
python3 measure_context_surface.py
```

The tool reports the always-loaded token total. Disabling hook-deliver rules reduces this number directly; disabling path-scoped rules does not (they were not counted in the baseline to begin with).

## Category Globs

The disable list supports fnmatch glob patterns. Note that fnmatch's `*` crosses `/` (unlike gitignore), so `swe/*` matches deep IDs like `swe/vcs/pr-conventions`.

| Glob | Matches | Effect |
|------|---------|--------|
| `ml/*` | 3 ML rules (all path-scoped) | `claudeMdExcludes` patterns added; no SessionStart token savings; declarative-only guarantee |
| `writing/*` | 4 writing rules (all path-scoped) | Same as above |
| `swe/vcs/*` | 2 VCS rules: `git-conventions` (hook-deliver) + `pr-conventions` (path-scoped) | `git-conventions` filtered from `additionalContext` (reclaims ~1.3k tokens); `pr-conventions` added to `claudeMdExcludes` |
| `swe/*` | 13 SWE rules | 4 core: warnings emitted, kept loaded; 3 hook-deliver: filtered from `additionalContext` (~5.1k tokens reclaimed); 6 path-scoped: `claudeMdExcludes` patterns added |

## Core Rule Protection

If you attempt to disable a core rule, the SessionStart hook emits a warning to stderr:

```
[inject_rules] WARNING: cannot disable core rule 'swe/agent-behavioral-contract' — kept loaded
```

The rule remains loaded. Core rules protect Praxion's operating contract (Surface Assumptions, Register Objection, Stay Surgical, Simplicity First; ADR conventions; agent coordination protocol; `.ai-work/`/`.ai-state/` conventions) and are structurally load-bearing for the rest of the ecosystem to reason on top of.

## Schema Version Handling

The `.claude/praxion-rules.yaml` format uses semantic versioning. The current schema is **version 1**.

- **Schema 1** (current): rules identified by `id`, glob support, `disable` list, no enable-list
- **Schema 2+**: not yet released

If your config specifies `version: 2` or higher:
- The hook emits a stderr warning: `Schema version N is not supported by this version of Praxion; falling back to no suppression`
- The hook falls back to injecting all rules (fail-open)
- Update your `.claude/praxion-rules.yaml` to `version: 1` and remove any unsupported fields

## Kill Switch: `PRAXION_DISABLE_RULE_INJECTION`

For debugging or temporary disabling, set the environment variable:

```bash
PRAXION_DISABLE_RULE_INJECTION=1 claude-code
```

This skips the `inject_rules.py` hook entirely. Effects:

- Hook-deliver rule bodies are absent from `additionalContext` (the three blacklistable always-loaded rules are not delivered)
- The hook does **not** run `claudeMdExcludes` reconciliation; any existing entries from prior sessions remain in effect via Claude Code's native runtime, so previously-disabled symlinked rules stay disabled
- Core rules symlinked into `~/.claude/rules/` continue to load via Claude Code's native rule mechanism

**Use case:** Troubleshooting rule interaction issues without uninstalling the plugin.

## SessionStart Logging

When a session starts, the `inject_rules.py` hook logs a summary line to stderr:

```
[inject_rules] Loaded 5 core rules; injected 3/3 hook-deliver rules (suppressed: none); symlink suppressions via claudeMdExcludes: none
```

With suppressions active (e.g., `disable: [ml/*, swe/memory-protocol]`):

```
[inject_rules] Loaded 5 core rules; injected 2/3 hook-deliver rules (suppressed: swe/memory-protocol); symlink suppressions via claudeMdExcludes: ml/eval-driven-verification, ml/experiment-tracking-conventions, ml/gpu-budget-conventions
```

This confirms which rules were loaded, which hook-deliver rules were filtered, and which symlink rules were added to `claudeMdExcludes` for the session.

If reconciliation wrote to `settings.json`, a second line appears:

```
[inject_rules] Reconciled claudeMdExcludes in /path/.claude/settings.json: 3 Praxion-managed, 0 user-managed preserved
```

When the YAML matches the existing `settings.json` state exactly, the reconciliation step is silently skipped (idempotency).

## Example Configurations

### Minimal Project (Token-Conscious)

Disable hook-deliver baseline + declare path-scoped categories as out-of-scope:

```yaml
version: 1
disable:
  - swe/memory-protocol
  - swe/agent-model-routing
  - swe/vcs/git-conventions
  - ml/*
  - writing/*
```

**SessionStart token reduction:** ~5,100 (all hook-deliver). Path-scoped categories contribute zero baseline cost regardless — disabling them adds declarative guarantees but no SessionStart savings.

### ML Project

Disable non-ML conventions while keeping training discipline:

```yaml
version: 1
disable:
  - swe/memory-protocol
  - swe/agent-model-routing
  - writing/*
```

**Rationale:** Project uses its own model routing and skips Praxion's memory protocol; writing rules are out-of-scope. ML rules stay enabled for training discipline.

### Standard Project

No disable list — accept all rules:

```yaml
# .claude/praxion-rules.yaml omitted entirely, or:
version: 1
disable: []
```

**Behavior:** Identical to original Praxion installations; all non-core rules load when their conditions are met.

## Further Reading

- [Architecture Guide: Rules section](architecture.md#3-components) — technical components implementing the two-channel delivery
- [Onboarding: Rules Configuration](../commands/onboard-project.md) — how to add this to an existing project
- [rules/_manifest.yaml](../rules/_manifest.yaml) — machine-readable rule taxonomy (auto-generated)
- [Example Configuration](../claude/config/praxion-rules.yaml.example) — template shipped by Praxion; copy to your project's `.claude/praxion-rules.yaml` and edit the `disable:` list
