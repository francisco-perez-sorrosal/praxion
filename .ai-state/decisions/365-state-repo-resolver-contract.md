---
id: dec-365
title: A single resolver answers which git repository owns .ai-state/, returning a five-variant sum type; state-mutating callers fail closed
status: accepted
category: architectural
date: 2026-09-02
summary: 'scripts/_state_repo.py is the sole answer to "which repo owns .ai-state/", returning InRepo | SidecarOwned | NotYetLinked | Dangling | Foreign with fully-resolved paths, never a bare path or an Optional. Two entry points split the contract - resolve_placement for readers, require_writable_placement for writers, which raises on the three unwritable variants so a broken or third-party link can never be written into. Revised by dec-366: SidecarOwned now carries the in-checkout state mount as its state_git_root plus the sidecar common dir and branch, discovery is stdlib and subprocess-free via the mount''s .git pointer file, and the consumer set drops the two containment guards and the dashboard entirely. Extended in draft with a fifth variant, NotYetLinked: a linked worktree carries no shadow until link runs, so an absent .ai-state in a worktree of a sidecar-owned project is its own named state rather than InRepo.'
tags: [resolver, sum-type, state-ownership, sidecar, fail-closed, data-structure-design, scripts]
made_by: agent
agent_type: systems-architect
branch: worktree-sidecar-placement
pipeline_tier: full
affected_files:
  - scripts/_state_repo.py
  - scripts/finalize_adrs.py
  - scripts/reconcile_ai_state.py
  - scripts/reconcile_aac_surfaces.py
  - scripts/finalize_chain.sh
  - scripts/refresh_claude_blocks.py
  - scripts/praxion-sidecar
dissent: "Six consumers now import a module that reads a manifest on paths as hot as a per-commit hook; the previous design had no such shared dependency, and a resolver that is slow, or that raises where a caller expected a path, becomes a single point of failure for machinery that was previously independent and individually fail-open. The state mount removed the hottest consumer (a PreToolUse guard on every write) from that set, which weakens but does not retire the objection."
---

> **Revised in place 2026-09-02** (still a draft) after `dec-366`
> changed how sidecar state is materialised. The decision's substance is
> unchanged — one resolver, a closed sum type, fully-resolved paths, a
> reader/writer entry-point split, identity compared and never re-derived.
> *(Corrected 2026-09-03: this note and the option heading below both still said
> "four-variant" after `NotYetLinked` was added; the type has **five** variants,
> as the title, the summary and the Decision have said throughout.)*
> Three things moved: `state_git_root` is the in-checkout **state mount** rather
> than the sidecar root; discovery is stdlib and subprocess-free via the mount's
> `.git` pointer file; and the consumer set lost `worktree_guard.py`,
> `project-root.ts` and `praxion-dashboard`, which need no resolver at all now
> that every Praxion path resolves inside the checkout.

## Context

Under sidecar placement `.ai-state/` is a symlink into the state mount, which is
a `git worktree` of a different git repository. Several existing consumers must
therefore stop assuming that the repository containing the project also owns the
state:

- `finalize_adrs.py` runs `git mv` and `git add` on ADR paths — both refuse a
  path beyond a symlink, so they need the *state* repository and realpaths.
- `reconcile_ai_state.py` reconciles branch-scoped divergence that does not
  exist when every checkout shares one physical tree.
- `reconcile_aac_surfaces.py` stages surfaces that may live beyond a shadow.
- `finalize_chain.sh` composes all of the above.
- `refresh_claude_blocks.py` writes to a `CLAUDE.md` whose location is now
  placement-dependent.

Two consumers named in the original draft — `worktree_guard.py` and the
dashboard's `project-root.ts` (with `praxion-dashboard` as its launcher) —
**left this set** with `dec-366`. Both broke only because a write or
read had to follow a symlink *escaping* the checkout; under the state mount the
resolved path lands inside the project root, so both keep their existing logic
and neither imports this module. That is a strictly better outcome than the
allowlist they were going to receive: two security-relevant files gain no new
dependency at all.

The naive shape is `state_repo_root() -> Path`, with each consumer branching on
`!= project_root`. That is the failure this decision exists to prevent. A bare
path cannot distinguish *in-repo* from *sidecar-owned* from *the link is
dangling* from *the link points at something that is not this project's
sidecar*. Seven consumers would each re-derive the distinction, and each would
have to get macOS realpath normalisation right independently — the class of bug
where `/Users/...` and `/System/Volumes/Data/Users/...` compare unequal and a
guard blocks a write it should allow.

