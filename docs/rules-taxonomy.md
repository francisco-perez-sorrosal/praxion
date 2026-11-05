---
diataxis: reference
audience: developer
---

# Rules Taxonomy and Disable Guide

Every Praxion-onboarded project inherits a curated set of rules: coding style, behavioral contract, agent coordination protocol, ADR conventions, and more. Some are always-loaded (cost tokens on every session); others load only when their trigger paths are read; a core rule may be path-scoped and keep a session-start text that stays always-loaded. This guide explains how rules are categorized, how the per-project disable mechanism reaches each category, and how to measure the cost of your choices.

## Token-Savings Ceiling (Read This First)

**The maximum baseline token reduction this mechanism can deliver is the sum of the sizes of the *disableable* hook-deliver rules — currently about 2,450 tokens across two rules** (tokenizer-measured 2026-11-01: the resident 753, git-conventions 1,699) (the routing rule's session-start text, `swe/agent-model-routing-resident`, and `swe/vcs/git-conventions`). Everything else in the disable list is a *policy guarantee*, not a token saver:

- **Core rules** (`core: true`, ~9,174 tokens, tokenizer-measured) are non-disableable. They load unconditionally — listing them in `disable:` emits a warning and changes nothing.
- **Path-scoped rules** (19 rules) are already lazy: they cost **zero tokens at SessionStart** regardless of the disable list. Adding them to `disable:` produces a *declarative* guarantee that they will never load — useful in projects where a generically-named trigger file could appear (`prepare.py` in a non-ML project) — but yields no baseline savings.
- **Disableable hook-deliver rules** are the only group whose disable status moves tokens. The three managed core units are hook-delivered too, but they are core, so the mechanism never moves them.

If your goal is to shrink the always-loaded surface beyond the ~2.45k-token hook-deliver ceiling, the lever is **not** the YAML — it is the `core: true/false` classification in `rules/_manifest.yaml`, or splitting bulky always-on rules into thin always-on summaries plus on-demand reference files under `skills/<name>/references/`. The YAML mechanism is a per-project filter over the rules already available; the `core` classification is the architectural decision about *which* rules are available at all.

## Two-Channel Delivery, One Disable List

Praxion delivers rules through two channels. The per-project `.claude/praxion-rules.yaml` disable list reaches **both** — different mechanism under the hood, single YAML interface.

| Channel | Delivery | Disable mechanism |
|---------|----------|-------------------|
| **Hook-deliver** | Body shipped via `additionalContext` JSON from `inject_rules.py`: at SessionStart, and for the three managed core units also at SubagentStart (inheriting spawns only). A rule marked `project_scope: managed` reaches only managed projects | Filtered out of `additionalContext` when in the YAML disable list; **also** receives a `claudeMdExcludes` entry as defense-in-depth against stale symlinks from a prior install when this rule was an `install: symlink` |
| **Symlink** | File installed to `~/.claude/rules/<id>.md`; Claude Code's native runtime loads it (unconditionally for always-on rules; on matching `Read` for path-scoped rules) | Portable glob (`**/.claude/rules/<id>.md`) reconciled into `claudeMdExcludes` in `.claude/settings.json`; Claude Code's runtime skips the file |

Together the two mechanisms give the YAML uniform reach: **any rule named in the disable list is guaranteed not to load**. The one exception is core rules (`core: true`) — they remain non-disableable, and attempts to disable them emit a stderr warning. The hook-delivery channel itself is the decision recorded in dec-167.

## Three Categories of Rules

### 1. Core Rules (non-disableable)

Five core entries encode Praxion's operating contract: four rules and the resident file of the ADR rule. They are **immune to the disable mechanism** — attempting to disable one emits a stderr warning and the rule remains loaded.

| ID | Rule file | Purpose | Token cost |
|----|-----------|---------|------------|
| `swe/adr-conventions` | `rules/swe/adr-conventions.md` | Architecture Decision Record format, lifecycle, finalize protocol | path-scoped on `.ai-state/decisions/**` (~2499 tokens when loaded); Codex keeps it always-on |
| `swe/adr-conventions-resident` | `rules/swe/adr-conventions-resident.md` | Session-start text of the ADR rule (its title and opening sentence), always-loaded | ~81 tokens (~132 with frontmatter) |
| `swe/agent-behavioral-contract` | `rules/swe/agent-behavioral-contract.md` | Four non-negotiable behaviors: Surface Assumptions, Register Objection, Stay Surgical, Simplicity First | ~370 tokens |
| `swe/agent-intermediate-documents` | `rules/swe/agent-intermediate-documents.md` | `.ai-work/` and `.ai-state/` document locations, lifetimes, task-slug convention | ~1130 tokens |
| `swe/swe-agent-coordination-protocol` | `rules/swe/swe-agent-coordination-protocol.md` | Agent pipeline, tier table, delegation checklists, parallel execution | ~4573 tokens |

Three of these five (the coordination protocol, the intermediate-documents rule and the ADR resident) reach managed projects only. An unmanaged project never loads them, and no disable entry is involved.

**Total always-loaded core tokens (managed project):** ~6,205 on the gate's default tokenizer (see [`measure_token_budget.py`](../scripts/measure_token_budget.py)'s `count_tokens`; `--model <id>` reads them on a current model's tokenizer, which counts higher).

`rules/CLAUDE.md` is not a rule: it is the rules tree's directory guide, skipped by the manifest and the installer, and Claude Code loads it on demand as a nested `CLAUDE.md` when a session touches `rules/`. It was a core rule until 2026-10-11.

### 2. Always-Loaded Hook-Deliver Rules (disableable, biggest token savings)

Two rules are disableable hook-deliver rules. They ship at SessionStart and contribute to the always-loaded token baseline; disabling them via the YAML filters them out of `additionalContext`, the most direct way to reclaim always-loaded tokens. The three managed core units (section 1) are also hook-delivered, but they are core and never filtered.

| ID | Rule file | Purpose | Token cost | Typical disabler |
|----|-----------|---------|------------|------------------|
| `swe/agent-model-routing-resident` | `rules/swe/agent-model-routing-resident.md` | Session-start text of the model-routing rule: the spawn directive and its deviations. The full rule (tier table, per-agent allocation) loads on `agents/**` and the routing policy reference. Disabled by listing its parent id `swe/agent-model-routing` | ~750 tokens | Projects using default model routing only |
| `swe/vcs/git-conventions` | `rules/swe/vcs/git-conventions.md` | Commit scope, message format, secrets discipline | ~1,700 tokens | Projects with different VCS policy or no Git |

**Total hook-deliver tokens reclaimable:** ~2,450

The full routing rule is path-scoped on `agents/**`, so a subagent that reads or edits `agents/**` now loads the whole rule, orchestrator directive included; hook delivery never reached a subagent before.

### 3. Path-Scoped Rules (disableable, declarative-only — zero baseline cost)

Thirteen rules load only when their `paths:` frontmatter matches a `Read` target. They cost **zero tokens at SessionStart** regardless of whether they appear in the YAML disable list. Disabling them yields no SessionStart token savings — the value is the **declarative guarantee** that the rule never applies in this project, even if a generically-named trigger file (e.g., `prepare.py` in a non-ML project) appears later.

| Category | Rule ID(s) | Activation pattern | Purpose |
|----------|------------|-------------------|---------|
| **SWE** | `swe/coding-style` | `.py`, `.ts`, `.rs`, `.go`, etc. | Language-specific code formatting |
| | `swe/id-citation-discipline` | Source files in language extensions | REQ-to-code traceability conventions |
| | `swe/shipped-artifact-isolation` | Rules, skills, agents | Constraints on project-portable artifacts |
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

# Or disable all rules in a category with globs
# disable:
#   - ml/*                # Not an ML project — guaranteed never to fire
#   - writing/*           # Project uses a different documentation standard
```

### Step 2: Understand the Behavior

- **No config file** → all rules load (backward compatible; no settings.json mutation)
- **Empty `disable:` list** → all rules load (same)
- **`disable: [swe/agent-model-routing]`** → the rule's session-start text (its resident) is suppressed from `additionalContext` at SessionStart (reclaims ~750 always-loaded tokens), and the path-scoped rule is added to `claudeMdExcludes`
- **`disable: [ml/*]`** → 3 `**/.claude/rules/ml/*.md` patterns written to `claudeMdExcludes`; ML rules guaranteed not to load even if trigger files appear (no SessionStart token savings — path-scoped rules already cost zero baseline)
- **Attempting `disable: [swe/agent-behavioral-contract]`** → stderr warning emitted, rule stays loaded (core protection)

The hook is **idempotent**: it recomputes the derived `claudeMdExcludes` on every SessionStart, replacing only Praxion-managed entries (those whose pattern starts with `**/.claude/rules/`) and preserving any other `claudeMdExcludes` entries you added by hand. Removing an entry from the YAML cleans up the corresponding `claudeMdExcludes` entry on the next session.

**Defense-in-depth against stale symlinks.** Two complementary steps ensure a rule's install-type change can't leak past the blacklist: (1) the installer's `sweep_stale_rule_symlinks` (in `lib/install_shared.sh`) prunes any `~/.claude/rules/` symlink that points into the repo's `rules/` tree but is no longer in the manifest as `install: symlink` — handling the case where a rule flipped from `symlink` to `hook-deliver` and the old link was never removed; (2) the SessionStart hook emits `claudeMdExcludes` entries for hook-deliver rules in the disable set too, so even if a stale link survives the sweep, Claude Code's runtime skips it.

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
| `swe/vcs/*` | 2 VCS rules: `git-conventions` (hook-deliver) + `pr-conventions` (path-scoped) | `git-conventions` filtered from `additionalContext` (reclaims ~1.7k tokens); `pr-conventions` added to `claudeMdExcludes` |
| `swe/*` | 16 SWE rules | 5 core: warnings emitted, kept loaded (three reach managed projects only); 2 disableable hook-deliver: filtered from `additionalContext` (~2.45k tokens reclaimed); 9 path-scoped: `claudeMdExcludes` patterns added |

## Core Rule Protection

If you attempt to disable a core rule, the SessionStart hook emits a warning to stderr:

```
[inject_rules] WARNING: cannot disable core rule 'swe/agent-behavioral-contract' — kept loaded
```

The rule remains loaded (the ADR rule on its path scope, its resident file always). Core rules protect Praxion's operating contract (Surface Assumptions, Register Objection, Stay Surgical, Simplicity First; ADR conventions; agent coordination protocol; `.ai-work/`/`.ai-state/` conventions) and are structurally load-bearing for the rest of the ecosystem to reason on top of.

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

This bypasses the manifest and the project's disable list: the `inject_rules.py` hook still runs and delivers only the managed core units. Effects:

- In a managed project the three managed core units are still delivered; in an unmanaged directory nothing is. The two disableable hook-deliver rules are absent from `additionalContext` in either case
- The hook does **not** run `claudeMdExcludes` reconciliation; any existing entries from prior sessions remain in effect via Claude Code's native runtime, so previously-disabled symlinked rules stay disabled
- Core rules symlinked into `~/.claude/rules/` continue to load via Claude Code's native rule mechanism

**Use case:** Troubleshooting rule interaction issues without uninstalling the plugin.

## SessionStart Logging

When a session starts, the `inject_rules.py` hook logs a summary line to stderr:

```
[inject_rules] Loaded 5 core rules; injected 5/5 hook-deliver rules (suppressed: none); claudeMdExcludes entries: none
```

With suppressions active (e.g., `disable: [ml/*, swe/vcs/git-conventions]`):

```
[inject_rules] Loaded 5 core rules; injected 4/5 hook-deliver rules (suppressed: swe/vcs/git-conventions); claudeMdExcludes entries: ml/eval-driven-verification, ml/experiment-commit-conventions, ml/experiment-tracking-conventions, ml/gpu-budget-conventions, swe/vcs/git-conventions
```

The `Loaded N core rules` count is the manifest's, the same in every scope; the injected count depends on scope. An unmanaged directory reads `injected 1/5`, because only `swe/vcs/git-conventions` reaches it. This confirms which rules were loaded, which hook-deliver rules were filtered, and which rules were added to `claudeMdExcludes` for the session. Note: the disabled hook-deliver rule (`swe/vcs/git-conventions`) appears in *both* the `suppressed:` list and the `claudeMdExcludes entries:` list — the latter is defense-in-depth against stale symlinks (see `compute_symlink_exclusions` in [`hooks/_rule_blacklist.py`](../hooks/_rule_blacklist.py)). Disabling `swe/agent-model-routing` suppresses the routing rule's session-start text through its parent's id, and adds both that text and the path-scoped rule to `claudeMdExcludes`.

### Misuse warnings

The hook surfaces several previously-silent misuses as stderr warnings, so a config typo can't masquerade as working configuration:

- **`disable:` as scalar instead of list** — `disable: ml/*` (without the `- `) was previously coerced to empty silently. Now emits: `WARNING: 'disable:' must be a YAML list, got str: 'ml/*'. Treating as empty.`
- **A pattern matching zero rules** — `disable: [my/typo-rule]` was previously a silent no-op. Now emits: `WARNING: disable pattern 'my/typo-rule' matched no rule in rules/_manifest.yaml — typo?`
- **Non-integer `version:`** — `version: "1"` was previously coerced to int 1 silently. Now emits: `WARNING: 'version:' field has non-integer value '1'; coercing to 1.`
- **Malformed `.claude/settings.json`** — was previously a quiet skip. Now emits a louder warning that names the consequence: *"Praxion-managed claudeMdExcludes reconciliation skipped — the YAML disable list will NOT be applied until the JSON is fixed."*

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
  - swe/agent-model-routing
  - swe/vcs/git-conventions
  - ml/*
  - writing/*
```

**SessionStart token reduction:** ~2,450 (both disableable hook-deliver rules). Path-scoped categories contribute zero baseline cost regardless — disabling them adds declarative guarantees but no SessionStart savings.

### ML Project

Disable non-ML conventions while keeping training discipline:

```yaml
version: 1
disable:
  - swe/agent-model-routing
  - writing/*
```

**Rationale:** Project uses its own model routing; writing rules are out-of-scope. ML rules stay enabled for training discipline.

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
- [Onboarding: Rules Configuration](onboarding.md) — how to add this to an existing project
- [rules/_manifest.yaml](../rules/_manifest.yaml) — machine-readable rule taxonomy (auto-generated)
- [Example Configuration](../claude/config/praxion-rules.yaml.example) — template shipped by Praxion; copy to your project's `.claude/praxion-rules.yaml` and edit the `disable:` list
