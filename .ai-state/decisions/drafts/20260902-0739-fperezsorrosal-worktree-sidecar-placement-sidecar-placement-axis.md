---
id: dec-draft-4b33b1df
title: Onboarding gains a placement axis; under sidecar placement the git ownership of .ai-state/ moves to a per-operator repository projected in by symlink
status: proposed
category: architectural
date: 2026-09-02
summary: A second onboarding axis (in-repo | sidecar) lets one operator run the full pipeline on a repository they do not own. Under sidecar the .ai-state/ path contract on disk is preserved and only its git ownership moves, to ${PRAXION_SIDECAR_ROOT}/<project-id>/, hidden from the project by .git/info/exclude. Placement is not freely orthogonal to mode - sidecar pairs only with existing.
tags: [onboarding, placement, sidecar, state-ownership, team-repo, symlink, git-exclude, personal-software-factory]
made_by: agent
agent_type: systems-architect
branch: worktree-sidecar-placement
pipeline_tier: full
superseded_in_part_by:
  - dec-draft-0516562a
affected_files:
  - scripts/praxion-sidecar
  - scripts/_state_repo.py
  - scripts/onboard-project
  - skills/onboard-project/SKILL.md
  - skills/onboard-project/references/phases-core.md
  - skills/onboard-project/references/phases-optional.md
  - skills/onboard-project/references/detection.md
  - docs/onboarding.md
dissent: "Praxion has never before asked an operator to hold project intelligence in a second repository they must remember exists, back up themselves, and reason about when two checkouts disagree; a design whose safety story is 'no remote by default' is one lost laptop away from losing every ADR, ledger row and calibration row a project ever produced, and the in-tree-but-excluded option loses only history rather than the whole tree."
---

## Context

Praxion's `/onboard-project` writes roughly twenty surfaces into a managed
project, and all but two are **committed**: the `.gitignore` block, the whole
`.ai-state/` tree, `.gitattributes`, `.claude/settings.json`, the four canonical
`CLAUDE.md` blocks, and every opt-in tier. Only `.git/hooks/*` and
`.claude/settings.local.json` are local by construction.

That is correct for a project the operator owns. It is wrong for the case this
decision addresses: **one operator wants the full pipeline on a team repository
whose other contributors do not use Praxion, and the repository must stay
Praxion-agnostic.** Today the only options are to commit Praxion's footprint
into someone else's repo, or to give up the pipeline.

Research verified the two things that make a different answer feasible. First,
every consumer of `.ai-state/` reaches it by plain path join and file read, so
a symlinked `.ai-state/` is transparent to all of them — the *containment
guards*, not the readers, are where a relocation actually breaks. Second,
`.git/info/exclude` is git's own per-clone ignore mechanism, inherited by every
worktree through the common directory, invisible to teammates, and requiring no
code change anywhere: an excluded symlink is absent from `git status` and
`git add -A`, and `git add` through it fails loudly rather than silently.

`dec-221` is the nearest precedent and points the other way on purpose: it moves
*disposable bulk* out of tree and deliberately keeps the *curated intelligence*
tier committed. This decision moves the curated tier out as well, for one
placement mode only, and says so rather than letting the two records quietly
disagree.

## Decision

Onboarding gains a **placement** axis alongside its four modes.

1. **`in-repo`** is today's behaviour and remains the default. Nothing changes.
2. **`sidecar`** puts the durable state in a per-operator git repository at
   `${PRAXION_SIDECAR_ROOT:-~/.praxion/sidecars}/<project-id>/` and projects it
   into the project by symlink. The **`.ai-state/` path contract on disk is
   preserved**; only the answer to "which git repository owns this path"
   changes. Every agent, hook, skill and command that reads `.ai-state/` is
   untouched.

   > **Narrowed by `dec-draft-0516562a`.** The projection mechanism is no longer
   > "a symlink into `${PRAXION_SIDECAR_ROOT}`". Each checkout mounts the
   > sidecar as a `git worktree` at `<checkout>/.praxion-state/` and the shadows are
   > *relative* symlinks pointing inward, because Claude Code's worktree
   > isolation refuses `Write`/`Edit` on any lexically-in-worktree path whose
   > realpath escapes the worktree. The path contract, the invisibility
   > mechanism and the reversibility below are unchanged.