There is a second reason the error cases must be in the type. A `.ai-state`
symlink pointing at *some other* directory — an operator's manual experiment,
another project's sidecar — is indistinguishable from a legitimate one by path
shape alone. Only comparing the target manifest's recorded identity against the
project — its recorded `origin` for a remote project, or the project root's
membership in the manifest's `roots:` list for a remote-less one — separates
them, and only the resolver is positioned to do that.

## Decision

`scripts/_state_repo.py` is the single answer, imported as a sibling module
exactly like `_repo_root.py` (`scripts/` is on `sys.path[0]` for all of them).

1. **The result is a five-variant sum type**, not a path and not an optional:

   - `InRepo` — carries `project_root`, `state_dir`, and `state_git_root`
     equal to `project_root`.
   - `SidecarOwned` — carries `project_root`, `state_dir`, `mount_dir`
     (`<project_root>/.praxion-state`, the state mount), `state_git_root` **equal to
     `mount_dir`** (every `git -C` for state runs inside the checkout),
     `sidecar_common_dir` (`<sidecar>/.git`, which identifies the sidecar across
     all its worktrees), `branch` (this checkout's sidecar branch), and a
     `SidecarIdentity {schema, id, origin}` — **not** a
     full parsed manifest. The resolver constructs this variant on every hook
     and finalize path, where it may lack PyYAML and can read only the three
     identity fields; a `manifest` field would hold a partial object whose
     absent `paths`/`autocommit`/`remote` keys are indistinguishable from
     legitimately-absent ones (the correlated-nullable smell this design
     eliminates elsewhere). Manifest content beyond identity is reached through
     a separate `ManifestView` sum (`MinimalView { identity } | FullView
     { identity, paths, excludes, autocommit, remote }`) that a consumer widens
     deliberately by calling the full reader — so "I only have the three
     identity fields here" is a representable, checkable state
     (`MinimalView`), not an under-populated bag. *(Amended 2026-09-03.)* The
     `ManifestView` sum was deliberately **not built**: the shipped identity
     object only ever carries the three fields, so the sum would ship with one
     inhabited variant and nothing to dispatch on. What survives is the split
     reader — identity on the hot path, wider content through a separate call —
     held as a **convention** rather than as a property of the type. Trigger to
     build it: any consumer that must branch on whether it holds full manifest
     content. Verified against the consumer set: the four stagers need only
     `{schema, id, origin, mount_dir, sidecar_common_dir}`; only
     `praxion-sidecar` and `sidecar_autocommit.py` (already full-YAML contexts)
     read the wider fields.
   - `NotYetLinked` — `.ai-state` is absent entirely and this checkout is a
     **linked worktree** of a project whose main checkout is `SidecarOwned`;
     carries `project_root`, `main_checkout_root`, `sidecar_common_dir` and the
     `SidecarIdentity`, and no `state_git_root` (there is nothing here to write
     to yet).
   - `Dangling` — the shadow is a symlink whose target does not exist (typically
     an unmaterialised mount); carries the link path and its target.
   - `Foreign` — the target exists but is not this project's sidecar; carries
     the resolved target and a `reason` from the closed set `no-manifest`,
     `manifest-unreadable`, `schema-too-new`, `identity-mismatch`,
     `not-a-git-repo`, `unrecognized-mount`.

   The fifth variant exists because `git worktree add` copies no `.ai-state` —
   the shadow is excluded from the project repository and never tracked — so a
   worktree seconds old has *no* shadow, which by shape alone is
   indistinguishable from an unmanaged project. Answering `InRepo` there
   silently retires the two channels that exist to materialise it (the
   post-checkout `link` and the SessionStart heal, both gated on placement),
   and the knowledge that rescued it lived in one consumer as an ad-hoc
   main-worktree fallback rather than in the type. "Which repo owns
   `.ai-state`?" therefore has a fifth honest answer — *this project's sidecar,
   but not materialised in this checkout yet* — and it is a state, not a
   boolean on `InRepo`: it carries the sidecar it will be linked into, which no
   flag could. It is not writable (`require_writable_placement()` refuses it,
   naming `praxion-sidecar link`), and it is a transition rather than a resting
   place: the same checkout resolves `SidecarOwned` the moment `link` runs.

2. **All paths are fully resolved by the resolver**, once. Consumers compare
   resolver-supplied paths with each other and never call `resolve()`
   themselves. This is what makes the realpath-normalisation problem a
   single-site concern.

2a. **Discovery is stdlib and subprocess-free on the hot path.** Read the
   `.ai-state` symlink → derive `<checkout>/.praxion-state` → read its `.git`
   **pointer file** (`gitdir: <sidecar>/.git/worktrees/<name>`) → strip the
   trailing `worktrees/<name>` segment → `sidecar_common_dir` → read the
   manifest beside it. Two file reads, no `git` invocation. An unrecognised
   pointer shape returns `Foreign(unrecognized-mount)` rather than guessing;
   `git rev-parse --git-common-dir` exists only as a fallback and is never the
   primary. Verified live against git 2.44.0.

2b. **`SidecarOwned` asserts the in-checkout realpath invariant.** `mount_dir`
   is inside `project_root`; `sidecar_common_dir` is outside it. A mount that
   fails either containment is `Foreign(unrecognized-mount)`, never a
   `SidecarOwned` carrying a surprising path. This is the constructor-level
   statement of the property that keeps Claude Code's worktree isolation, the
   worktree guard, and the dashboard's containment checks all satisfied.

3. **Two entry points split the contract by caller obligation.**
   `resolve_placement()` returns the sum type and is for readers, which may
   degrade. `require_writable_placement()` returns only `InRepo | SidecarOwned`
   and raises on the other three; every state-mutating script uses it,
   so a mutating caller cannot silently take the permissive path. The
   distinction is in the API rather than in a convention each caller remembers.

4. **Invariants are constructor-enforced.** `InRepo.state_git_root ==
   project_root` and `SidecarOwned.state_git_root != project_root` hold by
   construction; the variants are frozen dataclasses built only inside
   `resolve_placement()`.

5. **The resolver does not depend on PyYAML, and its degraded reader carries
   the evolution contract.** It runs inside `finalize_adrs.py` and hooks in
   consumer projects whose interpreter may lack PyYAML — the pyenv-shim failure
   `finalize_chain.sh` already documents. It reads only the frozen triple
   `{schema, project.id, project.origin}` with a stdlib line parser. Because
   this stdlib reader is the one that *gates state-mutating callers*, the
   forward-compatibility guarantee is its responsibility, not just the full
   parser's: it **parses `schema` first and hard-refuses `schema != 1`**
   (returning `Foreign(schema-too-new)`) before trusting any other line, so a
   future schema-2 layout that relocated `project.id` cannot make the old
   positional parser read a stale line and yield a confident wrong identity —
   a successful-but-wrong parse that "any parse difficulty ⇒ foreign" would not
   catch. `{schema, project.id, project.origin}` are a **frozen, top-level,
   never-relocated compatibility triple** any future `schema` bump must
   preserve in place. `praxion-sidecar` remains the full-fidelity reader and
   sole writer; tests assert the two readers agree on the triple across
   fixtures **and** that the stdlib reader refuses a hand-written schema-2
   fixture that renests `project`.

6. **Identity is compared, never re-derived — and the comparison is defined for
   both identity kinds.** Derivation lives in `praxion-sidecar` and runs once
   at `init`. For an `OriginDerived` project the resolver compares the observed
   `remote.origin.url` against the recorded `project.origin`. For a remote-less
   `PathDerived` project, `origin` is `null` on both sides, so origin comparison
   gives **zero** protection — the resolver instead checks whether the observed
   `.ai-state` realpath's owning-project root is a **member of the manifest's
   `roots:` list**; a non-member link belongs to another project and resolves as
   `Foreign(identity-mismatch)`. This promotes `roots:` from informational to
   load-bearing for the remote-less population, and the resolver **compares a
   realpath against a recorded list** rather than re-deriving the `PathDerived`
   hash — so the single-derivation-owner invariant is preserved
   (`praxion-sidecar` appends to `roots:` on each new checkout at `init`/`link`).
   A silent re-key never happens in either case; `praxion-sidecar link --rekey`
   is the explicit escape.

## Considered Options

### A — `state_repo_root() -> Path`, consumers compare against the project root

Pros: smallest possible surface; no new type; each consumer keeps its existing
control flow.

Cons: cannot express `Dangling` or `Foreign` at all, so both degrade into "some
path", and the mutating consumers write into whatever it happens to be. Seven
independent realpath comparisons. The identity check has nowhere to live.

### B — `Optional[Path]`, `None` meaning in-repo

Pros: marginally more informative than A; a familiar Python idiom.

Cons: `None` conflates "in-repo" with "could not determine", which are opposite
instructions for a writer. The error cases still carry no data, so a diagnostic
cannot say *why* the link is unusable — which is most of what an operator needs.

### C — Five-variant sum type with a reader/writer entry-point split (chosen)

Pros: every legal and illegal state is named and carries its evidence; the
writer/reader obligation is in the API rather than in a convention; realpath
normalisation happens once; the identity check has an obvious home; consumers
get exhaustive handling and a linter can see a missed variant.

Cons: seven consumers gain a shared dependency they did not have; the module
runs git subprocesses on hot paths including a PreToolUse guard; a raising
`require_writable_placement()` introduces an exception into scripts that
previously had none.

### D — Put the answer in the manifest and have each consumer read it directly

Pros: no shared module; no import coupling.

Cons: seven parsers of one file, which is the same divergence problem one level
down, and the consumers on the hot path cannot afford a YAML dependency.

## Consequences

**Positive.** Placement becomes a question with one answer. The two error
variants turn a class of silent-wrong-repository writes into loud refusals with
a stated reason. Adding a future consumer is an import plus a `match`, not a
re-derivation. `InRepo` keeps every existing code path byte-identical, so the
resolver is additive for the ~all projects that never adopt sidecar placement.

**Negative.** A shared dependency on paths that run per commit and per session.
The sharpest version of this objection has been **removed by
`dec-366`**: `worktree_guard.py`, a PreToolUse hook on every
`Write`/`Edit`, is no longer a consumer, so the resolver no longer owes a
per-write fast-exit budget. What remains is the finalize chain and the
SessionStart hooks, where the stdlib two-read discovery above is cheap enough
that the obligation is met by construction rather than by care.
`require_writable_placement()` raising means
callers that previously could not fail now can, and each needs its refusal
message wired to the resolver's `reason`. The `Foreign(identity-mismatch)`
variant will fire on legitimate operator actions (renaming a GitHub
organisation) and the escape hatch must be discoverable or it reads as breakage.

## Disconfirmation

**Falsifier.** If, across the consumer set, `Dangling` and `Foreign` are handled
identically at every site — every caller collapsing them to "refuse, print the
message" — then the two variants bought a distinction nobody uses and should
merge into one `Unusable { reason }`. Under the state mount `Dangling` acquires
a *second*, more common cause (an unmaterialised mount awaiting the SessionStart
heal) that is genuinely recoverable rather than an error, which makes the
distinction more likely to earn its keep — so if it *still* collapses at every
site, the falsifier has fired hard.

The original second clause of this falsifier — profiling showing the resolver
slowing `worktree_guard.py` — is **retired**: the guard is no longer a consumer.
Its replacement: if the two-read stdlib discovery ever needs a `git` subprocess
on the finalize path to be correct, the "no subprocess on the hot path" property
was aspirational rather than structural, and the manifest-location decision
(sidecar git common dir) should be revisited.

**Steelmanned runner-up.** Option A is defensible on the grounds that the
consumers are not symmetric: only `finalize_adrs.py` genuinely needs the state
repository, only the two guards genuinely need containment, and only
`reconcile_ai_state.py` needs the mode. Four consumers needing four different
facts is arguably four small local questions rather than one shared abstraction,
and a shared module is how a codebase acquires a hub that every change must
route through. The counter is narrower than it looks: the realpath
normalisation and the identity check are *the same* work for all of them, and
duplicating those two specifically is where the bugs live. If the resolver's
surface grows beyond those two facts plus the variant tag, option A's objection
becomes correct and the module should be split.

**Reversal trigger.** The resolver acquiring a third responsibility beyond
"which repository owns this, and is the link trustworthy" — for example if it
starts serving manifest content to consumers rather than just the identity
fields — is the signal that it has become a hub and should be decomposed.
