# Spec: install-refresh (a marketplace install's first session after a plugin update brings its script links, rule links and instructions to the new version)

**Task slug**: `install-refresh`
**Created**: 2026-11-10
**Pipeline run**: 2026-11-10 (one session: intake, design, acceptance design, 12 plan steps, verification and a delta re-verification)
**Start date**: 2026-11-10
**End date**: 2026-11-10
**Archived**: 2026-11-10 (pre-merge, on branch feat/install-refresh; the merge to main finalizes the two drafts named below)
**Status**: completed -- final verdict PASS WITH FINDINGS (the final run FAILed once, on F1, closed by Spec Question SQ-05 and confirmed by the delta re-verification at `b59390d1`)
**Tier**: Standard (planned 5 of 16 charged spawns, with the step loop's implementer and reviewer agents ledgered as iterations, not charged; the verifier's calibration verdict reads `correct`: 25 requirements and 62 outer-loop nodes were too much for Lightweight, and nothing in the work needed Full's extra stages)
**Complexity**: medium-large by size (25 requirements, 12 plan steps, 34 files changed from the base to the archive head, about 4.2k lines added), medium by shape (one mechanism in one hook, run in sequence)
**Base commit**: `4cf729a5` · outer loop designed at `6e4a3fac` (drivers amended for SQ-01 and SQ-02 at `366744db`) · design `33a0541e` and `22bf1d82` · first production commit `8c4ef1c1` · final-run head `c06b84da` · archive head `b59390d1`
**Pipeline branch**: `feat/install-refresh`
**ADRs**: `dec-499` (category: architectural -- the first-session completion owns the update path; it narrows the earlier first-session ADR named under Key Decisions) and `dec-498` (category: implementation -- the personal values are carried from the previous version's render); finalize rewrites both ids to stable `dec-NNN` records
**Evidence base**: the two ADR drafts under `.ai-state/decisions/drafts/`; the spec digest `sha256:6764cd1e1aee` of `SPEC_EXTRACT.md` (the verifier re-checked it fresh in the delta re-verification); the branch's 19 commits from the base; the iteration ledger (21 records) and the light-review records of steps 1, 4, 6 and 7; the verifier's final report and its delta re-verification at `b59390d1`; and the verifier's probes, which ran the real hook over scratch machines built from the outer loop's driver. No eval session ran.

## Feature Summary

A marketplace install's first session after `claude plugin update praxion@bit-agora` now brings its script links, rule links and rendered instructions to the new version, with no relink.

Before this change a re-armed first-session completion refreshed only the rule links, and it never re-pointed a live one. `~/.claude/CLAUDE.md` and the `~/.local/bin` script links kept pointing into the previous version's directory of the plugin cache, so every release needed `bash install.sh --relink`, which a marketplace install has no clone to run (`td-593`). A second defect, `td-602`, let the acceptance drivers re-render the checkout's own `claude/config/CLAUDE.md` in place, which rewrote the operator's live global instructions whenever the suite ran.

Now the hook runs an **update path** when three things hold: the existing re-arm fires (the completion marker is older than the plugin cache directory), an earlier completion exists (the marker is present), and the plugin root is a version directory of the plugin cache. The path has three independent, fail-open steps. The rule step re-points every rule link into another cached version (live or dangling) and then sweeps and links as the existing refresh does. The script step plans over a snapshot of `~/.local/bin`: it re-points a cache link under an offered name, removes a cache link under a name the version no longer offers and links a free offered name. The instructions step classifies `~/.claude/CLAUDE.md` into one of five states and, for a live render of another version, re-renders the new template with the personal values the old render carried, writing the render and then the link by rename. A default fills only a placeholder the old render never carried, and an unrecoverable render keeps the old one. Any failure prints one stderr line naming `/praxion-complete-install`; success is silent; the marker is written either way, so a later session of the same version does nothing.

Everything else is unchanged. A link outside the plugin cache (a clone checkout's included), a regular file, a first install and a `--plugin-dir` session are never touched by the update path. The installer, `install.sh --check`, `hooks/hooks.json`, the template and the rules are untouched. An absent or dangling instructions entry recovers exactly as a first install does today, with its terminal-only confirmation prompt (SQ-04, SQ-05). No test run writes into the checkout's `claude/config/` files: the install drivers now run the installer from a stand-in copy of the tree, and an operator's own relink from a clone still renders into that clone.

Verified at `b59390d1`: all 62 outer-loop nodes pass; the bare root suite gave 18,010 passed, 37 skipped, 0 failed; the eval pocket 4,296 passed and the chronograph pocket 288 of 288. The always-loaded reading is 19,894 tokens at the base and at the head (the brief's 19,918 is a stale figure, not a regression), the Codex and Cursor exports are byte-identical (172 files, 0 differ), and `bash install.sh --check` gives the same verdict (rc 1, the same warning set) before and after. On the operator's own layout (a clone at `.../dev/praxion` beside a marketplace install), the real hook left 78 of 78 clone links as they were.

## What Was Built

- **Pure core** `hooks/_install_refresh.py` (226 lines, stdlib-only, no I/O): the cache-target predicate `cache_version_dir` (a path holding `plugins/cache/<marketplace>/praxion/<version>` as consecutive segments), the five-state instructions classifier `classify_instructions` (`NoInstructions`, `UserOwned`, `ForeignLink`, `CachedRender`, `MissingCachedRender`; one classifier and an exhaustive dispatch replace the old `_surfaces_present`) and the script-link planner `plan_script_links` (`Keep`, `Repoint`, `Remove`, `Link`), the single choke point for "never act on a regular file or a link outside the cache".
- **Effects and the update path** `hooks/_install_update.py` (538 lines): the snapshot readers (`snapshot_bin`, `snapshot_instructions`), `offered_scripts` (one predicate for the first install and the refresh), `refresh_scripts` and `apply_script_actions` (first error kept, raised after the loop), `carry_forward_instructions`, the one atomic writer `_build_and_rename` that the render and the link swap share, the rule step (`_update_rules` over `_run_rule_linkers`), the dispatcher `_update_instructions`, `_run_update_path` and its one-line `_report_incomplete`. It also holds the first-install instruction setup that step 8 moved out of the hook to avoid a circular import (`_fresh_instructions_setup`, `_confirm_install`, `_prompt_with_timeout`).
- **Hook** `hooks/auto_complete_install.py` (354 lines): the entry point, the cold first-install path and the gate that chooses between the two paths (`_is_update_run`, `_surfaces_installed`).
- **Value recovery** `scripts/render_claude_md.py::recover_values`: the pure inverse of `render_claude_md`, strict (equal line counts, literal lines equal, one value per key) and `None` on any doubt. The template and its render are now a cross-version contract, enforced by a round-trip test over the shipped template.
- **Rule re-point** `lib/install_shared.sh::repoint_cached_rule_symlinks` (bash 3.2-safe, fail-safe on an unreadable manifest): re-points a manifest-place link that targets another cached Praxion version, skips a link that is already the same file (`-ef`), never creates a link for a rule N+1 does not link. The installer and `--check` never call it.
- **Documents**: the "After plugin updates" paragraph of `README.md` and the update path in `README_DEV.md` (update and restart; a relink only for a clone install), and the Install-path completeness rows of `.ai-state/DESIGN.md` and `docs/architecture.md` (identical file lists).
- **Tests**: the outer loop `tests/acceptance/test_plugin_update_*.py` (six files, 62 nodes) over `tests/acceptance/drivers/plugin_update.py`; hook unit tests in `hooks/test__install_refresh.py`, `hooks/test_install_update.py` and `hooks/test_auto_complete_install.py`; `scripts/test_render_claude_md.py`; the bash-level `tests/test_repoint_cached_rule_symlinks.py`; and `tests/fixtures/plugin_cache_targets.tsv`, one example table of cache and clone targets asserted in both the Python and the bash tests, which keeps the two copies of the cache rule equal.
- **Drivers** (REQ-11): `tests/acceptance/drivers/model_routing_move.py`, `tests/acceptance/drivers/adr_rule_move.py` and `tests/e2e/drivers/routing_install_journey.py` now run `install.sh` from a stand-in copy of the shipped tree, so no test writes the checkout's configuration.
- **Not touched**: `install.sh`, `install_claude.sh`, `hooks/hooks.json`, `claude/config/CLAUDE.md.tmpl`, `rules/`, `CLAUDE.md`, the Codex and Cursor exporters and the `--check` predicates.

## Requirements

### Observable Surface

- `claude plugin update praxion@bit-agora` — the user's update command, as the brief states it
- `bash install.sh --relink` — the existing clone relink command
- `install.sh --relink` — the same command as the brief writes it
- `bash install.sh --check` — the existing install check
- `/praxion-complete-install` — the existing, documented hand path that completes a marketplace install
- `hooks/auto_complete_install.py` — the existing first-session completion, the plugin's SessionStart hook; a test stands in for a session start by running it with `HOME` and `CLAUDE_PLUGIN_ROOT` set, as Claude Code does
- `HOME` — the user's home directory, which every path below starts from
- `CLAUDE_PLUGIN_ROOT` — the variable Claude Code sets to the plugin version a hook runs from
- `~/.claude/plugins/cache/bit-agora/praxion` — the plugin cache; Claude Code installs each version into its own directory under it and keeps older ones after an update
- `~/.claude/CLAUDE.md` — the user's global instructions, a link to a rendered file
- `~/.local/bin` — the directory the user's script links live in
- `~/.claude/rules` — the directory the user's rule links live in
- `claude/config/CLAUDE.md.tmpl` — the shipped template, with placeholders for the personal values
- `claude/config/CLAUDE.md` — the rendered instructions file inside a checkout or a version's directory
- `claude/config/.personal_info.env` — the personal values a checkout's installer has saved
- `README.md` — the readme, whose "After plugin updates" paragraph documents the update path
- `python3 scripts/resolve_test_scope.py` — the command that derives the tests a change needs
- `GitHub` — the code host whose profile URL is one of the personal values

### Terms

Terms used below and in the requirements: **N** is the plugin version installed before the update and **N+1** the version after it. **The first session of N+1** is the first Claude Code session start after the update and a restart. **The update path** is what that first session does on its own, with no relink run. A **marketplace install** has its `~/.claude/CLAUDE.md` and its script links in `~/.local/bin` pointing into a version's directory under the plugin cache; a **clone install** has them pointing into a clone checkout of the repository. A script **N+1 offers** is one a fresh install of N+1 links into `~/.local/bin`; a rule **N+1 links** is one a fresh install of N+1 links into `~/.claude/rules`. **Personal values** are the username, the email address and the `GitHub` URL.

### REQ-01: Script links follow the update

**When** the first session of N+1 starts
**and** `~/.local/bin` holds a link into another version's directory of the plugin cache, under the name of a script N+1 offers
**the system** re-points that link to the same script in N+1's directory, and leaves a link that already points into N+1's directory exactly as it is
**so that** the scripts a user runs are N+1's from that session on, with no relink.

### REQ-02: Scripts with a free name are linked

**When** the first session of N+1 starts
**and** N+1 offers a script under a name that `~/.local/bin` holds nothing for
**the system** links that name in `~/.local/bin` to the script in N+1's directory
**so that** a script a release adds reaches a marketplace install on its first session.

### REQ-03: Links to scripts a release drops are removed

**When** the first session of N+1 starts
**and** `~/.local/bin` holds a link into any version's directory of the plugin cache, N+1's included, under a name N+1 does not offer as a script
**the system** removes that link
**so that** no script link is left serving an earlier version's file or dangling once that version is removed.

### REQ-04: Links outside the plugin cache are never touched

**When** the first session of N+1 starts
**and** `~/.local/bin` holds a link that points anywhere outside the plugin cache, into a clone checkout of the repository or elsewhere, whether or not it resolves
**the system** leaves that link exactly as it was, neither re-pointed, replaced nor removed, even when N+1 offers a script under the same name
**so that** a developer install keeps running its own checkout's scripts.

### REQ-05: Regular files are never touched

**When** the first session of N+1 starts
**and** `~/.local/bin` holds a regular file, not a link, under the name of a script N+1 offers
**the system** leaves that file in place and byte-identical
**so that** an update never overwrites a program the user put there.

### REQ-06: The instructions re-render with N's personal values

**When** the first session of N+1 starts on a marketplace install
**and** `~/.claude/CLAUDE.md` resolves to N's render, with N's directory still in the plugin cache
**the system** makes `~/.claude/CLAUDE.md` read exactly as N+1's `claude/config/CLAUDE.md.tmpl` with each placeholder replaced by the personal value N's render carried for it, even when the values a fresh install would derive today differ
**so that** a template change in a release reaches the user on that first session with their own identity intact.

### REQ-07: The update path asks nothing

**When** the first session of N+1 starts after an update from N
**and** `~/.claude/CLAUDE.md` is anything but absent or a link into the plugin cache that no longer resolves
**the system** asks no question and waits for no answer, whether or not a terminal is attached
**so that** an update completes unattended at session start.

### REQ-08: A default fills only a value N never had

**When** the first session of N+1 renders the instructions
**and** N+1's template holds a personal-value placeholder that N's render carried no value for
**the system** fills that placeholder, and only that one, with the value a fresh install of N+1 would use
**so that** a default never replaces a value the user already had.

### REQ-09: A clone install's instructions are never touched

**When** the first session of N+1 starts
**and** `~/.claude/CLAUDE.md` is a link that points anywhere outside the plugin cache, such as a clone checkout's `claude/config/CLAUDE.md`
**the system** leaves the link pointing where it pointed, and leaves the file it points to byte-identical with an unchanged modification time
**so that** a developer's own rendered instructions are never re-pointed or re-rendered by an update.

### REQ-10: Nothing refreshed still depends on N

**When** the first session of N+1 has refreshed a marketplace install
**and** N's directory is then removed from the plugin cache
**the system** has left `~/.claude/CLAUDE.md`, every script link and every rule link it refreshed or added resolving to an existing file outside N's directory
**so that** removing an old version breaks nothing the update refreshed.

### REQ-11: Test runs never write the checkout's configuration

**When** any of the repository's tests run, the whole suite, any one pocket of it, or the scope `python3 scripts/resolve_test_scope.py` derives, including every test that runs the installer
**the system** leaves the checkout's `claude/config/CLAUDE.md` and `claude/config/.personal_info.env` byte-identical with unchanged modification times, and leaves either file absent if it was absent before the run
**so that** a test run can never rewrite the operator's live global instructions, which link to that file.

### REQ-12: An operator's clone relink still renders into the clone

**When** an operator runs `bash install.sh --relink` from their own clone into their own home directory
**and** that clone holds saved values in its `claude/config/.personal_info.env`
**the system** renders that clone's `claude/config/CLAUDE.md` from its template with those values, and links `~/.claude/CLAUDE.md` to it, as it does before this change
**so that** isolating test runs never changes what a developer install does.

### REQ-13: The documented update path needs no relink

**When** a marketplace user reads how to update, in the "After plugin updates" paragraph of `README.md` or in any release or upgrade note that describes the update path
**the system** tells them that `claude plugin update praxion@bit-agora` and a restart are enough, with no `bash install.sh --relink`, or names exactly the case in which the relink is still needed
**so that** the documented path matches what an update does.

### REQ-14: A failure never blocks a session

**When** any step of the first-session refresh fails, for example a tool is missing, a directory is not writable or a file cannot be read
**the system** lets the session start, ends its session-start step with a success status, and reports the failure in at most one line that names `/praxion-complete-install` as the way to complete the refresh by hand
**so that** an update can degrade a session's setup but never stop a session, and the user learns how to finish it.

### REQ-15: A failed render keeps the previous instructions

**When** the first-session refresh of `~/.claude/CLAUDE.md` fails part-way
**the system** leaves `~/.claude/CLAUDE.md` resolving to a complete render, N's or N+1's, never to a missing, empty or half-written file
**so that** a failed update never leaves a session without its global instructions.

### REQ-16: Silent after the first session of a version

**When** a later session of the same version starts, with no plugin install, update or removal since the first session of that version, whether that first session's refresh succeeded or failed
**the system**'s first-session completion changes no file or link in the home directory and prints nothing
**so that** the refresh runs once per version and costs nothing afterwards.

### REQ-17: The change adds no personal value to the repository

**When** the change is compared with its base revision
**the system** shows no line the change adds, in any tracked file, test fixture or recorded log, that holds a real username, email address or `GitHub` URL, neither the operator's nor a copy of the repository's own default values; tests use made-up values, and the installer's existing default identity values stay as they are
**so that** the change leaks no identity through the repository.

### REQ-18: The update path prints no personal value

**When** the first session of N+1 carries the instructions forward or refreshes the script and rule links, whether it succeeds or fails
**the system** prints and logs no personal value, while the recovery of an absent or dangling instructions entry keeps the confirmation prompt a first install shows today, which displays the derived values on the terminal and writes them to no log
**so that** a user's identity never reaches session output or a log, except the consent prompt that shows the user their own values.

### REQ-19: Rule links follow the update

**When** the first session of N+1 starts
**and** `~/.claude/rules` holds a link, live or dangling, into another version's directory of the plugin cache, at the place of a rule N+1 links
**the system** re-points that link to the same rule in N+1's directory, and leaves a link that already points into N+1's directory exactly as it is
**so that** a rule's new text in a release governs sessions from that first session on, with no relink.

### REQ-20: Every rule N+1 links has a link, and nothing else is linked

**When** the first session of N+1 starts
**and** the place of a rule N+1 links holds nothing in `~/.claude/rules`, or holds a link that no longer resolves
**the system** links that place to the rule in N+1's directory, and creates no link for any other file N+1 ships among its rules
**so that** a rule a release adds reaches the install, and a rule the release delivers another way is never linked.

### REQ-21: Links to rules N+1 no longer links are removed

**When** the first session of N+1 starts
**and** `~/.claude/rules` holds a link into any version's directory of the plugin cache, N+1's included, at a place that is not a rule N+1 links
**the system** removes that link
**so that** a rule a release stops linking stops loading in every session.

### REQ-22: Live rule links outside the plugin cache are never touched

**When** the first session of N+1 starts
**and** `~/.claude/rules` holds a link that resolves to a file outside the plugin cache, in a clone checkout of the repository or elsewhere
**the system** leaves that link exactly as it was, neither re-pointed, replaced nor removed, even at the place of a rule N+1 links
**so that** a developer install keeps loading its own checkout's rules.

### REQ-23: Regular files among the rules are never touched

**When** the first session of N+1 starts
**and** `~/.claude/rules` holds a regular file, not a link, at the place of a rule N+1 links
**the system** leaves that file in place and byte-identical
**so that** an update never overwrites a rule the user wrote.

### REQ-24: A regular-file instructions file belongs to the user

**When** the first session of N+1 starts after an update from N
**and** `~/.claude/CLAUDE.md` is a regular file, not a link
**the system** leaves that file in place and byte-identical, neither replaced nor re-rendered, and still refreshes the script and rule links as the requirements above describe
**so that** a user who owns their global instructions keeps them through every update.

### REQ-25: An absent or dangling instructions entry recovers as a first install does

**When** the first session of N+1 starts after an update from N
**and** `~/.claude/CLAUDE.md` is absent, or is a link into the plugin cache that no longer resolves because N's render is already gone
**the system** sets up `~/.claude/CLAUDE.md` exactly as a first install does today, and refreshes the script and rule links by the same rules as the update path, so a clone's live links stay its own
**so that** an update made after the old version was removed still completes, with no regression of the existing first-install behaviour.

## Spec Question Answers

Four round-0 answers came from the orchestrator before design, five Spec Questions were recorded through acceptance design and final verification, and every one is closed by amending the requirement text or by an answer recorded in the design. The spec digest moved three times through them: from `456c15b7fa82` to `220fba839962` (SQ-03), to `8854a48c34eb` (SQ-04) and to `6764cd1e1aee` (SQ-05, the digest of the text archived above).

Round-0 answers (the orchestrator, before design):

1. **Rule links are in scope**, under the same rule as scripts: re-point a link into another version's cache directory, remove a link to a rule N+1 no longer links, never touch a clone's link or a regular file. Links stay only for the rules a fresh install links, and a live link into a clone is never re-pointed. REQ-10 and REQ-19 to REQ-23 carry it.
2. **The personal-values guard covers only the lines this change adds** (REQ-17). The installer's existing default identity values stay as they are.
3. **The tension between test isolation and an operator's clone relink needs no requirement change.** Acceptance design raises any conflict with a frozen journey as a Spec Question (it raised SQ-01 and SQ-02).
4. **A regular-file `~/.claude/CLAUDE.md` belongs to the user** and is never replaced or re-rendered by the update path (REQ-24). If N's render is already gone, so the instructions link dangles, that session behaves as a first install does today, with no regression (REQ-25). Script and rule links are refreshed either way.

Interpretations taken while writing the acceptance criteria (stated, not asked; a Spec Question could have overturned any of them):

- KS1's "a link into N's cache" is read as a link into any other version's directory of the cache, so a skipped version or a downgrade is covered by the same rule.
- KS1's "scripts N+1 ships that N lacked" is read as every script N+1 offers whose name in `~/.local/bin` is free, the rule the rule-link refresh already applies to rules.
- KS1 leaves a dropped script unstated: a link into the cache for a script N+1 no longer offers is removed, so nothing keeps pointing into an earlier version.
- The fail-open guard keeps the existing contract that a failed completion reports itself in one line naming the command that finishes the job by hand.
- Rule links keep today's handling of a dangling link at a rule's place (relinked to N+1's rule wherever it pointed, as the existing tests pin); only a live link outside the cache is protected. Script links follow KS2 literally: a script link outside the cache is never touched, resolving or not.
- In the dangling case of round-0 answer 4, "refreshed" means the same rules as the update path, so a clone's live links stay its own there too.

### SQ-01: The routing-move install driver writes the checkout's configuration

- **Kind:** specification (REQ-11, raised by acceptance design under round-0 answer 3)
- **Question:** `tests/acceptance/drivers/model_routing_move.py::install` runs `bash install.sh code --relink` from the checkout into a scratch home, and at the base that writes the checkout's `claude/config/CLAUDE.md` and `claude/config/.personal_info.env`. Every test that reaches it contradicts REQ-11.
- **Answer:** answered by the spec as written; the drivers were amended. `install` and `install_check` run `install.sh` from a stand-in copy of the shipped tree (`stand_in_root`, built with `plugin_update.shipped_tree`). Three frozen-scenario edits, no assertion dropped or weakened: `plant_old_install` links the base's links into that copy's `rules/`; `routing_install_journey.Installed` gains a `checkout` field; and in `test_the_install_links_the_full_rule_and_not_the_session_start_text` the rule path is read from `done.checkout` instead of the checkout root. Done at `366744db`, before the first production commit.

### SQ-02: The ADR-rule-move install driver writes the checkout's configuration

- **Kind:** specification (REQ-11)
- **Question:** `tests/acceptance/drivers/adr_rule_move.py::install` makes the same call from the checkout, reached by `test_adr_rule_is_delivered_by_its_path.py`.
- **Answer:** answered by the spec as written; `install` runs from a stand-in copy, as in SQ-01. Two frozen-scenario edits: the installed rule file is read from the stand-in copy, and `adr_rule_move.GLOBAL_INSTRUCTIONS` changes from the rendered `claude/config/CLAUDE.md` to the shipped `claude/config/CLAUDE.md.tmpl`, because the old oracle read the render that earlier installs left in the checkout and failed with `FileNotFoundError` on a checkout no installer had written. Its oracle is file names only, so the content swap does not touch it.

### SQ-03: Which command does a failed refresh's report line name?

- **Kind:** specification (REQ-14, raised by acceptance design)
- **Question:** "names the command which completes the refresh by hand": the Observable Surface names `bash install.sh --relink`, but a marketplace install has no clone to run it from. The README's hand path is `/praxion-complete-install`.
- **Answer:** the line names `/praxion-complete-install`. The update path acts only on marketplace installs, and a clone's links and instructions are never touched (REQ-04, REQ-09, REQ-22), so the line never needs the clone's relink command. REQ-14 was amended (digest `220fba839962`).

### SQ-04: Does REQ-18 cover the first-install prompt of the REQ-25 recovery?

- **Kind:** specification (REQ-18 against REQ-25, raised by the architect at design and recorded by the orchestrator)
- **Question:** REQ-18 said the refresh prints no personal value, but REQ-25's recovery behaves exactly as a first install does today, and today's prompt shows the derived values for confirmation.
- **Answer:** REQ-18 governs the carry-forward re-render and the script and rule link refresh, whether they succeed or fail. The recovery keeps today's confirmation prompt, terminal only, written to no log. REQ-18 was amended (digest `8854a48c34eb`); no scenario changed.

### SQ-05: Does the recovery cover an absent `~/.claude/CLAUDE.md`, not only a dangling link?

- **Kind:** specification (REQ-07, REQ-18 and REQ-25, raised by the verifier as finding F1 at final verification; recorded and answered by the orchestrator)
- **Question:** with the completion marker present and `~/.claude/CLAUDE.md` removed, the update path showed today's first-install prompt, which displays the derived values. The design maps the absent state to the first-install setup, as the base does, but REQ-07 and REQ-18 exempted only a dangling cache link and REQ-25 named only that case.
- **Answer:** an absent entry recovers exactly as a dangling one does: today's first-install setup, with its terminal-only confirmation prompt and no log. This is the design's reading and today's behaviour, so it is no regression, and silencing that state would leave a user who lost their instructions with none until the hand path. REQ-07, REQ-18 and REQ-25 were amended (digest `6764cd1e1aee`). No scenario changed; the inner-loop test `hooks/test_install_update.py::TestInstructionStates::test_a_missing_file_is_set_up_as_a_first_install_sets_it_up` already pinned the routing. **Answered on the user's behalf:** the user's round-0 answer 4 covered the dangling case, and the orchestrator extended it to the absent state under the user's standing delegation, so the user can see here that a spec question was answered for them (verifier note I3).

Reading recorded, not asked (verifier note I1): REQ-15 ("leaves `~/.claude/CLAUDE.md` resolving to a complete render") names no instructions state. A failed fresh setup in the absent or dangling state leaves the entry as it found it, because the hook cannot do better without breaking REQ-25's "exactly as a first install". On the vocabulary of SQ-04 REQ-15 governs the carry-forward only, and nothing contradicts it. The requirement text above is archived as it stood; adding "and `~/.claude/CLAUDE.md` resolves to N's render" to its When clause would say what this reading says.

Assumptions taken while designing and planning (`LEARNINGS.md § Assumptions & Constraints Taken`), the load-bearing ones:

- Claude Code keeps the previous version's directory until at least the new version's first session. The value recovery depends on it; if it changes, add the user-scope store (the ADR's reversal trigger).
- The completion marker's presence tells an update from a first install, and the cache directory's modification time moves on every update (the re-arm's premise).
- The template keeps at most one placeholder per line with literal text around it, so a render changes nothing but the placeholders.
- A declined first-install prompt in the recovery behaves as it does today: a decline marker, no completion marker, nothing else.
- Loop agents (implementer and reviewer spawns the step-loop driver issues under a request id) are ledgered iterations, not charged spawns, per `scripts/spawn_count.py`. The charged estimate was 5 of 16; counted otherwise it would have been about 19.

## Footprint Readings

The spec carries no footprint criterion: its only footprint row is `hook-latency`, declared under `### Footprints Not Measured` because the registry names no instrument for it and the added work runs on one session per version, inside the hook's existing registered time budget. `python3 scripts/check_footprint_criteria.py install-refresh --stage verify --base-ref 4cf729a5 --json` exits 0 with `findings: []` (the plan stage over the union of the plan's `Files` gave 0 fail, 0 warn, 0 info).

The health guards that name a footprint were read anyway:

| Reading | Base | Head | Result |
|---|---|---|---|
| Always-loaded tokens (`python3 scripts/measure_token_budget.py --json`) | 19,894 (a `git archive` of `4cf729a5`) | 19,894 | unchanged; no always-loaded path is in the diff. The brief's 19,918 is a stale figure |
| Codex and Cursor exports (four Codex exporters and `export-cursor-rules.py`, roots normalised) | 172 files | 172 files | 0 differ |
| `bash install.sh --check` | rc 1 | rc 1 | the same warning set (CLAUDE.md not rendered, no saved personal info, unlinked scripts); `install.sh`, `install_claude.sh` and the `--check` predicates are not in the diff |

## Traceability

Rendered from `traceability.yml` at archival. There were no un-reconciled fragments (step 11 reconciled the single file before the verifier ran) and no requirement carried `architectural_elements:`, so the matrix has four columns. A requirement counts as tested when its unit tests and its outer-loop (acceptance) nodes together are non-empty: the `Test(s)` cell lists both kinds, each grouped by file with the count and the node names. `Status` is the verifier's reading across the final run and the delta re-verification, judged against the root run of 18,010 passed and 37 skipped (0 failed) at `c06b84da`, whose code tree equals `b59390d1`, and the step-10 gate's 62 of 62 outer-loop nodes.

| Requirement | Test(s) | Implementation | Status |
|---|---|---|---|
| REQ-01 | unit: `hooks/test__install_refresh.py` (5: test_link_into_another_cached_version_under_an_offered_name_is_repointed, test_dangling_link_into_a_removed_cached_version_under_an_offered_name_is_repointed, test_link_whose_text_is_the_offered_path_is_kept, test_link_whose_real_path_is_the_offered_path_is_kept_whatever_its_text, test_each_link_class_gets_exactly_its_action); unit: `hooks/test_install_update.py` (6: test_a_cache_link_is_repointed_to_the_offered_script, test_a_relative_cache_link_is_repointed_too, test_a_link_already_to_the_offered_script_keeps_its_inode, test_a_successful_repoint_leaves_no_temporary_link, test_a_failed_repoint_leaves_the_old_link_and_no_temporary_link, test_every_action_is_applied_and_the_first_error_raised_after_the_loop); acceptance: `tests/acceptance/test_plugin_update_refreshes_links.py` (4: test_the_first_session_ends_with_a_success_status, test_script_links_into_the_previous_version_now_point_into_the_new_one, test_a_script_link_into_a_skipped_older_version_now_points_into_the_new_one, test_a_script_link_already_into_the_new_version_is_left_exactly_as_it_was) | `hooks/_install_refresh.py::plan_script_links`; `hooks/_install_update.py::refresh_scripts, apply_script_actions, snapshot_bin` | PASS |
| REQ-02 | unit: `hooks/test__install_refresh.py` (1: test_offered_name_with_no_entry_is_linked); unit: `hooks/test_install_update.py` (6: test_a_free_name_is_linked_and_the_directory_created, test_names_the_executable_user_facing_scripts_with_their_paths, test_leaves_out_what_the_operator_does_not_run, test_leaves_out_a_directory, test_a_plugin_without_scripts_offers_none, test_link_never_overwrites_what_sits_under_its_name); acceptance: `tests/acceptance/test_plugin_update_refreshes_links.py` (1: test_a_script_the_new_version_offers_under_a_free_name_is_linked) | `hooks/_install_refresh.py::plan_script_links`; `hooks/_install_update.py::offered_scripts, refresh_scripts, apply_script_actions` | PASS |
| REQ-03 | unit: `hooks/test__install_refresh.py` (2: test_cache_link_under_a_dropped_name_is_removed, test_new_versions_own_link_under_a_dropped_name_is_removed); unit: `hooks/test_install_update.py` (3: test_a_cache_link_for_a_dropped_script_is_removed, test_remove_unlinks_a_link_only, test_remove_of_a_missing_name_is_not_an_error); acceptance: `tests/acceptance/test_plugin_update_refreshes_links.py` (1: test_a_cache_link_under_a_name_the_new_version_does_not_offer_is_removed) | `hooks/_install_refresh.py::plan_script_links`; `hooks/_install_update.py::refresh_scripts, apply_script_actions` | PASS |
| REQ-04 | unit: `hooks/test__install_refresh.py` (8: test_table_row_is_classified_as_the_cache_or_not, test_plugin_root_returns_its_own_version_directory, test_file_inside_the_cache_returns_the_enclosing_version_directory, test_dot_dot_segments_leaving_the_version_directory_are_not_the_cache, test_live_clone_link_under_an_offered_name_is_never_touched, test_dangling_link_outside_the_cache_under_an_offered_name_is_never_touched, test_clone_link_under_a_dropped_name_is_never_removed, test_no_action_but_keep_names_an_entry_that_is_not_a_cache_link); unit: `hooks/test_install_update.py` (3: test_a_regular_file_and_a_clone_link_are_left_as_they_were, test_a_link_carries_its_text_and_its_real_path, test_a_dangling_link_has_no_real_path); acceptance: `tests/acceptance/test_plugin_update_refreshes_links.py` (1: test_a_script_link_outside_the_plugin_cache_is_never_touched) | `hooks/_install_refresh.py::cache_version_dir, plan_script_links`; `hooks/_install_update.py::refresh_scripts, snapshot_bin` | PASS |
| REQ-05 | unit: `hooks/test__install_refresh.py` (4: test_regular_file_under_an_offered_name_is_not_acted_on, test_directory_under_an_offered_name_is_not_acted_on, test_a_file_or_other_entry_gets_no_action_at_all, test_no_action_but_keep_names_an_entry_that_is_not_a_cache_link); unit: `hooks/test_install_update.py` (4: test_a_regular_file_and_a_clone_link_are_left_as_they_were, test_tells_a_link_a_file_and_another_kind_apart, test_a_file_and_another_kind_carry_no_link_data, test_remove_unlinks_a_link_only); acceptance: `tests/acceptance/test_plugin_update_refreshes_links.py` (1: test_a_regular_file_under_an_offered_script_name_is_left_byte_identical) | `hooks/_install_refresh.py::plan_script_links`; `hooks/_install_update.py::refresh_scripts, snapshot_bin, apply_script_actions` | PASS |
| REQ-06 | unit: `scripts/test_render_claude_md.py` (6: test_recover_values_round_trips_the_shipped_template, test_recover_values_returns_none_when_line_counts_differ, test_recover_values_returns_none_when_a_literal_line_differs, test_recover_values_returns_none_when_one_key_carries_two_values, test_recover_values_returns_empty_dict_for_template_without_placeholders, test_recover_values_recovers_an_empty_value_as_empty_string); unit: `hooks/test_auto_complete_install.py` (4: test_the_new_template_is_filled_with_the_previous_renders_values, test_the_link_points_at_this_versions_render, test_the_previous_render_is_left_as_it_was, test_a_relative_link_into_the_previous_version_is_carried_forward); unit: `hooks/test_install_update.py` (1: test_a_live_link_carries_its_text_and_resolves); acceptance: `tests/acceptance/test_plugin_update_rerenders_instructions.py` (1: test_the_instructions_read_as_the_new_template_filled_with_the_previous_values) | `scripts/render_claude_md.py::recover_values`; `hooks/_install_update.py::snapshot_instructions, carry_forward_instructions` | PASS |
| REQ-07 | unit: `hooks/test_auto_complete_install.py` (1: test_nothing_is_read_from_stdin); unit: `hooks/test_install_update.py` (2: test_the_prompt_shows_on_the_terminal_and_nowhere_else, test_a_regular_file_is_left_byte_identical); acceptance: `tests/acceptance/test_plugin_update_rerenders_instructions.py` (1: test_the_update_path_asks_nothing_and_waits_for_no_answer) | `hooks/_install_update.py::snapshot_instructions, carry_forward_instructions, _update_instructions, _fresh_instructions_setup` | PASS (the absent state is covered by SQ-05) |
| REQ-08 | unit: `scripts/test_render_claude_md.py` (6: test_recover_values_round_trips_the_shipped_template, test_recover_values_returns_none_when_line_counts_differ, test_recover_values_returns_none_when_a_literal_line_differs, test_recover_values_returns_none_when_one_key_carries_two_values, test_recover_values_returns_empty_dict_for_template_without_placeholders, test_recover_values_recovers_an_empty_value_as_empty_string); unit: `hooks/test_auto_complete_install.py` (4: test_a_default_fills_only_the_key_the_previous_render_never_carried, test_no_default_is_derived_when_every_key_was_carried, test_a_key_neither_carried_nor_derivable_stays_a_named_placeholder, test_an_unrecoverable_render_raises_its_own_error_type); unit: `hooks/test_install_update.py` (4: test_the_missing_keys_are_the_template_names_not_carried, test_nothing_is_missing_when_every_template_key_was_carried, test_a_default_fills_only_a_missing_key_and_never_a_carried_one, test_a_missing_key_without_a_default_stays_out); acceptance: `tests/acceptance/test_plugin_update_rerenders_instructions.py` (1: test_a_default_fills_only_the_placeholder_the_previous_render_had_no_value_for) | `scripts/render_claude_md.py::recover_values`; `hooks/_install_update.py::snapshot_instructions, carry_forward_instructions` | PASS (a recovered `{{KEY}}` token is kept as a value, `td-615`) |
| REQ-09 | unit: `hooks/test__install_refresh.py` (2: test_link_outside_every_cache_version_directory_is_foreign_whether_live_or_dangling, test_table_row_is_classified_as_the_cache_or_not); unit: `hooks/test_auto_complete_install.py` (2: test_a_clone_link_and_its_render_are_left_as_they_are, test_a_link_already_into_this_version_is_left_as_it_is); unit: `hooks/test_install_update.py` (6: test_a_missing_entry_is_absent, test_a_regular_file_is_a_file, test_a_link_outside_the_cache_is_left_where_it_points, test_a_state_the_dispatch_does_not_know_is_a_bug_not_a_silent_skip, test_a_directory_is_another_kind, test_a_dangling_link_carries_its_text_and_does_not_resolve); acceptance: `tests/acceptance/test_plugin_update_rerenders_instructions.py` (2: test_a_clone_installs_instructions_link_keeps_pointing_into_the_clone, test_a_clone_installs_rendered_file_is_byte_identical_with_its_modification_time) | `hooks/_install_refresh.py::classify_instructions`; `hooks/_install_update.py::snapshot_instructions, carry_forward_instructions, _update_instructions` | PASS |
| REQ-10 | unit: `hooks/test_install_update.py` (3: test_a_repointed_link_outlives_the_removal_of_the_old_version, test_a_cache_root_with_a_marker_reaches_the_update_path_whatever_the_surfaces, test_a_checkout_root_with_a_marker_and_missing_surfaces_keeps_the_cold_path); acceptance: `tests/acceptance/test_plugin_update_refreshes_links.py` (1: test_removing_the_previous_versions_leaves_everything_refreshed_resolving) | `hooks/_install_update.py::refresh_scripts`; `hooks/auto_complete_install.py::_is_update_run, _surfaces_installed` | PASS |
| REQ-11 | acceptance: `tests/acceptance/test_plugin_update_test_runs_leave_the_checkout_alone.py` (1: test_running_the_installer_tests_leaves_the_checkout_configuration_unchanged) | (none; see the note below the table) | PASS (the full root run left both files absent, as they were) |
| REQ-12 | acceptance: `tests/acceptance/test_plugin_update_test_runs_leave_the_checkout_alone.py` (1: test_an_operators_relink_from_a_clone_renders_into_that_clone_with_its_saved_values) | (none; see the note below the table) | PASS |
| REQ-13 | acceptance: `tests/acceptance/test_plugin_update_documentation.py` (3: test_the_update_paragraph_names_the_update_command, test_the_update_paragraph_says_a_restart_completes_the_update, test_the_update_paragraph_mentions_a_relink_only_for_a_named_clone_case) | `README.md`; `README_DEV.md` | PASS (the verifier judged the release-note part: no separate note describes the update path) |
| REQ-14 | unit: `hooks/test_install_update.py` (5: test_a_failing_step_does_not_stop_the_next_one, test_a_failure_prints_one_line_with_the_exception_type_only, test_the_first_of_several_failures_is_the_one_reported, test_the_marker_is_rewritten_after_a_failure, test_an_unwritable_marker_after_a_failure_still_reports_the_failure); unit: `hooks/test_auto_complete_install.py` (1: test_an_unrecoverable_render_is_reported_in_one_line_naming_its_type); acceptance: `tests/acceptance/test_plugin_update_fails_open_and_quietly.py` (2: test_a_failed_refresh_ends_the_session_start_step_with_a_success_status, test_a_failed_refresh_reports_itself_in_one_line_naming_the_command_to_finish_by_hand) | `hooks/_install_update.py::_run_update_path, _report_incomplete, snapshot_instructions, carry_forward_instructions`; `hooks/auto_complete_install.py::_run` | PASS |
| REQ-15 | unit: `hooks/test_auto_complete_install.py` (5: test_an_unrecoverable_render_keeps_the_previous_link_and_writes_no_render, test_an_unreadable_new_template_keeps_the_previous_render, test_an_unwritable_render_directory_keeps_the_previous_render_and_no_temporary, test_a_failed_rename_of_the_render_keeps_the_previous_render_and_no_temporary, test_a_failed_swap_of_the_link_keeps_the_previous_render_and_no_temporary); acceptance: `tests/acceptance/test_plugin_update_fails_open_and_quietly.py` (1: test_a_failed_refresh_leaves_the_instructions_resolving_to_a_complete_render) | `hooks/_install_update.py::snapshot_instructions, carry_forward_instructions` | PASS |
| REQ-16 | unit: `hooks/test_install_update.py` (5: test_a_fully_successful_run_prints_nothing, test_a_marked_cache_install_with_surfaces_runs_the_update_steps, test_a_checkout_root_never_reaches_the_update_path, test_a_first_install_without_a_marker_never_reaches_the_update_path, test_missing_surfaces_keep_the_cold_path); acceptance: `tests/acceptance/test_plugin_update_fails_open_and_quietly.py` (2: test_a_later_session_of_the_same_version_changes_no_file_or_link, test_a_later_session_of_the_same_version_prints_nothing) | `hooks/_install_update.py::_run_update_path`; `hooks/auto_complete_install.py::_run, _is_update_run` | PASS |
| REQ-17 | acceptance: `tests/acceptance/test_plugin_update_keeps_identity_out_of_the_repository.py` (1: test_no_line_the_change_adds_holds_a_personal_value) | (none; see the note below the table) | PASS (0 hits over 4,231 added lines) |
| REQ-18 | unit: `hooks/test_install_update.py` (2: test_a_failure_prints_one_line_with_the_exception_type_only, test_a_fully_successful_run_prints_nothing); unit: `hooks/test_auto_complete_install.py` (2: test_no_personal_value_is_printed, test_no_personal_value_is_written_outside_the_two_renders); acceptance: `tests/acceptance/test_plugin_update_fails_open_and_quietly.py` (2: test_the_refresh_prints_no_personal_value, test_the_refresh_logs_no_personal_value) | `hooks/_install_update.py::_run_update_path, snapshot_instructions, carry_forward_instructions`; `hooks/auto_complete_install.py::_run` | PASS (the absent state is covered by SQ-05; it was the final run's F1) |
| REQ-19 | unit: `tests/test_repoint_cached_rule_symlinks.py` (4: test_a_live_link_into_another_version_is_repointed, test_a_dangling_link_into_another_version_is_repointed, test_a_relative_link_into_another_version_is_repointed, test_a_link_already_into_the_current_version_keeps_its_inode); unit: `hooks/test_install_update.py` (1: test_repoints_a_live_link_into_the_previous_version); acceptance: `tests/acceptance/test_plugin_update_refreshes_links.py` (3: test_rule_links_into_the_previous_version_now_point_into_the_new_one, test_a_dangling_rule_link_into_a_skipped_older_version_now_points_into_the_new_one, test_a_rule_link_already_into_the_new_version_is_left_exactly_as_it_was) | `lib/install_shared.sh::repoint_cached_rule_symlinks`; `hooks/_install_update.py::_run_rule_linkers, _update_rules` | PASS |
| REQ-20 | unit: `hooks/test_install_update.py` (1: test_still_sweeps_and_links_as_the_refresh_does); unit: `tests/test_repoint_cached_rule_symlinks.py` (1: test_a_place_with_no_link_is_not_created); acceptance: `tests/acceptance/test_plugin_update_refreshes_links.py` (2: test_a_rule_the_new_version_links_gets_a_link_at_an_empty_or_dangling_place, test_the_cache_links_among_the_rules_are_exactly_the_rules_the_new_version_links) | `hooks/_install_update.py::_update_rules`; `hooks/auto_complete_install.py::_run_rule_linker` | PASS |
| REQ-21 | unit: `tests/test_repoint_cached_rule_symlinks.py` (1: test_a_place_outside_the_keep_set_is_left_to_the_sweep); unit: `hooks/test_install_update.py` (1: test_still_sweeps_and_links_as_the_refresh_does); acceptance: `tests/acceptance/test_plugin_update_refreshes_links.py` (1: test_a_cache_link_at_a_place_the_new_version_does_not_link_is_removed) | `hooks/_install_update.py::_update_rules` | PASS |
| REQ-22 | unit: `hooks/test__install_refresh.py` (2: test_table_row_is_classified_as_the_cache_or_not, test_relative_text_is_joined_to_the_link_directory); unit: `tests/test_repoint_cached_rule_symlinks.py` (2: test_a_live_link_outside_the_cache_is_left_as_it_is, test_the_shells_cache_rule_agrees_with_the_shared_rows); unit: `hooks/test_install_update.py` (2: test_leaves_a_live_link_into_a_checkout_as_it_is, test_the_refresh_alone_leaves_a_live_link_into_another_version); acceptance: `tests/acceptance/test_plugin_update_refreshes_links.py` (1: test_a_live_rule_link_outside_the_plugin_cache_is_never_touched) | `hooks/_install_refresh.py::cache_version_dir`; `lib/install_shared.sh::repoint_cached_rule_symlinks` | PASS |
| REQ-23 | unit: `tests/test_repoint_cached_rule_symlinks.py` (1: test_a_regular_file_at_a_rules_place_is_left_byte_identical); acceptance: `tests/acceptance/test_plugin_update_refreshes_links.py` (1: test_a_regular_file_at_a_rules_place_is_left_byte_identical) | `lib/install_shared.sh::repoint_cached_rule_symlinks` | PASS |
| REQ-24 | unit: `hooks/test_install_update.py` (1: test_a_regular_file_is_left_byte_identical); acceptance: `tests/acceptance/test_plugin_update_rerenders_instructions.py` (2: test_a_regular_file_instructions_is_left_byte_identical, test_a_regular_file_instructions_still_gets_its_script_and_rule_links_refreshed) | `hooks/_install_update.py::_update_instructions` | PASS |
| REQ-25 | unit: `hooks/test__install_refresh.py` (3: test_live_link_into_a_cache_version_directory_is_a_cached_render, test_dangling_link_into_a_cache_version_directory_is_a_missing_cached_render, test_every_snapshot_kind_maps_to_exactly_one_state); unit: `hooks/test_install_update.py` (5: test_a_dangling_cache_link_is_set_up_as_a_first_install_sets_it_up, test_a_missing_file_is_set_up_as_a_first_install_sets_it_up, test_the_dangling_link_setup_leaves_a_clones_live_links_its_own, test_a_refusal_writes_the_decline_marker_and_no_completion_marker, test_a_refusal_is_no_failure_and_the_rules_and_scripts_are_still_refreshed); acceptance: `tests/acceptance/test_plugin_update_rerenders_instructions.py` (3: test_a_dangling_instructions_link_is_set_up_as_a_first_install_sets_it_up, test_a_dangling_instructions_link_still_gets_its_script_and_rule_links_refreshed, test_a_dangling_instructions_link_leaves_a_clones_live_links_its_own) | `hooks/_install_update.py::_fresh_instructions_setup, _confirm_install`; `hooks/_install_refresh.py::classify_instructions` | PASS (the absent state was added by SQ-05; its routing is pinned by an inner-loop test) |

REQ-11, REQ-12 and REQ-17 have no implementation entry by design. REQ-11 is met by the drivers amended at acceptance design (`366744db`); its one outer-loop node runs the installer-driving selection nested, and the claim over "the whole suite" was read by the verifier on the full root run: `claude/config/CLAUDE.md`, `claude/config/.personal_info.env` and `.personal_info.env` were absent before and still absent after it. REQ-12 guards installer behaviour this change leaves unchanged. REQ-17 is a property of every added line, and the verifier scanned 4,231 added lines with 0 hits for the operator's identity (the only identity-shaped values are the made-up `example.invalid`, `y.example` and `mail.example` and the moved existing `github.com/anon` fallback). REQ-13's implementation is the two README files; the part of its text about "any release or upgrade note" was judged by the verifier, who found no separate note describing the update path.

**Coverage**: all 25 requirements are covered. Every requirement carries acceptance evidence, and 21 of them also carry recorded unit evidence (128 unit entries and 40 acceptance entries in the map; the 40 acceptance entries stand for the 62 outer-loop nodes, since a parametrized function is one entry). REQ-11, REQ-12, REQ-13 and REQ-17 have no unit entry. No requirement is UNTESTED, and the verifier's scripted comparison found every `acceptance:` list equal to the scenario nodes of its requirement (25 of 25).

## Key Decisions

Two ADR drafts carry the architectural and design decisions; the entries below are from `LEARNINGS.md § Decisions Made`, the step learnings and the verifier's rulings.

**[systems-architect] The first-session completion owns the update path (`dec-499`, architectural)**: a re-armed run (marker older than the cache directory), after an earlier completion and from a cache version directory, refreshes the instructions, the script links and the rule links; rule links into another cached version are re-pointed, which narrows `dec-491` (its clause "never re-points a live link, wherever it points" becomes "never re-points a live link outside the plugin cache"; its own reversal trigger named this move). A first install and a `--plugin-dir` run are unchanged. **Why**: it closes `td-593` without touching the installer, so every installer health guard holds trivially, and the existing marker re-arm already covers scripts, rules and instructions once the re-armed path runs all three. **Alternatives**: a version-keyed marker (the runner-up: it detects a new version exactly, at the cost of a marker-format change for every existing install and the loss of the removal re-arm that `dec-491`'s dangling-link recovery relies on); a Praxion-owned `current` link every surface points through (rejected: a new persistent artifact that `--check` and `_managed_rule_rel_path` do not recognise); a bash `refresh_script_symlinks` shared with the installer (below).

**[systems-architect] Register Objection to `td-593`'s 2026-11-08 note**: that note proposed a shared bash `refresh_script_symlinks` and `script_is_user_facing` in `lib/install_shared.sh`. The installer's predicate (`dec-042`: `merge_driver_*` and `git-*-hook.sh` excluded) and the hook's (`*-hook.sh` excluded) differ on one shipped file, `scripts/diagram-regen-hook.sh`, so one shared predicate would move either the operator's clone path or every marketplace install's `~/.local/bin`, and the installer's relink is a take-over by design. The script refresh therefore lives in the hook; the rule re-point lives in the library, because the manifest reader there is bash without PyYAML. The divergence is deliberate scope, and `td-613` carries the follow-up.

**[systems-architect] Personal values carried from the previous render (`dec-498`, implementation)**: `render_claude_md.recover_values` aligns N's render with N's template. A default fills only a key N never carried, and an unrecoverable render is kept, never re-rendered with defaults. **Why**: no marketplace install records its values anywhere else (the hook's cold path writes no values file, `complete_install_from_plugin` renders no instructions and `.personal_info.env` is a clone's), so nothing new is persisted and the door stays two-way. **Alternatives**: a user-scope store (the runner-up: it survives the old version's removal, at the cost of a second copy of personal values in the home and a store every future version must read); N's `.personal_info.env` (no marketplace install has one); template-free parsing (a weaker form of the chosen option).

**[systems-architect] The absent or dangling instructions entry recovers as a first install does** (a clause of `dec-499`): derived values, the confirmation prompt with its timeout, a render into N+1 and a link, while the links go through the refresh rules and never through `link_rules` or `_link_scripts`, which take every link over, a clone's included. Round-0 answer 4(b) fixes the behaviour; SQ-04 and SQ-05 fix what the prompt may show.

**[implementation-planner] Pure core in a private sibling, `hooks/_install_refresh.py` (process decision, no ADR)**: the cache predicate, the classifier and the script planner live there and the hook keeps the effects. **Why**: the architect set a trigger (extract if the hook passes about 650 lines) and the update path adds 150 to 200 lines plus effects, so extracting up front gives the core mock-free tests. **Alternatives**: everything in the hook (it would cross the trigger inside the series and need a later refactor step).

**[implementation-planner] One vertical slice per surface (process decision)**: scripts (steps 3 to 5), rules (6), instructions (7, 8). **Why**: each slice leaves the hook working and turns a bounded set of outer-loop nodes green; one wiring step would own about 40 nodes and exceed an implementer window. **Alternatives**: horizontal layers with one integration step.

**[implementation-planner] Ownership, review and mutation tagging (process decisions)**: each outer-loop guard belongs to the step that introduces the code path it guards, and a parametrized function to the last step that turns its last case green (machine-checked: every one of the 40 scenario functions is in exactly one `Read-only` field and the per-step counts sum to 62). `review: force` went on steps 1, 4, 6 and 7 (the architect's two, the value recovery split across steps 1 and 7 and the rule re-point in step 6, plus step 4, the only step that unlinks and replaces entries in the user's `~/.local/bin`); `tier: H` on step 7 only; `mutation: on` on steps 1, 4, 5 and 7, where the fail-open design is exactly where a passing test can hide a dead read. The architecture documents are updated once, in step 10, and the eight advisory project principles are given by set (A for steps under `scripts/`, `hooks/` and `tests/`; B for steps 9 and 10).

**[implementer] One atomic writer for links and renders**: `_build_and_rename(destination, build)` builds beside the destination and `os.replace`s it over, and the instructions swap reuses the link writer. **Why**: the render and the link need the same never-neither guarantee, kept in one place. **Alternatives**: a second, render-only writer.

**[implementer] First-install instruction setup moved into `_install_update.py`, and a refused confirmation is `InstallDeclinedError`**: the move avoided a circular import and kept the two-argument signatures about 25 tests call; a refusal on the update path is caught by `_run_update_path` and writes no completion marker, as the cold path does with no marker. **Alternatives**: injecting the hook's prompt as a callable; a step return value.

**[implementer] A residual placeholder in the previous render counts as a carried value**: `carry_forward_instructions` keeps whatever `recover_values` returns, a literal `{{KEY}}` included. **Why**: every hook render is made with the three derived keys, so a residual can only be a key `derive_defaults` cannot fill either. The implementer called this a dead branch. The verifier ruled it **W1** (a surfaced-in-LEARNINGS assumption that REQ-08's "no value" reading contradicts, latent today); it is `td-615`.

**Cross-check of `LEARNINGS.md ### Decisions Made` against the ADR drafts** (13 entries). Two carry a `dec-draft` id and a draft; the architect's third entry (the dangling recovery) is a clause of `dec-499`, and the script-refresh objection above is that draft's Considered Options. The other ten have no ADR: the six planner entries are plan-level and stated as such, and the four implementer entries follow the rule that the implementer authors no ADR. One of them deserves the orchestrator's look: the hook is now split into two private sibling modules (`hooks/_install_refresh.py` from the planner's decision, and `hooks/_install_update.py` added by step 7a), which meets the `architectural` falsifier (a component added in the hook family). Both modules are named in `.ai-state/DESIGN.md` and `docs/architecture.md`, but no ADR records the split, and neither draft's `affected_files` names either module. The planner recorded the first sibling as implementing the architect's own stated option, and the second came from the orchestrator's step 7a.

## Verification and Rework

**Light reviews inside the step loop.** Steps 1, 4, 6 and 7 carried `review: force`. Step 1 (`recover_values`) was accepted in round 1, with two non-blocking notes: a lazy template lookup in its test, and the `{{KEY}}` read-back that became W1. Steps 4, 6 and 7 each got a `revise` in round 1 and an `accept` in round 2, three one-round revisions in all:

- **Step 4 (the script-refresh effects)**: F1, the "first error kept, raised after the loop" behaviour was pinned by no test; F2, a link already gone before its removal or before cleanup of a failed re-point must not raise. Both closed with tests that kill the named mutants. Residual, not blocking: two sessions starting together can make one session's `os.replace` fail with `FileNotFoundError`, and the final state converges.
- **Step 6 (the rule re-point)**: F1, a textual prefix check for "already into the current version" would have rewritten a relative or respelled link into N+1, so it became the same-file test `-ef` (a dangling link makes it false, so it still falls through to the re-point); F2, a parametrized test with branching was split in two.
- **Step 7 (the carry-forward)**: F1, purity, so `_missing_keys` and `_with_defaults` are pure and `derive_defaults()` is called once, at the edge, only when a key is missing; F2, the hook file size, routed to a new **step 7a**; F3, a magic slice became `_PLACEHOLDER_BRACE_WIDTH`; F4, logic in tests moved into helpers.
- **Step 7a** was added before issue by the orchestrator: a pure move of the update path's effects and its tests into `hooks/_install_update.py` and `hooks/test_install_update.py`, so the hook stayed under 800 lines with step 8 still to add four instruction states. The hook ended at 354 lines. `hooks/test_install_update.py` sits at exactly 800, and the carry-forward test classes stayed in `hooks/test_auto_complete_install.py` (2,153 lines; `td-611`) because moving them would have put the new file over the ceiling and outside the step's `Check`.

The step loop ran steps 1 to 10, 7a and 11 in 21 of 26 iterations. Steps 1, 4, 5 and 7 carried `mutation: on` and none was blocked; the sensor's survivors in world-read functions are `td-616`.

**Final verification (at `c06b84da`)**: **FAIL** with 1 FAIL, 7 WARN and 3 INFO. **F1**: with the completion marker present and `~/.claude/CLAUDE.md` removed, N+1's first session printed the confirmation question and the three derived values (a made-up identity in the probe) on stderr, against REQ-07 and REQ-18's text. The cause was a spec-versus-design conflict with no production defect behind it: the design mapped the absent state to the first-install setup, as the base does, and SQ-04 had covered only the dangling case. The verifier tagged it `[UNSURFACED-ASSUMPTION]` and proposed a rework worktree (`rw-752c610d`, lightweight, architecture class). The orchestrator took the verifier's first remedy instead and resolved it by Spec Question SQ-05, with no rework worktree and no production change. The WARNs were W1 (the `{{KEY}}` token, `td-615`), W2 (the hook test file, `td-611`), W3 (`prepare_update` at 87 lines, `td-617`), W4 (mutation survivors, `td-616`), W5 (the shape of `TEST_RESULTS.md` sections for steps 7 and 10, advisory), W6 (a suite test rewrites the tracked `SPECS_INDEX.md`, `td-612`) and W7 (the quiet CI-equivalent suites had not completed).

**Delta re-verification (`c06b84da` to `b59390d1`, a state-only commit)**: **PASS WITH FINDINGS**, 0 FAIL, 6 WARN, 3 INFO. F1 closed: the amended REQ-07, REQ-18 and REQ-25 match the code (`classify_instructions` maps an absent entry to `NoInstructions`, and `_update_instructions` sends it and `MissingCachedRender` down one branch to `_fresh_instructions_setup`), the pinning test passes, and each other requirement was read against the absent state. The verifier corrected one claim of its own first report: the routing test already existed at `c06b84da`. W7 closed: root `18010 passed, 37 skipped` (the baseline's 37; the quiet run took 1,804 s), eval format, lint and pyright clean with 4,296 passed, chronograph 288 of 288 read from its progress marks (at `-qq` pytest prints no summary line). Step 10's three reds under load (an install-check rule-link test and two signal and timeout tests, the class of `td-535`) did not recur. The `/code-review` and `/context-security-review` lenses over the delta found nothing new.

**Other checks that held.** Every Key Signal KS1 to KS6 and every health guard passes on code reading, the 62-node outer loop, the verifier's probes and the completed suites. The operator-layout probe (a clone at `.../dev/praxion`, relinked with the real `install.sh --relink`, a marketplace marker present, N+1 landed) left 78 clone links, the instructions link and the clone's render unchanged, with hook exit 0 and empty stderr. The verifier found the security review PASS (a constant bash script with positional arguments and no `shell=True`; no secret or identity in added lines; no context artifact changed), the calibration verdict `correct` (Standard fitted: 12 plan steps, 4 review-forced steps with 3 one-round revisions, 30 files and about 4.2k added lines, one ADR pair, no mid-task re-tier), and the architecture documents consistent (`check_architecture_projection.py` rc 0, 15 of 15 rows). The baseline had 0 failures at `33a0541e`, so no failure is undisposed. The only plan deviations were step 7a (added) and step 8's move of the first-install helpers, both inside declared `Files` and surfaced in `LEARNINGS.md`.

## Open Findings

None blocks the merge. Rows are in `.ai-state/TECH_DEBT_LEDGER.md` (source `verifier`, 2026-11-10):

- **`td-611`** (important, complexity): `hooks/test_auto_complete_install.py` is 2,153 lines against the 800-line ceiling (1,771 at the base). Move the carry-forward classes to a third sibling test module, add it to the hook's derived scope, and split the remaining cold-path classes by concern.
- **`td-612`** (important, test isolation): a root-suite test rewrites the tracked `.ai-state/specs/SPECS_INDEX.md` (seen at the baseline capture and at the step-10 full run, restored by hand each time), the same class as `td-602`. The likely writer is `regenerate_specs_index.py` reached with the real repo root; name the node by a before and after hash bisect, then run it over a `tmp_path` copy and pin it with a guard.
- **`td-613`** (important, drift): the installer's `script_is_user_facing` and its four inline copies exclude `git-*-hook.sh` (`dec-042`) while the hook's `offered_scripts` excludes every `*-hook.sh`. They differ on `scripts/diagram-regen-hook.sh`, so a marketplace install completed by the installer's hand path has that link removed by its next update refresh. Fix: one predicate in the library, deciding the `*-hook.sh` question deliberately.
- **`td-614`** (important): `/praxion-complete-install`, the hand path the failure line names, renders no instructions, and its plugin-root fallback (`ls -d .../praxion/*/ | head -1`) can pick the oldest cached version. After an instructions-step failure the named command does not finish the job. Fix: render the instructions with recovered values from the hand path and resolve the root from `installed_plugins.json`.
- **`td-615`** (suggested): a recovered unsubstituted `{{KEY}}` token is kept as a carried value where REQ-08 reads it as no value (W1). Latent, because `derive_defaults` always returns the three shipped keys. Fix: treat a value equal to its own placeholder as missing in `_missing_keys`, with a unit test.
- **`td-616`** (suggested, coverage gap): mutation-sensor survivors in world-read functions with no test through the real adapter: `_run_rule_linkers` (15), `_run_git_config` (11), `_plugin_root` (9), `_run` (9) and `_prompt_with_timeout` (27, moved code).
- **`td-617`** (suggested, complexity): the outer-loop driver's `prepare_update` is 87 lines against the 50-line ceiling; extract one planter per role when the outer loop is next amended through an answered Spec Question.

Not on a row: W5 (advisory: the Step 7 and Step 10 green sections of `TEST_RESULTS.md` are 1,121 and 1,382 bytes against the shape checker's 1,024; they end with the pipeline's working files), and the INFO notes I1 (REQ-15's reading, under Spec Question Answers), I2 (the routing test sets `PRAXION_AUTO_COMPLETE=1`, so it pins the routing and the rendered values, not the terminal prompt or the link target, which SQ-05 does not claim) and I3 (who answered SQ-05, recorded above).

The two rows this pipeline set out to close are the orchestrator's to close at merge: `td-593` (resolved by this pipeline, per the planner's note) and `td-602` (the verifier's KS5 reading is PASS on the full root run, while `td-612` keeps the same class open for a different writer). Two architect candidates, the predicate divergence and the hand path's gap, are now `td-613` and `td-614`.

## Gotchas Worth Keeping

- **A `--plugin-dir` session must never re-render into its checkout.** The update path runs only when the plugin root is a cache version directory, and a unit test pins a checkout root; without that gate the hook would repeat `td-602` through a session, not a test.
- **The cache predicate needs the whole structure, not a suffix.** `cache_version_dir` matches `plugins/cache/<marketplace>/praxion/<version>` as five consecutive segments. A lone `praxion` segment is exactly what an operator's clone directory is called, so four clone-shaped rows (this operator's layout among them) are pinned as not-cache in `tests/fixtures/plugin_cache_targets.tsv`, asserted by both the Python and the bash tests. It accepts any marketplace name but only the plugin `praxion`. The bash glob's `*` also crosses `/`, so a target with extra segments between `cache` and `praxion` reads as cache to bash and not to Python; Claude Code's layout never produces one.
- **Two script predicates are deliberately not unified here.** The hook's `offered_scripts` (`*-hook.sh` excluded) and the installer's (`git-*-hook.sh` excluded) differ on `scripts/diagram-regen-hook.sh`; unifying them in this change would move either the clone path or every marketplace install's links. `td-613` owns the decision.
- **The marker is written even when a step fails.** That keeps a later session of the same version silent, and it means a failed refresh is never retried; the one stderr line is the user's only prompt to run `/praxion-complete-install`, which (`td-614`) cannot finish a failed instructions render.
- **Hook code must stay 3.9-safe and the library bash 3.2-safe.** No runtime `X | Y`, no `match`, no `zip(strict=)` (a `# noqa: B905` with its reason sits in `recover_values`), no `typing.assert_never` (a local `unreachable` closes each dispatch), and `Union` carries `noqa: UP007`; in bash, no `mapfile` and no associative arrays. `hooks/test_auto_complete_install.py` loads the hook by file path, so the hook puts its own directory on `sys.path` to import its siblings.
- **The mutation sensor runs a test file from a copy one directory deeper** (`hooks/mutants/`, `scripts/mutants/`), so a test that finds the repository with `HOOKS_DIR.parent` or `SCRIPTS_DIR.parent` fails there with `run-failed`. The hook tests locate the repository as the nearest ancestor holding `lib/install_shared.sh` and put `scripts/` on `sys.path` and `PYTHONPATH`; `test_render_claude_md.py` walks the parents for the shipped template.
- **A passing test can hide a dead read in a fail-open design.** The broad `except Exception` steps are where the sensor found survivors in world-read functions (`td-616`); the replacement for a world-read mock is one adapter-level test through the real subprocess, file or stdin.
- **The template and its render are a cross-version contract.** One placeholder per line, literal text around it, and a render that changes nothing else; a template edit that breaks this makes the next update unrecoverable (it fails safe: the old render stays, one line is printed), and the round-trip test over the shipped template is its enforcer. The update also depends on the old version's directory surviving until the new version's first session.
- **A link already into the running version is "already current" by same-file test, not by text.** A textual prefix check rewrites a relative or respelled link into N+1; `-ef` keeps its inode and its text. A link or root spelled through different prefixes (`/var` against `/private/var`) is re-rendered or re-pointed once, to the same file, which is harmless and unhandled.
- **Any driver that runs `install.sh` from the repository root writes the checkout's configuration.** The install drivers must build a stand-in copy of the tree (`plugin_update.shipped_tree`, `stand_in_root`); a new one that does not re-creates `td-602`, and the nested checkout-isolation scenario runs every test file naming `render_claude_md` or `auto_complete_install`, so every new test there must use `tmp_path` homes and made-up identities.
- **Task-brief figures can be stale.** The brief's 19,918 always-loaded tokens measured 19,894 at the base; re-measure a health guard's number at the base commit before treating a difference as the change's.
- **Reading the suites.** The full root suite takes about 1,040 s alone (1,516 s overlapping the driver's background gate runs, 1,804 s in the quiet CI-equivalent run) and rewrites the tracked `.ai-state/specs/SPECS_INDEX.md` (`td-612`); restore it with `git checkout` and commit by explicit path. A pocket run with `-q` on top of `addopts = "-ra -q"` is `-qq` and prints no summary line, so read the progress marks. A `Check:` command runs without a shell, so list test files one by one; a `Read-only:` field is one line, because sub-bullets parse as zero owners.

## Follow-up

- At merge: finalize rewrites the two draft ids in this archive and in the ADR cross-references (`dec-491` carries `superseded_in_part_by` the first draft), and the orchestrator closes `td-593` and decides `td-602`. The orchestrator also decides whether the split of the hook into two private siblings (see Key Decisions) deserves its own ADR.
- Optional before relying on the requirement text: add REQ-15's instructions-state precondition (verifier note I1).
- The `.ai-state/DESIGN.md` decision checkpoint was not advanced: `check_design_checkpoint.py` lists unrelated un-folded ADRs from `dec-392` onward that this pipeline did not read.
- `td-613` and `td-614` are the follow-ups with user-visible reach: a marketplace install completed by the hand path loses the `diagram-regen-hook.sh` link on its next update, and a failed instructions render cannot be completed by the command the failure line names.
