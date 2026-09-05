---
id: dec-359
title: Praxion CLAUDE.md block writers resolve their target through a per-path placement intent, and never write to a path the team already owns
status: accepted
category: architectural
date: 2026-09-02
summary: Block-target resolution moves out of each writer and into the placement resolver. CLAUDE.md joins the manifest's paths map with one of three intents - untouched when the team already has one (blocks go to a shadowed CLAUDE.local.md), shadow by default when there is none, share when --share CLAUDE.md is passed. Managed-project detection gains CLAUDE.local.md so a sidecar project is not misread as unmanaged.
tags: [claude-md, canonical-blocks, onboarding, placement, detection, sidecar, refresh-claude-blocks]
made_by: agent
agent_type: systems-architect
branch: worktree-sidecar-placement
pipeline_tier: full
affected_files:
  - scripts/refresh_claude_blocks.py
  - skills/onboard-project/references/phases-core.md
  - skills/onboard-project/references/claude-md-blocks.md
  - skills/onboard-project/references/detection.md
  - skills/onboard-project/references/phases-optional.md
  - claude/canonical-blocks
dissent: "Defaulting to a shadowed CLAUDE.md means the operator's project prompt lives in a file the team will never see and never review, so a Praxion-shaped instruction set silently governs commits landing in a shared repository - the reviewability that a committed CLAUDE.md provides is a feature this default deliberately gives up."
---

## Context

Onboarding writes seven canonical `CLAUDE.md` blocks into a managed project.
`scripts/refresh_claude_blocks.py` hardcodes the target as
`repo_root / "CLAUDE.md"` in two places, and Phase 6 assumes that file exists
and is Praxion's to append to.

Under sidecar placement that assumption fails in two different ways, and the
mid-design amendment made the distinction explicit: **the project's own
`CLAUDE.md` may itself reference Praxion, or may not exist at all.**

- A team repository that already has a `CLAUDE.md` has one the team wrote and
  reviews. Appending Praxion blocks to it is a visible, tracked modification of
  a shared file — precisely the footprint sidecar placement exists to avoid.
- A team repository with no `CLAUDE.md` presents a different question. Creating
  one is itself an act of adoption the team did not ask for; but the operator
  legitimately wants the full block set, including Project Essentials, which is
  genuinely project-specific and useless in a global config.

Research also established that the two highest-value blocks for a Praxion
operator — Behavioral Contract and Praxion Process — already substantially
duplicate the operator's own global `CLAUDE.md`. Their per-project copy exists
mainly for a *teammate* without the plugin, which is a beneficiary that does not
exist in the sidecar scenario.

Finally, detection state four (`partially-managed`) greps `CLAUDE.md` for
`^## Agent Pipeline$`. A sidecar project whose blocks live elsewhere would fail
that predicate and read as unmanaged, so a re-run would try to onboard it from
scratch.

## Decision

1. **Block-target resolution moves out of the writers and into the placement
   resolver.** Every writer — Phase 6, Phase 5b, Phase 8d, and
   `refresh_claude_blocks.py` — asks `placement.block_target()` instead of
   assuming `repo_root / "CLAUDE.md"`. Under in-repo placement the answer is
   unchanged, so this is additive for existing projects.

2. **`CLAUDE.md` becomes an ordinary entry in the manifest's `paths:` map**,
   carrying one of the same three intents every other managed path carries.
   It needs no bespoke field:

   - **`untouched`** (`reason: preexisting-team-file`) — the project has a
     tracked `CLAUDE.md`. Praxion never writes to it; all blocks go to the
     shadowed `CLAUDE.local.md`, which Claude Code loads last with the highest
     precedence.
   - **`shadow`** — the default when no `CLAUDE.md` exists. `CLAUDE.md` itself
     becomes a symlink into the sidecar, excluded via `.git/info/exclude`. The
     operator gets a full private project prompt; the team sees nothing.
   - **`share`** — `--share CLAUDE.md` opts into a real, tracked, committed
     file.

   `CLAUDE.local.md` is shadowed in all three cases.

3. **The general invariant is that no Praxion writer targets a path whose intent
   is `untouched`.** This is not a `CLAUDE.md` special case; it holds for every
   entry in `paths:`, and `CLAUDE.md` is simply its first instance. Enforced at
   the resolver, which is the only site that maps a logical target to a path.

4. **Detection consults `CLAUDE.local.md` alongside `CLAUDE.md`.** One clause in
   the state-four predicate.

