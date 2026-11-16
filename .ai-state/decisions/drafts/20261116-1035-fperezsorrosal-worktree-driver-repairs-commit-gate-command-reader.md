---
id: dec-draft-c02617e5
title: The commit gate asks a stdlib reader of the command field, after its grep, whether a Bash call is a commit
status: proposed
category: implementation
date: 2026-11-16
summary: hooks/commit_gate.sh keeps its grep fast path for payloads naming neither git nor commit, cuts the exact extent of tool_input.command with one sed (escaped backslashes and quotes replaced by control-character placeholders) and passes a command without the word commit at no interpreter cost, and otherwise runs hooks/_commit_command.py (json and shlex, python3 -I -S through PRAXION_PYTHON, the project's .venv interpreter, else python3), which prints commit, not-a-commit or uncertain; only the exact word not-a-commit skips the gated checkers, so a crash or any doubt runs them.
tags: [hooks, commit-gate, fast-path, bash, shlex]
made_by: agent
agent_type: systems-architect
branch: worktree-driver-repairs
pipeline_tier: full
affected_files:
  - hooks/commit_gate.sh
  - hooks/_commit_command.py
  - hooks/test_commit_command.py
  - hooks/test_commit_gate.py
affected_reqs: [REQ-33, REQ-34]
---

## Context

The commit gate decides whether to start a gated checker with `grep -q 'git.*commit'` over the whole hook payload. A read-only call whose description or transcript path names both words, or a `git log --grep=commit`, starts every gated checker, and a blocking checker then judges a staged set no commit is about to record and can refuse the call. Narrowing the text pattern to the command string does not work: the raw JSON escapes quotes, and a pattern that stops at an escaped quote would skip a real commit, the worse failure. The gate runs on every Bash call of every managed project through six registrations.

## Decision

Keep the grep as stage 0 (a payload naming neither word exits 0 at today's cost). On a match, one `sed` first replaces every `\\` and then every `\"` with a control character (JSON forbids raw control characters in strings, so the placeholders cannot collide) and cuts the command value up to its first remaining quote: its exact extent. A value without `commit` (and without a `\u` escape) exits 0 there, with no interpreter: this settles the description, transcript-path and `git show` cases. Otherwise run a stdlib-only reader, `hooks/_commit_command.py`, found beside the gate and started with `-I -S` by the first of `$PRAXION_PYTHON`, `$CLAUDE_PROJECT_DIR/.venv/bin/python` and `python3` (the finalize chain's order; on the authoring machine `python3` is a pyenv shim costing 210 to 260 ms per start, the venv interpreter 20 to 30 ms). It parses the payload once (anything unreadable is `uncertain`), tokenizes the command in POSIX mode with control operators and unquoted newlines as separators, recurses into `bash -c`/`sh -c` scripts (depth two), treats substitutions and `eval` as `uncertain`, skips leading assignments and git's global options, and reads the git subcommand: `commit` is a commit, another git built-in is not, anything else (an alias, an unknown option, a variable) is `uncertain`. The gate skips the checkers only when the reader prints exactly `not-a-commit`; every other outcome, a crash included, runs them as before. Category `implementation`: the gate keeps its responsibility and its callers; the decision lives inside it.

## Considered Options

### A text pattern over the raw command string

Cheapest, but stops at an escaped quote and would skip a real commit.

### `jq` in the shell

Exact parsing without Python, but not guaranteed to be installed in a managed project; a missing `jq` would have to run the checkers, giving no gain there.

### Each checker classifies the command itself

Reuses the checkers' existing payload parsing, but a checker start costs more than the reader, six checkers would each need the rule, and the reminders would still start.

## Consequences

Positive: read-only calls that mention a commit start no checker and cannot be refused by one; every listed commit form still starts them; a reader failure fails toward checking.

Negative: a real commit pays one extra interpreter start per gated hook; a non-commit command holding the word pays one reader start instead of a checker start; a commit whose command holds no contiguous `commit` (an alias, a quote-split word) is not judged, as at base whenever no other field held the words; non-commit git subcommands whose text holds the word (`git merge --no-commit`) are no longer judged, as the same subcommands without the word never were. The added cost on a read-only mention is bounded by a footprint criterion (median within 30 ms of the silent path).
