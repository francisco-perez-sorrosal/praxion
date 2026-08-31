---
id: dec-055
title: Hybrid bash + slash-command orchestration for greenfield onboarding (Option C)
status: accepted
category: architectural
date: 2026-04-18
summary: Bash handles deterministic prereqs and minimal filesystem scaffold; the slash command handles conversational flow, app generation, and mushi-doc generation. Each layer does what it does best.
tags:
  - onboarding
  - bash
  - slash-command
  - separation-of-concerns
made_by: user
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - scripts/onboard-project
  - skills/onboard-project/references/seed-pipeline.md
affected_reqs:
  - REQ-ONBOARD-01
  - REQ-ONBOARD-02
  - REQ-ONBOARD-03
  - REQ-ONBOARD-04
  - REQ-ONBOARD-05
  - REQ-ONBOARD-06
  - REQ-ONBOARD-07
  - REQ-ONBOARD-08
  - REQ-ONBOARD-09
  - REQ-ONBOARD-10
  - REQ-ONBOARD-11
---

## Context

The research stage (`.ai-work/praxion-project-onboarding/RESEARCH_FINDINGS.md` §4) compared three orchestration shapes for the greenfield flow:

- **Option A — Bash-thin, Claude-thick.** Bash does only `mkdir + git init`, then `exec claude` with a long inline seed prompt that contains every instruction (run `/init`, ask the question, generate the app, generate the mushi doc, etc.).
- **Option B — Bash-thick, Claude-thin.** Bash writes the whole scaffold (CLAUDE.md, AGENTS.md, full `.gitignore`, mushi-doc template, default app skeleton via `pixi`/`uv`), validates everything, then `exec claude` with a one-line seed.
- **Option C — Hybrid.** Bash does the cheap deterministic things (prereq checks, mkdir, git init, minimal `.gitignore`, empty `.claude/`), then `exec claude` with a seed that is just the slash-command invocation `/new-cc-project`. The slash command, a first-class Praxion artifact, drives the conversational flow.

Option A buries the entire onboarding UX inside a long shell-quoted prompt that nobody can review cleanly, and the prompt is invisible to Claude Code's slash-command discovery, so it cannot be reused from inside an existing session. Option B duplicates Praxion logic in shell (mushi-doc templating, `.gitignore` extension, app scaffolding) and gives up the conversational quality of Claude's natural Q&A. Option C keeps each layer doing what it does well.

The user's brief converged on Option C with prompt-over-template discipline (recorded separately in dec-053).

## Decision

Adopt Option C. Specifically:

**Bash layer (`new_cc_project.sh`, ~40 lines):**
- Validate prereqs (claude binary, i-am plugin, git) with distinct exit codes and friendly error messages (REQ-ONBOARD-02–04).
- Argument parse (`<project-name>` required, `[target-dir]` optional, defaults `$PWD`) (REQ-ONBOARD-01).
- Reject pre-existing non-empty targets (REQ-ONBOARD-05).
- Create directory, `git init -q`, write minimal AI-assistants `.gitignore` (REQ-ONBOARD-06), create empty `.claude/`.
- Print one pre-flight stdout line (REQ-ONBOARD-07).
- `exec claude --permission-mode acceptEdits "/new-cc-project"` from inside the new directory (REQ-ONBOARD-08).

**Slash-command layer (`commands/new-cc-project.md`):**
- Guard: confirm the working directory matches the scaffold shape (REQ-ONBOARD-09).
- Invoke `/init` to generate CLAUDE.md, append the Praxion `## Agent Pipeline` block (REQ-ONBOARD-10).
- Ask exactly one content question (REQ-ONBOARD-11).
- Branch into default-app generation or custom-app generation; both share the same outer frame (`/init` → app → mushi doc → stage → `/co` hint).
- Generate the mushi doc last so anchors point at real lines.

The bash layer's responsibility ends the moment `exec claude` fires. Everything user-facing after that is the slash command's surface.

## Considered Options

### Option A — Bash-thin, Claude-thick (single big seed prompt)

**Pros:** smallest bash. Easy to evolve by editing one prompt.

**Cons:** the seed prompt is opaque shell-quoted text — no syntax highlighting, no review surface, no reuse, no testability. If the user is already in a Claude session, they cannot just `/new-cc-project` because no slash command exists. The whole UX lives inside a string literal.

### Option B — Bash-thick, Claude-thin (full scaffold in bash)

**Pros:** deterministic, fast, no first-turn surprises. Bash failures are visible early.

**Cons:** duplicates Praxion logic in shell. Templates (mushi doc, app code, `.gitignore` rules) drift independently from their Praxion sources of truth. Conversational UX (asking "what to build?") is cruder in bash than via Claude's `AskUserQuestion`. Educational doc cannot say "you just built X" because bash doesn't know.

### Option C — Hybrid (chosen)

**Pros:**
- Each layer does what it is best at: bash for cheap deterministic checks, Claude for conversational and generative work.
- The slash command is a first-class Praxion artifact: testable, versioned, discoverable via Claude Code's command catalog, reusable from any existing session (`/new-cc-project foo` from any directory).
- Bash failures are loud and early; Claude failures are recoverable mid-session.
- Clean separation of concerns aligns with prompt-over-template (dec-053) and with shipped-artifact-isolation.

**Cons:**
- Two artifacts to maintain instead of one.
- Handoff timing: the user sees a brief gap between bash's pre-flight line and Claude's first response (a second or two of `claude` startup).
- A Claude-Code-internal change to slash-command invocation timing would shift the handoff feel.

## Consequences

**Positive:**
- The slash command is reusable from inside an existing Claude session — a user already in some other project can run `/new-cc-project my-other-project` without going through bash. (The guard check then short-circuits if the target already exists; future iteration could lift the slash command to do the scaffold itself when invoked without an existing one.)
- Each layer is independently testable: bash with shell assertions on a fresh tmp dir, slash command via inspection of generated artifacts.
- Adds zero always-loaded content. The slash command is invoked on demand; the script is invoked from the shell.
- Contributors who want to evolve the conversational UX touch only the slash command. Contributors who want to evolve prereq checks touch only bash.

**Negative:**
- Two surfaces to keep aligned (e.g., the `.gitignore` shape bash writes must remain consistent with what `/onboard-project` later expects to extend). Mitigation: bash's `.gitignore` block uses the canonical AI-assistants comment header (`# AI assistants`) so `/onboard-project`'s presence-check matches.
- Slight increase in moving parts compared to A; mitigation is that the slash command is just a markdown file with prose, not new code.
