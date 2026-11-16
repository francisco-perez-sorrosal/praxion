---
id: dec-draft-5310f592
title: A shipped shell hook tells the main conversation, once per move, that a Bash command left it in another directory
status: proposed
category: architectural
date: 2026-11-16
summary: hooks/notice_working_directory.sh, registered under PreToolUse for every tool and PostToolUse for Bash, keeps one three-state record per main-conversation session and adds one additionalContext line when a Bash command leaves the session away from its home (its start directory, or the worktree the harness moved it into); POSIX sh only, fail-open, correct whether or not the moving call's PostToolUse payload already shows the new directory.
tags: [hooks, cwd, worktree, bash, additional-context, shipped]
made_by: agent
agent_type: systems-architect
branch: worktree-driver-repairs
pipeline_tier: full
affected_files:
  - hooks/notice_working_directory.sh
  - hooks/test_notice_working_directory.py
  - hooks/hooks.json
affected_reqs: [REQ-31, REQ-32]
---

## Context

A `cd` inside a Bash command persists in the main conversation and moves the session out of its checkout root; relative paths, the observation log and the worktree guard then follow the wrong directory. It is on record three times, the last with a memory line already forbidding it, so memory does not hold the lesson and no artifact guarded it. The Claude Code hooks reference (read 2026-11-16) says a hook payload's `cwd` follows Claude (the worktree root after entering a worktree, the new directory after a `cd`), that `CLAUDE_PROJECT_DIR` stays at the start directory, that `PreToolUse` and `PostToolUse` may add `additionalContext` beside the tool result, that `CwdChanged` cannot reach the model, that subagent payloads carry `agent_id`, and that hooks of one event run in parallel. It does not say whether the `PostToolUse` payload of the call that ran the `cd` already shows the new directory. The hook ships to every managed project and fires on every tool call, so its silent path must start no interpreter.

## Decision

Add one hook component, `hooks/notice_working_directory.sh <pre|post>`, POSIX `sh` with builtins plus one `cat`, registered in `hooks/hooks.json` as two new groups: `PreToolUse` with matcher `""` (`pre`) and `PostToolUse` with matcher `Bash` (`post`). It keeps one record per main-conversation session under `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/praxion/cwd-notice/<session_id>`, in one of three states: `Unseen`, `Settled(home, last)`, `Moving(home, last)`. A change of `cwd` seen at `post` is a Bash move; a change seen at `pre` is a Bash move only when the record is `Moving` (a Bash call whose command held `cd`, `pushd` or `popd` ended with its payload unchanged), else a move the harness made, which becomes the session's home silently. A Bash move away from home adds one line naming the new directory and home; a move to home adds nothing. Subagent payloads, unreadable payloads and paths the shell cannot write into JSON add nothing; the script always exits 0. No live probe of the payload question is run: neither answer would remove a registration, a process or a write from the silent path.

## Considered Options

### A stateless PostToolUse hook on Bash behind a `cd` prefilter

Announce when the payload's `cwd` is not the project root after a `cd`-bearing command. Simplest, but never fires if the moving call's payload shows the old directory, announces on every `cd` in a session that lives in a worktree (its `cwd` is never `CLAUDE_PROJECT_DIR`), and cannot tell a worktree entry from a drift into the main checkout.

### A CwdChanged hook

Fires exactly on a change, but its output is limited to `watchPaths` and a terminal `systemMessage`; nothing reaches the model.

### The chosen hook with a Python judge on a change

Exact JSON parsing of the paths, but under the old-directory answer it starts an interpreter at the next call, whose command holds no directory change, against the requirement that such a call start none.

## Consequences

Positive: the session is told once per move, beside the moving call's result when the payload shows it and beside the next call's result otherwise; a worktree session is silent in its own worktree and told when a `cd` takes it into the main checkout; no interpreter on any path; nothing is written into a managed project.

Negative: one `sh` and one `cat` per tool call (in parallel with hooks already registered); a path holding a backslash, a double quote or a control character is never announced; under the old-directory answer a Bash move made without a `cd`/`pushd`/`popd` word is taken for a harness move; two payload fields are cut by position in the documented key order; a per-user state file per session, pruned after seven days.

## Disconfirmation

- **Falsifier:** a live session in which the hook stays silent after a `cd` into a subdirectory, or announces a session's own worktree root on an ordinary call, or in which a silent call is measured starting an interpreter.
- **Steelmanned runner-up:** the stateless PostToolUse hook. If the payload of the moving call always shows the new directory (the reference's "the new directory after Claude runs `cd`" reads that way), it is correct for the ordinary session in a third of the code, and worktree sessions could be handled by treating any `.claude/worktrees/<name>` root as home, a pure string test. It loses only when the payload lags, when a worktree lives elsewhere, and on a drift into the main checkout, which it reads as coming home.
- **Reversal trigger:** evidence that the harness passes a `cwd` the session will not keep (a reset after the hook fired) on ordinary calls, or that `PreToolUse` additionalContext is dropped by the harness; either would make the `pre` registration cost without benefit and favour the runner-up.
