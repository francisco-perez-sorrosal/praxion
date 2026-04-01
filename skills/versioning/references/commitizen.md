# Commitizen Reference

Detailed configuration and usage reference for Commitizen (`commitizen-tools/commitizen`). For tool detection and flag mapping across all versioning tools, see [../SKILL.md](../SKILL.md).

## `[tool.commitizen]` Config Reference

All settings live in `pyproject.toml` under the `[tool.commitizen]` section. Alternative config files (`.cz.toml`, `cz.toml`) are supported but `pyproject.toml` is the canonical location for Python projects.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | `"cz_conventional_commits"` | Commit rule scheme. Use `"cz_conventional_commits"` for standard conventional commits. |
| `version` | string | (required) | Current project version. Commitizen reads and writes this field on each bump. |
| `version_files` | list[string] | `[]` | Files to update with the new version on bump. See [Version Files Patterns](#version-files-patterns). |
| `tag_format` | string | `"$version"` | Git tag format. Use `"v$version"` for `v1.2.3` tags. The `$version` placeholder is replaced with the new version. |
| `update_changelog_on_bump` | bool | `false` | Automatically regenerate `CHANGELOG.md` during `cz bump`. Equivalent to passing `--changelog` on every bump. |
| `changelog_start_rev` | string | `null` | Git ref (tag or commit) from which to start generating changelog entries. Commits before this ref are excluded. |
| `major_version_zero` | bool | `false` | When `true`, `feat` and breaking changes produce MINOR bumps instead of MAJOR, keeping the project in the `0.x` range. |
| `changelog_incremental` | bool | `false` | When `true`, only append new entries to the changelog instead of regenerating the entire file. |
| `bump_message` | string | `"bump: version $current_version -> $new_version"` | Commit message template for the bump commit. |
| `style` | list[dict] | (conventional) | Changelog commit type grouping and display. Customize which commit types appear and under what headings. |
| `allowed_prefixes` | list[string] | `["Merge", "Revert", ...]` | Commit message prefixes that Commitizen ignores (does not treat as conventional commit violations). |
| `retry_after_failure` | bool | `false` | Retry the bump if the commit hook fails. |

### Example Configuration

```toml
[tool.commitizen]
name = "cz_conventional_commits"
version = "0.0.1"
version_files = [
    ".claude-plugin/plugin.json:version",
    "memory-mcp/pyproject.toml:version",
    "task-chronograph-mcp/pyproject.toml:version",
    "decision-tracker/pyproject.toml:version",
]
tag_format = "v$version"
update_changelog_on_bump = true
changelog_start_rev = "v0.0.1"
major_version_zero = true
```

## Version Files Patterns

The `version_files` list tells Commitizen which files to update when bumping. Each entry is a `filepath` or `filepath:search_text` string.

### How Substring Matching Works

Commitizen uses **line-by-line substring matching**, not full parsing. The `:search_text` suffix narrows which line gets updated:

1. Open the file
2. Find lines containing `search_text` (substring match)
3. On matching lines, replace the old version string with the new one

### TOML Files

```toml
# pyproject.toml entry:
# "memory-mcp/pyproject.toml:version"
#
# Matches the line:
#   version = "0.0.1"
# And updates it to:
#   version = "0.2.0"
```

The search text `version` matches any line containing that word. In a standard `pyproject.toml`, the `version` field under `[project]` is typically unambiguous.

### JSON Files

```json
// plugin.json entry:
// ".claude-plugin/plugin.json:version"
//
// Matches the line:
//   "version": "0.0.1",
// And updates it to:
//   "version": "0.2.0",
```

### Edge Cases

- **Multiple matches on different lines.** If a file has multiple lines containing the search text with version-like strings, Commitizen may update all of them. Ensure each target file has a single unambiguous version field, or use a more specific search text.
- **No search text specified.** When the entry is just a filepath (no `:suffix`), Commitizen searches for the current version string anywhere in the file. This is fragile for files where the version string might appear in comments or documentation.
- **Regex patterns.** Commitizen also supports regex patterns in `version_files` for complex matching. Use the `version_files` entry format `"filepath:regex_pattern"` where the pattern uses a named group `(?P<version>...)`.

## Tag Format and `major_version_zero`

### `tag_format`

Controls the format of git tags created by `cz bump`:

- `"v$version"` produces tags like `v1.2.3` (most common convention)
- `"$version"` produces tags like `1.2.3`
- `"release-$version"` produces tags like `release-1.2.3`

Commitizen also reads existing tags using this format to determine the current version from git history. The format must be consistent across all tags.

### `major_version_zero`

Controls bump behavior during `0.x` development:

| Commit Type | `major_version_zero = false` | `major_version_zero = true` |
|-------------|------------------------------|----------------------------|
| `fix:` | PATCH (0.0.1 -> 0.0.2) | PATCH (0.0.1 -> 0.0.2) |
| `feat:` | MINOR (0.0.1 -> 0.1.0) | MINOR (0.0.1 -> 0.1.0) |
| `feat!:` or `BREAKING CHANGE` | MAJOR (0.0.1 -> 1.0.0) | MINOR (0.0.1 -> 0.1.0) |

When ready to release `1.0.0`, either remove `major_version_zero` or set it to `false`, then make a breaking change commit.

## PEP 440 Pre-Release Workflow

Commitizen supports PEP 440 pre-release versions for development releases between milestones.

### Dev Releases

```bash
# From 0.0.1, create a dev release:
cz bump --prerelease dev --changelog
# Produces: 0.0.2.dev0

# Subsequent dev bumps increment the dev number:
cz bump --prerelease dev --changelog
# Produces: 0.0.2.dev1
```

### Pre-release Types

| Type | Flag | Example | PEP 440 |
|------|------|---------|---------|
| Dev | `--prerelease dev` | `0.0.2.dev0` | Development release |
| Alpha | `--prerelease alpha` | `0.0.2a0` | Alpha release |
| Beta | `--prerelease beta` | `0.0.2b0` | Beta release |
| RC | `--prerelease rc` | `0.0.2rc0` | Release candidate |

### Finalizing a Pre-release

To go from a pre-release to a final release:

```bash
# Currently at 0.0.2.dev1
cz bump --changelog
# Produces: 0.0.2 (strips the pre-release suffix, auto-detects increment)
```

## Changelog Settings

### `update_changelog_on_bump`

When `true`, every `cz bump` automatically regenerates the changelog. Equivalent to always passing `--changelog`. Recommended for most projects to keep the changelog in sync with releases.

### `changelog_start_rev`

Limits changelog generation to commits after the specified git ref. Useful when:

- Bootstrapping versioning on a project with existing history (avoids retroactive entries)
- Starting fresh after a major rewrite

```toml
changelog_start_rev = "v0.0.1"  # Only include commits after this tag
```

### Changelog Format

Commitizen generates changelogs in the **Keep a Changelog** style by default, grouping entries by commit type:

- **feat** -> Added / Features
- **fix** -> Fixed / Bug Fixes
- **refactor** -> Refactored
- **perf** -> Performance

The `style` config field customizes grouping and display names.

## Common `cz bump` Flags

| Flag | Description |
|------|-------------|
| `--dry-run` | Show what would happen without making changes. Does not modify files, create commits, or tags. |
| `--changelog` | Regenerate `CHANGELOG.md` as part of the bump. |
| `--increment PATCH\|MINOR\|MAJOR` | Force a specific bump type instead of auto-detecting from commits. |
| `--prerelease dev\|alpha\|beta\|rc` | Create a pre-release version. |
| `--yes` | Skip confirmation prompts. Required for CI/CD automation. |
| `--check-consistency` | Verify that all `version_files` targets contain the current version before bumping. |
| `--no-verify` | Skip pre-commit and commit-msg hooks during the bump commit. |
| `--files-only` | Update version files but do not create a git commit or tag. |
| `--annotated-tag` | Create an annotated tag instead of a lightweight tag. |
| `--changelog-to-stdout` | Print the changelog diff to stdout instead of writing to file. |

## `cz version` Commands

| Command | Description |
|---------|-------------|
| `cz version` | Show the Commitizen tool version (not the project version). |
| `cz version --project` | Show the project version from `[tool.commitizen] version`. |
| `cz version --verbose` | Show both the tool version and the project version. |

## GitHub Actions Integration

A minimal release workflow using Commitizen in GitHub Actions:

```yaml
name: Release

on:
  push:
    branches: [main]
    paths-ignore: ['CHANGELOG.md']

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Full history required for commit analysis

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install commitizen
        run: pip install commitizen

      - name: Bump version
        id: cz
        # continue-on-error handles re-triggers where no bumpable commits exist
        continue-on-error: true
        run: |
          cz bump --changelog --yes 2>&1 | tee bump_output.txt
          echo "version=$(cz version --project)" >> $GITHUB_OUTPUT

      - name: Push changes and tags
        if: steps.cz.outcome == 'success'
        run: git push --follow-tags

      - name: Create GitHub Release
        if: steps.cz.outcome == 'success'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          VERSION="v${{ steps.cz.outputs.version }}"
          gh release create "$VERSION" --generate-notes --title "$VERSION"
```

### Key Design Points

- **`fetch-depth: 0`** -- Commitizen needs full git history to analyze commits since the last tag.
- **`continue-on-error: true`** -- Makes the workflow idempotent. If triggered by its own push (changelog update), no bumpable commits exist and `cz bump` exits non-zero gracefully.
- **`paths-ignore: ['CHANGELOG.md']`** -- Reduces unnecessary workflow triggers, though `continue-on-error` is the real idempotency mechanism.
- **`--yes`** -- Skips interactive confirmation, required for CI.

### Commitizen GitHub Action (Alternative)

The community-maintained `commitizen-tools/commitizen-action` wraps the above steps. It simplifies configuration but adds a dependency on a third-party action. For full control, use the manual approach shown above.
