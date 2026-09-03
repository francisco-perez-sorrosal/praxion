---
id: dec-draft-0516562a
title: Sidecar state is materialised as a git worktree mounted inside each checkout, with shadows as intra-checkout relative symlinks
status: proposed
category: architectural
date: 2026-09-02
summary: Claude Code's worktree isolation refuses Write/Edit on any lexically-in-worktree path whose realpath escapes the worktree, with no sanctioned exemption, which would leave .ai-state/ unwritable by every agent in every pipeline worktree. Under sidecar placement each checkout now materialises the sidecar as a real directory at <checkout>/.praxion - a git worktree of the sidecar on a per-checkout branch - and every shadow becomes a relative symlink into it, so all Praxion writes resolve inside the checkout and both containment guards stay unmodified.
tags: [sidecar, state-mount, git-worktree, worktree-isolation, claude-code, containment, branch-scoped-state, merge-back]
made_by: agent
agent_type: systems-architect
branch: worktree-sidecar-placement
pipeline_tier: full
supersedes_in_part:
  - dec-draft-4b33b1df
affected_files:
  - scripts/praxion-sidecar
  - scripts/_state_repo.py
  - scripts/finalize_adrs.py
  - scripts/finalize_chain.sh
  - scripts/reconcile_ai_state.py
  - commands/merge-worktree.md
  - dashboard_app/src/server/artifacts/project-root.ts
  - skills/onboard-project/references/phases-core.md
  - docs/onboarding.md
dissent: "This buys a write path by taking on a git-worktree lifecycle (creation, per-checkout branch naming, prune, dirty-refusal) and a convergence step the previous design did not have - every channel that can observe a merged project branch must merge the sidecar branch too, and a branch nothing observes stays unmerged until someone looks - and it does so on the strength of an undocumented harness behaviour that could be given a sanctioned exemption in any release, at which point the entire mechanism is machinery bought to route around a temporary constraint."
---

## Context

`dec-draft-4b33b1df` establishes sidecar placement: the durable state lives in a
per-operator git repository and is *projected* into the project by symlinks that
`.git/info/exclude` hides. The plan recorded one assumption it could not verify
at design time — that Claude Code's own worktree isolation, which blocks edits
targeting the main checkout, would not also block writes through a symlink into
a third location. The risk row named a fallback: `permissions.additionalDirectories`.

Both were falsified live on 2026-09-02 (Claude Code 2.1.258), in a session
pinned to a linked worktree — the exact regime in which Standard and Full
pipelines run:

| Write-tool target | Result |
|---|---|
| lexically-in-worktree symlink escaping the worktree (git or non-git target) | **refused by the harness**, not by `worktree_guard.py` |
| lexically-in-worktree symlink whose target is inside the worktree | allowed |
| real directory inside the worktree that is a nested git repo | allowed |
| direct absolute path outside the worktree | allowed |
| `permissions.additionalDirectories` naming the escape target | **still refused** — read-scope only |
| Bash write through the escaping symlink | allowed |

