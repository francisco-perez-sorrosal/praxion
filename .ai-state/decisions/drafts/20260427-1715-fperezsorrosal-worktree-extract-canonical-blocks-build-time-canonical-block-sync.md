---
id: dec-draft-26a0b592
title: Build-time canonical-block sync over runtime bash injection
status: proposed
category: architectural
date: 2026-04-27
summary: Eliminate four-block byte-identical duplication between onboard-project.md and new-project.md via canonical files + sync script + pre-commit enforcement; reject runtime !-injection because ${CLAUDE_PLUGIN_ROOT} expansion in command bodies is unverified and policy-fragile.
tags:
  - shipped-artifacts
  - duplication
  - canonical-blocks
  - pre-commit-hook
  - onboarding
  - build-time
  - tech-debt
  - td-001
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - claude/canonical-blocks/agent-pipeline.md
  - claude/canonical-blocks/compaction-guidance.md
  - claude/canonical-blocks/behavioral-contract.md
  - claude/canonical-blocks/praxion-process.md
  - scripts/sync_canonical_blocks.py
  - scripts/git-pre-commit-hook.sh
  - commands/onboard-project.md
  - commands/new-project.md
  - hooks/test_onboard_praxion_block.py
---

## Context

The two flagship onboarding commands — `commands/onboard-project.md` (existing-project onboarding) and `commands/new-project.md` (greenfield bootstrap) — embed four byte-identical Markdown blocks that the commands inject into a user's `CLAUDE.md`: §Agent Pipeline (~1,818 bytes), §Compaction Guidance (~421 bytes), §Behavioral Contract (~843 bytes), §Praxion Process (~880 bytes). Total duplicated content: ~3,962 bytes per file, ~7,924 bytes across both files.

Today's mirror discipline is enforced by a single test (`hooks/test_onboard_praxion_block.py`) that covers only the §Praxion Process block, and by author care. The other three blocks rely entirely on author discipline. The tech-debt ledger logged this as `td-001` (severity: important; class: duplication; owner-role: implementation-planner) on 2026-04-27, with the suggested fix to extract canonical blocks to a single source of truth at `claude/canonical-blocks/<slug>.md`.

The architecture phase must choose the extraction mechanism. Three options were on the table:

- **A. Runtime `!`-injection** — `` !`cat ${CLAUDE_PLUGIN_ROOT}/claude/canonical-blocks/<slug>.md` `` placeholders in both command files. Single source of truth at runtime; both commands carry the same one-line placeholder.
- **B. Build-time compilation** — canonical Markdown files plus a sync script (`scripts/sync_canonical_blocks.py`) that detects drift (`--check`) or rewrites embedded blocks (`--write`). Pre-commit hook enforces sync. Both commands continue to embed the full block content; the duplication is structurally pinned to the canonical files.
- **C. Hybrid** — B as the safety net, A as the primary mechanism gated on an empirical verification test confirming `${CLAUDE_PLUGIN_ROOT}` expansion works in `` !`...` `` injection.

Two pieces of evidence shaped the decision:

1. The researcher (verified pre-architecture) found **zero precedent** for `${CLAUDE_PLUGIN_ROOT}` inside command-body `` !`...` `` injection in the entire codebase. The only documented use of `${CLAUDE_PLUGIN_ROOT}` is in `hooks/hooks.json`. The official Claude Code docs do not explicitly confirm `${CLAUDE_PLUGIN_ROOT}` expansion in command-body bash injection. This is unverified ground.
2. The `disableSkillShellExecution` managed-settings flag — used in enterprise-managed Claude Code installations — replaces all `` !`...` `` blocks with `[shell command execution disabled by policy]`. Option A breaks under this policy; Option C degrades to B; Option B is unaffected.

## Decision

**Adopt Option B: build-time compilation with pre-commit enforcement.**

The four canonical blocks live as standalone files at `claude/canonical-blocks/<slug>.md`. A new stdlib-only Python script `scripts/sync_canonical_blocks.py` is invokable in three modes (`--check`, `--write`, `--dry-run`). The pre-commit hook runs `--check` whenever a canonical-block file or one of the two command files is staged; on drift, the commit is blocked with a remediation message naming `python3 scripts/sync_canonical_blocks.py --write && git add ...` as the fix.

The pre-commit check is **blocking, not auto-fixing** — matching the ergonomic of the existing `check_shipped_artifact_isolation.py` hook delegation. The maintainer sees the diff before staging, never has files modified mid-commit.

The path shape `claude/canonical-blocks/<slug>.md` is chosen over alternatives because (a) `claude/config/` already exists as a precedent, (b) the directory is outside the `commands` glob in `plugin.json` so files are not exposed as slash commands, (c) it matches the suggestion in the td-001 ledger entry, (d) `claude/` is shipped as part of the plugin tree without manifest changes.

## Considered Options

### Option A — Runtime `!`-injection

Both commands carry `` !`cat ${CLAUDE_PLUGIN_ROOT}/claude/canonical-blocks/<slug>.md` `` placeholders. Output replaces the placeholder before the LLM sees the rendered command body.

**Pros:**
- Single source of truth at runtime — both commands literally read the same canonical file at invocation time.
- No on-disk visual debt — command files become smaller and free of duplication.
- No build step — maintainers edit canonical files only; commands always reflect the latest.

