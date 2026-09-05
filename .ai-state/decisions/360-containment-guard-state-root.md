---
id: dec-360
title: Both containment guards accept a second, explicitly-declared state root, while keeping their original checks intact
status: retired
category: implementation
date: 2026-09-02
retired_by:
  - dec-366
summary: RETIRED before implementation. This decision admitted one declared containment escape into worktree_guard.py and the dashboard's project-root.ts so that a sidecar reached by an escaping symlink could be written and read. dec-366 materialises sidecar state as a git worktree inside each checkout instead, so every Praxion path resolves inside the project root and there is no escape left to admit - the question this record answered no longer exists. Both guards keep their current logic unchanged.
tags: [security, path-traversal, containment, worktree-guard, dashboard, sidecar, allowlist, retired]
made_by: agent
agent_type: systems-architect
branch: worktree-sidecar-placement
pipeline_tier: full
affected_files:
  - hooks/worktree_guard.py
  - dashboard_app/src/server/artifacts/project-root.ts
  - scripts/praxion-dashboard
  - scripts/_state_repo.py
---

> **RETIRED 2026-09-02 by `dec-366`, before implementation.** The
> body below is preserved as written; read it as the reasoning that *was*
> correct for a design where sidecar state was reached by a symlink escaping the
> checkout. It is not. See `## Prior Decision` at the end for what changed, what
> survives, and the condition under which this record re-opens.

## Context

Research identified exactly two code paths that break when `.ai-state/` becomes
a symlink into another repository, and both break for the same reason: they
resolve symlinks and then require containment.

- `hooks/worktree_guard.py` (PreToolUse on `Write`/`Edit`/`NotebookEdit`)
  resolves the target, finds its git toplevel, and blocks when that differs from
  the session worktree. A write into the sidecar is precisely that shape. This
  fires only inside linked worktrees — which is where Standard and Full pipelines
  run, so it fires exactly where the capability is most wanted.
- `dashboard_app/src/server/artifacts/project-root.ts` calls `fs.realpath` on
  both the project root and the target and requires the resolved target to stay
  inside the resolved root. This fires unconditionally: every dashboard read of
  an ADR, ledger, metrics report or sentinel report would fail.

Both are correct as written. Neither is a bug. They implement the security
property that a symlink escaping the project is exactly what an attacker would
construct, and the sidecar design constructs it deliberately. The question is
how to admit one specific escape without admitting the class.

## Decision

Both guards gain **one additional permitted root**, obtained from an explicit
declaration rather than inferred from the request or the filesystem.