3. Two new components carry the mode: `scripts/praxion-sidecar` (the only
   writer of the sidecar and of the `.git/info/exclude` Praxion block) and
   `scripts/_state_repo.py` (the resolver, specified separately).
4. Invisibility is delivered by a marker-delimited Praxion block in
   `.git/info/exclude` rather than by the `.gitignore` block, which is tracked.
   *(Clarified 2026-09-03.)* The claim is a **closure property, not a list**:
   every path Praxion causes to appear inside the checkout is covered by the
   block, including paths a hook or a command seeds rather than onboarding.
   Which literal entries the block holds is therefore implementation that
   follows from the property — it is regenerated wholesale from one source and
   is expected to grow whenever Praxion learns to write a new path. Stating it
   as a list is what let a hook-seeded example file surface in `git status` on
   an otherwise invisible installation: a missing entry is a violation of this
   clause, not a new decision.
5. **Placement is not freely orthogonal to mode.** Of the eight pairs, five are
   legal: all four `in-repo` pairs, and `sidecar × existing`. `sidecar × new`,
   `sidecar × hackathon` and `sidecar × promote` are refused at the argument
   boundary. Sidecar placement exists to hide Praxion from co-owners of a
   repository the operator does not control; `new` scaffolds a repository the
   operator just created, `hackathon` installs a deliberately throwaway
   footprint, and mode `promote` means hackathon-to-fully-managed, which cannot
   arise from a state that is itself illegal. The representation is a sum type
   whose sidecar variant carries no mode field at all, so the illegal pairs are
   unrepresentable rather than merely validated against.
6. **Capability availability is placement-dependent** in three classes. Most
   capabilities are fully local under sidecar. `quality` and `obsidian` write
   tracked files that are ordinary project hygiene rather than Praxion
   branding, so they are offered but never silently: the operator sees the file
   list and confirms or declines. `ci` is **unavailable** — GitHub workflows,
   a label manifest and two repository secrets are visible by construction and
   have no invisible variant.
7. Movement between placements is mechanical in both directions:
   `praxion-sidecar publish` moves state into the project preserving history
   via `git subtree`; `absorb` is the inverse.

## Considered Options

### A — In-tree but excluded, no external repository

Keep `.ai-state/` exactly where it is and list it in `.git/info/exclude`.

Pros: by far the simplest; no second repository, no identity derivation, no
`git mv` across repository boundaries, no promotion machinery. It still needs
the two containment-guard fixes, so it is not free, but it needs nothing else.

Cons: `git clean -fdx` — a routine command in a team repo — deletes the entire
intelligence tree with no recovery. There is no history: an ADR corrupted by a
bad merge driver is simply gone. There is no backup path even for an operator
who wants one. And worktrees still need a symlink to reach the main checkout's
copy, so the design keeps the guard work and discards the safety it bought.

### B — Orphan branch plus a nested worktree inside the project repository

Pros: one repository; git-native; history preserved.

Cons: the refs leak on `git push --all` and `--mirror`, so the operator's
private state can reach the team remote by an ordinary command. The project's
own hooks fire on state commits. Nested worktrees underneath pipeline worktrees
are confusing to reason about and to clean up.

### C — `~/.claude/projects/<key>/` as the state home

Pros: already exists; already keyed per project; no new location to explain.

Cons: Claude-Code-specific, so the Codex and Cursor export paths cannot see it;
machine-local with no versioning; not a git repository, so no history, no
backup, no promotion.

### D — Bare repository with `core.worktree` pointed at the project (vcsh pattern)

Pros: no symlinks for the main checkout; a known pattern in dotfile management.

Cons: needs the same guard fixes as the chosen option; worktrees still need
symlinks; two git repositories share one working tree, which is materially
harder to reason about than two trees with an explicit link between them.
Dominated by the chosen option on every axis except symlink count.

### E — Sidecar repository projected in by symlink (chosen)

Pros: the project's tracked tree is genuinely untouched; state has history, and
a backup path exists if the operator wants one; one sidecar serves every clone
and worktree of a project; the failure mode of a wrong `git add` is a loud
error rather than a silent leak; promotion in and out is mechanical.

Cons: a second repository the operator must know about; two new components to
maintain. ~~branch-scoped state isolation is lost, taking `reconcile_ai_state.py`
and the `observations.jsonl` merge driver out of play for this mode~~ —
corrected by `dec-draft-0516562a`: the state mount keeps both in play, on the
sidecar side, at the price of a merge-back step.

