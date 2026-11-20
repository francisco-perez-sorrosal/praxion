---
id: dec-519
draft_id: dec-draft-5310f592
title: A shipped shell hook tells the main conversation, once per move, that a Bash command left it in another directory
status: retired
retired_by:
  - dec-522
category: architectural
date: 2026-11-16
summary: hooks/notice_working_directory.sh, registered under PreToolUse for every tool and, for Bash, under PostToolUse and PostToolUseFailure, keeps one three-state record per main-conversation session and adds one additionalContext line when a Bash command leaves the session away from its home (its start directory, or the worktree the harness moved it into); POSIX sh only, fail-open, correct whether or not the moving call's PostToolUse payload already shows the new directory.
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

## As built

One assumption of this decision was wrong and was corrected before the merge. The decision registered the `post` half under `PostToolUse` only and attributed a change first seen at a `pre` with no moving record to the harness. That holds only if every Bash call fires `PostToolUse`. The hooks reference (read again 2026-11-17) says `PostToolUse` runs after a tool completes successfully and `PostToolUseFailure` when a tool that started executing fails, and its example of the latter is a Bash command whose error begins `Exit code 1`. So `cd sub && <a command that fails>` never reached `post`: the next `pre` took `sub` for the session's home, and a later return to the project root was announced as a move away. The final verifier found it by a probe. The `post` half is now registered under both events (matcher `Bash`), a failure's `error` text is not read as part of the command, and the notice names the event that fired it. One limit stays: the reference says cancelling a running tool fires neither event, so a move made by a call the user interrupts is first seen at the next `pre`. The hook still has not run under a live harness; this correction came from the reference, not from one.

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

## Prior Decision

**What removed this decision's subject.** `dec-522` removed `hooks/notice_working_directory.sh`, its test and its three registrations, on the user's word of 2026-11-20. The first live sessions after the hook shipped (Claude Code 2.1.326 and 2.1.327) showed the harness sending its own `Environment update` after a Bash `cd`, naming the new and the previous directory, so every move drew two notices; a failing Bash command did not keep its `cd`; and on 2026-11-20 the harness reset a `cd` that left the working directories. The hook's question (how to tell the session it moved) is answered by the harness, not by a different hook, so this record is retired rather than superseded. **What would bring it back:** a supported CLI that moves the session on a Bash `cd` without announcing it. The design above, with its as-built correction, is the starting point then.
