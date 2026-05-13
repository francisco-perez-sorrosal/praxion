---
id: dec-166
title: Frontmatter-metadata taxonomy for rules; no directory rename
status: accepted
category: architectural
date: 2026-05-13
summary: Express the rules taxonomy (core / blacklistable / domain) via frontmatter and a generated `rules/_manifest.yaml` rather than reorganizing directories, preserving zero blast radius for broadcast rules.
tags: [rules, taxonomy, frontmatter, blacklist, token-budget]
made_by: agent
agent_type: systems-architect
branch: worktree-rules-reorg-blacklist
pipeline_tier: full
affected_files:
  - rules/swe/agent-behavioral-contract.md
  - rules/swe/swe-agent-coordination-protocol.md
  - rules/swe/agent-intermediate-documents.md
  - rules/swe/adr-conventions.md
  - rules/swe/memory-protocol.md
  - rules/swe/agent-model-routing.md
  - rules/swe/vcs/git-conventions.md
  - rules/CLAUDE.md
  - rules/_manifest.yaml
  - scripts/regenerate_rules_manifest.py
affected_reqs:
  - REQ-01
  - REQ-05
  - REQ-06
---

## Context

Praxion ships 22 rule files; 8 are always-loaded (~15.3k tokens) and 14 are path-scoped. The user has asked for two things:

1. A richer semantic taxonomy for rules than the current flat `swe/ml/writing/` layout.
2. A per-project blacklist mechanism so projects can suppress rules they don't need.

The user clarified that "directory = semantic grouping" and "core-ness (non-disableable) is an orthogonal attribute." This means the taxonomy must express two independent axes: semantic group AND blacklistability.

Research (`.ai-work/rules-reorg-blacklist/RESEARCH_FINDINGS.md`) catalogues five taxonomy options. The five top-referenced rules (`agent-behavioral-contract.md` 20 refs, `id-citation-discipline.md` 14, `swe-agent-coordination-protocol.md` 12, `agent-intermediate-documents.md` 12, `adr-conventions.md` 9) carry 30-50 file-update cost if renamed; sentinel BC03 and `auto_complete_install.py:115` hardcode the path of `rules/swe/agent-behavioral-contract.md`.

A directory-based taxonomy that expresses both axes simultaneously requires a filesystem cross-product (`rules/core/swe/...`, `rules/blacklistable/swe/...`) which the user explicitly rejected. The alternatives are:

- Rename files into semantic dirs (Options A/B/C in research): clean filesystem, but 30-50 file references break.
- Frontmatter metadata (Option E): zero blast radius, semantic group + core-ness encoded as fields.

## Decision

The rules taxonomy is expressed via:

1. **Frontmatter on each rule** carrying `core: true|false` and (informationally) `load: always_on|path_scoped` and `install: symlink|hook-deliver`.
2. **A generated `rules/_manifest.yaml`** committed to git, listing every rule with its taxonomy attributes. The manifest is the machine-readable source consumed by the installer, the SessionStart hook, and (optionally) Codex's exporter.
3. **No existing rule file is renamed or moved.** All current paths (especially the 5 broadcast rules' paths) are preserved.

Future new rules MAY land in new semantic subdirectories (e.g., `rules/swe/artifacts/`, `rules/swe/pipeline/`) when this is natural and no external references exist yet — this is additive, not retroactive. Existing rules stay where they are.

The semantic group is implied by the existing directory (`swe/`, `ml/`, `writing/`, `swe/vcs/`); the core-ness is explicit in frontmatter. Two axes, two mechanisms.

A new `scripts/regenerate_rules_manifest.py` walks `rules/`, reads frontmatter, and emits `rules/_manifest.yaml` with a `--check` mode (analogous to `scripts/sync_canonical_blocks.py`) that fails CI if the committed manifest drifts from filesystem reality.

## Considered Options

### Option 1 — Domain-first directory rename (`rules/core/`, `rules/protocol/`, `rules/conventions/`)

Move the 5 core always-loaded rules to `rules/core/`, blacklistable always-loaded rules to `rules/protocol/`, etc.

**Pros:** Filesystem-visible taxonomy; `ls rules/` shows the taxonomy directly.
**Cons:** Renames the 5 broadcast rules → 30-50 file updates in agents/skills/commands/canonical-blocks. Breaks sentinel BC03 + `auto_complete_install.py:115` sentinel. High coordination cost.

### Option 2 — Function-first rename (`rules/philosophy/`, `rules/pipeline/`, `rules/decisions/`, `rules/artifacts/`, ...)

Rename every rule into a function category.
**Pros:** Maximally clean taxonomy.
**Cons:** Renames ALL rules → maximal blast radius. Every rule path in every agent/skill/command updates. Rejected on cost.

### Option 3 — Frontmatter-metadata taxonomy (chosen)

Each rule's frontmatter declares `core: true|false`. A generated manifest aggregates the taxonomy. No files move.

**Pros:** Zero blast radius. Sentinel BC03 + `auto_complete_install.py:115` keep working unchanged. All 30-50 reference sites stay valid. Core-ness is declared next to the rule (most discoverable place for rule authors). Pattern composes with the existing `codex: portability: claude_only` frontmatter.

**Cons:** Semantic groups are not visible in `ls rules/swe/` — users see a flat directory mixing core and blacklistable rules. Mitigation: `rules/_manifest.yaml` is human-readable + committed; `docs/rules-taxonomy.md` (new) is the entry point. The dashboard could also surface this view.

### Option 4 — Hybrid (Option 3 + additive nesting for new rules)

Take Option 3 as the default; permit new rules to land in semantic subdirectories when no cross-references exist yet (e.g., a future `rules/swe/artifacts/shipped-artifact-isolation.md` IF we were creating it now). Existing rules don't move.

**Pros:** Combines metadata clarity with eventual filesystem expressiveness as new content arrives.
**Cons:** Slightly more permissive — invites churn over time. Mitigated by `regenerate_rules_manifest.py` always reading frontmatter regardless of directory.

**Decision:** Option 3 with the additive nesting clause from Option 4. Existing rules stay. New rules MAY use semantic subdirs.

## Consequences

**Positive:**

- Zero blast radius across the 30-50 reference sites that would otherwise need updating.
- Sentinel BC03 and `auto_complete_install.py:115` sentinel checks continue to work without code changes.
- Rule authors declare core-ness alongside the rule content, not in a separate registry.
- The manifest is machine-readable and committed — accessible to installers, hooks, dashboard, and Codex bridge.
- Pattern is composable with `codex: portability: ...` frontmatter already in use.

**Negative:**

- The semantic taxonomy is not visible by listing the directory; users must read frontmatter or consult `_manifest.yaml`. Discoverability is partly external (a `docs/rules-taxonomy.md` document and the manifest itself).
- Two artifacts to keep in sync: rule frontmatter and generated manifest. Mitigated by `--check` mode + CI.

**Operational:**

- Implementation phase A produces the manifest + generator script with `--check` mode, integrated into pre-commit and CI.
- Adding a new rule requires: add frontmatter, run `python3 scripts/regenerate_rules_manifest.py`, commit both rule and updated manifest. Mirrors the `sync_canonical_blocks.py` workflow.
- Removing a rule: delete the rule file, regenerate, commit.
- The `--check` failure produces a clear "manifest drift detected; run regenerate_rules_manifest.py" message.

**Cross-cutting:**

- This decision pairs with `dec-167` (hook-delivered blacklist mechanism) — the manifest is consumed by both the installer and the new hook.
- The decision implicitly supports `dec-168` (frontmatter as single source of truth for core protection).