The operative rule is **realpath containment of lexically-in-worktree paths**.
It is documented in effect ("Claude Code blocks an Edit, Write, or NotebookEdit
that targets a path in the main checkout") but not in mechanism; there is no
settings key, environment variable or `EnterWorktree` flag that exempts a path;
and it applies to every subagent spawned from an isolated session.

The consequence under the design as written: in every pipeline worktree,
`.ai-state/`, `CLAUDE.local.md`, a shadowed `CLAUDE.md` and
`.claude/settings.local.json` are unwritable by `Write`/`Edit`/`NotebookEdit` —
the primary tools of the implementer, test-engineer, verifier, planner and
architect. Reads succeed. Bash writes succeed. Only the tools agents actually
use fail, mid-step, with a message that misdirects toward a worktree copy that
does not exist.

## Decision

Under sidecar placement, every project checkout — the main checkout **and**
every linked worktree, uniformly — materialises the sidecar as a **state mount**.

1. **The mount.** `<checkout>/.praxion/` is a real directory that is a
   `git worktree` of the sidecar repository, on a per-checkout branch: `main`
   for the project's main checkout, `wt/<worktree-dir-name>` for each linked
   worktree, branched from the base checkout's sidecar branch.

2. **The shadows point inward.** `.ai-state`, `CLAUDE.local.md`, a shadowed
   `CLAUDE.md` and `.claude/settings.local.json` become **relative** symlinks
   into the mount (`.praxion/.ai-state`, `../.praxion/settings.local.json`, …),
   never absolute links into `${PRAXION_SIDECAR_ROOT}`. A link that reaches the
   right file by escaping the checkout is classified as `LinkElsewhere` and
   refused, because it works today and breaks the moment a worktree opens.
   *(Amended 2026-09-03, `ARCH_WT_RULING.md` § 15.)* The harness loads a symlinked `CLAUDE.local.md`/`settings.local.json` but refuses `Write`/`Edit` on the three **file** shadows even when their realpath is inside the checkout, so tool writes to those three must target the mount path directly (`.ai-state`, a directory shadow, is unaffected).

3. **The in-checkout realpath invariant.** For every path Praxion asks an agent
   to write, `realpath(path)` is inside the checkout the session runs in. This
   is the property the whole decision exists to install, and it is structural —
   a consequence of where the mount sits — rather than a hope about harness
   behaviour.

4. **Both containment guards stay unmodified.** `worktree_guard.py`'s existing
   `_is_within(target.resolve(), session_root)` early return is already correct
   under the invariant; `project-root.ts` keeps both its lexical and realpath
   containment checks with no second permitted root and no environment channel.
   The dashboard's only change is one entry (`.praxion/.ai-state`) in its
   `ALLOWED_ARTIFACT_ROOTS` constant, because it re-applies that allowlist to
   the *resolved* relative path.

5. **Uniform, not discriminated.** The main checkout mounts the same way a
   linked worktree does. A `Link | SidecarWorktree` materialisation
   discriminator in the resolver would have one inhabitant per placement and
   would force two code paths through `link`, `doctor`, the resolver and the
   dashboard for no behavioural gain.

6. **The mount name is a code constant (`.praxion`), not a manifest field.**
   The manifest schema and its frozen `{schema, project.id, project.origin}`
   triple are untouched. The manifest's *location* moves to the sidecar's git
   common directory, because a tracked manifest would be materialised inside
   every checkout and its machine-local `roots:` list would conflict across
   branches.

7. **Branch-scoped state returns, and with it a convergence step.**
   *(Revised 2026-09-02, user-approved; `ARCH_WT_RULING.md` § 13.)*
   `praxion-sidecar merge-back` merges a worktree's sidecar branch into the
   current checkout's, running `reconcile_ai_state.py` against the mount and
   using the sidecar's own merge drivers. It is **not an ordering rule.** It is
   a convergence step — safe to run any number of times, and run from every
   channel that can observe a merged project branch: the project `post-merge`
   finalize chain (converge before draft promotion), the SessionStart heal
   (`praxion-sidecar link`), and `/merge-worktree` explicitly (still preferred
   for same-run visibility, no longer load-bearing). A manual `git merge`, a
   GitHub squash merge followed by `git pull`, and a
   `git reset --hard origin/main` therefore all converge without operator
   memory.

   A branch is merged **only on positive evidence** that its recorded project
   branch is merged — an ancestor test, or the squashed-branch patch-id test
   for a squash merge. A deleted project branch, a removed project worktree, a
   missing mapping and an unresolvable ref are **not** evidence: those branches
   stay unmerged, keep their commits, and are reported by `doctor` with the
   explicit fix. A conflict in an **automatic** run is aborted — a mount is
   never left mid-merge — and only the explicit `merge-back --from` may leave
   conflict markers. Unmerged state is never dropped automatically; removing
   the mount and then `merge-back --from <branch> --drop --yes` is the only
   path, and a branch is deleted automatically only when it is an ancestor of
   the base branch.

Every mechanism claim above was verified live with git 2.44.0 before this
decision was taken, not read from documentation: the mount creates inside
another repo's tree; realpaths land inside the checkout in both the main
checkout and a linked worktree; `git status` stays empty and `git add -A` stages
nothing; `git add` through a shadow still fails loudly (`beyond a symbolic
link`); `post-checkout` fires on `git worktree add` with `pwd` = the new
worktree; `info/exclude` reaches linked worktrees via the common dir;
divergence and merge-back both work; `git worktree add` refuses an
already-checked-out branch; `git mv` works with mount realpaths and fails loudly
with shadow paths; and the sidecar common dir is derivable from the mount's
`.git` pointer file with stdlib alone.

## Considered Options

### A — Only `.ai-state` becomes a sidecar git worktree; other shadows stay symlinks

Pros: pays the worktree cost only where the harness forces it; the main checkout
keeps the simpler "symlink to my sidecar" mental model, and one directory
acquires a nested repo instead of every checkout.

Cons: the harness rule is about realpath, not about `.ai-state` specifically, so
`CLAUDE.local.md`, a shadowed `CLAUDE.md` and `.claude/settings.local.json`
remain unwritable inside worktrees. A `git worktree` materialises a *tree* and
cannot place three individual files at their project-relative locations, so this
option cannot be extended to cover them. It also forces a materialisation
discriminator into the resolver and two code paths through `link`. The chosen
option is this one generalised, and is *smaller*.

### B — Keep the symlink; agents write `.ai-state` via Bash inside worktrees

Pros: zero new machinery; Bash writes through the escaping symlink are confirmed
to work; the constraint could ride in the project's `CLAUDE.local.md`.

Cons: the failure is a refused agent mid-step, recovered non-deterministically,
and the harness's own message misdirects. Reads succeed while writes fail — the
worst partial breakage. And it makes a correctness property depend on a model
following an instruction, which is the "unenforced invariant is documentation,
not design" failure this plan refuses everywhere else. Retained only as an
emergency escape.

### C — Rely on `worktree.symlinkDirectories` being exempt from the realpath check

Pros: if exempt, zero-cost and Claude-Code-native; `EnterWorktree` does create
the worktrees Praxion pipelines use, so the setting is in scope.

Cons: the exemption is unverified and undocumented; the setting covers only
Claude-created worktrees, not `git worktree add`; its direction is
main→worktree, so the link chains into the main checkout's own escaping symlink
and the realpath still escapes; and it covers directories only, leaving the
three file shadows broken. Building the central write path on an undocumented
behaviour is a wager, not a trade-off.

### D — Under sidecar placement, pipelines run in the main checkout (no linked worktrees)

Pros: deletes more of the design than any other option — no mount, no branch
model, no merge-back, no ordering constraint, no new `doctor` checks. And the
Pipeline Isolation rule's *stated* rationale (collision between concurrent
pipelines) is genuinely weak for a single operator working one task at a time,
who gets branch isolation from `git checkout -b`.

