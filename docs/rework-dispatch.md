# Dispatching Reworks

A how-to for handling the rework loop's user-facing handoff: when the verifier emits `REWORK_MANIFEST.md` and N rework worktrees are spawned, this guide walks you through dispatching them, monitoring progress, answering mid-run prompts, and merging back into the pipeline.

Read this guide when the verifier signals reworks are needed. It is the single document for the dispatch user experience; the architecture rationale lives in [`architecture.md` § 10.1 Verifier Rework Loop](architecture.md#101-verifier-rework-loop), and the reference flag spec lives in `scripts/dispatch-reworks --help`.

## Table of contents

- [Why this guide exists](#why-this-guide-exists)
- [How dispatch integrates with the pipeline](#how-dispatch-integrates-with-the-pipeline)
- [The flow at a glance](#the-flow-at-a-glance)
- [Quick reference](#quick-reference)
- [Walkthrough — default `--bg` mode](#walkthrough--default---bg-mode)
- [Walkthrough — `--terminals` mode](#walkthrough----terminals-mode)
- [Monitoring](#monitoring)
- [Handling mid-rework prompts](#handling-mid-rework-prompts)
- [After reworks complete](#after-reworks-complete)
- [Troubleshooting](#troubleshooting)
- [How it works under the hood](#how-it-works-under-the-hood)
- [Related](#related)

## Why this guide exists

The verifier rework loop produces multiple parallel work streams that each require a separate Claude Code session in a distinct worktree. Before `scripts/dispatch-reworks` existed, dispatching them was a manual chore — open a new terminal, `cd` to a worktree, type `claude /resume-rework`, repeat for every rework. For three reworks that was three terminals, three context switches, and three opportunities to make a typo at exactly the moment when momentum mattered most.

The dispatcher collapses that to a single command. But the command has two modes (`--bg` for headless, `--terminals` for visible), a notification hook that fires on completion, and a monitoring surface (`claude agents`) that is process-tree-gated — running it from inside your orchestrator session fails by design. The mechanics are well-engineered but non-obvious; piecing them together from `--help`, the slash-command body, and the verifier's one-liner is the friction this document removes.

## How dispatch integrates with the pipeline

Rework dispatch is the **mid-pipeline backward edge** of Praxion's verifier rework loop. The full loop:

1. The orchestrator runs the standard pipeline (architect → planner → implementer → test-engineer → verifier).
2. The verifier emits PASS / FAIL / WARN findings against acceptance criteria. When FAIL findings cluster around specific architectural surfaces, Phase 12.5 of the verifier produces a structured `REWORK_MANIFEST.md` — one row per rework needed.
3. The orchestrator creates a rework worktree per row via `EnterWorktree`, then surfaces a dispatch instruction to you.
4. **This guide picks up here.** You run `scripts/dispatch-reworks` to fan out the reworks into parallel Claude sessions. Each session re-enters the pipeline from the architect (or another agent named in the manifest), focused on the specific finding.
5. Each rework session resolves its scope, commits its changes, and returns. You merge the rework worktrees back into the orchestrator's pipeline branch.
6. The orchestrator re-runs the verifier. If clean, the pipeline proceeds to merge-to-main. If new findings appear, the loop repeats.

The dispatcher is small but load-bearing — it is the *only* user touchpoint in the rework loop's parallel-execution slice. Get it right and the loop scales; get it wrong and N reworks become N user chores.

## The flow at a glance

![Rework dispatch user flow — sequence diagram showing verifier emitting the manifest, the orchestrator creating worktrees, dispatch-reworks fanning out in --bg or --terminals mode, and the user monitoring via claude agents in a fresh pane or per-window in --terminals mode](diagrams/rework-dispatch/rendered/user-flow.svg)

## Quick reference

| Mode | Command | What you see | Cost per dispatch |
|---|---|---|---|
| **Default headless** (`--bg`) | `scripts/dispatch-reworks` | N session IDs printed with `claude logs <id>` / `claude stop <id>` hints; fresh Cursor pane runs `claude agents` for the unified dashboard; macOS notifications on completion | **O(1)** — one monitoring pane opened once, scales regardless of N |
| **Visible terminals** (`--terminals`) | `scripts/dispatch-reworks --terminals` | N external terminal windows open with `claude` pre-staged and `/resume-rework` pre-typed | **O(N)** — one Enter keypress per window |
| **Preview only** (`--dry-run`) | `scripts/dispatch-reworks --dry-run` (combinable with `--terminals`) | The dispatch plan as `would dispatch: <mode> · <worktree-name> · <command shape>` per row | Zero sessions spawned |

> [!TIP]
> Always run `scripts/dispatch-reworks --dry-run` before the first real dispatch of a session to confirm the manifest parsed correctly and the worktree paths look right.

The slash-command wrapper `/dispatch-reworks` accepts the same flags as the script — use whichever surface is easier to discover from where you are.

## Walkthrough — default `--bg` mode

The default mode runs all reworks as detached background sessions. You see no terminal proliferation; one monitoring pane gives you the unified view.

**Step 1**. In your main Cursor terminal pane (where the orchestrator session is running), the verifier's Phase 12.5 message tells you reworks were created. The message names the dispatch script.

**Step 2**. Run the dispatcher:

```bash
scripts/dispatch-reworks
```

Or via the slash command from inside the orchestrator session: `/dispatch-reworks`.

**Step 3**. The dispatcher prints one block per worktree:

```text
Dispatched 3 rework session(s):
  rework: foo-fix → id 1a2b3c4d
    peek:   claude logs 1a2b3c4d
    cancel: claude stop 1a2b3c4d
  rework: bar-fix → id 5e6f7g8h
    peek:   claude logs 5e6f7g8h
    cancel: claude stop 5e6f7g8h
  rework: baz-fix → id 9i0j1k2l
    peek:   claude logs 9i0j1k2l
    cancel: claude stop 9i0j1k2l

To monitor all sessions in one view: open a fresh Cursor terminal pane and run `claude agents`.
macOS notifications will fire when each session completes (via the osascript Stop hook).
```

The dispatcher returns immediately — sessions run detached in `~/.claude/daemon/`.

> [!IMPORTANT]
> `claude agents` is process-tree-gated upstream — it refuses to run from inside any Claude Code session (returns `'claude agents' is not available in this environment.`). **You must open a fresh Cursor terminal pane (⌘+\`)** with no `claude` parent process and run `claude agents` there. The orchestrator's pane is busy running your main session and cannot host the agent-view TUI.

**Step 4**. Open a fresh Cursor pane (⌘+\`) and run:

```bash
claude agents
```

The TUI dashboard shows all N rework sessions with their state (Working, Needs input, Completed, Failed). Press `Space` to peek at a session's recent output, `Enter` (or `→`) to attach for full interaction, `←` to detach back to the dashboard.

**Step 5**. Continue working in your orchestrator pane. macOS notifications will fire when sessions complete or stall; the dashboard also updates in real-time. You do not need to actively watch.

## Walkthrough — `--terminals` mode

The visible mode opens N external terminal windows — useful when you want to watch each rework live, or are debugging a new rework class.

**Step 1**. Run the dispatcher with the flag:

```bash
scripts/dispatch-reworks --terminals
```

**Step 2**. The dispatcher first verifies that the `claude-cli://` URI handler is registered on your machine. If not, it exits with a clear error and suggests `--bg` as the alternative.

**Step 3**. N new terminal windows open — using your last-used terminal emulator (iTerm2, Ghostty, Terminal.app, etc.). Each window:

- has `cwd` set to the correct rework worktree
- is running an interactive `claude` session
- has `/resume-rework` pre-typed in the prompt box

**Step 4**. Press **Enter** in each window to start the rework. Yes, one keypress per window — the `claude-cli://` deep link does not auto-submit prompts by design (this is an upstream security posture, not something Praxion can route around).

> [!WARNING]
> If you're smoke-testing the dispatcher against a synthetic manifest, **do not press Enter in those test windows** — the `/resume-rework` slash command will run for real if you do. Close the test windows manually instead.

## Monitoring

### `claude agents` in a fresh pane

The unified monitoring surface for `--bg` mode. Open a Cursor terminal pane (⌘+\`) **outside the orchestrator session**, run `claude agents`, leave it open. It updates live as sessions progress.

> [!IMPORTANT]
> Running `claude agents` from inside any active `claude` session returns `'claude agents' is not available in this environment.` This is an upstream behavior tracked at [anthropics/claude-code#59340](https://github.com/anthropics/claude-code/issues/59340) and documented in [`CLAUDE.md` § Known Claude Code Limitations](../CLAUDE.md). The workaround is permanent: monitor from a fresh pane.

### Per-session inspection

The dispatcher prints `claude logs <id>` and `claude stop <id>` hints for every dispatched session, so you can peek or cancel any single rework from any shell — including the orchestrator pane. This is the always-available fallback when the unified dashboard is not.

```bash
claude logs 1a2b3c4d        # tail the rework session's recent output
claude logs 1a2b3c4d -f     # follow live (Ctrl-C to stop)
claude stop 1a2b3c4d        # cancel this rework
```

### Notifications

A `Stop` hook (`hooks/notify_bg_session_state.py`) fires a macOS-visible notification when a `--bg` rework session completes. The hook uses a marker-file correlation to identify rework sessions (see [How it works](#how-it-works-under-the-hood)) and emits via `osascript -e 'display notification ...'`. You do not have to keep the dashboard open — the notification will reach you.

To opt out of notifications globally, set `PRAXION_DISABLE_OBSERVABILITY=1` in your environment.

## Handling mid-rework prompts

Rework sessions follow the standard pipeline contract — the architect agent may ask clarifying questions via `AskUserQuestion` when it encounters genuine ambiguity. When this happens:

- **In `--bg` mode**: the session's row in `claude agents` flips to **Needs input** (yellow). Peek with `Space`, then `Enter` to attach. Answer the prompt in the attached TUI, then detach with `Ctrl-d` (or your terminal's detach key). The session resumes.
- **In `--terminals` mode**: the prompt appears inline in that rework's terminal window. Answer it there.

Either way, the rework continues from where it paused — you do not need to restart anything.

## After reworks complete

When all rework sessions report Completed (in the dashboard or via notifications), the rework worktree branches each contain the rework's fixes ready to merge back. The orchestrator session is what merges them — you signal completion by returning to the orchestrator pane and asking it to continue the pipeline. The orchestrator typically:

1. Merges each rework worktree branch into the parent pipeline worktree
2. Re-runs the verifier
3. Either advances to merge-to-main (if the verifier is now clean) or surfaces another rework loop (if new findings appear)

## Troubleshooting

<details>
<summary>The macOS notification didn't fire when a rework completed</summary>

The hook fires only when:

1. The session's marker file at `~/.claude/rework_sessions/<short_id>` exists (the dispatcher writes it; the hook deletes it after firing)
2. The Stop event payload's `session_id` field is present (it is, on Claude Code 2.1.141+)
3. `PRAXION_DISABLE_OBSERVABILITY` is not set in the environment that ran `claude --bg`
4. The hook is registered in the installed plugin's `hooks/hooks.json` and the hook script is in the installed plugin cache

If the marker file persists in `~/.claude/rework_sessions/` after the session ended, the hook never ran — most likely the installed plugin's `hooks/notify_bg_session_state.py` is missing or out of date. See [`README_DEV.md` § Dev-link mode](../README_DEV.md#dev-link-mode) for the development-time fix.

Run `osascript -e 'display notification "test" with title "Praxion"'` directly to confirm macOS notifications work at all on your machine.

</details>

<details>
<summary><code>claude agents</code> says "not available in this environment"</summary>

You are inside an active Claude Code session — that's the gate. Open a **new** Cursor terminal pane (⌘+\` from anywhere in Cursor) where no `claude` is running, then `claude agents` will open the dashboard normally.

If it still fails from a fresh pane, your account may not have agent-view enabled (it shipped in Claude Code 2.1.139 and requires Pro / Max / Team / Enterprise / API plan tiers). Confirm with `claude auth status`.

Tracked upstream as [anthropics/claude-code#59340](https://github.com/anthropics/claude-code/issues/59340).

</details>

<details>
<summary><code>--terminals</code> mode: "claude-cli:// handler not registered"</summary>

The `claude-cli://` URI handler ships with Claude Code 2.1.91+ but the registration only happens after the first interactive `claude` session on your machine. Run `claude` once in any directory, then re-run `scripts/dispatch-reworks --terminals`.

To verify the handler is registered without dispatching anything:

```bash
lsregister -dump > /tmp/lsdump.txt && grep claude-cli /tmp/lsdump.txt
```

</details>

<details>
<summary>Session IDs look like garbage characters instead of 8 hex digits</summary>

Pre-Phase-2 versions of the dispatcher had a UTF-8 multi-byte parsing bug in the `backgrounded · <id>` line extraction (the middle-dot `·` is `\xc2\xb7`). The current dispatcher uses `awk '{print $NF}'` which is locale-safe. If you see corrupted IDs, you are running an old version — re-run `./install.sh code` from the project root.

</details>

## How it works under the hood

<details>
<summary>The marker-file correlation pattern (why the notification hook works)</summary>

Claude Code's Stop hook event payload carries `session_id` but does **not** carry the session's `--name` field or a state reason. The hook cannot tell "is this Stop event for a rework session or for the user's main coding session?" from the payload alone.

The fix: the dispatcher writes a small marker file `~/.claude/rework_sessions/<short_id>` (where `<short_id>` is the 8-hex prefix of the session UUID) every time it spawns a `--bg` rework. The marker's content is the worktree slug. When the hook fires, it derives `<short_id>` from the payload's `session_id`, checks the marker exists, reads the slug for the notification message, and deletes the marker after firing.

This converts a **schema-coupled filter** (read fields the upstream doesn't always provide) into a **side-effect-coupled filter** (check filesystem state Praxion controls). When you can't trust upstream schemas, instrument your own correlation.

</details>

<details>
<summary>Why <code>osascript</code> notifications and not <code>terminalSequence</code></summary>

The `terminalSequence` hook output field (Claude Code 2.1.141) emits a terminal escape sequence into the session's TTY — bell, window-title change, or iTerm2's notification escape `\x1b]9;<msg>\x07`. The issue: `--bg` sessions are *detached* and have no controlling TTY. The escape sequence has nothing to render into, so it silently no-ops. `osascript -e 'display notification ...'` shells out to macOS's `NSUserNotification` subsystem directly, which works regardless of TTY presence.

</details>

<details>
<summary>Why <code>claude agents</code> needs a fresh terminal pane</summary>

The gate appears to be parent-process-based: if `claude` is anywhere in the invoking process's ancestry, `claude agents` refuses. The gate is the same whether you shell out from inside a session, from a subagent's Bash tool, or from a `bash -c` nested inside `claude`. A fresh terminal pane has the shell as the immediate child of your terminal emulator (or login shell), no `claude` ancestor — that's the working condition.

This is an upstream design choice (preventing nested-session confusion) rather than a Praxion-side gap. The friction is the silent error message, not the behavior itself — filed at [anthropics/claude-code#59340](https://github.com/anthropics/claude-code/issues/59340) asking for a more informative error string.

</details>

## Related

- [`docs/architecture.md` § 10.1 Verifier Rework Loop](architecture.md#101-verifier-rework-loop) — the architectural design of the rework loop (what reworks are, when they fire, what the manifest contains)
- [`agents/verifier.md`](../agents/verifier.md) Phase 12.5 — the verifier's manifest-emission and worktree-spawn protocol
- [`commands/dispatch-reworks.md`](../commands/dispatch-reworks.md) — slash-command surface; same flag passthrough as the script
- [`scripts/dispatch-reworks --help`](../scripts/dispatch-reworks) — authoritative flag and exit-code reference
- [`hooks/notify_bg_session_state.py`](../hooks/notify_bg_session_state.py) — the osascript notification hook
- [`README_DEV.md` § Dev-link mode](../README_DEV.md#dev-link-mode) — for contributors editing the hook locally
- [`CLAUDE.md` § Known Claude Code Limitations](../CLAUDE.md) — `claude agents` process-tree gate, other upstream caveats
- [`.ai-state/decisions/drafts/20260514-1413-fperezsorrosal-worktree-orchestrator-handoff-ux-research-hybrid-rework-dispatch.md`](../.ai-state/decisions/drafts/) — the ADR for the hybrid-dispatch + notification-hook decision
