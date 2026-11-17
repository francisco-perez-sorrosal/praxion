---
name: release
description: Cut a stable release by dispatching the Release CI workflow (bump + changelog + tag + GitHub release)
argument-hint: "[patch|minor|major]"
allowed-tools: [Bash(gh:*), Bash(git:*), Read, Grep, Glob]
disable-model-invocation: true
---

Cut a stable release. Praxion's release is a **manual CI workflow** (`.github/workflows/release.yml`, `workflow_dispatch`) that runs Commitizen on a clean runner. This skill **dispatches that workflow** -- it does NOT bump locally -- so the workflow stays the single mechanism that changes version strings (no local/CI double-bump). The workflow, in one tagged commit, updates the version files and regenerates `CHANGELOG.md` (`update_changelog_on_bump = true`), tags it, pushes, and publishes the GitHub release.

## Process

1. **Preconditions**:
   - Confirm the current branch is `main` (`git rev-parse --abbrev-ref HEAD`). If not, stop and report -- releases cut from `main`.
   - Confirm `origin/main` contains everything to be released: `git fetch origin` then `git rev-list --left-right --count main...origin/main`. The CI workflow checks out `origin/main`, so any local commits not yet pushed will be **excluded** from the release. If local `main` is ahead, push it first (`git push origin main`) before dispatching; surface this to the user.
   - Read the push's CI run before dispatching (`gh run list --branch main --limit 3`; `gh run view <run-id>` on a failure). CI clones shallow, and a local suite runs with full history, so a shallow-clone failure is visible only there. Dispatch only when the `Test` run for the pushed head reads completed and successful: near its end the workflow can read "queued" again while its last job (the coverage floor) waits for a runner, so an earlier green reading is not the final one (observed 2026-11-15, not re-probed).
   - Judge the go against the head `origin/main` has at that moment, not the head you last tested: the weekly audit pushes a metrics commit that no push workflow runs on, so origin can sit one commit past the tested head. `gh run list --commit <sha>` lists every workflow that ran on a commit (`Test` and `Test (scheduled)` report on the same commits); when origin moved, settle the extra commit with the derived test scope locally.
2. **Check release staleness**: run `python3 scripts/check_release_staleness.py` and record its verdict in the report to the user. This diagnostic is advisory by design (it does not block the cut), but the release process is the one recurring decision point where "what artifacts are unreleased" is actionable -- reading its output here is how any document elsewhere that asserts an artifact has or hasn't shipped stays honest against what this release will actually publish.
4. **Map `$ARGUMENTS` to the `increment` input**:
   - `$ARGUMENTS` empty -- `increment=auto` (Commitizen detects the bump type from conventional commits since the last tag)
   - `$ARGUMENTS` is `patch` / `minor` / `major` -- force that bump type
5. **Dispatch the workflow**: `gh workflow run release.yml --ref main -f increment=<auto|patch|minor|major>`
6. **Watch to completion**: find the run (`gh run list --workflow=release.yml --limit 1`) and `gh run watch <run-id> --exit-status`. If it fails, report the failing step and stop.
7. **Report results**: the new version + tag, and the GitHub release URL (`gh release view "v<version>" --json url,tagName,name`). Confirm the tag includes its own `CHANGELOG.md` entry, then count the entries: the generated lines must equal the typed `feat`, `fix`, `refactor` and `perf` commits since the previous tag. An untyped commit is fine only when it is a later attempt at a plan step whose first commit is listed.
8. **Marketplace note**: if consumers install via the marketplace, remind the user the marketplace entry / cache may need refreshing (`claude plugin marketplace update`, then `claude plugin update praxion`) to serve the new version.
   Also sync the local checkout: the workflow pushes a bump commit, so run `git fetch origin` then `git merge --ff-only origin/main` before the next local commit.

## Notes

- **Do not run `cz bump` locally.** The workflow is authoritative; a local bump would create a divergent tag/version and defeat the "single mechanism" guarantee.
- A preview of the computed bump (without changing anything) is available via `cz bump --dry-run --yes` if Commitizen is installed locally -- read-only, optional. Its "Invalid version tag" lines for backup tags are harmless (seen 2026-11-15).
- **The changelog lists only typed commits.** Only `feat`, `fix`, `refactor` and `perf` commits (and breaking changes) appear in it. Each bump adds the new version's section and replaces only an unreleased section, keeping every earlier line: a commit missing from a released section is never picked up later, and only a hand edit of the unreleased section is lost.
- The workflow is idempotent on the GitHub-release step (it skips if the tag's release already exists).
