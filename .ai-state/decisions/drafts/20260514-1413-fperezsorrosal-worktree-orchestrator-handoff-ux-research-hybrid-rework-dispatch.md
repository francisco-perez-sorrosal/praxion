---
id: dec-draft-88106752
title: "Hybrid rework dispatch — headless --bg default, opt-in --terminals visible, single script + notification hook"
status: proposed
category: architectural
date: 2026-05-14
summary: "Ship scripts/dispatch-reworks with two mutually-exclusive modes (--bg default, --terminals opt-in) plus a notification hook to close the headless-mode discovery loop; slash-command wrapper for symmetry with future deferred-manifest consumers."
tags: [rework-loop, dispatch, dx, claude-code, hooks, notifications]
made_by: agent
agent_type: systems-architect
branch: worktree-orchestrator-handoff-ux-research
pipeline_tier: lightweight
affected_files:
  - scripts/dispatch-reworks
  - hooks/notify_bg_session_state.py
  - commands/dispatch-reworks.md
  - agents/verifier.md
  - hooks/hooks.json
---

## Context

ROADMAP Topic 1 surfaced a UX friction at the end of the verifier-rework-loop pipeline: when the verifier emits a multi-row `REWORK_MANIFEST.md` and the main agent spawns N rework worktrees, the user currently has to manually open a fresh Claude Code session in each one and run `/resume-rework`. The user's words: *"three separate terminals, three separate sessions, three manual context-switches."* The rework loop is functional but the dispatch UX assumes the user enjoys juggling terminals.

Two rounds of research surfaced the available primitives:

1. **`claude --bg "<prompt>"` (Claude Code 2.1.139+)** starts a full detached Claude session in the current shell's cwd, monitored via the new `claude agents` TUI dashboard. The session is a complete conversation (slash commands work) and runs as a true background process. This is the headless path.