1. **`worktree_guard.py`** — after computing the target's git root, if that root
   equals the resolved state repository for this project, allow. Every other
   foreign git tree — the main checkout, a sibling worktree — still blocks. The
   hazard the guard was built for (an agent resolving a bare relative path to
   the main repo and corrupting the main branch's tree) is untouched, because
   the main checkout is not the state repository.

2. **`project-root.ts`** — the **lexical** containment check against the project
   root stays mandatory and unchanged, so `../../etc/passwd` is still rejected
   before any filesystem call. Only the **realpath** containment check gains a
   second permitted root: a resolved target must land inside the resolved
   project root *or* inside the resolved state root. The allowed-artifact-root
   check applies to both.

3. **The second root comes from the environment, never from a request.**
   `scripts/praxion-dashboard` resolves placement at launch and exports
   `PRAXION_STATE_ROOT`; the server layer reads it once. There is no request
   parameter, no header and no query string that can influence which roots are
   permitted.

4. **The root is resolved once, by the resolver.** Both guards compare
   resolver-supplied resolved paths rather than calling `resolve()` themselves.
   This is not tidiness: on macOS `/Users/...` and
   `/System/Volumes/Data/Users/...` are the same directory reached by different
   paths, and two independent normalisations are how a guard ends up blocking a
   write it should allow, or worse.

5. **Absent declaration, behaviour is byte-identical to today.** With no
   sidecar, `worktree_guard.py` sees a non-symlinked `.ai-state` and fast-exits
   before any additional work; the dashboard sees no `PRAXION_STATE_ROOT` and
   evaluates exactly one root.

## Considered Options

### A — Disable the guards when a sidecar is present

Pros: trivial; no per-path reasoning.

Cons: removes the cross-worktree protection entirely in exactly the regime where
pipelines run in parallel and the original incident occurred. Trades a specific
allowance for a blanket one.

### B — Allowlist one explicitly-declared root in each guard (chosen)

Pros: the allowance is enumerable, declared out of band, and inspectable; every
other escape still fails; the dashboard's lexical pre-check — the part that
actually stops traversal attacks — is untouched; the no-sidecar path is
unchanged.

Cons: both guards now have a second source of truth for "what is permitted", and
a misconfigured `PRAXION_STATE_ROOT` widens the dashboard's read surface to
whatever it names. Two files with security-relevant logic now depend on the
resolver.

### C — Have the dashboard read through a copy rather than the symlink

Pros: no guard change at all.

Cons: a copy is stale by construction, and the dashboard's value is showing live
pipeline state. It also needs a synchronisation mechanism that does not exist,
to avoid a change that is a few lines.

## Consequences

**Positive.** Both guards keep doing their jobs for every case except one named,
declared exception. The dashboard renders sidecar-placed projects with its
traversal protection intact. The environment-variable channel means the
permitted roots are fixed at process start and cannot be influenced by anything
a request carries. Projects without a sidecar are unaffected in behaviour and in
cost.

**Negative.** Two security-relevant files gain a dependency on the resolver, so
a resolver bug now has a security-adjacent blast radius it did not have before.
`PRAXION_STATE_ROOT` is a new lever: whoever can set the dashboard's environment
can widen its read surface, which is a smaller concern than it sounds (they can
already set `PRAXION_PROJECT_ROOT`) but is a second lever rather than one.
`worktree_guard.py` is a PreToolUse hook on every write, so its fast-exit path
must stay genuinely fast or every edit in every project pays for a feature most
projects do not use.

## Disconfirmation

**Falsifier.** If a path is found that satisfies lexical containment in the
project root *and* realpath containment in the state root while being neither —
some combination of nested symlinks and a state root positioned inside the
project tree — then treating the two checks as independent is wrong, and the
containment logic needs to be expressed as a single predicate over a set of
roots rather than two checks with different root sets. A test that positions the
sidecar *inside* the project directory should be written specifically to probe
this.

**Steelmanned runner-up.** Option C — read through a copy — is stronger than it
looks for the dashboard specifically. The dashboard is read-only, its data is
already snapshot-like (reports, ledgers, ADRs), and it already polls on an
interval rather than watching. A read-through-copy design would leave the
strictest containment check in the codebase completely untouched, which for a
component that serves arbitrary project directories over HTTP is worth a great
deal. The reason to decline it is that the copy needs invalidation, and an
invalidation bug shows up as the dashboard confidently displaying stale state —
a failure mode that is harder to notice than a rejected path. But if the
falsifier above fires, option C for the dashboard (keeping the allowlist only in
`worktree_guard.py`, where there is no read-only alternative) is the right
retreat.

**Reversal trigger.** A third permitted root wanting to exist in either guard.
Two is an allowlist; three is a policy, and a policy belongs in one place with
its own tests rather than duplicated across a Python hook and a TypeScript
server module.

## Prior Decision

**What removed this decision's subject.** `dec-366` changed how
sidecar state is materialised: instead of a symlink escaping the checkout into
`${PRAXION_SIDECAR_ROOT}/<id>/`, each checkout mounts the sidecar as a
`git worktree` at `<checkout>/.praxion-state/` and the shadows become *relative*
symlinks pointing inward. Every Praxion path therefore resolves **inside the
project root**. The question this record answered — "how do we admit one
specific containment escape without admitting the class?" — no longer has a
subject: there is no escape.

Concretely, both clauses lapse:

- **`worktree_guard.py`** needs nothing. Its existing
  `_is_within(target.resolve(), session_root)` early return fires before any git
  logic, because the resolved target is inside the session worktree. Verified
  against the source.
- **`project-root.ts`** keeps *both* containment checks and gains no second
  realpath root and no `PRAXION_STATE_ROOT` environment channel. One small
  change survives, and it is a different decision than this one: because
  `assertProjectPath` re-applies `isAllowedArtifactPath` to the **resolved**
  relative path — which under the mount reads `.praxion-state/.ai-state/…` — that
  allowlist constant gains a `.praxion-state/.ai-state` entry. An allowlist entry for
  an in-project prefix is not a containment relaxation, so it is recorded in the
  plan and in `dec-366`, not here.

This is a **retirement, not a supersession**: `dec-366` makes no
claim about whether admitting a declared escape was the right answer to the
question. It removed the question.

**Re-open condition** (retired records return to `accepted` and clear
`retired_by` if their subject returns). If a Praxion write path is found that
must target the sidecar's git common directory — or any path outside the
checkout — by absolute path, then a containment escape exists again and this
record's analysis, including its option table and its falsifier about treating
the dashboard's two checks as independent, becomes live. The most likely route:
a future component that operates on the sidecar repository itself rather than
through a mount.

**What survives regardless.** The falsifier recorded above is still worth a test
under the new design, in a sharper form: position the sidecar *inside* the
project directory and assert the dashboard's lexical and realpath checks agree.
The chosen design makes that configuration ordinary rather than exotic, so the
probe is cheaper to write and more likely to matter.
