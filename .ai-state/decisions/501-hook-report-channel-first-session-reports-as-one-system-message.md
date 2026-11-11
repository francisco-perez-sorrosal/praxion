---
id: dec-501
draft_id: dec-draft-09b8d460
title: The first-session hook sends every report to the user as one systemMessage per run
status: accepted
category: behavioral
date: 2026-11-10
summary: "The first-session hook's reports (a first install's completion line, a first install's or an update refresh's failure line naming /praxion-complete-install, and dec-500's interpreter-floor notice) are gathered over the run and written once, as the systemMessage of exactly one JSON object that is the hook's whole standard output, or not at all. Standard error carries no report, because Claude Code shows a hook's stderr on exit 0 to no one. Extends dec-500 from the floor notice to every report."
tags: [hooks, first-session, system-message, install-refresh, hook-output, td-619]
made_by: agent
agent_type: orchestrator
branch: fix/hook-report-channel
pipeline_tier: standard
affected_files:
  - hooks/auto_complete_install.py
  - hooks/_install_update.py
  - tests/acceptance/test_plugin_update_fails_open_and_quietly.py
  - tests/acceptance/test_hook_reports_reach_the_user.py
  - hooks/test_install_reports.py
  - .ai-state/specs/SPEC_install-refresh_2026-11-10.md
affected_reqs: [REQ-14]
dissent: "Claude never learns that the install failed, so it cannot repeat the hand path to a user who missed the message; adding additionalContext would let it."
---

## Context

The plugin's first-session hook (`hooks/auto_complete_install.py`, a SessionStart hook) wrote its reports to stderr: `[Praxion] Auto-install complete.` after a first install, and `[Praxion] <what> could not finish (<ExceptionType>); run /praxion-complete-install to complete it.` after a failed first install or update refresh. It always exits 0. Claude Code's hooks reference (`code.claude.com/docs/en/hooks.md`, re-read 2026-11-10) says "Claude never sees stderr from a hook that exits 0" and gives debug logging as the only way to read it. A $0 run of the installed 0.61.0 hook in a throwaway home confirmed that every report went to stderr only (td-619). The README and the install-refresh spec's REQ-14 describe a report the user reads, and no user could read it.

dec-500 had already put the interpreter-floor notice on stdout as a `systemMessage`, written on its own before the install or update path ran. Had a second writer also written a JSON object, stdout would have held two JSON lines, which the reference calls a parse failure when one of them sets a field.

## Decision

- A run's reports are gathered in the order they fire, each a complete line starting `[Praxion]`, and written once at the hook's I/O edge.
- A non-empty report is written as exactly one JSON object, `{"systemMessage": "<lines joined by newlines>"}`, followed by a newline. That object is the hook's whole standard output. An empty report writes nothing on either stream.
- No report is written to stderr.
- Lines gathered before an unexpected exception are still written. The hook never raises into the harness, and the floor notice must not be lost to a later failure.
- A write that fails (a reader that closed the pipe) is absorbed, and standard output is pointed at the null device so the interpreter's shutdown flush cannot fail: the hook still exits 0.
- The line texts are unchanged.

## Considered Options

- **`systemMessage` only.** Chosen. The reference says it is shown to the user, and SessionStart does not discard it. Claude's context stays free of install chatter on every first session.
- **`systemMessage` plus `additionalContext`.** Rejected for now. Claude would also learn of a failure, but every first session would add install text to Claude's context, and no behaviour needs Claude to act on it. This is the dissent.
- **Keep a copy on stderr for the debug log.** Rejected. It doubles the line against the outer loop's one-line contract, and the debug log already records the hook's stdout.
- **Plain-text stdout.** Rejected. On SessionStart that becomes context for Claude, not a message to the user.

## Consequences

- A user now sees the failure line and the hand path at the start of the session that failed, and sees a first install's completion line.
- The frozen acceptance test of install-refresh's REQ-14 was channel-blind: it joined both streams. It is amended through SQ-06 of that spec to assert the channel.
- The premise is unproven live, as dec-500's is. **Reversal trigger:** an interactive session that does not display a plugin SessionStart `systemMessage`. Then the reports move to plain-text stdout, as context Claude relays.
- The first install's confirmation prompt still writes to stderr and cannot be answered (stdin is drained first). It is td-620, not decided here; the render module's own unresolved-placeholder warning on stderr is td-623.
