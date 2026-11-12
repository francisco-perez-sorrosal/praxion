# Spec: hand-path-instructions (the command the refresh's failure line names finishes the job)

**Task slug**: `hand-path-instructions`
**Created**: 2026-11-11
**Pipeline run**: 2026-11-11 (one session). The steps:
- intake;
- spec, with four round-0 Spec Questions;
- acceptance design, with three late Spec Questions;
- design and a 12-step plan;
- steps 1 to 5 in the step loop, and steps 6 to 12 outside it after the td-605 loop-state defect;
- final verification, in-place rework, and a delta re-verification.

**Archived**: 2026-11-11 (pre-merge, on branch `fix/hand-path-instructions`)
**Status**: completed. Final verdict PASS WITH FINDINGS (0 FAIL, 13 WARN). Delta re-verification PASS WITH FINDINGS (0 FAIL, 3 WARN, fixed or dispositioned).
**Tier**: Standard. The calibration verdict reads `correct`: 17 requirements across the installer, two skills and three hook modules, and a write into the person's identity.
**Complexity**: medium-high: 17 requirements, 3 production hook modules (1 new), 2 shell installers, 2 skills, 4 doc surfaces.
**Base commit**: `103eb39e`. Further commits:
- acceptance design `e5da62ee`, design state `97a5fc1d`;
- the steps, `0037ce08` to `14f5d9a4`;
- rework `a3861d7f` and `640d1c39`, state `e2ef327e`.

**Pipeline branch**: `fix/hand-path-instructions`
**ADRs (promoted at merge)**:
- `dec-505` (architectural): the hand path's instructions step beside the update path;
- `dec-506` (behavioral): both skills resolve the substituted root;
- `dec-507` (implementation): two render slots, and readers follow the link.

**Related specs**: `SPEC_install-refresh_2026-11-10.md` (the five instruction states and the carry-forward the hand path reuses) and `SPEC_hook-report-channel_2026-11-11.md` (the failure line, now a `systemMessage`, that names this command).

## Feature Summary

The first-session hook's failure line tells a marketplace user to run `/praxion-complete-install`. Before this, that command could not do the job:
- It rendered no instructions.
- Its plugin-root expression `${CLAUDE_PLUGIN_ROOT:-$(ls -d …/praxion/*/ | head -1)}` resolved to the oldest cached version for every marketplace user. Claude Code substitutes the bare `${CLAUDE_PLUGIN_ROOT}` token into a skill's body, and the variable is not in the Bash tool's environment (docs read 2026-11-11). So the fallback always ran, and a lexical listing puts the oldest version first: 0.43.0 of 13 on the machine where this was found.

Now:
- Both hand-path skills resolve the installed version: the substituted root, else the plugin registry's praxion `installPath`, user scope first. They never list the cache, and unsubstituted text stays inert.
- The command the skill hands over runs the rules and scripts steps fail-soft, then the instructions step last:
  - It carries the identity the earlier render held.
  - Where that render cannot be read back, it asks for each personal value, with the git-derived default and a confirmation.
  - It leaves a regular file and a clone's link alone, and says so.
  - It never writes a derived identity without consent. End of input is never consent.
- It closes with a report that says "done" only when nothing failed and the instructions are not left behind.

## What Was Built

- **`hooks/_install_hand_path.py`** (new): the instructions entry the installer calls. It handles the terminal conversation (offer, values, confirmation), takes the answers on standard input and writes exactly one outcome line with exit status 0, 1 or 3. It is stdlib-only and imports on Python 3.9.
- **`hooks/_install_refresh.py`:**
  - `CachedRender.render`, the path the link names.
  - The pure decision core `plan_hand_path_instructions`, with its `Readback`, `HandPathPlan` and `HandPathOutcome` sums.
  - `render_slot` (`PRIMARY` / `ALTERNATE`).
- **`hooks/_install_update.py`:**
  - `read_back`, and a carry-forward that reads the render the link names.
  - `write_instructions`, the one writer, which never replaces the file the link resolves to. It writes `claude/config/CLAUDE.alternate.md` when the link names the installed version's own primary render.
- **`install_claude.sh`:**
  - `complete_install_from_plugin` is a sequence of fail-soft steps through `run_fail_soft`. The interactive leftover-state cleanup runs in an uncaptured errexit subshell.
  - The instructions step runs last, and one report line is printed per step.
- **`install.sh`:** its help text.
- **`skills/praxion-complete-install/SKILL.md`, `skills/praxion-complete-uninstall/SKILL.md`:** one resolution block, which differs between the two skills only in the not-found line. The install skill says what its command finishes.
- **Tests:**
  - New hook modules `test_install_read_back.py`, `test_install_hand_path.py`, `test_install_hand_path_prompts.py` and `test_install_hand_path_process.py`.
  - `tests/test_complete_skills_resolve_root_alike.py`, `tests/test_complete_skills_registry_fallback.py`, `tests/test_complete_install_steps_fail_soft.py`.
  - The outer-loop scenarios under `tests/acceptance/test_hand_path_*.py` and `tests/e2e/test_hand_path_finishes_a_stopped_refresh.py`.

## Footprint Readings

| Id | Baseline | Final | Limit | Reading |
|---|---|---|---|---|
| FC-01 the skill listing | 14268 tokens (`6e23ef38`) | 14268 tokens (`14f5d9a4`) | at or below 14320 | measured (tokenizer) |
| FC-02 prompt-size findings naming the hand-path skills | (absolute) | 0 findings | 0 | measured |

Health readings:
- The always-loaded budget stays at 19,918 tokens.
- No Codex or Cursor generated file names either skill, so nothing was regenerated.
- Derived scope green at `2209cafa` (root 9,618, acceptance and e2e 5,281, eval 4,296, chronograph) and over `2209cafa..14f5d9a4` (9,461, 5,183, 4,296, 128).

## Key Decisions

- **Two render slots, and every reader follows the link** (`dec-507`). The architect weighed moving the hand-edited render aside and rejected it. That would break REQ-08's inode guard, and a second slot that readers did not follow would fail the next update at every release. The guard test was made to bite only after review: the stale primary and the alternate first held the same identity.
- **The hand path calls the Python the update path owns** (`dec-505`), never a bash re-implementation. The installer's hardcoded maintainer identity (td-627) never reaches it.
- **Substituted root, else registry** (`dec-506`). Unsubstituted text is read through a quoted heredoc, so it can never expand from the shell. The person's own `CLAUDE_PLUGIN_ROOT` export (as on the maintainer's machine, pointing at a dev checkout) is never read.
- **A deliberate change to the hook's observable output.** The update refresh's failure line names `UnrecoverableRenderError` where it named the raw exception type. The four cases are `PermissionError`, `IsADirectoryError`, `FileNotFoundError`, and `UnicodeDecodeError` for an undecodable render.
- **Process:**
  - The step loop stopped at step 5 on td-605: a review-forced step whose fixes were committed outside the loop cannot be reviewed in it. Steps 6 to 12 ran outside the loop under the same gates.
  - Two reviews were resolved by the orchestrator with recorded proof.
  - The rework ran in place, because every manifest row was `suggested`.
