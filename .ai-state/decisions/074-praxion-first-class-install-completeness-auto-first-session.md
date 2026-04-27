---
id: dec-074
title: Install-path completeness via first-session auto-completion + retain /praxion-complete-install
status: proposed
category: architectural
date: 2026-04-27
summary: Marketplace plugin install becomes self-sufficient via a SessionStart auto-completion hook that converges all install paths on the same end state; /praxion-complete-install is retained as an explicit re-invocation path.
tags: [install, marketplace, channel-d, auto-install, hook, idempotency, no-asymmetry]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - hooks/auto_complete_install.py
  - hooks/hooks.json
  - scripts/render_claude_md.py
  - install_claude.sh
  - commands/praxion-complete-install.md
affected_reqs: [REQ-09, REQ-10, REQ-11, REQ-12, REQ-13, REQ-15]
---

## Context

Praxion currently has three install paths with asymmetric end states:

1. **Clone install** (`./install.sh code`): produces `~/.claude/CLAUDE.md` (rendered from `claude/config/CLAUDE.md.tmpl` with personal-info substitution), `~/.claude/rules/**` symlinks, `~/.local/bin/**` script symlinks. Full Channel D.
2. **Marketplace + complete-install** (`claude plugin install i-am@bit-agora` then `/praxion-complete-install`): produces `~/.claude/rules/**`, `~/.local/bin/**`. Does NOT produce `~/.claude/CLAUDE.md` (the rendering step is in `install.sh code` only). Partial Channel D.
3. **Marketplace only** (`claude plugin install i-am@bit-agora`): produces NONE of these. The orchestrator has zero Praxion process awareness in non-Praxion projects. No Channel D.

The user has directed: "the marketplace plugin install should be made fully self-sufficient" and "the asymmetry... is to be eliminated, not designed around." The directive is explicit: plugin install must result in the same end state as clone install.

The Key Decision Question posed in the task: deprecate `/praxion-complete-install` (fold logic into auto-install) vs. retain it as a separate finisher with stronger nudges.

Claude Code's plugin manager has no `PostInstall` event today (verified against the hooks taxonomy in the official docs); the only reliable trigger for "run something after plugin install" is the operator's first session start after the plugin is present.

## Decision

Implement first-session auto-completion via a new `SessionStart` hook (`hooks/auto_complete_install.py`) AND retain `/praxion-complete-install` as an explicit re-invocation path. The hook detects missing global surfaces (`~/.claude/CLAUDE.md` not a Praxion symlink OR `~/.claude/rules/swe/agent-behavioral-contract.md` absent OR marker file absent) and runs the completion logic non-interactively (using `git config user.name`/`user.email` defaults) or interactively (single confirm prompt with 30-second timeout that accepts defaults on timeout). On success, writes a marker file `~/.claude/.praxion-complete-installed`. Subsequent sessions fast-skip in <50 ms via the marker.

To avoid duplication, `install_claude.sh:223` `render_claude_md()` (currently an inline Python heredoc) is extracted to `scripts/render_claude_md.py` and is called by both the existing clone-install flow and the new auto-completion hook. The Bash function delegates to the script. No behavior change for clone install.

`/praxion-complete-install` is retained — its description and leading paragraph are updated to communicate that it is no longer the standard finisher (auto-install handles that case) but remains usable for reconfiguration (`--reconfigure` forces re-prompt), recovery from a corrupted state, or explicit operator preference. The command's underlying logic is unchanged.

## Considered Options

### Option A — Deprecate `/praxion-complete-install`, fold into auto-install only

A single auto-install hook handles everything; the explicit command is removed (or aliased to a no-op with deprecation message). Operator UX is simpler at first install; the explicit re-invocation entry point is gone.

**Pros**: one fewer command to maintain; honors the no-asymmetry directive most literally; aligns with "fully self-sufficient" framing.
**Cons**: removes the explicit re-invocation path used for reconfiguration and recovery; operators who want to re-run setup must remember an env-var or recreate state to re-trigger the auto-install; reduces operator agency.

### Option B — Retain `/praxion-complete-install`, no auto-install (status quo + nudges)

First-session hook detects missing surfaces and emits a strong nudge (or blocks via exit-2 with a clear pointer). Operator must run the command. Two-step UX.