Cons: unenforceable. `EnterWorktree` is a harness tool and `/create-worktree` is
a habit; the moment a worktree exists anyway, the failure is B's mid-step
refusal arriving unannounced. A rule Praxion cannot enforce is advice, and
advice does not close a correctness gap. It also gives up the unstated second
benefit of worktrees — code changes on their own branch, main checkout
undisturbed — which matters more on a repository the operator does not own.

### E — Per-worktree real-directory copy, synced to the sidecar on Stop/finalize

Pros: no worktree lifecycle, no branch model, no ordering constraint; realpath
containment holds; a copy is the least surprising thing on disk.

Cons: it is the chosen option with git's merge machinery replaced by a
hand-rolled sync. Divergence resolves by last-writer-wins or an rsync heuristic;
a concurrent pipeline silently clobbers a ledger row. The chosen option gets
three-way merge, the existing `.gitattributes` drivers, conflict *detection* and
history for the same lifecycle cost. Strictly dominated.

### F — State mount: sidecar worktree per checkout, shadows pointing inward (chosen)

Pros: fixes the entire class (all four shadows, main checkout and worktrees)
with one mechanism; deletes two planned code changes rather than adding them
(`worktree_guard.py` and `praxion-dashboard` leave the design entirely, and the
dashboard's change shrinks to one constant); makes the write-path property
structural rather than assumed; restores branch-scoped state and puts
`reconcile_ai_state.py` and the merge drivers back in play; shrinks the DS-9
index race by construction, since each mount has its own index.

Cons: a git-worktree lifecycle to own (create, branch-name, prune, refuse-dirty);
a merge-back step with a hard ordering constraint; a nested git repository inside
every checkout; a `git clean -ffdx` can now lose *uncommitted* mount state
(plain `-fdx` cannot — git skips nested repos); and the sidecar's seeded skeleton
must carry a real file in every directory, because a worktree materialises only
tracked content.

## Consequences

**Positive.** The write path is correct by construction rather than by
assumption, and the property is checkable in one sentence. Two security-relevant
files — a PreToolUse hook on every write, and an HTTP-facing path guard — keep
their current logic and gain no new dependency, which is a strictly better
security outcome than the allowlist this replaces. `git status` invisibility,
the loud `git add` failure, and the `.ai-state/` path contract all survive
unchanged. Branch-scoped state returns: two pipelines no longer see each other's
drafts, the sidecar's merge drivers become load-bearing instead of vestigial,
and the per-mount index deletes the cross-pipeline half of the commit race.

**Negative.** A lifecycle to own and a convergence step to run, both described
above. Every checkout carries a nested git repository, which is one more thing an
operator can be surprised by. `reconcile_ai_state.py` returns from "no-op under
sidecar" to "runs at merge-back", so a reader must now know *where* it runs
rather than *whether*. And the design now depends on git worktree semantics in a
place it previously depended only on symlinks — a smaller surface than the
harness, but not zero. The mount also does not fully close the write-path gap it was built for: the three file shadows still refuse a direct `Write`/`Edit`, and an agent must target the mount path for those three, even though the directory shadow (`.ai-state`) writes through cleanly.

**Neutral.** `dec-draft-4b33b1df`'s placement axis, mode pairing, capability
classes and `publish`/`absorb` machinery are untouched; only its projection
*mechanism* and its shared-live-tree consequences are narrowed. The consult
dispositions (CH-01…CH-07) are all preserved: `SidecarIdentity`/`ManifestView`,
the `roots:`-membership identity check, the excludes-disjointness constructor,
the commit lock, the schema-first stdlib reader, the split slot types and the
`PathEntry` sum all survive, three of them narrowed and none re-opened.

## Prior Decision

`dec-draft-4b33b1df` is narrowed in two clauses, not replaced.

- **Clause 2 (projection mechanism)** said state is "projected into the project
  by symlink". It is now projected by a git worktree mounted at
  `<checkout>/.praxion`, with symlinks pointing *inward* to it. The placement
  axis, the `.ai-state/` path contract, the `.git/info/exclude` invisibility
  mechanism and the `publish`/`absorb` reversibility are unchanged.
- **Its Consequences** recorded "state is now shared live across worktrees …
  `reconcile_ai_state.py` and the squash-safety diagnostic become no-ops in this
  mode" as an accepted cost with a reversal trigger. That premise no longer
  holds; state is branch-scoped again and both reconcilers have work to do on
  the sidecar side.

The honest framing, recorded so a later reader is not misled: **this is not the
reversal trigger firing.** No lost write was observed. The mechanism was chosen
for the write path, and branch-scoped isolation is a *consequence* of it — a
welcome one that the test lens argued for and did not win on the merits. It
arrives with a cost the shared-live-tree design did not have (the merge-back
ordering constraint), so it is a trade, not a free correction.

`dec-draft-a3f65ba3` — "both containment guards accept a second,
explicitly-declared state root" — is **retired** by this decision rather than
superseded, because its question is gone rather than answered differently: with
the in-checkout realpath invariant there is no containment escape to admit. Its
own record carries the re-open condition.

## Disconfirmation

**Falsifier — retired and replaced 2026-09-02 (`ARCH_WT_RULING.md` § 13).** The
original read: *one ADR draft written inside a pipeline worktree that is not
promoted after `/merge-worktree`, where the cause is a missing sidecar
merge-back.* Its subject was the **ordering rule** — an operator or a command
having to run merge-back first. Decision item 7 no longer contains that rule, so
"the operator forgot" is not a reachable cause; a falsifier whose mechanism has
been deleted is not evidence about the design that replaced it, and restating it
would be dishonest bookkeeping.

**The falsifier that replaces it** is narrower and harder to satisfy: one draft
written in a worktree whose project branch is merged **by any path**, which is
not promoted by the next post-merge finalize *or* the next session start — that
is, a channel that *observes* the merge and does not converge. It is a coverage
claim about the three channels, not a claim about memory. Deliberately excluded:
a merge **no** channel observes (merged on another machine, never pulled, never
opened in a session) leaves the branch unmerged and reported, which is the
chosen behaviour, not a failure — acting on absent evidence is the worse error.

**A second falsifier the convergence step introduces**, recorded because it is
new risk rather than inherited: an eligibility **false positive** — a branch
merged into the sidecar's base branch while its project work was in fact not
merged — which would mean the squashed-branch patch-id detector is unsound for
some merge shape. The retreat is pre-decided and cheap: drop that test, fall
back to ancestor-only evidence plus the explicit verb, and pay one manual
command per squash-merged branch. The mount, the channels and the state machine
all survive it unchanged.

A third, cheaper falsifier: a future Claude
Code release documenting a sanctioned exemption (a settings key, an
`EnterWorktree` flag, or a confirmed `worktree.symlinkDirectories` carve-out),
which removes the *forcing* argument. That would not automatically make this
wrong — branch-scoped state and the merge drivers have independent value — but
the design would then have to be re-argued on the remaining merits rather than
inherited.

**Steelmanned runner-up.** Option D is stronger than its rejection sounds. It
deletes the mount, the branch model, the merge-back, the ordering constraint and
three `doctor` checks — a large fraction of P1's remaining surface — and its
premise is not merely "avoid the harness": a single operator running one pipeline
at a time gets branch isolation from an ordinary `git checkout -b` and pays
nothing for worktree machinery they never use concurrently. The Pipeline
Isolation rule's stated rationale really is weak for this population. The only
reason to decline it is enforceability: Praxion cannot prevent `EnterWorktree`,
so D's failure mode is option B's mid-step refusal arriving with no warning. If
the convergence-coverage falsifier fires, D is the retreat — and it should be
taken as a deliberate, documented posture with a placement-scoped exception to
the Pipeline Isolation rule, not as a patch.

**Reversal trigger.** Any of: the convergence-coverage falsifier firing once (a
channel that observed a merge and did not converge); an eligibility false
positive; a documented harness exemption appearing; or the mount acquiring a
*third* materialisation shape — at two shapes this is a mount, at three it is a policy and belongs behind
one abstraction with its own tests.