- **Out of scope, filed:**
  - td-625: the hand path's script links overwrite owned files.
  - td-626: `--check` cannot see stale instructions.
  - td-627: the clone installer's hardcoded identity.
  - td-628: mutation survivors in the file reads.
  - td-629: one registry-precedence rule for the hook and the installer.
  - td-630: the lexical render-slot comparison.
  - td-631: Python 3.9 runtime coverage.
  - td-632: the rules-failure branch's test and `install_claude.sh`'s size.
- **Unproven live:** Claude Code's substitution of the token in a cached plugin's skill body. A session that loads the skill from a cache copy would show it.

## Requirements

### Observable Surface

- `/praxion-complete-install` — the existing hand path: a plugin skill the person invokes; it runs only a read-only check and hands over a command for the person's own terminal
- `install.sh code --complete-install` — the command the skill hands over, written out with the resolved plugin root in front, and run by the person in their own terminal, where its prompts can be answered on standard input
- `install.sh code --check` — the read-only health check the skill runs itself
- `/praxion-complete-uninstall` — the hand path's reversal: a plugin skill that runs the same read-only check and hands over `install.sh code --complete-uninstall` for the person's own terminal
- `Praxion plugin not found — nothing to uninstall` — the uninstall skill's existing not-found report
- `install.sh code` — a clone checkout's own installer
- `${CLAUDE_PLUGIN_ROOT}` — the path Claude Code substitutes into a plugin skill's body when it loads the skill: the absolute path of the plugin's installed version (Claude Code docs, skills reference "Available string substitutions" and plugin manifest reference "Where each variable resolves", read 2026-11-11)
- `CLAUDE_PLUGIN_ROOT` — the environment variable Claude Code exports to hook, MCP and LSP processes. Per the same docs it is not present in the environment of commands Claude runs through the Bash tool, so a value there comes from the person's own configuration
- `~/.claude/plugins/installed_plugins.json` — Claude Code's plugin registry (`installed_plugins.json`); each praxion entry lists an install path (`installPath`) and a scope
- `~/.claude/plugins/cache/bit-agora/praxion` — the plugin cache: one directory per version, older ones kept after an update
- `~/.claude/CLAUDE.md` — the person's global instructions
- `claude/config/CLAUDE.md.tmpl` — the shipped template inside a version's directory, with placeholders for the personal values
- `claude/config/CLAUDE.md` — the rendered instructions inside a version's directory or a clone checkout
- `~/.claude/rules` — where the person's rule links live
- `~/.local/bin` — where the person's script links live
- `hooks/auto_complete_install.py` — the plugin's first-session hook, which runs the update refresh
- `systemMessage` — the hook output field Claude Code shows the person
- `[Praxion] Update refresh could not finish` — the start of the hook's failure line, which names `/praxion-complete-install`
- `Praxion complete install done` — the hand path's existing closing line
- `Praxion plugin not found` — the start of the skill's existing not-found report
- `claude plugin install praxion@bit-agora` — the install command the not-found report names
- `skills/README.md` — the skills catalog, which holds a row for the hand path
- `python3` — the interpreter on the person's PATH; stock macOS ships Python 3.9
- `HOME` — the person's home directory, which every path above starts from
- `GitHub` — the code host whose profile URL is one of the personal values
- `tests/test_complete_commands_hand_off_to_terminal.py` — the existing test that the skill never runs the mutating command itself
- `python3 scripts/measure_token_budget.py --json` — the instrument for the listing-tokens footprint
- `python3 scripts/check_agent_prompt_size.py --json` — the instrument for the prompt-size footprint

### Terms

- **The hand path** is `/praxion-complete-install` together with the command it hands over, run in the person's own terminal.
- **The installed version** is the version directory the skill resolves (REQ-01).
- **Personal values** are the username, the email address and the `GitHub` URL.
- **An earlier render** is `claude/config/CLAUDE.md` inside a version directory of the plugin cache other than the installed one.
- A render **reads back** when it is exactly its own version's template with each placeholder replaced by a single-line value, and a placeholder that appears more than once by the same value each time. The values it carried are then known.
- **The derived value** is the value a fresh install would use for a personal value: the one derived from the person's git identity, or the anonymous stand-in when there is none.
- **An answer** is a line the person enters on the command's input. Pressing Enter accepts the default the prompt offers. An input that ends is no answer.
- **The instructions are left behind** when, at the end of the run, `~/.claude/CLAUDE.md` is absent, dangles, or resolves to a render other than one of the installed version's template, and it is neither the person's own nor a clone's (REQ-11).

### REQ-01: The skill hands over the installed version's command

**When** the person invokes `/praxion-complete-install` or `/praxion-complete-uninstall`
**and** the path Claude Code substitutes for `${CLAUDE_PLUGIN_ROOT}` in the skill is an existing directory, or failing that, `~/.claude/plugins/installed_plugins.json` lists for the praxion plugin an install path that is an existing directory, a user-scope entry before any other
**the system** runs `install.sh code --check` from that directory and hands over `install.sh code --complete-install` (or, for the uninstall skill, `install.sh code --complete-uninstall`) with that directory written out in front of it. It never picks a version directory by listing the plugin cache, and never uses a `CLAUDE_PLUGIN_ROOT` value that the shell running the skill's commands carries from elsewhere
**so that** the command finishes, or reverses, the version Claude Code has installed, not the oldest cached one, and not a checkout the person's own configuration happens to export.

### REQ-02: No installed plugin, no command

**When** the person invokes `/praxion-complete-install` or `/praxion-complete-uninstall`
**and** neither the substituted root nor the registry names an existing directory
**the system** reports `Praxion plugin not found` (with `claude plugin install praxion@bit-agora` as the way to install it, from the install skill; `Praxion plugin not found — nothing to uninstall`, from the uninstall skill), runs no check and hands over no command, even when `~/.claude/plugins/cache/bit-agora/praxion` holds version directories
**so that** the person is never handed a command that would install from a version Claude Code does not run.

### REQ-03: The skill says what the command finishes

