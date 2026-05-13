---
id: dec-167
title: Hook-delivered blacklist for always-loaded rules; symlink-based for core and path-scoped
status: accepted
category: architectural
date: 2026-05-13
summary: Move blacklistable always-loaded rules out of the global symlink set and deliver them via a SessionStart hook reading a per-project `.claude/praxion-rules.yaml`; core rules and path-scoped rules continue using native symlinks.
tags: [rules, blacklist, hook, token-budget, sessionstart, additional-context]
made_by: agent
agent_type: systems-architect
branch: worktree-rules-reorg-blacklist
pipeline_tier: full
affected_files:
  - hooks/inject_rules.py
  - hooks/test_inject_rules.py
  - hooks/hooks.json
  - hooks/auto_complete_install.py
  - lib/install_shared.sh
  - rules/_manifest.yaml
  - .claude/praxion-rules.yaml
affected_reqs:
  - REQ-02
  - REQ-03
  - REQ-04
  - REQ-07
---

## Context

The user's stated motivation for the blacklist is token-cost reduction: "only use the rules that they need." The 8 always-loaded rules consume ~15.3k tokens; path-scoped rules cost 0 tokens until triggered. Therefore the token-reduction target is always-loaded rules specifically.

Claude Code's rule-loading mechanism reads `~/.claude/rules/**/*.md` at session start. This directory is **global** to all projects (verified by `ls ~/.claude/rules/`). Both Praxion installers (`install_claude.sh` and `auto_complete_install.py:_link_rules()`) create per-file symlinks into this global location.

The architectural constraint: there is no native Claude Code mechanism for per-project rule filtering (research thread 5). Any blacklist must be implemented in Praxion's own layer.

Research catalogues five mechanism options:

- **A (deny-list as `additionalContext`)**: behavioral suppression only; rules still in context window; no token reduction.
- **B (`PRAXION_DISABLE_*` env vars)**: behavioral suppression only; same problem; scales poorly (~15 flags).
- **C (symlink management)**: physical reduction, BUT mutates a global directory shared across all projects — race conditions when multiple sessions are open; broken for marketplace install which uses the plugin cache as a shared resource.
- **D (per-project install)**: physical reduction, BUT contradicts the global-symlink model.
- **E (manifest + hook-injected delivery)**: physical reduction; works for both install models.

The user's behavioral contract item "Surface Assumptions" requires me to be explicit: behavioral-only suppression (A, B) does not satisfy the spirit of the request. Only physical exclusion (C, D, or E) reduces tokens. C and D have hard incompatibilities. E is the remaining viable option.

## Decision

Adopt a **two-channel delivery** for rules:

1. **Channel 1 — Symlink (native Claude Code loading):**
   - Core always-loaded rules (per the taxonomy ADR `dec-166`): `agent-behavioral-contract.md`, `swe-agent-coordination-protocol.md`, `agent-intermediate-documents.md`, `adr-conventions.md`, `rules/CLAUDE.md`.
   - All path-scoped rules.
   - Symlinked into `~/.claude/rules/` exactly as today.

2. **Channel 2 — Hook delivery (`additionalContext` at SessionStart):**
   - Blacklistable always-loaded rules: `memory-protocol.md`, `agent-model-routing.md`, `vcs/git-conventions.md`.
   - NOT symlinked. Delivered via a new `hooks/inject_rules.py` SessionStart hook.

The new hook:

1. Reads `rules/_manifest.yaml` (under `$CLAUDE_PLUGIN_ROOT`) to learn which rules are blacklistable and have `install: hook-deliver`.
2. Reads `$CWD/.claude/praxion-rules.yaml` (if it exists) for the project's blacklist.
3. Resolves globs against the manifest (`ml/*` expands to all three ML rules; `swe/memory-protocol` matches one).
4. Enforces core protection: if the blacklist resolves to any rule with `core: true`, the hook removes it from the suppression set and warns to stderr.
5. Concatenates the rule bodies of the non-suppressed blacklistable rules under a `## Praxion Rules (auto-injected)` header.
6. Emits the result as `additionalContext`.

The installer (`link_rules()` in `lib/install_shared.sh` AND `_link_rules()` in `auto_complete_install.py`) is extended to read the manifest and skip rules with `install: hook-deliver` — these rules are physically not present in `~/.claude/rules/`.

The hook is registered in `hooks/hooks.json` as a synchronous SessionStart hook after `inject_memory.py`. Failure is non-fatal: malformed YAML or missing manifest produces empty `additionalContext` and a stderr warning, never blocks session start.

A new `PRAXION_DISABLE_RULE_INJECTION=1` env var disables the hook entirely (escape hatch consistent with the existing `PRAXION_DISABLE_*` family).

## Considered Options