5. **`scripts/render_claude_md.py` is explicitly out of scope.** It renders the
   *global* `~/.claude/CLAUDE.md` from a template and never touches a project
   file; naming it as a block writer would be a category error.

## Considered Options

### A — Always write to `CLAUDE.local.md` under sidecar placement

Pros: the simplest rule with no cases at all; `CLAUDE.local.md` is gitignored by
Claude Code convention and loads last; no decision to record.

Cons: a repository with no `CLAUDE.md` gets a `CLAUDE.local.md` that reads as
"personal overrides on top of a project prompt" when it is in fact the entire
project prompt. It is also inconsistent with the shadow model used for every
other path: `.ai-state` is shadowed at its canonical name, and there is no
reason `CLAUDE.md` should be the one path Praxion renames rather than shadows.

### B — Always shadow `CLAUDE.md`, in every case

Pros: one mechanism, uniform with `.ai-state`.

Cons: catastrophic when the team already has a `CLAUDE.md` — shadowing replaces
a tracked file with a symlink, which git sees as a modification of a shared
file. The exact opposite of the goal.

### C — Three intents on one `paths:` map (chosen)

Pros: one representation for every managed path; `untouched` is expressible and
distinguishable from "never considered", so `link`, `status`, `doctor` and the
onboarding phases share one interpretation rather than four heuristics; a `link`
that guesses wrong on `CLAUDE.md` overwriting a team file becomes structurally
impossible.

Cons: three cases the operator may need explained; the intent is fixed at init
and changing it later requires an explicit migration that moves block content.

### D — A dedicated `claude_md.case` manifest field

Pros: the decision is named where a reader looks for it.

Cons: two representations of one fact — the same path would appear in both
`paths:` and `claude_md`, and they could disagree. Rejected on the strength of
the interface-designer's challenge, which made the general case for the unified
map.

## Consequences

**Positive.** A team repository that already references Praxion is left exactly
as the team wrote it, verifiable by a byte-comparison test after a full
onboarding run. An operator on a repository with no `CLAUDE.md` gets the full
block set with zero tracked footprint. Block-target resolution stops being
duplicated across four writers. The `untouched` intent generalises beyond
`CLAUDE.md` to any path an operator wants Praxion to keep its hands off.

**Negative.** The three-case rule is genuine surface area an operator must
understand, and the default (`shadow`) is the least discoverable of the three —
a teammate looking at the repository sees no `CLAUDE.md` at all while the
operator's session behaves as if there is a detailed one. Changing intent after
init requires a migration rather than an edit. Every block writer gains a
dependency on the resolver, including `refresh_claude_blocks.py`, which
deliberately runs with no git dependency at consumer sites today.

**Neutral.** Under in-repo placement every path resolves exactly as before, so
the change is invisible to existing projects.

## Disconfirmation

**Falsifier.** If operators in the `untouched` case routinely end up
hand-copying Praxion blocks into the team's `CLAUDE.md` anyway — because the
team turns out to want them — then the premise that a team repository must stay
Praxion-agnostic is wrong for that population, and the honest default becomes
`share` with a review step, not `untouched`. Equally: if the shadowed-`CLAUDE.md`
default produces confusion in practice (an operator forgetting the file is not
in the repository, or a `git clean` removing the symlink and the session
silently losing its project prompt), the default should flip to
`CLAUDE.local.md` and option A wins.

**Steelmanned runner-up.** Option A — always `CLAUDE.local.md`, never shadow
`CLAUDE.md` — is right if one weights *predictability* over *uniformity*.
`CLAUDE.local.md` is a documented Claude Code convention that every Claude Code
user already understands as "my private per-project instructions", and it exists
whether or not Praxion is involved; a shadowed `CLAUDE.md` is a Praxion
invention that looks like an ordinary file and is not one. Option A also has
exactly one case, so there is nothing to explain, nothing to migrate between,
and no way for `link` to touch a team file because it never targets `CLAUDE.md`
at all. The counter is that it makes `CLAUDE.md` the single path Praxion renames
rather than shadows, which is an inconsistency a reader has to hold in their
head — but that is a smaller cost than this decision's three cases, and option A
is the stronger runner-up of the four.

**Reversal trigger.** A third writer of Praxion blocks appearing outside the
onboarding phases, or Claude Code changing `CLAUDE.local.md`'s precedence or
discovery rules, should prompt re-examining the case split as a whole rather
than patching one branch.
