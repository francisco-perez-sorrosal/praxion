---
id: dec-500
draft_id: dec-draft-0d5cf540
title: The hooks declare a Python 3.11 with PyYAML floor and name a shortfall at install check and first session
status: accepted
category: architectural
date: 2026-11-10
summary: "Every Praxion hook runs under the first python3 on PATH, which stock macOS makes 3.9 without PyYAML. The floor the hooks need today, Python 3.11 with PyYAML, is declared once in hooks/_interpreter_floor.py. install.sh --check and the first session after an install or update name the shortfall: the latter as a systemMessage, since a SessionStart hook's stderr on exit 0 reaches neither Claude nor the user. The hooks are not rewritten to run below the floor, and the plugin does not pick or ship an interpreter."
tags: [hooks, interpreter, python-floor, pyyaml, install-check, first-session, td-599]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - hooks/_interpreter_floor.py
  - hooks/auto_complete_install.py
  - install_claude.sh
  - README.md
affected_reqs: []
dissent: "A notice names the gap without closing it; a launcher that picks a capable interpreter would make the hooks work on stock macOS."
---

## Context

`hooks/hooks.json` registers every Python hook as `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/<hook>.py`, so a hook runs under whichever `python3` comes first on the user's PATH. On stock macOS that is `/usr/bin/python3`, 3.9.6 without PyYAML. A $0 probe of the 27 registered Python hooks under it (td-599, 2026-11-08) found each degrading on its own: rule injection skips without PyYAML and would next stop on 3.10 syntax, `capture_session.py` stops on `zip(strict=...)`, and the code-quality hooks stop on `import tomllib` (3.11). No file declared what the hooks need and nothing checked it, so a managed session could lose its procedures with no message anyone saw.

The user chose option 1 of three: declare the floor and diagnose a shortfall. The other two were to make every hook run on 3.9, or to have the plugin choose or ship its interpreter.

## Decision

- The floor is Python 3.11 with PyYAML: what the hooks need today. It is declared once, in `hooks/_interpreter_floor.py`, which keeps to Python 3.7 syntax because the interpreter it judges parses it first.
- `install.sh --check` runs that module under the hook interpreter. Below the floor the check warns with the module's line, naming the interpreter, each shortfall and the fix, and the check fails.
- The first-session hook (`auto_complete_install.py`) names the shortfall on the run that writes its marker, so once per plugin version. The line goes out as a `systemMessage` in JSON on stdout. Claude Code's hook reference says Claude never sees a hook's stderr on exit 0, and gives debug logging as the only way to read it, so stderr would reach no one.
- The README states the requirement in its installation section.

## Considered Options

- **Make every hook 3.9-safe.** Rejected for now: the hooks would lose `tomllib` and 3.10 syntax, and PyYAML would still be missing on stock macOS.
- **Have the plugin pick or ship an interpreter** (for example, a `uv run` launcher in `hooks.json`). Rejected for now: it adds a dependency and a per-hook start-up cost to every session.
- **Report on stderr, as the hook's other reports do.** Rejected: by the hook reference, that line reaches neither the user nor Claude.

## Consequences

- A user below the floor learns it once per version, and `install.sh --check` re-checks at any time. The hooks still degrade below the floor; the gap is now named, not closed.
- A floor change is one edit to `FLOOR` or `REQUIRED_MODULES` and the README sentence.
- The hook's other first-session reports still write to stderr; moving them onto the same channel is td-619.
- The check judges the first `python3` on the PATH of the shell running `install.sh --check`. Claude Code may start hooks with a different PATH. The first-session notice judges the interpreter the hook actually runs under.

## Disconfirmation

- **Falsifier.** A live first session below the floor that shows no notice would make the channel choice wrong, since the choice rests on the hook reference. So would a hook that fails at the floor itself (3.11 with PyYAML), because then the floor is wrong.
- **Steelmanned runner-up.** A `uv run --python 3.11 --with pyyaml` launcher in `hooks.json` would make every hook work wherever `uv` is installed, with no notice needed. That closes the gap, where this decision only names it.
- **Reversal trigger.** Revisit if a user below the floor reports a broken session despite the notice, or if Claude Code ships a supported way for a plugin to declare its hook interpreter.
