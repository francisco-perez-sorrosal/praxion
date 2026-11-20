---
id: dec-draft-f27caf95
title: "Retire the working-directory notice hook: the harness itself tells the session when a Bash command moves it"
status: proposed
category: architectural
date: 2026-11-20
summary: "hooks/notice_working_directory.sh, its test and its three registrations in hooks/hooks.json are removed. On the Claude Code versions in use (2.1.326 and 2.1.327) the harness sends its own 'Environment update' naming the new and the previous directory after a Bash cd, so the hook's line duplicated it on every move while it started a shell on every tool call of every session; the harness also resets a cd that leaves the working directories, and a failing Bash command does not keep its cd, which the hook's PostToolUseFailure half guarded against. The decision that added it is retired."
tags: [hooks, cwd, bash, additional-context, retirement, shipped]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - hooks/hooks.json
  - scripts/CLAUDE.md
  - .ai-state/DESIGN.md
dissent: "The harness's notice is undocumented and its first CLI version unknown, so a managed project on an older CLI loses its only warning that a Bash cd moved the session."
---

## Context

The working-directory notice hook was added because a `cd` inside a Bash command persisted in the main conversation and moved the session out of its checkout, three times on record, once with a memory line already forbidding it. It shipped in v0.66.0. The first live session after it (Claude Code 2.1.326, 2026-11-17) showed the harness sending its own line after a Bash `cd`, `# Environment update: Primary working directory: X (was Y)`, with the hook's line beside it for the same move; after a return home the harness spoke and the hook rightly did not. The same was seen on 2.1.327. The same session showed that a Bash command that fails does not keep its `cd`, so the hook's `PostToolUseFailure` registration guards a move that does not happen on these versions. On 2026-11-20 a Bash command that changed into a directory outside the session's working directories was answered with `Shell cwd was reset to <project root>`: the harness now also undoes a move out of the working directories. The hook's own cost is one shell and one `cat` on every tool call of every session in every managed project, and one extra line per move; its one addition to the harness's notice was naming the session's home, where the harness names the previous directory. The user decided on 2026-11-20 to retire it.

## Decision

Remove `hooks/notice_working_directory.sh`, `hooks/test_notice_working_directory.py` and their three registrations in `hooks/hooks.json` (`PreToolUse` matcher `""` as `pre`; `PostToolUse` and `PostToolUseFailure`, matcher `Bash`, as `post`). `PostToolUseFailure` held only this hook and leaves the file. The rows naming the hook in `.ai-state/DESIGN.md` and `scripts/CLAUDE.md` go with it. The per-session records it wrote under `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/praxion/cwd-notice/` are left to age: nothing reads them, and the hook pruned only its own. The removal reaches a session only after a release, a plugin update and a restart; until then the installed copy keeps running from the plugin cache, which this change does not touch.

## Considered Options

### Keep the hook for older CLIs

Keeps the warning on a CLI that predates the harness's notice. But the version that introduced the notice is not known (its heading text is in every installed CLI back to 2.1.319 and the code path is minified), so the hook would run on every tool call of every session to serve versions nobody can name, and on every current version it doubles the notice.

### Keep only the `pre` half

Drops two registrations and the failure guard, but the `pre` half alone is the one that fires on every tool call, so it keeps the whole cost and still duplicates the harness on each move.

### Retire it (chosen)

No shell on any tool call, one notice per move instead of two, and one hook fewer to keep in step with the harness.

## Consequences

Positive: every tool call of every session in every managed project starts one shell and one `cat` fewer; each Bash move draws one notice, the harness's, instead of two; the hook directory and its registration file shrink by one component.

Negative: the notice no longer names the session's home, only the previous directory; a managed project on a CLI older than the harness's notice loses the warning entirely; the protection now rests on harness behaviour no document states.

## Disconfirmation

- **Falsifier:** a live session on a current CLI in which a Bash `cd` inside the working directories moves the session and no `Environment update` (or reset line) reaches the model.
- **Steelmanned runner-up:** keep the hook for older CLIs. If many managed projects pin an old Claude Code, a hook that costs about 0.01 s a call is cheap insurance for the one mistake memory has repeatedly failed to prevent, and the duplicate line on current versions is noise, not harm.
- **Reversal trigger:** a recorded session drift on a supported CLI that the harness did not announce, or a Claude Code release note that removes or changes the working-directory notice; either would bring the hook back, and the retired decision keeps its full design to rebuild from.
