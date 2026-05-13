---
id: dec-168
title: Frontmatter `core: true` is the single source of truth for non-disableability
status: accepted
category: behavioral
date: 2026-05-13
summary: A rule's `core: true` frontmatter is the canonical declaration of non-disableability; the generated manifest derives from it; the SessionStart hook refuses to suppress any rule marked core, emitting a stderr warning on attempted disable.
tags: [rules, core-protection, frontmatter, hook, invariant]
made_by: agent
agent_type: systems-architect
branch: worktree-rules-reorg-blacklist
pipeline_tier: full
affected_files:
  - rules/swe/agent-behavioral-contract.md
  - rules/swe/swe-agent-coordination-protocol.md
  - rules/swe/agent-intermediate-documents.md
  - rules/swe/adr-conventions.md
  - rules/CLAUDE.md
  - rules/_manifest.yaml
  - hooks/inject_rules.py
  - scripts/regenerate_rules_manifest.py
affected_reqs:
  - REQ-04
  - REQ-06
---

## Context

The user explicitly stated: "core rules have to be there, yes or yes." The blacklist mechanism MUST refuse to disable core rules, even when the user requests it (typo, misunderstanding, or category-glob that incidentally includes a core rule).

There are several places this invariant could live:

- **Hard-coded list in `hooks/inject_rules.py`**: Simple but fragile — adding/removing core rules requires code changes.
- **A separate `rules/_core.yaml` registry file**: Explicit, but yet another artifact to keep in sync with the manifest.
- **Manifest `core: true/false`**: One artifact, but the manifest is generated FROM frontmatter — two layers between rule author and enforcement.
- **Frontmatter on each rule**: Closest to the rule itself; canonical declaration; everything else derives from this.

The architectural principle (per CLAUDE.md "Context Engineering"): the right information must reach the right place at the right time, with one source of truth. Declarations should live where authors look first.

## Decision

**A rule's frontmatter `core: true` is the canonical declaration** that the rule is non-disableable. The generated `rules/_manifest.yaml` derives the `core` field by reading frontmatter; the SessionStart hook (`inject_rules.py`) reads the manifest to enforce the invariant.

Three layers:

1. **Source of truth**: Rule frontmatter. `core: true` or `core: false` (explicit).
2. **Derived artifact**: `rules/_manifest.yaml` aggregates the values. Committed; checked via `regenerate_rules_manifest.py --check` in CI and pre-commit.
3. **Enforcement**: `hooks/inject_rules.py` reads the manifest. When a project's blacklist resolves to any rule with `core: true`, the hook:
   - Removes that rule ID from the suppression set (the rule is still injected/loaded).
   - Emits a stderr warning naming the rule(s) and explaining that core rules cannot be disabled.
   - Continues processing the rest of the blacklist normally.

Failure mode: a rule without `core:` frontmatter at all is treated as `core: false` by the manifest generator. Explicit declaration is required for core protection. The `--check` mode in the manifest generator validates that the 5 core rules carry `core: true` (a hardcoded list in the generator script, not in the hook).

The 5 core rules at v1 are:

1. `rules/swe/agent-behavioral-contract.md` — the four behavioral non-negotiables; the entire Praxion philosophy operates on top of these.
2. `rules/swe/swe-agent-coordination-protocol.md` — pipeline tier table, calibration, delegation; Praxion without this is undifferentiated.
3. `rules/swe/agent-intermediate-documents.md` — `.ai-work/` and `.ai-state/` lifecycle; every pipeline agent depends on it.
4. `rules/swe/adr-conventions.md` — ADR format consumed by sentinel, finalize, multiple agents.
5. `rules/CLAUDE.md` — meta-rules; explains how rules work in the first place.

## Considered Options

### Option 1 — Hard-coded core list in `inject_rules.py`

```python
CORE_RULES = {
    "swe/agent-behavioral-contract",
    "swe/swe-agent-coordination-protocol",
    "swe/agent-intermediate-documents",
    "swe/adr-conventions",
    "CLAUDE",
}
```

**Pros:** Simple. Visible in hook code.
**Cons:** Two places (rule and hook) to update when adding a core rule. Drift risk. Rule author has no visibility into core-ness when reading the rule itself.

### Option 2 — Manifest as source of truth (no frontmatter)

Edit `_manifest.yaml` directly to set `core: true`. Skip frontmatter.
**Pros:** One artifact only.
**Cons:** Rule author reads the rule file and has no clue if it's core. The declaration lives away from the content. Doesn't compose with the existing convention of attributes-on-the-rule (e.g., `paths:`, `codex:`).

### Option 3 — Frontmatter authoritative, manifest derived (chosen)

Rule frontmatter sets `core: true|false`. Generator script reads frontmatter. Manifest is committed (so installer/hook don't need to regenerate at runtime). `--check` mode catches drift.

**Pros:** Single source of truth (the rule itself). Discoverable by rule authors. Pattern composes with existing `paths:` and `codex:` frontmatter. Manifest as derived artifact is committed so consumers don't need to regenerate.
**Cons:** Two artifacts on disk (rule frontmatter + manifest). Drift detection required. Mitigated by `--check` in pre-commit and CI.

## Consequences

**Positive:**

- Rule authors see `core: true` in the rule file — the most discoverable place.
- Adding a new core rule is one change: add the rule with `core: true` frontmatter, run `regenerate_rules_manifest.py`, commit both.
- The hook is mechanical: reads manifest, enforces invariant. No business logic about which rules are core embedded in code.
- The architecture mirrors how `codex: portability:` is handled — frontmatter as authoritative.

**Negative:**

- Drift between frontmatter and manifest is possible without enforcement. Mitigated by `--check` in pre-commit + CI; sentinel could optionally add a check.
- The manifest must be committed (it's a derived artifact). This is the same model as `DECISIONS_INDEX.md` (also derived, also committed).

**Operational:**

- Pre-commit hook: `python3 scripts/regenerate_rules_manifest.py --check` fails if drift detected; advice line "run regenerate_rules_manifest.py to update".
- CI: same check as a guard.
- Future addition: when sentinel scans rules, it could verify `core: true` rules carry the right paths (e.g., no core rule with `install: hook-deliver` — that combination would be incoherent).

**Behavioral (the warning):**

When a project tries to disable a core rule, the hook emits to stderr:

```
[inject_rules] WARNING: Core rule(s) cannot be disabled by .claude/praxion-rules.yaml:
  - swe/agent-behavioral-contract  (matched: agent-behavioral-contract)
  - swe/adr-conventions             (matched: swe/*)
These rules remain loaded. Remove them from `disable:` to silence this warning.
See docs/rules-taxonomy.md for the core rule list.
```

This warning is informative, non-fatal, and points the user to the relevant doc. The hook continues to process the rest of the blacklist normally.

**Cross-cutting:**

- Depends on `dec-166` (taxonomy by frontmatter and manifest) — this ADR specifies HOW the `core` axis works within that taxonomy.
- Consumed by `dec-167` (hook-delivered blacklist) — the hook implements this invariant.