**Pros**: preserves separation between Claude Code's plugin idiom and Praxion's user-level setup; respects "plugin install does only what plugin install does."
**Cons**: the asymmetry persists during the period between plugin install and operator running the finisher; the no-asymmetry directive becomes "the asymmetry is healable on first session" rather than truly eliminated; operators in non-interactive environments cannot run the command.

### Option C — Auto-completion + retain command for explicit re-invocation (selected)

First-session hook auto-completes; `/praxion-complete-install` survives as an explicit re-invocation entry point with `--reconfigure` semantics. Auto-install is non-load-bearing for the command's existence; the command is non-load-bearing for correctness.

**Pros**: directive satisfied (asymmetry eliminated on first session); command preserved for reconfiguration / recovery / power-user use; both interactive and non-interactive environments handled.
**Cons**: maintains one more hook; one more env var (`PRAXION_DISABLE_AUTO_COMPLETE`); slight first-session latency on first-ever Praxion install (~3-5 seconds for symlink + render, comparable to existing `/praxion-complete-install` runtime).

### Option D — Bundle CLAUDE.md rendering into the plugin itself

Move the personal-info substitution into a hook that runs on plugin install. Avoids first-session timing entirely.

**Pros**: install completes the moment the plugin lands.
**Cons**: Claude Code does not expose a plugin-install event; this would require a separate mechanism (e.g., a startup hook on the plugin's first MCP-server launch). Couples the install flow to MCP-server lifecycle, which is unrelated. Rejected as architectural over-coupling.

## Consequences

**Positive**:

- The marketplace plugin install becomes fully self-sufficient: the operator's first Claude Code session converges on the same end state as a clone install. The bottom-right cell of the 9-cell matrix (marketplace-only, non-onboarded, no Channel D) is eliminated after first session.
- `/praxion-complete-install` remains usable for reconfiguration (`--reconfigure`), recovery (corrupted symlinks), or explicit operator preference. Backward compatibility preserved.
- `render_claude_md` extraction to `scripts/render_claude_md.py` is a structural-beauty improvement: removes a Python heredoc from a Bash file; enables reuse by the hook without duplication.
- Personal-info substitution gracefully falls back to git-config defaults when interactive input is unavailable (CI, headless containers, non-interactive shells).

**Negative**:

- One additional `SessionStart` hook in `hooks.json`. Fast-path adds <50 ms to first session start; subsequent sessions add <5 ms (marker file stat).
- First-session UX includes a (single) confirm prompt with 30-second timeout-accept. Operators may be surprised the first time; subsequent sessions are silent.
- An operator with no `git config user.email` set lands literal `anon@unknown` placeholders; the override prompt surfaces this. Acceptable: the operator can `--reconfigure` later.
- The marker file (`~/.claude/.praxion-complete-installed`) is operator-scoped state outside of any project; deletion (manual or by `--complete-uninstall`) re-arms the auto-install. Operators must understand this.

**Operational**:

- Auto-install hook is sync `async: false` with a 5-second timeout for the fast path and a 30-second timeout for the prompt path. Always exits 0 (never blocks session start).
- Logging: stderr only on action; stdout silent on no-op.
- Rollback: remove `auto_complete_install.py` from `hooks.json`; delete the script. The clone-install path and `/praxion-complete-install` command are unchanged.
- Idempotency: marker-file detection + symlink-target verification. Re-running on an already-completed install is a no-op.

## Related Decision

This ADR is the install-completeness counterpart to `dec-075` (Praxion-as-First-Class — process-driven development with universal rule-inheritance). dec-075 establishes the principle and the rule-inheritance mechanism (Workstream A); this ADR resolves the install-path completeness question (Workstream B) that dec-075 implicitly assumed.

The two ADRs are coupled by the requirement that Channel D be universal across install paths — which dec-075 stated as an assumption and this ADR delivers as a mechanism. This ADR's auto-install hook is the mechanism by which dec-075's three-layer architecture becomes universally available across install paths. Without this ADR, the Workstream A design would have a gap for marketplace-only operators in non-onboarded projects (no L1, no Channel D). The two records are intentionally split because they address distinct concerns (process enforcement vs. install topology) and may evolve independently. Neither supersedes nor re-affirms the other in the formal ADR-conventions sense; they are coupled-but-independent.
