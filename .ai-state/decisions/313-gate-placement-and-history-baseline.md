---
id: dec-313
title: Gate placement follows input kind, and the append-only baseline is the merge-base
status: accepted
category: architectural
date: 2026-07-31
summary: State-reading gates live in scripts/ (unfiltered CI), history-reading gates live in fitness/ (fetch-depth 0); the CONSULT append-only baseline is the branch merge-base, and finalize stages what it wrote.
tags: [gate-liveness, scope-fidelity, ci, adr-finalize, consult-ledger, append-only]
made_by: agent
agent_type: systems-architect
branch: worktree-gate-integrity-and-overlay
pipeline_tier: full
affected_files:
  - scripts/check_adr_frontmatter_promotion.py
  - scripts/finalize_adrs.py
  - fitness/tests/test_consult_append_only.py
  - .github/workflows/test.yml
  - .github/workflows/architecture.yml
dissent: >
  Placing both gates in fitness/ would give one home, one convention, and one
  git-reachability idiom instead of two, at the cost of a documented blind spot on
  finalize_adrs.py-only PRs; and the merge-base baseline buys stability of verdict by
  accepting a real miss (a row added and then mutated inside one branch) that a
  consecutive-commit walk would catch.
---

# Gate placement follows input kind, and the append-only baseline is the merge-base

## Context

Two gate families were commissioned in the same pipeline and superficially resemble each
other — both "assert a contract over the repository". Placing them by resemblance would
have produced a scope-fidelity failure of the kind `rules/swe/gate-liveness.md` clause 5
names, in the very pipeline written to close gate-liveness debt.

Three measured facts frame the decision, all verified in the authoring worktree:

- `pyproject.toml` sets `testpaths = ["tests", "scripts"]`, so a bare `pytest` never
  collects `fitness/`. The only CI path to `fitness/tests/` is `architecture.yml`'s
  `fitness-functions` job, which is `paths:`-filtered.
- That filter includes `.ai-state/decisions/**` and `.ai-state/CONSULT_*.md`; it does
  **not** include `scripts/finalize_adrs.py`.
- `test.yml`'s `test-root` job runs `pytest` on every pull request and every push to main
  with **no** `paths:` filter, but does **not** override `fetch-depth`, so its checkout is
  shallow and `git show <older-rev>:<path>` is unavailable there. `architecture.yml`'s
  `fitness-functions` job sets `fetch-depth: 0` with a comment naming precisely this class
  of gate as the reason.

Separately, the defect the first gate exists to catch was reproduced mechanically: `git mv`
stages the **index** blob, not a just-written working-tree modification, so
`finalize_adrs.py`'s write-then-`git mv` sequence stages a stale version of the file it just
rewrote. A released tag carries a finalized ADR self-identifying as an unpromoted draft.

## Decision

**Gate placement follows the gate's input kind, not its subject matter.**

- A gate whose input is **repository state** — the current bytes of tracked files — lives in
  `scripts/` as a `check_*.py` plus a sibling `test_check_*.py`. It reaches CI through
  `test-root`'s unfiltered `pytest`, so it fires on every PR regardless of which paths
  changed. The ADR-frontmatter-promotion gate is of this kind.
- A gate whose input is **repository history** — content at a prior revision — lives in
  `fitness/tests/`, in its own file. It reaches CI only through `architecture.yml`, whose
  filter must be verified to contain the paths the gate polices, and whose job guarantees
  full history. The `CONSULT_*.md` append-only gate is of this kind.
- **No shared helper is extracted.** The state gate never invokes git; the only candidate
  shared surface has one caller. Extraction is deferred until a second history-reading gate
  exists.