**Cons:**
- `${CLAUDE_PLUGIN_ROOT}` expansion in `` !`...` `` injection is **unverified** for command bodies. The only confirmed usage is in `hooks/hooks.json`. If verification fails (or a future Claude Code change breaks it), every onboarded user gets a literal placeholder instead of the block content — a silent, severe regression.
- `disableSkillShellExecution` (managed enterprise setting) replaces the placeholder with `[shell command execution disabled by policy]`. Hard-failure mode in any enterprise install.
- Verification cost: the architect would need to run a scratch command to test expansion before committing to this mechanism. Even if it passes today, future Claude Code updates could regress without our knowledge.
- New Claude Code mechanism dependency that the rest of Praxion does not use elsewhere.

### Option B — Build-time compilation (chosen)

Canonical files + sync script + pre-commit enforcement. Embedded blocks are rewritten by `--write`; drift is detected by `--check`.

**Pros:**
- Zero runtime risk — works in every environment (clone install, marketplace install, dev mode, enterprise-managed).
- No Claude Code mechanism dependency — pure build-time mechanics using stdlib Python.
- Matches existing precedents (`scripts/finalize_adrs.py`, `scripts/render_claude_md.py`, `scripts/check_shipped_artifact_isolation.py`). Operators already know this pattern.
- Mechanically enforceable — the pre-commit hook is the structural guarantee. Author discipline is no longer load-bearing.
- Bypass via `--no-verify` is a known operator escape hatch consistent with every other pre-commit check.
- Test extension is straightforward — the existing `_extract_block_section` helper in `hooks/test_onboard_praxion_block.py` already does the work; adding a byte-identity assertion against `claude/canonical-blocks/<slug>.md` is a one-line extension per block.

**Cons:**
- Visual debt remains on disk — both command files still contain the duplicated text. Readers may believe the duplication is unmanaged. Mitigation: a comment in each block section names the canonical file as the source of truth.
- Maintainers learn a new sync command (`scripts/sync_canonical_blocks.py --write`). One-command ergonomic cost.
- Pre-commit hook gets one more check, slightly increasing the latency of every commit that touches the relevant files.
- Hook bypass via `--no-verify` allows drift to land. Mitigated by the test (when it runs in CI, deferred follow-on) and by the code review surface.

### Option C — Hybrid

B as the safety net, A as the primary mechanism if a verification test passes.

**Pros:**
- Best of both worlds when A works.
- Falls back to B cleanly when A is disabled by policy or the mechanism is missing.

**Cons:**
- Three moving parts: the canonical files, the sync script, and the runtime fallback wiring. Plus a verification test that becomes a permanent CI fixture.
- Operator mental model gets harder: "which path is active right now?" — the answer depends on the runtime environment.
- All of B's costs (sync script, hook check) plus the additional surface of A's risk if verification regresses post-merge.
- Premature complexity: the cost is paid up-front; the benefit (visual cleanliness) is realized only in the A-active path, which is the riskiest path.

## Consequences

**Positive:**

- Structural duplication is eliminated; future drift is mechanically prevented at commit time.
- The mechanism uses only stdlib Python and existing precedent — no new dependencies, no new mental models.
- Works identically in clone install, marketplace install, dev mode, and enterprise-managed environments.
- The byte-identical guarantee becomes a unit-testable contract; the existing test file extends naturally.
- The fix sets a reusable pattern: future shipped artifacts that need cross-file consistency can adopt the same `<artifact>/canonical-<concept>/<slug>.md` + `scripts/sync_<concept>.py` shape.

**Negative:**

- Visual debt on disk remains — both command files still contain the duplicated block content. This may confuse readers who do not realize the duplication is structurally pinned. Mitigation: a one-line comment in each `## §<Block> Block` section names the canonical file.
- Pre-commit hook bypass is possible. Acknowledged risk; CI integration of the sync check is a sensible follow-on.
- Adding a new directory `claude/canonical-blocks/` slightly grows the install surface. Marginal cost; consistent with existing structure.

**Operational:**

- Maintainers editing a canonical block: edit `claude/canonical-blocks/<slug>.md`, run `python3 scripts/sync_canonical_blocks.py --write`, stage all three files (canonical + both commands), commit.
- Maintainers tempted to edit a command file directly: pre-commit hook catches the drift, points at the canonical file, maintainer redoes the edit there. Slight friction; correct behavior is reinforced.
- A future architectural pass could remove the on-disk visual debt by switching to Option A *if* `${CLAUDE_PLUGIN_ROOT}` expansion in command bodies is empirically verified and the enterprise-policy fallback is acceptable. That would be a separate ADR.

**Decisions deferred to follow-on work:**

- CI integration of `sync_canonical_blocks.py --check` (separate PR; out of scope here).
- Adding `claude/canonical-blocks/` to `SHIPPED_ROOTS` in `check_shipped_artifact_isolation.py` (small extension; the implementer should make this change as part of this work — flagged in `SYSTEMS_PLAN.md`'s Risk Assessment).
- Adding `hooks/test_onboard_praxion_block.py` to CI (separate concern; raised by researcher; not in scope).
