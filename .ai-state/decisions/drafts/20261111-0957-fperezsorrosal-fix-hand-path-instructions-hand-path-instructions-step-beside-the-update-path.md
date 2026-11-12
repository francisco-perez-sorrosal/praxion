---
id: dec-draft-133a8cf4
title: "The hand path's instructions step is a Python entry beside the update path, sharing its classifier, recovery and atomic writer"
status: proposed
category: architectural
date: 2026-11-11
summary: "/praxion-complete-install's command gains an instructions step: install_claude.sh runs the new hooks/_install_hand_path.py, which composes the update path's five-state classifier, recover_values and build-and-rename writer and adds only the terminal conversation (offer, value questions with git-derived defaults, confirmation); each step fails soft and the closing report says done only when nothing failed and the instructions are not left behind."
tags: [installer, hand-path, instructions, personal-values, marketplace]
made_by: agent
agent_type: systems-architect
branch: fix-hand-path-instructions
pipeline_tier: standard
affected_files:
  - hooks/_install_hand_path.py
  - hooks/_install_update.py
  - hooks/_install_refresh.py
  - install_claude.sh
  - install.sh
  - hooks/test_install_hand_path.py
affected_reqs: [REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09, REQ-10, REQ-11, REQ-12, REQ-13, REQ-14, REQ-15, REQ-16, REQ-17]
dissent: "Driving the hook's own update path from the installer would reuse one more piece (its gate and step loop), at the cost of coupling the hand path to the hook's marker and systemMessage channel."
---

## Context

`/praxion-complete-install` is the hand path the update refresh's failure line names (dec-501), but its command, `install_claude.sh::complete_install_from_plugin`, has a rules step and a scripts step and no instructions step. After an instructions failure (dec-498's unrecoverable render, or any I/O error) the named command printed `Praxion complete install done` over instructions still linked to the previous version's render (td-614). The pieces the fix needs exist in the update path's Python: the five-state classifier, `recover_values`, `carry_forward_instructions`, the atomic `_build_and_rename`. The hand path has what the hook lacks: the person's terminal.

## Decision

- A new private module `hooks/_install_hand_path.py` (stdlib, importable on Python 3.9) is the hand path's instructions step and its CLI: `python3 <root>/hooks/_install_hand_path.py --root <root>`. It snapshots and classifies `~/.claude/CLAUDE.md` with the update path's classifier, reads the linked render back, and plans with a new pure `plan_hand_path_instructions` in `hooks/_install_refresh.py`. It converses on stderr and stdin (an offer; for an unreadable or missing render, one question per personal value with its git-derived default, then a confirmation), writes through the update path's `write_instructions` (extracted from `carry_forward_instructions`), prints one outcome line on stdout and exits 0 (finished or not ours), 3 (left behind: skipped, no answer, a checkout) or 1 (failed).
- `complete_install_from_plugin` runs the rules, scripts and legacy steps as before, but fail-soft with recorded outcomes, then the instructions step last, then a summary. It prints `Praxion complete install done` only when no step failed and the instructions are not left behind, and returns 1 when a step failed.
- The derived value is git's, else the anonymous stand-in; the installer's `DEFAULT_*` and `prompt_personal_info` are not used, and no values file is written.
- The hook's update path is unchanged in behaviour.

## Considered Options

### Grow `hooks/_install_update.py` with a `__main__` and the conversation
Rejected: it puts a terminal conversation and a CLI into the hook's effects module (556 lines), mixing two callers' concerns in one file.

### A bash step over `prompt_personal_info` and `render_claude_md`
Rejected: a second implementation of the five states, the maintainer's hardcoded identity as defaults (td-627), and a `.personal_info.env` inside the cache version directory, a second store no update reads.

### Run the hook's update path from the installer in a terminal mode
Runner-up; see Disconfirmation.

## Consequences

- The command the failure line names finishes the job, with the identity carried, or confirmed by the person, never silently derived.
- The instructions logic has one owner; the hand path adds a conversation and an outcome vocabulary.
- A private exit-status-plus-one-line contract binds the Python entry and bash; both ship in one version directory.
- Bash's `set -e` makes fail-soft steps subtle; the REQ-14 scenarios pin them.

## Disconfirmation

- **Falsifier (the component added and the responsibility moved):** `hooks/_install_hand_path.py` is added, and setting up the instructions on the hand path moves into it from nowhere. It is wrong if the hand path's instructions handling ever diverges from the update path's classification of the same `~/.claude/CLAUDE.md` (a state the hook calls user-owned that the hand path rewrites, or the reverse), if any bash code reads or writes the render, or if the hook's frozen `test_plugin_update_*` / `test_hook_reports_*` scenarios change.
- **Steelmanned runner-up:** run `auto_complete_install`'s update path from the installer with a terminal flag. It reuses the hook's step loop and gate, so the two callers could never drift even in step order, and it needs no new module. It loses because the hand path wants none of the gate (it must run whatever the marker says), none of the marker write, and none of the `systemMessage` channel, and because a terminal mode inside a SessionStart hook is a prompt the hook must never show (td-620).
- **Reversal trigger:** a third caller of the instructions step appears (for example a `--reconfigure` for marketplace installs), at which point the conversation belongs in the shared effects module, or Claude Code gains a way for a hook to converse with the person, which would let the hook finish without a hand path.
