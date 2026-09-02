---
id: dec-draft-bdbeea95
title: A single resolver answers which git repository owns .ai-state/, returning a four-variant sum type; state-mutating callers fail closed
status: proposed
category: architectural
date: 2026-09-02
summary: scripts/_state_repo.py is the sole answer to "which repo owns .ai-state/", returning InRepo | SidecarOwned | Dangling | Foreign with fully-resolved paths, never a bare path or an Optional. Two entry points split the contract - resolve_placement for readers, require_writable_placement for writers, which raises on the two error variants so a broken or third-party link can never be written into.
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
  - hooks/worktree_guard.py
  - scripts/praxion-dashboard
dissent: "Seven consumers now import a module that runs git subprocesses and reads a YAML manifest on paths as hot as a PreToolUse guard and a per-commit hook; the previous design had no such shared dependency, and a resolver that is slow, or that raises where a caller expected a path, becomes a single point of failure for machinery that was previously independent and individually fail-open."
---

## Context

Under sidecar placement `.ai-state/` is a symlink into a different git
repository. Several existing consumers must therefore stop assuming that the
repository containing the project also owns the state:

- `finalize_adrs.py` runs `git mv` and `git add` on ADR paths — both refuse a
  path beyond a symlink, so they need the *state* repository and realpaths.
- `reconcile_ai_state.py` reconciles branch-scoped divergence that does not
  exist when every checkout shares one physical tree.
- `reconcile_aac_surfaces.py` stages surfaces that may live beyond a shadow.
- `finalize_chain.sh` composes all of the above.
- `worktree_guard.py` blocks writes into any git tree other than the session
  worktree — which, verified against the code, is exactly what a write into the
  sidecar looks like.
- The dashboard's path guard resolves symlinks and requires containment.
- `refresh_claude_blocks.py` writes to a `CLAUDE.md` whose location is now
  placement-dependent.

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

1. **The result is a four-variant sum type**, not a path and not an optional:

   - `InRepo` — carries `project_root`, `state_dir`, and `state_git_root`
     equal to `project_root`.
   - `SidecarOwned` — carries `project_root`, `state_dir`, `state_git_root`,
     `sidecar_root`, and a `SidecarIdentity {schema, id, origin}` — **not** a
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
     (`MinimalView`), not an under-populated bag. Verified against the consumer
     set: the four stagers, both guards and the dashboard need only
     `{schema, id, origin, sidecar_root}`; only `praxion-sidecar` and
     `sidecar_autocommit.py` (already full-YAML contexts) read the wider fields.
   - `Dangling` — the shadow is a symlink whose target does not exist; carries
     the link path and its target.
   - `Foreign` — the target exists but is not this project's sidecar; carries
     the resolved target and a `reason` from the closed set `no-manifest`,
     `manifest-unreadable`, `schema-too-new`, `identity-mismatch`,
     `not-a-git-repo`.

2. **All paths are fully resolved by the resolver**, once. Consumers compare
   resolver-supplied paths with each other and never call `resolve()`
   themselves. This is what makes the realpath-normalisation problem a
   single-site concern.

3. **Two entry points split the contract by caller obligation.**
   `resolve_placement()` returns the sum type and is for readers, which may
   degrade. `require_writable_placement()` returns only `InRepo | SidecarOwned`
   and raises on the two error variants; every state-mutating script uses it,
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

### C — Four-variant sum type with a reader/writer entry-point split (chosen)

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

**Negative.** A shared dependency on hot paths. `worktree_guard.py` is a
PreToolUse hook on every `Write`/`Edit`, so the resolver must fast-exit before
any subprocess when `.ai-state` is not a symlink — a performance obligation the
guard did not previously have. `require_writable_placement()` raising means
callers that previously could not fail now can, and each needs its refusal
message wired to the resolver's `reason`. The `Foreign(identity-mismatch)`
variant will fire on legitimate operator actions (renaming a GitHub
organisation) and the escape hatch must be discoverable or it reads as breakage.

## Disconfirmation

**Falsifier.** If, across the consumer set, `Dangling` and `Foreign` are handled
identically at every site — every caller collapsing them to "refuse, print the
message" — then the two variants bought a distinction nobody uses and should
merge into one `Unusable { reason }`. Equally: if profiling shows the resolver's
fast-exit path measurably slowing `worktree_guard.py` on a normal in-repo
project, the shared-module design is paying a cost the in-repo majority should
not bear, and the guard needs its own cheaper predicate.

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