**When** the skill summarizes its check and hands over the command
**the system** tells the person that the command brings `~/.claude/CLAUDE.md` to the installed version as well as linking the rules and scripts, and that it may ask for their personal values. The skill's own description and its row in `skills/README.md` say the same
**so that** the person running the named command knows it finishes the instructions too.

### REQ-04: The instructions change is offered and can be declined

**When** the command reaches the instructions
**and** it would change what `~/.claude/CLAUDE.md` holds or points to (REQ-05, REQ-06, REQ-08, REQ-09)
**the system** first offers that change with its own prompt, as it offers the rules and the scripts. When the person declines, it writes nothing to `~/.claude/CLAUDE.md` or to any render, and names the instructions as skipped in its closing report
**so that** every change the hand path makes to the person's global instructions is one they agreed to.

### REQ-05: A readable earlier render's identity is carried forward

**When** the person accepts the instructions change
**and** `~/.claude/CLAUDE.md` is a live link into an earlier render that reads back
**the system** makes `~/.claude/CLAUDE.md` read exactly as the installed version's `claude/config/CLAUDE.md.tmpl` with each placeholder replaced by the value the earlier render carried, even when the derived values differ. It asks no question about the personal values, and it leaves the earlier render byte-identical. `~/.claude/CLAUDE.md` still reads the same after the earlier version's directory is removed from the cache
**so that** a refresh that stopped short is finished with the person's identity intact.

### REQ-06: A derived value fills only a value never carried

**When** the hand path carries an earlier render's values forward
**and** the installed version's template holds a placeholder that the earlier render carried no value for, or left as the placeholder itself
**the system** fills that placeholder, and only that one, with its derived value
**so that** a derived value never replaces a value the person already had.

### REQ-07: Instructions already current are left as they are

**When** the command reaches the instructions
**and** `~/.claude/CLAUDE.md` is a live link into the installed version's own render, and that render reads back with a value for every placeholder of the installed version's template
**the system** leaves the link and the render byte-identical, offers no change, asks nothing, and reports the instructions as current
**so that** running the hand path again is safe and quiet about what is already done.

### REQ-08: An unreadable render is replaced only with the person's answers

**When** the person accepts the instructions change
**and** `~/.claude/CLAUDE.md` is a live link into the render of any version in the plugin cache, the installed one included, that does not read back, for example because it was hand-edited, cut short or rendered from another template
**the system** asks the person, at a prompt in their terminal, for each personal value, offering its derived value as the default. After the last value is answered, it shows the values it will write and asks the person to confirm: Enter or "y" confirms, "n" declines. Only after the person confirms does it make `~/.claude/CLAUDE.md` read as the installed version's template filled with the values the person gave or accepted. A decline leaves the link and every render byte-identical and names the instructions as skipped in the closing report. The render the link pointed to before is never modified either way
**so that** the person's identity is never silently replaced with a derived one, and nothing they wrote is overwritten.

### REQ-09: Missing instructions are set up with the person's answers

**When** the person accepts the instructions change
**and** `~/.claude/CLAUDE.md` is absent, or is a link into the plugin cache that no longer resolves
**the system** asks for each personal value as REQ-08 describes and, with the person's answers, makes `~/.claude/CLAUDE.md` read as the installed version's template filled with those values
**so that** the hand path finishes an install whose instructions are missing.

### REQ-10: No answer writes no identity

**When** the hand path asks a question about the instructions, the offer of REQ-04 or a personal value of REQ-08 or REQ-09
**and** the input ends before an answer
**the system** writes no personal value, leaves `~/.claude/CLAUDE.md` and every render exactly as they were, and never reports the instructions as set up
**so that** a derived identity is never written for a person who was never asked.

### REQ-11: The person's own and a clone's instructions are left alone, and the report says so

**When** the command reaches the instructions
**and** `~/.claude/CLAUDE.md` is anything other than a link, such as a regular file, or is a link that points anywhere outside the plugin cache, such as a clone checkout's `claude/config/CLAUDE.md`, whether or not it resolves
**the system** leaves it, and any file it points to, byte-identical with unchanged modification times, offers no change and asks for no personal value. Its closing report says it left the instructions alone, and whether that is because they are the person's own file or a link outside the plugin cache
**so that** the hand path never takes over instructions it does not own, and the person knows why they were not touched.

### REQ-12: A checkout's command leaves the instructions alone

**When** the command runs from a plugin root that is not a version directory of the plugin cache, such as a clone checkout
**the system** changes nothing in `~/.claude/CLAUDE.md` or in any file it points to, asks for no personal value, and names `install.sh code` from that checkout as the way to set up its instructions
**so that** the hand path never moves a marketplace install's instructions into a checkout, and never renders a clone's instructions behind its own installer's back.

### REQ-13: A failed instructions change keeps working instructions

**When** the instructions change fails part-way, for example because a directory is not writable or a file cannot be read
**the system** leaves `~/.claude/CLAUDE.md` as it was before the change, or resolving to the complete new render, never to a missing, empty or half-written file
**so that** a failure on the hand path never leaves a session without the global instructions it had.

### REQ-14: One step's failure costs no other step

**When** one of the command's steps (instructions, rules, scripts) fails
**the system** still offers and runs the remaining steps, names the failed step and the kind of failure in its closing report, and ends with a failure status
**so that** the person gets everything the command can still do, and a script or a person reading the status learns the run did not finish.

### REQ-15: The closing report is truthful

**When** the command finishes its steps
**the system** ends with a report that names, for the instructions, the rules and the scripts, which it set up, which were already current, which it left alone and why, which the person skipped, and which it could not do. For each step the person skipped or the command could not do, the report says how to finish it; for a skipped step that may be running the same command again and accepting the step. It prints `Praxion complete install done` only when no step failed and the instructions are not left behind
**so that** the person never reads "done" over instructions that are still broken or out of date.

### REQ-16: The identity goes only into the instructions

**When** the hand path writes the personal values
**the system** writes them only into the rendered instructions, saves no other copy of them in the home directory or the plugin cache, and writes them to no log. It shows them only at its own prompts and in its report, in the person's terminal
**so that** the rendered instructions stay the one place the identity lives, the place the next update reads it from.

### REQ-17: The hand path works with stock macOS python3

**When** the `python3` on the person's PATH is Python 3.9, as stock macOS ships it
**the system**'s handed-over command handles the instructions as REQ-04 to REQ-16 describe, with no failure caused by the interpreter's version
**so that** the hand path finishes the install on a Mac with no extra interpreter installed.

## Spec Question Answers

Round 0, for the orchestrator to answer before design. Each carries the reading the requirements take now. An answer that differs amends the requirement text named.

### SQ-01: What does KS4's "`CLAUDE_PLUGIN_ROOT` when set" mean for a skill? (REQ-01)

