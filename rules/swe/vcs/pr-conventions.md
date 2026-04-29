---
paths:
  - ".github/**/*.md"
  - "commands/*pr*.md"
  - "commands/*merge*.md"
  - "commands/release.md"
  - "rules/swe/vcs/git-conventions.md"
---

## PR Conventions

Companion to `git-conventions.md`. This rule covers PR workflow and the safety contract for PRs that touch `.ai-state/`. Path-scoped — it loads only when you are editing PR-adjacent surfaces (GitHub metadata, merge/PR commands, the release command, or the sibling git-conventions rule).

### Branch Naming

- Short-lived, topic-based branches. Merge within hours to days, not weeks.
- Conventional prefixes: `feat/<slug>`, `fix/<slug>`, `refactor/<slug>`, `docs/<slug>`, `test/<slug>`, `chore/<slug>`.
- Author-prefixed in multi-user contexts: `<user>/<topic>` (e.g., `alice/feat-auth`). The ADR fragment-filename scheme (`<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md`) encodes author identity from branch names, so keeping the user prefix consistent aids traceability.
- Kebab-case only. Sanitize to `[a-z0-9-]`.

### `.ai-state/` Safety Contract at PR Time

PRs that touch `.ai-state/` carry obligations beyond regular code PRs because the `.ai-state/` tree has structured reconciliation (semantic merge drivers, post-merge hooks, fragment-to-stable finalize).

**Before opening a PR that touches `.ai-state/`:**

- Run `python scripts/finalize_adrs.py --dry-run` locally. Confirm any draft ADRs in `.ai-state/decisions/drafts/` promote cleanly — no collisions, no missing cross-references.
- Run the full project test suite (`pytest scripts/` at minimum).
- Include in the PR description an explicit note: "Touches `.ai-state/`". List the affected subpaths (e.g., `decisions/drafts/`, `observations.jsonl`, `ARCHITECTURE.md`) so reviewers know semantic merge will apply.

**When in doubt, rebase on latest `main` before opening the PR.** This narrows the merge-time reconciliation surface.

### Merge Policy

**Default: fast-forward only (`git merge --ff-only`).** Preserves a linear history on the target branch; post-merge git hooks fire as expected on the moved tip. When the source branch has diverged from the target, rebase the source onto the target first (`git rebase <target>` from inside the worktree) so the next attempt fast-forwards — the rebase exercises the merge drivers on `.ai-state/memory.json` and `.ai-state/observations.jsonl` if any conflicts in those files exist. Do not silently fall back to a non-fast-forward merge commit.

**Do not squash-merge PRs that touch `.ai-state/`.** Squash collapses the source-branch history into a single commit on the target; the resulting tree replaces the target's `.ai-state/` wholesale, erasing any state the target accumulated since the branch diverged. Consequences include:

- Merged-main ADRs whose cross-references were rewritten at finalize can regress to pre-finalize draft ids.
- `.ai-state/observations.jsonl` events captured on main while the branch was alive are deleted.
- `sentinel_reports/SENTINEL_REPORT_*.md` and `calibration_log.md` entries are lost.

Enforcement is layered:
- `/merge-worktree` refuses `git merge --squash` locally when the source branch touched `.ai-state/`.
- `scripts/check_squash_safety.py` runs in the post-merge hook and emits a loud warning when it detects squash-erasure post-hoc (non-blocking, since the hook fires after the merge completes). Recovery uses `git reflog`.

**Rebase-and-merge is acceptable** if the rebase is run locally first and the reconciliation scripts (`reconcile_ai_state.py`, `finalize_adrs.py`) are exercised against the rebased branch before pushing.

### Review Expectations for `.ai-state/`-touching PRs

- **Reviewers verify ADR drafts have the required frontmatter shape** per `adr-conventions.md` — fragment filename, `id: dec-draft-<hash>`, `status: proposed`. The finalize step at merge rewrites `id` and cross-references; review the draft in its draft form, not against what it will become.
- **Do not review `DECISIONS_INDEX.md` changes.** The index is regenerated automatically at finalize from the on-disk ADR set; hand-edited index changes on a PR are a signal of drift.
- **Treat `.ai-state/observations.jsonl` and `.ai-state/memory.json` as mergeable data.** The semantic merge drivers reconcile concurrent writes. Reviewers confirm the delta looks structurally sensible (new keys / appended events), not line-by-line.
- **Architecture docs (`.ai-state/ARCHITECTURE.md` and `docs/architecture.md`) respect section ownership.** Systems architect owns design-target sections; implementer owns as-built sections; doc-engineer validates dev-facing wording. Conflicting edits to the same section are a review concern; edits to different sections are expected to compose.

### Stacked PRs and Multi-PR Feature Work

When a pipeline's implementation plan decomposes into multiple ordered PRs (e.g., foundation → core → UX layers):

- Each PR in the stack is independently mergeable — CI must pass against a tree that has only this PR's parents merged.
- ADR drafts created in earlier PRs finalize at their own merge; later PRs in the stack can reference the now-stable `dec-NNN` once the earlier PR is merged, or use `dec-draft-<hash>` if cross-referencing a still-unmerged draft. Do not cross-reference a draft that belongs to a different, unmerged PR's branch — the cross-reference will dangle until both merge.
- Rebase the later PRs whenever an earlier PR in the stack merges, so the stack remains linear and finalize runs cleanly at each level.

### Forward Path: Multi-User Team Mode

The fragment-ADR scheme already encodes author identity via the filename (`<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md`). A `finalize_adrs.py --author <email>` flag is a small extension that would let an author-scoped finalize run on each merge — useful if two users' branches both land on the same day with independent drafts.

For multi-user setups, consider adding to CI:
- Pre-merge dry-run: a GitHub Action that runs `python scripts/finalize_adrs.py --dry-run --branch "$HEAD_REF"` on every PR touching `.ai-state/decisions/drafts/`. Fails CI if the dry-run detects a collision or missing cross-reference.
- `.ai-state/` diff surfacing: a PR comment that lists `.ai-state/` paths touched, so reviewers see semantic-merge scope at a glance.

### Self-Test Before Merging

- Is the source branch up to date with `main`?
- If `.ai-state/` is touched: has `finalize_adrs.py --dry-run` been run and inspected?
- Is the merge strategy regular-merge (or rebase-and-merge with local reconciliation)? Not squash for `.ai-state/`-touching branches.
- Are all cross-references in the ADR drafts internally consistent (pointing to sibling drafts or to already-stable `dec-NNN` on main)?

If any answer is no, pause and address before merging. The post-merge hook provides warnings, not guarantees.
