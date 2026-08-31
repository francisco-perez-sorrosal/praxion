---
id: dec-346
title: Unified onboard CLI contract — argument-presence mode selection and capability-ID flags
status: accepted
category: behavioral
date: 2026-08-30
summary: One entry script whose mode is selected by positional-argument presence, with a uniform --with/--without capability-ID vocabulary replacing bespoke negative flags, legacy exit codes 2-6 preserved and 7-8 appended.
tags: [onboarding, interface-design, cli, flags, exit-codes, error-grammar]
made_by: agent
agent_type: interface-designer
branch: worktree-onboarding-unification
pipeline_tier: full
affected_files:
  - scripts/onboard-project
  - skills/onboard-project/SKILL.md
  - install_claude.sh
dissent: "Overloading positional-argument presence to select between 'create a project there' and 'onboard the project here' makes one entrypoint do two categorically different jobs; a user who types a stray argument gets a scaffold instead of an onboard."
---

## Context

Unification replaces `new_project.sh` + `/new-project` + `/onboard-project` with one entry script (`scripts/onboard-project`) and one user-invocable skill (`/praxion:onboard-project`) covering four modes: `new`, `existing`, `hackathon`, `promote`.

The existing surface has three ergonomic problems the CLI contract must resolve:

1. **Two entrypoints with a mirror-image guard each.** `new_project.sh` + `/new-project`'s §Guard aborts and redirects to `/onboard-project` when the directory is not freshly scaffolded; `/onboard-project`'s pre-flight aborts and redirects to `/new-project` when it is. Both hand-encode the same "greenfield signature" in separate prose, synced by nothing. The user is required to know which of two commands applies before the tool will tell them.
2. **Bespoke negative booleans.** `--no-aac` and `--no-obsidian` (plus three `PRAXION_NEW_PROJECT_*` env equivalents) cover two of what are now seven optional capabilities. The pattern does not scale, and negatives compose badly (`--no-aac --no-obsidian --no-ml --no-ci`).
3. **A published exit-code contract.** Codes 2–6 are documented in `docs/greenfield-onboarding.md`'s troubleshooting table and are load-bearing for anyone scripting the entry point.

There is also no dry-run: today the only way to learn what onboarding would do is to let it do it.

## Decision

**Mode is selected by positional-argument presence**, not by a required flag:

| Invocation | Mode |
|---|---|
| `onboard-project` | detected from cwd — `existing`, or `new` if empty, or `promote` if hackathon state is present |
| `onboard-project my-app [target-dir]` | `new` — create, scaffold, onboard |

This makes "onboard where I am" the zero-argument default while preserving `new_project.sh my-app` muscle memory exactly. `--mode <new|existing|hackathon|promote>` exists as an explicit override for scripts and fails fast (exit 2) when it contradicts detected state. The two mirror-image guards collapse into one detector that routes instead of refusing.

**Capabilities get one uniform vocabulary** — `core`, `arch`, `quality`, `ci`, `aac`, `ml`, `obsidian`, `observability` — used identically by `--with <ids>`, `--without <ids>`, `--profile <minimal|standard|full>`, the Profile checkboxes, the progress lines, the final summary, and the skill's `argument-hint`. `--no-aac` / `--no-obsidian` are accepted for one release with a stderr deprecation warning, then removed.

**Non-interactive and preview surfaces are first-class**: `--yes` (accept all detected defaults, ask nothing), `--check` (dry-run: detect, report, exit; writes nothing and never launches Claude), `--json` (machine-readable detection/plan), `--no-launch` (do the bash-side work, print the resolved plan and seed prompt, do not `exec claude`), plus `--quiet` / `--verbose` / `--no-color` with `NO_COLOR` and non-TTY honoured.

**Exit codes**: 2–6 preserved verbatim (usage / no `claude` / no plugin / no `git` / target exists non-empty); `7` = refused (plugin-source-repo guard or state incompatible with the requested mode); `8` = `--check` only, work pending. `--check` returning 0/8 rather than 0/1 keeps "nothing to do" distinguishable from "broken," mirroring `sync_canonical_blocks.py --check`.