**The append-only gate's baseline is the branch merge-base** (`git merge-base origin/main
HEAD`, falling back to `main`), comparing the merge-base revision's content against the
working tree. When the baseline revision is unreachable, the gate **skips with a named
reason** rather than passing.

**The comparison unit is every line in the file beginning with `|` that is not a table
header or its separator**, computed identically for both sides, with an ordered-subsequence
relation: every baseline row must appear, in order, among the working rows. This is
deliberately a whole-file rule rather than a per-table one.

**The frontmatter defect is fixed at its root as well as gated**: `finalize_adrs.py` stages
the destination path's post-rewrite content immediately after `git mv`, restoring the
invariant *whatever finalize stages is what finalize wrote*. Cross-reference rewrites in
sibling files remain unstaged, as documented.

## Considered Options

### Option A — Both gates in `fitness/tests/` (rejected)

One home, one convention, one git idiom. Rejected on clause 5: a pull request touching only
`scripts/finalize_adrs.py` — the code whose defect the frontmatter gate exists to catch —
runs zero fitness jobs, because that path is absent from `architecture.yml`'s filter. The
gate would correctly police everything inside a narrower-than-documented scope and return a
false all-clear for the one input shape that matters most.

### Option B — Both gates in `scripts/` (rejected)

Uniform placement and unfiltered CI. Rejected because `test-root` does not override
`fetch-depth`. Under actions/checkout's shallow default every `git show <baseline>:<path>`
fails, so the append-only gate degrades to a permanent skip. A gate that never runs is
indistinguishable from no gate. Overriding `fetch-depth` on `test-root` was considered and
rejected as a disproportionate change to the repository's primary test job for one gate,
when a job already exists with the property and the right path filter.

### Option C — Split, plus a shared history-reading helper (rejected for now)

Rejected on `Simplicity First`: the state gate does not invoke git, so the helper would have
exactly one caller while creating a dependency edge between `scripts/` and `fitness/`.
Revisit when a second history-reading gate lands.

### Option D — `HEAD~1` as the append-only baseline (rejected)

Cheaper and needs no remote ref. Rejected on two grounds. It misses the demonstrated
violation shape — a row mutated in commit 2 of a three-commit branch and untouched by commit
3 compares clean against `HEAD~1`. More fundamentally, `HEAD~1` makes the verdict a function
of push cadence rather than of pull-request content: the same change passes or fails
depending on whether one more commit sits on top. A gate whose verdict is not a function of
the thing it gates is not a gate. `HEAD~1` additionally carries the merge-commit ambiguity
this repository already documents in `scripts/check_squash_safety.py`, which restricts itself
to single-parent commits for exactly that reason.

### Option E — Walk every consecutive commit pair in `merge-base..HEAD` (rejected for now)

The only strategy that proves append-only across every intermediate state. Rejected on cost
and prior art: O(commits) git invocations, no existing instance of the pattern in this
repository, and it buys only the residual named under Consequences. It remains available as
a pure upgrade with no design rework.

### Option F — Reorder `promote_draft` to rename-then-write instead of adding a stage (rejected)

Appealing because it avoids a new subprocess call. Rejected because it does not work: the
reproduction shows `git mv` stages the index blob, so no ordering of write and rename
produces a correctly staged destination without an explicit stage.

## Consequences

**Positive.**

- Each gate's computed input set matches its documented scope on the axis that determines
  whether it can fire at all. The frontmatter gate fires on a `finalize_adrs.py`-only pull
  request; the append-only gate fires on any change to the files it polices.
- The append-only gate's verdict is a function of the pull request's content, so it is stable
  across re-runs and pushes.
- The whole-file row-extraction rule is structurally immune to the prior failure in which a
  row appended after the trailing prose sections fell outside every parsed table and became
  invisible to counting. It also covers both of the two-table file's tables without
  table-specific logic.
- The frontmatter gate's `--staged` mode reads index blobs, so the defect is caught at the
  commit that would ship it rather than one release later — the working tree is *correct* at
  that moment, which is why a working-tree-only gate passes.
- Fixing the root cause means the gate is a standing guarantee rather than a recurring alarm.

**Negative / accepted.**

- Two conventions for gate placement instead of one. Mitigated by stating the rule once:
  state-reading gates to `scripts/`, history-reading gates to `fitness/`.
- The append-only gate misses a row **added in one commit and mutated in a later commit of
  the same branch**. This is a genuine loss, not a vacuous one: the original disposition was
  committed and is in history unless the branch is squash-merged. Accepted because the
  demonstrated incident is the pre-existing-row shape, which this baseline catches and the
  rejected one does not, and because the upgrade path is known.
- On a push to main the baseline resolves to `HEAD` and the comparison degrades to
  working-tree-versus-`HEAD` — vacuous on a clean tree. The pull-request trigger is the live
  path; the push run is a second layer. Locally the degraded form still catches an in-place
  mutation before it is committed, which is how the live incident actually occurred.
- One additional subprocess call per promoted draft.

## Disconfirmation

**Falsifier.** If a `CONSULT_*.md` in-place mutation is ever observed reaching `main` in the
add-then-mutate-within-one-branch shape, the merge-base baseline is insufficient and the
consecutive-pair walk is required. Symmetrically, if a pull request that reintroduces the
frontmatter defect is ever merged without the `scripts/`-placed gate firing, the placement
argument is unsound and the gate belongs at the pre-commit seam only.

**Steelmanned runner-up.** Option A — both gates in `fitness/` — is stronger than its
rejection suggests. The scope hole it accepts is a single path (`scripts/finalize_adrs.py`)
that could simply be added to `architecture.yml`'s `paths:` filter, at which point the
clause-5 objection evaporates and the repository gains one gate home, one convention, and
one git-reachability idiom rather than two. The reason that variant was not chosen is that a
path filter is a second thing to keep in sync with the gate's intent — it is precisely the
"convention lives at two textual sites" shape — whereas an unfiltered job needs no
maintenance at all. If the repository ever consolidates its gate surface, Option A plus a
filter entry is the shape to consolidate toward.

**Reversal trigger.** Revisit when any of: (a) a second history-reading gate is proposed,
which makes the shared-helper extraction earn its place; (b) `test-root` gains
`fetch-depth: 0` for an unrelated reason, which removes Option B's disqualifier; (c) an
add-then-mutate-within-one-branch violation is observed, which promotes Option E from
deferred to required; or (d) `architecture.yml`'s path filter is consolidated such that it
provably covers every producer of every defect its jobs police.
