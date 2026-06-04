---
description: Cut a stable release by dispatching the Release CI workflow (bump + changelog + tag + GitHub release)
argument-hint: [patch|minor|major]
allowed-tools: [Bash(gh:*), Bash(git:*), Read, Grep, Glob]
disable-model-invocation: true
---

Cut a stable release. Praxion's release is a **manual CI workflow** (`.github/workflows/release.yml`, `workflow_dispatch`) that runs Commitizen on a clean runner. This command **dispatches that workflow** -- it does NOT bump locally -- so the workflow stays the single mechanism that changes version strings (no local/CI double-bump). The workflow, in one tagged commit, updates the version files and regenerates `CHANGELOG.md` (`update_changelog_on_bump = true`), tags it, pushes, and publishes the GitHub release.

## Process

1. **Preconditions**:
   - Confirm the current branch is `main` (`git rev-parse --abbrev-ref HEAD`). If not, stop and report -- releases cut from `main`.
   - Confirm `origin/main` contains everything to be released: `git fetch origin` then `git rev-list --left-right --count main...origin/main`. The CI workflow checks out `origin/main`, so any local commits not yet pushed will be **excluded** from the release. If local `main` is ahead, push it first (`git push origin main`) before dispatching; surface this to the user.
2. **Map the argument to the `increment` input**:
   - No argument -- `increment=auto` (Commitizen detects the bump type from conventional commits since the last tag)
   - `patch` / `minor` / `major` -- force that bump type
3. **Dispatch the workflow**: `gh workflow run release.yml --ref main -f increment=<auto|patch|minor|major>`
4. **Watch to completion**: find the run (`gh run list --workflow=release.yml --limit 1`) and `gh run watch <run-id> --exit-status`. If it fails, report the failing step and stop.
5. **Report results**: the new version + tag, and the GitHub release URL (`gh release view "v<version>" --json url,tagName,name`). Confirm the tag includes its own `CHANGELOG.md` entry.
6. **Marketplace note**: if consumers install via the marketplace, remind the user the marketplace entry / cache may need refreshing (`claude plugin marketplace update`, then `claude plugin update i-am`) to serve the new version.

## Notes

- **Do not run `cz bump` locally.** The workflow is authoritative; a local bump would create a divergent tag/version and defeat the "single mechanism" guarantee.
- A preview of the computed bump (without changing anything) is available via `cz bump --dry-run` if Commitizen is installed locally -- read-only, optional.
- The workflow is idempotent on the GitHub-release step (it skips if the tag's release already exists).