## Consequences

**Positive.** A team repository can host the full pipeline with an empty
`git status`. The `.ai-state/` path contract is preserved, so the change is
invisible to the agent fleet, the skills, and every reader. `git add` through
the shadow fails closed rather than leaking. The manifest gives four
consumers — CLI, resolver, guards, onboarding — one parsed interpretation of
placement instead of four heuristics. `publish` makes the decision reversible,
which matters because an operator's judgement about whether a team will adopt
Praxion is exactly the kind of judgement that changes.

**Negative.** ~~State is now shared live across worktrees rather than diverging
and reconciling at merge; two concurrent pipelines on one project see each
other's drafts immediately. `reconcile_ai_state.py` and the squash-safety
diagnostic become no-ops in this mode, so a reader must know the mode to know
whether they ran.~~ — **this clause no longer holds; narrowed by
`dec-draft-0516562a`.** The state mount gives each checkout its own sidecar
branch, so state is branch-scoped again, `reconcile_ai_state.py` and the merge
drivers are back in play (on the sidecar side, at merge-back), and each mount
has its own git index. The cost that replaces it is a **merge-back ordering
constraint**: a worktree's sidecar branch must merge before the project branch,
or the post-merge ADR promotion finds no drafts. See that record's
`## Prior Decision` for why this is a trade rather than a free correction — the
mechanism was chosen for the write path, and branch-scoped isolation is a
consequence of it, not a vindication of the trigger recorded below.

There is no automatic backup, and with no remote by default a
lost machine loses the intelligence — an operator responsibility this design
documents rather than solves. Placement multiplies the onboarding test matrix:
every capability now has a placement dimension. And each checkout now carries a
nested git repository, which is one more thing an operator can be surprised by.

**Neutral.** `dec-221`'s two-tier model is not contradicted for its own scope —
disposable bulk still goes out of tree, and machine-specific absolute paths are
still never committed (the manifest lives in the sidecar). What changes is that
the curated tier gains a second legal home.

## Disconfirmation

**Falsifier.** If, after real use, the sidecar's git history is never consulted —
no `git log` on the sidecar, no recovery from it, no cross-machine sync — then
the entire justification for a *repository* rather than a plain excluded
directory has evaporated, and option A was right: same guard fixes, far less
machinery. **This falsifier is now stronger, not weaker** — under
`dec-draft-0516562a` the repository is load-bearing in a second way (it is what
`git worktree` mounts from, and what merge-back merges within), so "the history
is never consulted" would have to coexist with machinery that exists only
because it is a repository.

~~A second, faster falsifier: if two concurrent Standard-tier pipelines
on one sidecar-placed project produce a single lost write in `calibration_log.md`
or a ledger, the shared-live-tree premise is wrong and the design needs
per-worktree state, which is a different architecture rather than a patch.~~ —
**retired: the shared-live-tree premise is gone.** Per-worktree state is what
`dec-draft-0516562a` implements, arrived at from the write path rather than from
this trigger. Its replacement, recorded in that decision: one ADR draft written
inside a pipeline worktree that is not promoted after `/merge-worktree` because
the sidecar merge-back was missed.

**Steelmanned runner-up.** Option A is stronger than its rejection makes it
sound. It requires no identity derivation, no manifest, no cross-repository
`git mv`, no `publish`/`absorb` machinery, and no second repository in the
operator's mental model — perhaps a third of the surface area of the chosen
design, for the same headline outcome of an empty `git status`. Its two named
weaknesses both have cheap partial answers: `git clean -fdx` can be mitigated by
the same SessionStart banner this design already ships, and backup can be
delegated to whatever the operator already backs up their home directory with.
The honest reason to still decline it is that "your entire project intelligence
is one routine command away from deletion, with no history" is a property that
degrades the *value* of accumulating intelligence at all — an operator who does
not trust the store stops investing in it. But that is a judgement about
behaviour under risk, not a measured fact, and it is the weakest joint in this
decision.

**Reversal trigger.** The surviving falsifier firing (the sidecar's history is
never consulted), or `dec-draft-0516562a`'s merge-back falsifier firing — the
latter reverses the *mechanism*, not this decision's placement axis.
Additionally: if Claude Code introduces first-class support for external
per-project state (an official mechanism for machine-local project intelligence
outside the repository), that mechanism should be evaluated as a replacement for
the sidecar rather than carrying both.
