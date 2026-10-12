---
id: dec-453
draft_id: dec-draft-a0a1950f
title: rules/CLAUDE.md is the rules tree's directory guide, not a core always-loaded rule
status: accepted
category: architectural
date: 2026-10-11
summary: "`rules/CLAUDE.md` leaves the core rule set: the manifest generator skips it like a catalog README, the installer stops linking it into `~/.claude/rules/` (the stale-symlink sweep removes existing links), and Claude Code loads it on demand as a nested CLAUDE.md when a session touches `rules/`. The core set becomes four rules; every session and every subagent spawn in every project stops paying ~840 tokens of rules-authoring notes."
tags: [rules, core-protection, token-budget, always-loaded, installer, manifest, startup-context]
made_by: fperez
agent_type: orchestrator
branch: main
pipeline_tier: Lightweight
affected_files:
  - rules/CLAUDE.md
  - rules/_manifest.yaml
  - scripts/regenerate_rules_manifest.py
  - scripts/test_regenerate_rules_manifest.py
  - scripts/measure_token_budget.py
  - scripts/test_measure_token_budget.py
  - hooks/test_inject_rules.py
  - eval/scripts/inheritance_probe.py
  - docs/rules-taxonomy.md
  - cursor/config/export-cursor-rules.py
  - install_cursor.sh
affected_reqs: []
supersedes: null
superseded_by: null
re_affirms: null
re_affirmed_by: null
retired_by: null
supersedes_in_part: [dec-167, dec-168]
superseded_in_part_by: null
dissent: "A user editing their own project rules in a managed project loses the global reminder to load rule-crafting and to respect the always-loaded budget."
---

## Context

The startup-context spike (`docs/independent-analysis/startup-context-diet-research.md`) measured every token a new session pays before work begins. `rules/CLAUDE.md` was one of five core always-loaded rules (dec-167, dec-168): the installer symlinked it into `~/.claude/rules/`, so its 837 tokens, notes on how Praxion's own rules tree is organised and edited, loaded in every session of every project on the machine and in every subagent spawn. About a hundred directories on the author's machine are not Praxion-managed and still received it.

The file fails the admission test it states itself: an always-loaded token must apply in more than 30% of sessions or be unconditionally relevant. Its content applies only when someone edits Praxion's `rules/` tree. dec-166 and dec-167 classified it as core because it was always-loaded when the taxonomy was drawn, not because a session outside this repository needs it. Claude Code already loads a `CLAUDE.md` in a subdirectory of the working directory on demand (on Read, Write or Edit of a file there), which is exactly the scope this content needs.

## Decision

`rules/CLAUDE.md` is the rules tree's directory guide, not a rule:

- `scripts/regenerate_rules_manifest.py` skips `CLAUDE.md` inside the rules tree as it skips `README.md`, and its expected core set drops the `CLAUDE` id. The manifest lists 23 rules with four core.
- The installer's manifest-driven `link_rules` no longer links it, and `sweep_stale_rule_symlinks` removes the existing `~/.claude/rules/CLAUDE.md` link on the next install (Claude and Cursor installers alike). The optional Cursor exporter skips it too; the Codex rules bridge already did.
- The file carries no rule frontmatter. In this repository it loads on demand as a nested `CLAUDE.md`, worktrees included.
- `measure_token_budget.py` stops counting the repository's own copy as always-loaded, and keeps counting a stale global link until a reinstall removes it, because the harness still loads that link.

## Considered Options

### Option 1: Keep it core (status quo)

Pros: no change; the authoring notes are visible to anyone editing rules anywhere. Cons: 837 tokens in every session and spawn of every project, for content that applies to one repository; it contradicts the budget rule it carries.

### Option 2: Make it path-scoped (`paths: ["rules/**"]`)

Pros: stays a rule, loads only when `rules/**` is touched. Cons: a path glob matches a managed project's own `rules/` directory too, where Praxion's tree notes are wrong; the installer would still link it everywhere; it keeps a directory guide in the rule family.

### Option 3: Directory guide loaded on demand (chosen)

Pros: zero resident cost outside this repository; the harness's own nested-CLAUDE.md loading gives the exact scope; consistent with `scripts/CLAUDE.md`, which already works this way. Cons: a managed project editing its own rules no longer sees the reminder; the `rule-crafting` skill's description carries that trigger instead.

## Consequences

Positive:
- Every session and every subagent spawn in every project sheds 837 tokens (current-generation tokenizer; 595 on the gate's default ruler).
- The core set is the four rules that encode the operating contract.

Negative:
- `docs/rules-taxonomy.md`, the eval inheritance probe and four test files change with it.
- Machines keep the stale link until the next `install.sh` run. The measurement counts the link honestly in the meantime.

## Disconfirmation

- **Falsifier:** agents editing Praxion's `rules/` tree start skipping the `rule-crafting` skill or the budget measurement, because the guide no longer arrives before the first edit. The trigger that would show it: a rule change that lands without a `measure_token_budget.py` reading, or a sentinel finding on rule shape that the guide would have prevented.
- **Steelmanned runner-up:** Option 2 keeps the guide inside the rule system's own loading and lets the manifest govern it, so one mechanism (rules) owns all rule-tree guidance instead of splitting it between rules and nested CLAUDE.md files.
- **Reversal trigger:** Claude Code stops loading nested `CLAUDE.md` files on demand, or managed projects start editing Praxion-shaped rule trees of their own, at which point a global guide earns its place again.

## Prior Decision

dec-167 and dec-168 each listed `rules/CLAUDE.md` among the core always-loaded rules. This decision narrows only that membership clause in both. dec-167's hook-delivered blacklist mechanism and its symlink delivery for the remaining core and path-scoped rules stay in force. dec-168's rule that `core: true` frontmatter is the single source of truth for non-disableability also stays in force, now over four core rules.