**Error grammar** is three-part throughout — what went wrong, why, and the exact command that fixes it — on stderr, never a stack trace as the primary surface.

**Failure containment**: a capability failure emits a warning line and the run continues; only prereq failures and guard refusals abort, and those happen before any write.

**Handoff to Claude** uses the proven `exec claude --permission-mode acceptEdits --allowedTools ... -- "<seed prompt>"` pattern with a plain prompt that instructs invoking the skill. Slash-in-argv (`claude "/praxion:onboard-project"`) is treated as unverified and is not relied upon.

The installed bin name is recommended as `praxion-onboard` (siblings: `praxion-dashboard`, `praxion-hackathon`, `praxion-feedback`), with `new-project` retained for one release as a deprecation-warning shim.

## Considered Options

### A. Required `--mode` flag on every invocation

- **Pro**: unambiguous; no overloading; trivially scriptable; a stray positional argument can never be misread.
- **Con**: forces the user to state something the tool can already detect with high confidence — the definition of friction, and it breaks `new_project.sh my-app` muscle memory outright. Every happy-path invocation becomes longer than today's.

### B. Two entrypoints preserved (`onboard-project` and `new-project`)

- **Pro**: zero migration cost; each script stays simple; no overloaded argument semantics.
- **Con**: preserves the exact problem the task exists to remove — two mirror-image guards, duplicated prereq logic, and a user who must classify their own project before the tool will help. Also keeps the canonical-block sync burden alive.

### C. Argument-presence mode selection + capability IDs (chosen)

- **Pro**: one entrypoint, one vocabulary shared with the skill's `argument-hint`, muscle memory preserved, guards become routing. `--with`/`--without` scale to any number of capabilities and compose cleanly.
- **Con**: positional presence is doing semantic work (see `dissent`). Mitigated by the detection announcement, which prints `Mode` and `Target` before any write, and by exit 6 when the named target exists and is non-empty.

## Consequences

**Positive**

- One command to learn; the zero-argument form is the common case.
- `--check` gives a zero-risk preview that does not exist today at all.
- The two hand-encoded greenfield-signature guards collapse to one detector, removing an unsynced duplicated-definition surface.
- The flag vocabulary and the skill's `argument-hint` are the same strings, so terminal and slash-prompt usage transfer.
- Legacy exit codes stay valid, so the published troubleshooting table and any user scripts keep working.

**Negative**

- Positional overloading: `onboard-project my-app` typed inside an existing project scaffolds a *subdirectory* rather than onboarding the project. Exit 6 catches the non-empty case; the detection announcement's `Target ... (will be created)` line catches the rest before any write.
- Two flags are deprecated, so `install_claude.sh` messaging, `docs/`, and `tests/new_project_test.sh` all need updating in the same change.
- Adds `--json`, `--check`, `--no-launch`, `--profile` to a script that previously had four flags — a larger surface, justified by the preview/scripting capabilities that were entirely absent.

## Disconfirmation

**Falsifier.** A user running `onboard-project <name>` from inside a project they meant to onboard in place, and getting a scaffolded subdirectory. If that happens more than once, positional-presence mode selection is wrong and Option A is right. The detection announcement is the guard against it; if the announcement is not being read, no amount of wording fixes the overloading.

**Steelmanned runner-up.** Option A (required `--mode`) trades a few keystrokes for the elimination of an entire class of misfire, and mode is exactly the kind of high-blast-radius, hard-to-reverse choice that the behavioural contract says should be explicit rather than inferred. The muscle-memory argument for positional presence is weak in absolute terms: `new_project.sh` users are a small population and are being asked to learn a new command name anyway. If detection-based routing produces any real-world misfire, A costs almost nothing to switch to.

**Reversal trigger.** Revisit if (a) any user report of an unintended scaffold from a stray positional argument, or (b) the `promote` mode's detection proves unreliable enough that `--full` becomes the de-facto required invocation — at which point mode is being stated explicitly anyway and the inference is buying nothing.