- **Kind:** specification (KS4 against the current Claude Code docs).
- **Question:** The docs (see Docs Verification below) say `${CLAUDE_PLUGIN_ROOT}` is substituted into a plugin skill's body when the skill loads, and is not in the environment of Bash-tool commands. So the skill never sees the variable as set. Any value its shell does carry is the person's own export. On this machine that export points at the dev checkout, and reading it would hand over the checkout's command, which REQ-12 then refuses to use for the instructions.
- **Reading taken:** REQ-01 reads "when set" as "the path Claude Code substitutes, when it names an existing directory", and forbids reading the variable from the shell's environment. A substitution that did not happen counts as not set, because the literal text would otherwise expand from that same environment. The registry is the fallback.
- **Also confirm:** the substituted path names the version the current session loaded. After an update and a restart, that is the version the registry names. In a session not restarted since an update, it is the earlier version. The reading accepts that: the next session's refresh carries forward from what the hand path wrote.
- **Answer (orchestrator, 2026-11-11, under the user's standing delegation of 2026-11-06):** the reading stands, and so does the stale-session caveat. "When set" means the path Claude Code substitutes into the skill's body, when it names an existing directory; the shell's `CLAUDE_PLUGIN_ROOT` is never read. Text that was not substituted must stay inert, never expanded from the shell. The intake evidence agrees: this machine's export points at the dev checkout, while the registry names `0.62.0`. No requirement text changes.

### SQ-02: What does the hand path do with the instructions when run from a checkout? (REQ-12)

- **Kind:** specification (scope edge that KS1 to KS5 leave unstated).
- **Question:** A `--plugin-dir` session substitutes a clone checkout as the plugin root, so the skill can hand over a checkout's command. KS3 covers an instructions link into a clone. It does not cover a link into the plugin cache, or an absent entry, met while the command runs from a checkout.
- **Reading taken:** leave the instructions alone and name the checkout's own installer. This is what the hand path does today, and the update path also acts only from a version directory of the cache.
- **Answer (orchestrator, 2026-11-11, standing delegation):** the reading stands. A checkout owns its instructions through its own installer (`install.sh code`, `--reconfigure` for new values), so the hand path from a checkout leaves them alone and names that installer. No requirement text changes.

### SQ-03: May the hand path save the personal values anywhere besides the render? (REQ-16)

- **Kind:** specification (constrains whether the clone install's prompt can be shared as it is).
- **Question:** The brief allows the hand path to share the clone install's prompt. That prompt also saves the values to a file beside the template, which on the hand path would be inside the cache version directory. dec-498 recorded that the update path persists no new copy and reads the identity from the previous render.
- **Reading taken:** the hand path saves no other copy, so the render stays the one store. A shared prompt is still possible without the save.
- **Answer (orchestrator, 2026-11-11, standing delegation):** the reading stands. A values file inside a cache version directory would be a second store that the next update never reads (dec-498 reads the identity from the previous render), so it would only drift. No requirement text changes.

### SQ-04: Does the same resolution fix cover `/praxion-complete-uninstall`? (REQ-01, REQ-02)

- **Kind:** scope (raised by the orchestrator from the context-engineer's spec-stage review in `CONTEXT_REVIEW.md`).
- **Question:** `skills/praxion-complete-uninstall/SKILL.md` resolves its root with the same `${CLAUDE_PLUGIN_ROOT:-$(ls -d …/praxion/*/ | head -1)}` expression. So on a stock machine it hands over the oldest cached version's uninstaller, the reversal that the install skill's own Reversal section names.
- **Answer (orchestrator, 2026-11-11, standing delegation):** in scope. It is the same defect in the same expression, and REQ-01's fix would otherwise leave the reversal on the old resolution. REQ-01 and REQ-02 now cover both skills, and the Observable Surface names the uninstall skill and its not-found report. Nothing else about the uninstall path changes. Requirement text amended: REQ-01, REQ-02, Observable Surface.

### AD-SQ-01: May the frozen Codex/Cursor export digests of the two hand-path skills change? (health guard)

- **Raised by:** acceptance design (`ACCEPTANCE_TESTS.md` SQ-01): the frozen export test pins the base digests of both skills' Codex exports, which any compliant change to REQ-01 and REQ-03 moves.
- **Answer (orchestrator, 2026-11-11, standing delegation):** allowed. The exports of the two hand-path skills may change, but only to exactly what their exporters regenerate from the amended skills; every other frozen export stays byte-identical. The export health guard's acceptance criterion now says so. The test-engineer amends the frozen guard minimally afterwards.

### AD-SQ-02: How does the person decline at the personal-values prompt? (REQ-08, REQ-09)

- **Raised by:** acceptance design (`ACCEPTANCE_TESTS.md` SQ-02).
- **Answer (orchestrator, 2026-11-11, standing delegation):** after the last value is answered, the command shows the values it will write and asks for a confirmation. Enter or "y" confirms; "n" declines. A decline leaves the link and every render byte-identical and names the instructions as skipped. REQ-09 inherits this through "as REQ-08 describes". End of input stays REQ-10, never consent. Requirement text amended: REQ-08.

### AD-SQ-03: Does "how to finish" cover skipped steps? (REQ-15)

- **Raised by:** acceptance design (`ACCEPTANCE_TESTS.md` SQ-03).
- **Answer (orchestrator, 2026-11-11, standing delegation):** yes. For each step the person skipped or the command could not do, the report says how to finish it; for a skipped step that may be running the same command again and accepting the step. Requirement text amended: REQ-15.

### Interpretations taken (stated, not asked)

- **I-01 (REQ-06):** On the hand path, a placeholder the earlier render never carried is filled with its derived value without a question, as on the update path. The person has already accepted the change at the REQ-04 offer, and the shared carry-forward stays one behavior.
- **I-02 (REQ-09):** For an absent or dangling entry, the hand path asks for each value, as KS2 asks for an unreadable render. It does not reuse the first-session hook's 30-second confirm-the-derived-values prompt. The hand path has the person's terminal, and the brief's intent is "rendered with their own identity". The hook's own handling of these states does not change.
- **I-03 (REQ-10, Terms):** An answer is a line on the command's input. So the acceptance drivers can answer the prompts through standard input, and an input that ends is never consent. The brief's flag that piped answers were read as "skip" is for the acceptance designer to settle in the driver against this definition.
- **I-04 (REQ-01):** When the registry holds more than one praxion entry, the user-scope entry wins. The installer's existing registry reader does this. The hook reads the first praxion entry whose path exists, which gives the same answer for the usual single entry.
- **I-05 (REQ-14, REQ-15):** Only a failed step gives a failure status. A step the person declines does not. A declined rules or scripts step still allows the done line, with the skip named. Declined instructions do not allow it, because the instructions are then left behind.

## Traceability

Rendered from the reconciled `traceability.yml` (single file, no fragments). Every node passed in the derived-scope runs at `2209cafa` and over `2209cafa..14f5d9a4`, and the rework's tests at `a3861d7f`.

| Requirement | Test(s) | Implementation | Status |
|-------------|---------|----------------|--------|
| REQ-01: The skill hands over the installed version's command | `tests/test_complete_skills_resolve_root_alike.py::test_the_two_blocks_differ_only_in_the_not_found_line`<br>`tests/test_complete_skills_resolve_root_alike.py::test_no_skill_lists_the_cache_or_defaults_a_shell_variable`<br>`tests/test_complete_skills_resolve_root_alike.py::test_the_substituted_token_is_read_through_a_quoted_heredoc`<br>`tests/acceptance/test_hand_path_resolves_the_installed_version.py::test_the_check_runs_from_the_installed_version_and_from_nowhere_else`<br>`tests/acceptance/test_hand_path_resolves_the_installed_version.py::test_the_installed_versions_directory_is_written_out_for_the_person`<br>`tests/e2e/test_hand_path_finishes_a_stopped_refresh.py::test_the_skill_hands_over_the_installed_versions_command` | `skills/praxion-complete-install/SKILL.md`<br>`skills/praxion-complete-uninstall/SKILL.md` | PASS |
| REQ-02: No installed plugin, no command | `tests/test_complete_skills_resolve_root_alike.py::test_the_two_blocks_differ_only_in_the_not_found_line`<br>`tests/acceptance/test_hand_path_resolves_the_installed_version.py::test_with_no_installed_plugin_no_installer_runs_despite_a_full_cache`<br>`tests/acceptance/test_hand_path_resolves_the_installed_version.py::test_the_install_skill_reports_the_plugin_not_found_and_how_to_install_it`<br>`tests/acceptance/test_hand_path_resolves_the_installed_version.py::test_the_uninstall_skill_reports_there_is_nothing_to_uninstall` | `skills/praxion-complete-install/SKILL.md`<br>`skills/praxion-complete-uninstall/SKILL.md` | PASS |
| REQ-03: The skill says what the command finishes | `tests/acceptance/test_hand_path_says_what_it_finishes.py::test_the_text_says_the_command_brings_the_global_instructions_along`<br>`tests/acceptance/test_hand_path_says_what_it_finishes.py::test_the_text_says_the_command_may_ask_for_personal_values` | `skills/praxion-complete-install/SKILL.md`<br>`skills/README.md` | PASS |
| REQ-04: The instructions change is offered and can be declined | `hooks/test_install_hand_path.py::TestOffer::test_the_choice_is_read_from_the_input`<br>`hooks/test_install_hand_path.py::TestOffer::test_the_offer_names_the_change_the_skip_and_why_in_the_designed_shape`<br>`hooks/test_install_hand_path.py::TestOffer::test_an_invalid_choice_asks_again`<br>`hooks/test_install_hand_path.py::TestCarryForward::test_the_change_is_offered_before_anything_is_written`<br>`tests/acceptance/test_hand_path_carries_a_readable_identity_forward.py::test_the_instructions_change_is_offered_at_its_own_prompt`<br>`tests/acceptance/test_hand_path_carries_a_readable_identity_forward.py::test_a_declined_offer_was_made`<br>`tests/acceptance/test_hand_path_carries_a_readable_identity_forward.py::test_a_declined_offer_writes_nothing_to_the_instructions_or_any_render`<br>`tests/acceptance/test_hand_path_carries_a_readable_identity_forward.py::test_a_declined_offer_says_how_to_finish_the_instructions`<br>`tests/acceptance/test_hand_path_carries_a_readable_identity_forward.py::test_a_declined_offer_is_named_as_skipped_and_the_run_is_not_called_done` | `hooks/_install_hand_path.py::main`<br>`hooks/_install_hand_path.py::run_instructions_step`<br>`hooks/_install_hand_path.py::ask_offer`<br>`install_claude.sh::complete_install_from_plugin`<br>`install_claude.sh::complete_install_instructions_step` | PASS |
| REQ-05: A readable earlier render's identity is carried forward | `hooks/test_install_carry_forward.py::TestInstructionsCarryForward::test_a_link_naming_a_file_other_than_the_primary_render_is_the_one_read`<br>`hooks/test_install_carry_forward.py::TestInstructionsCarryForward::test_the_primary_render_is_not_read_when_the_link_names_another_file`<br>`hooks/test__install_refresh.py::test_a_render_that_is_not_the_primary_file_is_named_as_it_is`<br>`hooks/test__install_refresh.py::test_the_render_is_normalised_the_way_the_link_text_is`<br>`hooks/test__install_refresh.py::test_every_cache_row_names_a_render_inside_its_version_directory`<br>`hooks/test__install_refresh.py::test_a_render_outside_its_version_directory_cannot_be_built`<br>`hooks/test_install_carry_forward.py::TestWriteInstructions::test_the_render_holds_the_given_values_and_the_link_points_at_it`<br>`hooks/test__install_refresh.py::test_each_state_gets_the_plan_its_precedence_row_names`<br>`hooks/test__install_refresh.py::test_the_installed_version_is_judged_by_directory_not_by_render_name`<br>`hooks/test_install_read_back.py::TestReadBack::test_a_render_that_reads_back_gives_its_values_and_no_missing_key`<br>`hooks/test_install_read_back.py::TestReadBack::test_the_render_the_link_names_is_read_and_not_the_versions_primary`<br>`hooks/test_install_read_back.py::TestConsecutiveUpdatesAfterAnAlternateWrite::test_the_next_update_reads_the_alternate_and_links_its_own_primary`<br>`hooks/test_install_read_back.py::TestConsecutiveUpdatesAfterAnAlternateWrite::test_the_update_after_that_reads_the_new_primary`<br>`hooks/test_install_hand_path.py::TestCarryForward::test_the_offer_is_accepted_and_the_values_carried_without_a_question`<br>`hooks/test_install_hand_path.py::TestCarryForward::test_the_earlier_render_is_left_byte_identical`<br>`hooks/test_install_hand_path.py::TestCarryForward::test_the_instructions_still_read_the_same_once_the_earlier_version_is_removed`<br>`hooks/test_install_hand_path.py::TestCarryForward::test_a_link_written_relative_to_the_claude_directory_is_followed`<br>`tests/acceptance/test_hand_path_carries_a_readable_identity_forward.py::test_the_instructions_read_as_the_new_template_filled_with_the_earlier_values`<br>`tests/acceptance/test_hand_path_carries_a_readable_identity_forward.py::test_no_question_is_asked_about_the_personal_values`<br>`tests/acceptance/test_hand_path_carries_a_readable_identity_forward.py::test_the_earlier_render_is_left_byte_identical`<br>`tests/acceptance/test_hand_path_carries_a_readable_identity_forward.py::test_the_instructions_still_read_the_same_once_the_earlier_version_is_removed`<br>`tests/acceptance/test_hand_path_carries_a_readable_identity_forward.py::test_the_closing_report_says_the_instructions_were_set_up_and_done`<br>`tests/e2e/test_hand_path_finishes_a_stopped_refresh.py::test_a_readable_render_ends_filled_with_the_values_it_carried_and_nothing_asked` | `hooks/_install_update.py::write_instructions`<br>`hooks/_install_update.py::carry_forward_instructions`<br>`hooks/_install_refresh.py::CachedRender`<br>`hooks/_install_refresh.py::plan_hand_path_instructions`<br>`hooks/_install_update.py::read_back`<br>`hooks/_install_hand_path.py::main`<br>`hooks/_install_hand_path.py::run_instructions_step` | PASS |
| REQ-06: A derived value fills only a value never carried | `hooks/test_install_carry_forward.py::TestWriteInstructions::test_only_the_keys_the_values_lack_are_filled_from_the_derived_ones`<br>`hooks/test_install_carry_forward.py::TestWriteInstructions::test_a_derived_value_never_replaces_a_given_one`<br>`hooks/test_install_carry_forward.py::TestWriteInstructions::test_nothing_is_printed_and_no_other_copy_is_saved`<br>`hooks/test_install_read_back.py::TestReadBack::test_a_key_only_the_installed_template_has_is_missing`<br>`hooks/test_install_read_back.py::TestReadBack::test_a_key_left_as_its_placeholder_is_missing`<br>`hooks/test_install_read_back.py::TestReadBack::test_the_values_are_read_against_the_template_of_the_version_that_rendered_them`<br>`tests/acceptance/test_hand_path_carries_a_readable_identity_forward.py::test_a_derived_value_fills_only_the_placeholder_the_earlier_render_carried_none_for` | `hooks/_install_update.py::write_instructions`<br>`hooks/_install_update.py::carry_forward_instructions`<br>`hooks/_install_refresh.py::CachedRender`<br>`hooks/_install_update.py::read_back` | PASS |
| REQ-07: Instructions already current are left as they are | `hooks/test__install_refresh.py::test_each_state_gets_the_plan_its_precedence_row_names`<br>`hooks/test__install_refresh.py::test_the_installed_version_is_judged_by_directory_not_by_render_name`<br>`hooks/test_install_hand_path.py::TestNoQuestion::test_current_instructions_are_left_as_they_are_and_nothing_is_asked`<br>`tests/acceptance/test_hand_path_carries_a_readable_identity_forward.py::test_current_instructions_are_left_byte_identical`<br>`tests/acceptance/test_hand_path_carries_a_readable_identity_forward.py::test_current_instructions_are_neither_offered_nor_asked_about`<br>`tests/acceptance/test_hand_path_carries_a_readable_identity_forward.py::test_current_instructions_are_reported_as_current`<br>`tests/acceptance/test_hand_path_carries_a_readable_identity_forward.py::test_a_second_run_after_finishing_finds_the_instructions_current` | `hooks/_install_refresh.py::plan_hand_path_instructions`<br>`hooks/_install_hand_path.py::main`<br>`hooks/_install_hand_path.py::run_instructions_step` | PASS |
| REQ-08: An unreadable render is replaced only with the person's answers | `hooks/test__install_refresh.py::test_each_state_gets_the_plan_its_precedence_row_names`<br>`hooks/test__install_refresh.py::test_a_render_goes_to_the_primary_slot_unless_the_link_resolves_to_it`<br>`hooks/test_install_read_back.py::TestReadBack::test_a_render_that_is_not_its_template_filled_in_is_unreadable`<br>`hooks/test_install_read_back.py::TestReadBack::test_a_render_that_cannot_be_decoded_is_unreadable`<br>`hooks/test_install_read_back.py::TestReadBack::test_a_render_that_is_a_directory_raises_and_is_not_read_as_unreadable`<br>`hooks/test_install_read_back.py::TestReadBack::test_a_render_that_cannot_be_opened_raises_its_error`<br>`hooks/test_install_read_back.py::TestReadBack::test_a_missing_template_of_the_rendering_version_raises`<br>`hooks/test_install_read_back.py::TestReadBack::test_a_missing_installed_template_raises`<br>`hooks/test_install_read_back.py::TestWriteInstructionsSlot::test_a_link_into_the_roots_primary_gets_the_alternate_and_the_primary_is_untouched`<br>`hooks/test_install_read_back.py::TestWriteInstructionsSlot::test_a_root_spelled_with_a_parent_segment_is_still_the_root_the_link_resolves_into`<br>`hooks/test_install_read_back.py::TestWriteInstructionsSlot::test_a_relative_link_into_the_roots_primary_gets_the_alternate`<br>`hooks/test_install_read_back.py::TestWriteInstructionsSlot::test_a_link_into_the_roots_alternate_gets_the_primary`<br>`hooks/test_install_read_back.py::TestWriteInstructionsSlot::test_a_link_into_another_version_gets_the_primary`<br>`hooks/test_install_read_back.py::TestWriteInstructionsSlot::test_no_link_gets_the_primary`<br>`hooks/test_install_hand_path.py::TestAskForValues::test_the_given_values_are_written_and_each_is_asked_with_its_default`<br>`hooks/test_install_hand_path.py::TestAskForValues::test_enter_at_each_prompt_renders_the_derived_values`<br>`hooks/test_install_hand_path.py::TestAskForValues::test_the_values_to_write_are_shown_before_they_are_written`<br>`hooks/test_install_hand_path.py::TestAskForValues::test_n_at_the_confirmation_leaves_everything_as_it_was_and_names_it_skipped`<br>`hooks/test_install_hand_path.py::TestAskForValues::test_the_installed_versions_own_hand_edited_render_is_not_modified`<br>`hooks/test_install_hand_path.py::TestValues::test_enter_at_each_prompt_takes_the_derived_value`<br>`hooks/test_install_hand_path.py::TestValues::test_a_typed_value_wins_and_is_stripped`<br>`hooks/test_install_hand_path.py::TestConfirmation::test_enter_or_y_confirms_and_n_declines`<br>`hooks/test_install_hand_path.py::TestConfirmation::test_anything_else_asks_again`<br>`hooks/test_install_hand_path.py::TestConfirmation::test_the_last_lines_show_the_three_values_and_never_say_default`<br>`tests/acceptance/test_hand_path_asks_for_an_identity_it_cannot_read.py::test_the_instructions_read_as_the_installed_template_filled_with_the_given_values`<br>`tests/acceptance/test_hand_path_asks_for_an_identity_it_cannot_read.py::test_each_personal_value_is_asked_for`<br>`tests/acceptance/test_hand_path_asks_for_an_identity_it_cannot_read.py::test_each_question_offers_the_derived_value_as_its_default`<br>`tests/acceptance/test_hand_path_asks_for_an_identity_it_cannot_read.py::test_after_the_last_value_the_values_to_be_written_are_shown_for_confirmation`<br>`tests/acceptance/test_hand_path_asks_for_an_identity_it_cannot_read.py::test_the_render_the_link_pointed_to_is_never_modified`<br>`tests/acceptance/test_hand_path_asks_for_an_identity_it_cannot_read.py::test_the_run_is_reported_done_once_the_instructions_are_set_up`<br>`tests/acceptance/test_hand_path_asks_for_an_identity_it_cannot_read.py::test_pressing_enter_at_each_question_renders_the_derived_values`<br>`tests/acceptance/test_hand_path_asks_for_an_identity_it_cannot_read.py::test_declining_at_the_values_prompt_leaves_the_link_and_every_render_byte_identical`<br>`tests/acceptance/test_hand_path_asks_for_an_identity_it_cannot_read.py::test_declining_at_the_confirmation_names_the_instructions_skipped_and_how_to_finish`<br>`tests/acceptance/test_hand_path_asks_for_an_identity_it_cannot_read.py::test_declining_at_the_values_prompt_is_not_reported_done`<br>`tests/e2e/test_hand_path_finishes_a_stopped_refresh.py::test_an_unreadable_render_ends_filled_with_the_values_the_person_typed` | `hooks/_install_refresh.py::plan_hand_path_instructions`<br>`hooks/_install_refresh.py::render_slot`<br>`hooks/_install_update.py::read_back`<br>`hooks/_install_update.py::write_instructions`<br>`hooks/_install_hand_path.py::ask_values`<br>`hooks/_install_hand_path.py::confirm_values`<br>`hooks/_install_hand_path.py::main`<br>`hooks/_install_hand_path.py::run_instructions_step` | PASS |
| REQ-09: Missing instructions are set up with the person's answers | `hooks/test__install_refresh.py::test_each_state_gets_the_plan_its_precedence_row_names`<br>`hooks/test_install_hand_path.py::TestAskForValues::test_missing_instructions_are_set_up_with_the_given_values`<br>`tests/acceptance/test_hand_path_asks_for_an_identity_it_cannot_read.py::test_missing_instructions_are_set_up_with_the_given_values` | `hooks/_install_refresh.py::plan_hand_path_instructions`<br>`hooks/_install_hand_path.py::main`<br>`hooks/_install_hand_path.py::run_instructions_step`<br>`hooks/_install_hand_path.py::ask_values`<br>`hooks/_install_hand_path.py::confirm_values` | PASS |
| REQ-10: No answer writes no identity | `hooks/test_install_hand_path.py::TestAskForValues::test_the_input_ending_writes_nothing_and_is_no_answer`<br>`hooks/test_install_hand_path.py::TestAskForValues::test_the_input_ending_for_an_absent_link_creates_no_link`<br>`hooks/test_install_hand_path.py::TestOffer::test_the_input_ending_is_no_answer`<br>`hooks/test_install_hand_path.py::TestValues::test_the_input_ending_at_any_value_is_no_answer`<br>`hooks/test_install_hand_path.py::TestConfirmation::test_the_input_ending_is_no_answer`<br>`hooks/test_install_hand_path.py::test_run_as_a_script_the_input_ending_exits_with_the_left_behind_status`<br>`tests/acceptance/test_hand_path_asks_for_an_identity_it_cannot_read.py::test_an_input_that_ends_reaches_a_question_about_the_instructions`<br>`tests/acceptance/test_hand_path_asks_for_an_identity_it_cannot_read.py::test_an_input_that_ends_leaves_the_instructions_and_every_render_as_they_were`<br>`tests/acceptance/test_hand_path_asks_for_an_identity_it_cannot_read.py::test_an_input_that_ends_writes_no_derived_value`<br>`tests/acceptance/test_hand_path_asks_for_an_identity_it_cannot_read.py::test_an_input_that_ends_never_reports_the_instructions_set_up` | `hooks/_install_hand_path.py::main`<br>`hooks/_install_hand_path.py::run_instructions_step` | PASS |
| REQ-11: The person's own and a clone's instructions are left alone, and the report says so | `hooks/test__install_refresh.py::test_each_state_gets_the_plan_its_precedence_row_names`<br>`hooks/test__install_refresh.py::test_a_checkout_run_names_a_persons_file_and_a_foreign_link_before_the_checkout`<br>`hooks/test_install_hand_path.py::TestNoQuestion::test_a_regular_file_is_left_alone_and_named_the_persons_own`<br>`hooks/test_install_hand_path.py::TestNoQuestion::test_a_link_outside_the_cache_is_left_alone_live_or_dangling`<br>`tests/acceptance/test_hand_path_leaves_instructions_it_does_not_own.py::test_instructions_not_owned_are_left_byte_identical_with_what_they_point_to`<br>`tests/acceptance/test_hand_path_leaves_instructions_it_does_not_own.py::test_instructions_not_owned_are_neither_offered_nor_asked_about`<br>`tests/acceptance/test_hand_path_leaves_instructions_it_does_not_own.py::test_the_closing_report_says_why_the_instructions_were_left_alone` | `hooks/_install_refresh.py::plan_hand_path_instructions`<br>`hooks/_install_hand_path.py::outcome_line`<br>`hooks/_install_hand_path.py::main`<br>`hooks/_install_hand_path.py::run_instructions_step` | PASS |
| REQ-12: A checkout's command leaves the instructions alone | `hooks/test__install_refresh.py::test_each_state_gets_the_plan_its_precedence_row_names`<br>`hooks/test__install_refresh.py::test_a_checkout_run_names_a_persons_file_and_a_foreign_link_before_the_checkout`<br>`hooks/test_install_hand_path.py::TestNoQuestion::test_a_checkout_leaves_the_instructions_alone_and_names_its_own_installer`<br>`hooks/test_install_hand_path.py::TestNoQuestion::test_a_checkout_still_names_a_regular_file_the_persons_own`<br>`tests/acceptance/test_hand_path_leaves_instructions_it_does_not_own.py::test_a_checkouts_command_changes_no_instructions`<br>`tests/acceptance/test_hand_path_leaves_instructions_it_does_not_own.py::test_a_checkouts_command_asks_for_no_personal_value`<br>`tests/acceptance/test_hand_path_leaves_instructions_it_does_not_own.py::test_a_checkouts_command_names_its_own_installer_for_the_instructions` | `hooks/_install_refresh.py::plan_hand_path_instructions`<br>`hooks/_install_hand_path.py::main`<br>`hooks/_install_hand_path.py::run_instructions_step`<br>`hooks/_install_hand_path.py::outcome_line` | PASS |
| REQ-13: A failed instructions change keeps working instructions | `hooks/test__install_refresh.py::test_a_render_goes_to_the_primary_slot_unless_the_link_resolves_to_it`<br>`hooks/test_install_read_back.py::TestWriteInstructionsSlot::test_a_failing_rename_leaves_the_link_and_the_file_it_resolves_to_as_they_were`<br>`hooks/test_install_read_back.py::TestWriteInstructionsSlot::test_a_failing_rename_into_the_primary_leaves_the_previous_render_linked`<br>`tests/acceptance/test_hand_path_reports_truthfully.py::test_a_failed_instructions_change_leaves_them_resolving_to_a_complete_render` | `hooks/_install_refresh.py::render_slot`<br>`hooks/_install_update.py::write_instructions` | PASS |
| REQ-14: One step's failure costs no other step | `tests/acceptance/test_hand_path_reports_truthfully.py::test_a_failed_instructions_change_still_offers_and_links_the_rules_and_scripts`<br>`tests/acceptance/test_hand_path_reports_truthfully.py::test_a_failed_instructions_change_is_named_with_its_kind_and_how_to_finish`<br>`tests/acceptance/test_hand_path_reports_truthfully.py::test_a_failed_instructions_change_ends_with_a_failure_status_and_no_done_line`<br>`tests/acceptance/test_hand_path_reports_truthfully.py::test_a_failed_scripts_step_still_finishes_the_instructions`<br>`tests/acceptance/test_hand_path_reports_truthfully.py::test_a_failed_scripts_step_is_named_and_ends_with_a_failure_status` | `install_claude.sh::complete_install_from_plugin`<br>`install_claude.sh::complete_install_rules_step`<br>`install_claude.sh::complete_install_scripts_step`<br>`install_claude.sh::run_fail_soft`<br>`install_claude.sh::link_user_scripts` | PASS |
| REQ-15: The closing report is truthful | `hooks/test_install_hand_path.py::test_every_outcome_prints_one_line_and_exits_with_its_status`<br>`hooks/test_install_hand_path.py::test_a_line_that_leaves_the_instructions_unfinished_says_how_to_finish`<br>`hooks/test_install_hand_path.py::test_every_failure_kind_has_words_and_none_carries_a_message`<br>`hooks/test_install_hand_path.py::TestFailures::test_an_unwritable_render_directory_is_a_permission_failure_and_keeps_the_link`<br>`tests/acceptance/test_hand_path_carries_a_readable_identity_forward.py::test_the_closing_report_says_the_instructions_were_set_up_and_done`<br>`tests/acceptance/test_hand_path_carries_a_readable_identity_forward.py::test_a_declined_offer_is_named_as_skipped_and_the_run_is_not_called_done`<br>`tests/acceptance/test_hand_path_carries_a_readable_identity_forward.py::test_current_instructions_are_reported_as_current`<br>`tests/acceptance/test_hand_path_asks_for_an_identity_it_cannot_read.py::test_the_run_is_reported_done_once_the_instructions_are_set_up`<br>`tests/acceptance/test_hand_path_asks_for_an_identity_it_cannot_read.py::test_declining_at_the_values_prompt_is_not_reported_done`<br>`tests/acceptance/test_hand_path_asks_for_an_identity_it_cannot_read.py::test_an_input_that_ends_never_reports_the_instructions_set_up`<br>`tests/acceptance/test_hand_path_leaves_instructions_it_does_not_own.py::test_the_closing_report_says_why_the_instructions_were_left_alone`<br>`tests/acceptance/test_hand_path_reports_truthfully.py::test_a_failed_instructions_change_ends_with_a_failure_status_and_no_done_line`<br>`tests/e2e/test_hand_path_finishes_a_stopped_refresh.py::test_the_rules_and_scripts_end_linked_from_the_installed_version`<br>`tests/e2e/test_hand_path_finishes_a_stopped_refresh.py::test_the_closing_report_says_the_install_is_done` | `hooks/_install_hand_path.py::main`<br>`hooks/_install_hand_path.py::outcome_line`<br>`install_claude.sh::complete_install_report`<br>`install_claude.sh::report_step`<br>`install_claude.sh::complete_install_instructions_step` | PASS |
| REQ-16: The identity goes only into the instructions | `hooks/test_install_read_back.py::TestReadBack::test_nothing_is_printed_and_nothing_is_written`<br>`hooks/test_install_read_back.py::TestWriteInstructionsSlot::test_nothing_is_printed_and_no_other_copy_is_saved`<br>`hooks/test_install_hand_path.py::test_a_given_value_is_in_the_render_and_nowhere_else_not_even_standard_output`<br>`hooks/test_install_hand_path.py::TestFailures::test_an_exception_message_never_reaches_the_line_or_the_output`<br>`hooks/test_install_hand_path.py::TestFailures::test_an_unexpected_exception_anywhere_is_named_unexpected`<br>`tests/acceptance/test_hand_path_asks_for_an_identity_it_cannot_read.py::test_the_given_values_are_written_into_the_rendered_instructions_and_nowhere_else`<br>`tests/acceptance/test_hand_path_asks_for_an_identity_it_cannot_read.py::test_no_log_written_during_the_run_holds_a_given_value` | `hooks/_install_update.py::read_back`<br>`hooks/_install_update.py::write_instructions`<br>`hooks/_install_hand_path.py::main`<br>`hooks/_install_hand_path.py::run_instructions_step` | PASS |
| REQ-17: The hand path works with stock macOS python3 | `hooks/test_install_hand_path.py::test_every_module_the_hand_path_imports_parses_as_python_3_9`<br>`hooks/test_install_hand_path.py::test_the_hand_path_imports_only_the_standard_library_and_its_siblings`<br>`hooks/test_install_hand_path.py::test_run_as_a_script_it_converses_on_standard_error_and_prints_one_line`<br>`tests/acceptance/test_hand_path_reports_truthfully.py::test_under_python_3_9_the_instructions_are_set_up_with_the_given_values` | `hooks/_install_hand_path.py::main` | PASS |