2. **`claude-cli://open?cwd=<path>&q=<encoded-prompt>` (Claude Code 2.1.91+)** is a registered macOS URI handler that opens a new terminal window (the user's last-used emulator — iTerm2, Ghostty, Terminal.app, etc.) with Claude running in the given cwd and the prompt pre-filled in the prompt box. The prompt is *not* auto-submitted; the user presses Enter. This is the visible path.

3. **`terminalSequence` hook output field (Claude Code 2.1.141)** allows a hook to emit terminal escape sequences (notification bell, macOS notification via iTerm2's `\x1b]9;<msg>\x07` sequence) when a session transitions through a lifecycle event. This makes background-session state changes discoverable without polling `claude agents`.

4. **Eliminated paths**: tmux fanout (dropped per user preference — `--bg` subsumes the headless need), `cursor` IDE terminal-pane automation (research confirmed `tasks.json runOn: folderOpen` is broken in Cursor with no fix timeline; no MCP/URI path exists), AppleScript window automation (macOS-only, scattered windows with no unified monitoring).

The user signed off on a *hybrid* approach during conversation: ship both `--bg` (headless, default) and `--terminals` (visible, opt-in) modes behind one script entry point, plus the notification hook to close the discovery loop for the default mode. This ADR codifies that decision.

## Decision

Ship **one script with two modes plus a notification hook**:

1. **`scripts/dispatch-reworks`** — single entry point. Flag-routed:
   - `--bg` (default): for each row in `REWORK_MANIFEST.md`, run `(cd <rework-worktree> && claude --bg "/resume-rework" --name "rework: <slug>")`. Sessions land in `~/.claude/daemon/` and are observable via `claude agents --cwd $(pwd)`.
   - `--terminals` (opt-in): for each row, run `open "claude-cli://open?cwd=<encoded-path>&q=%2Fresume-rework"`. Opens N external terminal windows; user presses Enter in each.
   - `--dry-run` (orthogonal to both): print the dispatch plan and exit without firing.
   - Modes are mutually exclusive; passing both is an error.

2. **`hooks/notify_bg_session_state.py`** — ~25–40-line Stop-event hook that fires a macOS-visible notification when a session whose display name starts with `rework: ` transitions to a notable state. Primary mechanism is the `terminalSequence` hook output field (Claude Code 2.1.141); fallback is shelling out to `osascript -e 'display notification …'` if `terminalSequence` is not honored on the running version. Registered in `hooks/hooks.json`; respects `PRAXION_DISABLE_OBSERVABILITY` opt-out.

3. **`commands/dispatch-reworks.md`** — thin slash-command wrapper invoking the bash script with passthrough flags. Provides discoverability via the `/`-command surface and establishes the template for the future `/skill-genesis-review` (ROADMAP Topic 3) and any other deferred-manifest consumer.

4. **`agents/verifier.md` Phase 12.5 message update** — rewrite the user-facing one-liner from *"Run `/resume-rework` in each fresh session"* to a message that surfaces both modes and points the user at the dispatch script.

The single entry-point (one script, not two) is a deliberate design property: it lets the user toggle between modes by adding/removing one flag, without having to remember two script names.

**Activation:** no — single-feature Lightweight-tier change; no cross-cutting structural decisions; no security/performance/simplicity tension warranting a multi-lens sweep. The decision was settled in user conversation before this ADR was authored; the architect's role is to codify, not re-litigate.

## Considered Options

### A. Headless only — `--bg` loop, no visible mode

**Pros:** smallest script (~50 LOC); single primary path; full `claude agents` integration.

**Cons:** no visible-mode affordance for the case when the user *wants* to watch the work (debugging a new rework class, first-time use, or "I want to see what's happening"). The user explicitly asked for both modes in conversation. Eliminated.

### B. Visible only — `claude-cli://` fan-out, no `--bg`

**Pros:** simplest mental model (each rework gets a window).

**Cons:** O(N) windows on screen — the original friction the feature is trying to remove. The Enter-keypress tax per window is irreducible. `claude-cli://` opens an external terminal emulator (not a Cursor pane), so the user still has to alt-tab. Without a headless option, the script has zero value for users running >2 reworks. Eliminated.

### C. Hybrid — `--bg` default + `--terminals` opt-in + notification hook *(chosen)*

**Pros:**
- O(1) default scaling (one entry point, all sessions invisible until the user opens `claude agents`).
- Opt-in O(N) visibility when the user wants it.
- Notification hook closes the discovery loop for the default mode (otherwise `--bg` requires the user to remember to check `claude agents`).
- Single entry point — toggle modes with one flag.
- No IDE coupling — works regardless of whether the user is in Cursor, VS Code, or a bare terminal.
- Reusable notification hook (any future `--bg` Praxion feature inherits it).

**Cons:**
- Script complexity ≈ 2× single-mode. Mitigated by keeping the mode dispatch in one `case` block.
- `--terminals` has an irreducible Enter-keypress tax per window (no `claude-cli://` parameter for auto-submit). Accepted as the cost of opting into visible mode.
- Mode mixing (some rows `--bg`, others `--terminals`) is not supported in v1. Accepted as YAGNI.

### D. tmux fanout (port `scripts/ccwt` to rework worktrees)

**Pros:** full interactive sessions visible at once in split panes; persistent across reconnects; the existing `scripts/ccwt` is the direct precedent.

**Cons:** the user explicitly asked to drop tmux in favor of the native `claude --bg` + `claude agents` primitives (which did not exist when `ccwt` was written). Requires `tmux` installed. The tiled-pane layout gets unwieldy with N>4. Eliminated by user preference; `scripts/ccwt` remains unchanged as a precedent for style only.

### E. Cursor terminal-pane automation

**Pros:** would integrate with the user's IDE without spawning external windows.

**Cons:** Topic 1b research confirmed there is no working surface — `tasks.json runOn: folderOpen` is broken in Cursor (acknowledged upstream bug, no fix timeline); `cursor agent` requires a binary update with unknown capabilities; no MCP/URI path to spawn into a Cursor integrated terminal; `cursor://anthropic.claude-code/open` opens the Claude Code *panel webview*, not a terminal pane. Eliminated by infeasibility.

## Consequences

### Positive

- **O(1) default UX**: the user runs one command and the rework dispatch is done; no terminal management. The dogfooded N=3 case (the case that surfaced the topic) takes one keystroke instead of three sessions × open-terminal × cd × run-command.
- **Opt-in visibility preserved**: power users (or first-time use of a rework class) can pass `--terminals` and see each session live.
- **Single entry point**: one script name to remember; toggle modes with a single flag. Lower cognitive load than two parallel scripts.
- **Notification hook is reusable**: any future Praxion feature that wants to fire a macOS notification when a `--bg` session transitions inherits the hook. Future-proofs the discovery story for `--bg` more generally.
- **No IDE coupling**: works identically in Cursor, VS Code, and a bare terminal. The dispatcher's behavior depends on `claude` CLI presence, not on a specific IDE.
- **Enables future deferred-manifest consumers**: `commands/dispatch-reworks.md` establishes the slash-command template that `/skill-genesis-review` (ROADMAP Topic 3) and any other "user runs a command later to consume a manifest" feature can follow. This decision *enables* Topic 3; it does not create a `supersedes` relationship — Topic 3 has not been authored yet, so cross-linking by `dec-draft-<hash>` is premature. The shared *pattern* (producer-emits-manifest → user-runs-command → consumer-acts-per-row) is documented in `RECONCILIATION.md § 3` and the present decision is the first instance to ship.
- **Reuse of existing parser**: the script shells out to `scripts/rework_manifest.py:parse_json_blocks()` rather than re-implementing JSON extraction in bash. Schema drift is impossible by construction.

### Negative

- **Script complexity ≈ 2× a single-mode equivalent**. Mitigated by keeping the mode dispatch in one `case` block at one indentation level; ~120 lines is the design ceiling. If it exceeds 200 lines, factor the shared pre-flight into a function — but do NOT split modes into separate scripts.
- **`--terminals` mode has an irreducible Enter-keypress tax** (one keystroke per window). `claude-cli://` has no auto-submit parameter and writing a PTY-automation layer is rejected as out-of-scope. Documented in the script's `--help` and accepted as the cost of opting into visible mode.
- **Mode mixing not supported in v1**. Some users may want to run two reworks visible and three headless. YAGNI; revisit if a concrete use case emerges. A future v2 could accept a manifest-row annotation (`dispatch_mode: bg|terminals`) without breaking the v1 contract.
- **Notification hook is fired globally**: registered against the Stop event for all Claude Code sessions, not just rework. The hook must filter by session name prefix (`rework: `) to avoid firing for unrelated sessions. If the filter is wrong, the user gets a desktop notification on every Claude session — a UX regression for non-rework workflows. Mitigated by an early-exit guard in the hook and a smoke-check during implementation.
- **One untested combination**: `claude --bg` + a custom plugin slash command (`/resume-rework`) inside a pre-existing worktree under `.claude/worktrees/`. The theoretical foundation is sound (full detached session, plugin registered globally, worktree-isolation step is skipped when cwd is already under `.claude/worktrees/`), but the combination has not been integration-tested. The implementation-planner must run a one-shot manual smoke-check (`cd <worktree> && claude --bg "/resume-rework --dry-run"`) before declaring the script done. If the slash command hangs on a permission prompt, the dispatcher falls back to `claude --bg --permission-mode acceptEdits "/resume-rework"`.
- **`terminalSequence` hook output field is not documented in Praxion's `skills/hook-crafting/references/output-patterns.md`** — it's referenced in Topic 1b research citing v2.1.141 release notes, but the exact syntax may differ. Mitigation: the hook is designed with an `osascript -e 'display notification'` fallback that works in all macOS terminal emulators and does not depend on a Claude Code hook-output field. The smoke-check during implementation decides which path ships.

### Neutral / for follow-up

- A future upstream feature request (`claude --bg --cwd <dir>`) would simplify the script (eliminating the `(cd "$path" && claude --bg …)` subshell), but the workaround is functional and not blocking. Deferred.
- The substrate codification proposed in `RECONCILIATION.md § 4.3` (manifest-bearing-reports convention, `.ai-state/<category>_reports/` storage rule) is deferred. The dispatcher reads `REWORK_MANIFEST.md` from its current `.ai-work/<task-slug>/` location.