### Option 1 — Behavioral-only deny list

Inject "ignore rules X and Y" into `additionalContext`. Rule text remains in context window.

**Pros:** Trivial implementation. No installer changes.
**Cons:** Does NOT reduce tokens. The user's motivation is token reduction; this satisfies the letter (a "blacklist exists") but not the spirit. Also behaviorally unreliable — Claude may still follow a loaded rule despite the instruction. Rejected.

### Option 2 — `PRAXION_DISABLE_*` env-var flags per rule

Extend the existing env-var pattern: one `PRAXION_DISABLE_<RULE>` flag per blacklistable rule.

**Pros:** Direct precedent (6 existing flags). Operators are familiar with it.
**Cons:** Same token-reduction failure as Option 1. Scales poorly: 15 blacklistable rules × 1 flag each = 15 flags to document. No category granularity without a new convention. Rejected as primary mechanism (will still exist as `PRAXION_DISABLE_RULE_INJECTION` escape hatch).

### Option 3 — Symlink management at SessionStart

A pre-session hook removes symlinks for blacklisted rules and re-creates them after.

**Pros:** Achieves physical token reduction.
**Cons:** Mutates a GLOBAL directory shared across all projects. If two Claude sessions are open on two different projects with different blacklists, they fight over the symlink set. Marketplace install path symlinks from plugin cache — removing a symlink affects all projects. BROKEN. Rejected.

### Option 4 — Hook-delivered (manifest + SessionStart hook), chosen

Blacklistable rules are not symlinked. They are delivered via `additionalContext` at SessionStart based on the project's blacklist.

**Pros:** Physical token reduction (rules not present in installed `~/.claude/rules/` AND not injected when blacklisted). Per-project blacklist lives in committed project config (`.claude/praxion-rules.yaml`). No global mutation. Works identically for user-level and marketplace install. Hook latency is ~50-200ms — well under 5s budget.

**Cons:** Architectural shift: blacklistable rules no longer use Claude Code's native rule-loading path. Users will see them under `## Praxion Rules (auto-injected)` header rather than mixed with `~/.claude/rules/`. Some confusion possible initially. Implementation complexity higher than Options 1/2.

## Consequences

**Positive:**

- Token cost reduction is real and measurable. A project disabling `vcs/git-conventions`, `memory-protocol`, and `agent-model-routing` reclaims ~13,783 chars ≈ 3,800 tokens of always-loaded context.
- No race conditions: per-project config lives in the project repo; hook runs per-session, reads project's config.
- Works identically for both install models.
- Composes with the existing hook patterns (`inject_memory.py`, `inject_worktree_banner.py`).
- The escape hatch (`PRAXION_DISABLE_RULE_INJECTION=1`) gives operators a fast off-switch.

**Negative:**

- A 4th SessionStart synchronous hook adds ~200ms latency. Existing total ~1s; new total ~1.2s; well under timeout.
- Blacklistable rules are no longer in `~/.claude/rules/` — diagnostic patterns that grep that directory will miss them. Mitigated by `docs/rules-taxonomy.md` documenting this and by the manifest being the source of truth.
- The taxonomy/install split (core vs blacklistable) is now operationally visible: looking at `~/.claude/rules/` shows only core+path-scoped, not the full set. Some users may find this confusing initially.

**Operational:**

- Hook failure is non-fatal — catches exceptions, returns empty `additionalContext`, logs to stderr. Cannot block SessionStart.
- Hook logs one line: `[inject_rules] Loaded 5 core rules; injected 2/3 blacklistable always-loaded rules (suppressed: memory-protocol)`. Visible in operator transcripts.
- Backward compatibility (REQ-01): A project without `.claude/praxion-rules.yaml` gets all blacklistable rules injected (zero behavior change vs current state).
- Phase ordering matters during rollout: installer must learn the new manifest format BEFORE the manifest is flipped to mark rules as `hook-deliver`. Otherwise existing symlinks remain stale. The migration plan in `SYSTEMS_PLAN.md` orders these steps correctly.

**Cross-cutting:**

- Depends on `dec-166` (frontmatter taxonomy + manifest) — the manifest is the data structure this mechanism reads.
- Depends on `dec-168` (core protection invariant) — the hook implements the invariant.
- Future v2 could extend this hook to blacklist path-scoped rules (by removing their symlinks) but that's out of scope for v1; path-scoped rules cost 0 tokens until matched, so token-reduction motivation doesn't apply.

**Security:**

- Trust model: same as `inject_memory.py`. Hook reads two YAML files from disk; no code execution. A malicious project blacklist cannot escalate; at worst it disables a rule (and core protection prevents disabling core rules).
- Resource bounds: I/O on two small files; bounded execution time; SessionStart timeout protects against hangs.
