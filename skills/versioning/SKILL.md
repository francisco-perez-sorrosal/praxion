---
name: versioning
description: Version bumping, changelog generation, release automation, and tool
  detection for multi-file projects. Covers SemVer strategy, tool-agnostic detection
  logic, flag mapping for common versioning tools, and breaking change guidelines
  for textual/config ecosystems. Use when bumping versions, generating changelogs,
  configuring release automation, choosing a versioning tool, or defining what
  constitutes a breaking change in a non-library project.
allowed-tools: [Read, Bash, Grep, Glob]
compatibility: Claude Code
---

# Versioning

Domain knowledge for version management, changelog generation, and release automation across versioning tools and project types.

**Satellite files** (loaded on-demand):

- [references/commitizen.md](references/commitizen.md) -- Commitizen config reference, `version_files` patterns, PEP 440 pre-release workflow, common flags, GitHub Actions integration

## Tool Detection

Detect the active versioning tool from project configuration files. Check in priority order (first match wins):

| Config Signal | Tool | Bump Command |
|---------------|------|--------------|
| `[tool.commitizen]` in `pyproject.toml` | Commitizen | `cz bump` |
| `[tool.semantic_release]` in `pyproject.toml` | python-semantic-release | `semantic-release version` |
| `[tool.bumpversion]` in `pyproject.toml` | bump-my-version | `bump-my-version bump` |
| `.release-please-manifest.json` | Release Please | PR-based (different flow) |
| `knope.toml` | Knope | `knope release` |
| `package.json` with `semantic-release` dep | semantic-release (JS) | `npx semantic-release` |

**Detection procedure:**

1. Read `pyproject.toml` -- check for `[tool.commitizen]`, `[tool.semantic_release]`, `[tool.bumpversion]` sections
2. Check for `.release-please-manifest.json` at the project root
3. Check for `knope.toml` at the project root
4. Check `package.json` for `semantic-release` in `devDependencies` or `dependencies`
5. If no tool detected, report to the user and suggest configuring one

## Flag Mapping

Map user intent to tool-specific CLI flags. The `/release` command uses this table to translate intent into the correct invocation.

| Intent | Commitizen | python-semantic-release | bump-my-version | Knope | semantic-release (JS) |
|--------|-----------|------------------------|----------------|-------|----------------------|
| **auto** | `cz bump --changelog` | `semantic-release version` | N/A (requires explicit part) | `knope release` | `npx semantic-release` |
| **dev** | `cz bump --prerelease dev --changelog` | `semantic-release version --prerelease` | `bump-my-version bump dev` | N/A | N/A |
| **patch** | `cz bump --increment PATCH --changelog` | `semantic-release version --patch` | `bump-my-version bump patch` | N/A | N/A |
| **minor** | `cz bump --increment MINOR --changelog` | `semantic-release version --minor` | `bump-my-version bump minor` | N/A | N/A |
| **major** | `cz bump --increment MAJOR --changelog` | `semantic-release version --major` | `bump-my-version bump major` | N/A | N/A |

**Notes:**

- Release Please uses a PR-based flow -- there is no direct bump command. Merging the release PR triggers the version bump.
- Knope and semantic-release (JS) auto-detect the bump type from commit history. Explicit increment overrides are not supported.
- All tools except bump-my-version support auto-detection from conventional commits.

## Breaking Change Guidelines

For textual and configuration projects (Markdown skills, agent prompts, rules, commands, hooks, plugin manifests), "breaking" requires an explicit definition since there is no compiled API to analyze.

### MAJOR (breaking)

- Skill or agent renamed or removed (breaks activation by name)
- Command renamed or removed (breaks `/<command>` invocation)
- Rule file renamed or removed (breaks `rules/` symlink paths)
- MCP server API changed (breaks hook integrations and client callers)
- `plugin.json` structural change (breaks marketplace install or plugin cache resolution)

### MINOR (feature)

- New skill, agent, command, or rule added
- New reference file added to an existing skill
- New MCP server tool or resource
- Enhanced prompt or instruction that adds capability without changing existing behavior
- New hook event handler

### PATCH (fix)

- Bug fix in hooks, scripts, or MCP server code
- Typo or documentation correction
- Prompt refinement that preserves existing behavior
- Dependency update in Python subprojects

### Ambiguous Cases

When a change spans multiple categories, use the highest applicable level. When in doubt between MINOR and MAJOR, ask: "Would a user who pinned the previous version encounter breakage if they upgrade?" If yes, it is MAJOR.

## Gotchas

- **Commitizen `version_files` uses substring matching.** The `:version` suffix in a `version_files` entry means "find the substring `version` on a line and replace the version string on that line." This works for both TOML (`version = "1.0.0"`) and JSON (`"version": "1.0.0"`). However, if a file has multiple lines containing the word `version` with version-like strings, Commitizen may update the wrong one. Ensure each target file has an unambiguous `version` field.

- **`major_version_zero = true` changes bump semantics.** When enabled, `feat` commits produce MINOR bumps instead of MAJOR, and `feat!` / `BREAKING CHANGE` commits produce MINOR instead of MAJOR. This keeps the project in the `0.x` range during early development. Disable it (or remove the setting) when ready to release `1.0.0`.

- **Commitizen requires a baseline tag.** The first `cz bump` fails if no tag matching `tag_format` exists in git history. Bootstrap with a manual tag (`git tag -a v0.0.1 -m "Bootstrap"`) before running any bump commands.

- **`--dry-run` does not check `version_files` accessibility.** A `cz bump --dry-run` can succeed even if a `version_files` target path is wrong or the file is missing. The error only surfaces during an actual bump. Validate paths manually after configuration changes.

## Version Strategy Patterns

### Single-Version Monorepo

All components share one version. A single bump updates every version file. Best for projects where components are always deployed together (e.g., a plugin ecosystem).

### Independent Versioning

Each component maintains its own version and changelog. Best for projects where components are published independently (e.g., a library collection).

### Choosing a Strategy

- If users install the project as a unit, use single-version
- If users install individual components, use independent versioning
- If in doubt, start with single-version -- splitting later is easier than merging

## Plugin Marketplace Publishing

When a project ships as a Claude Code plugin via an external marketplace manifest — a separate repo with `.claude-plugin/marketplace.json` pointing at the plugin's source — the marketplace version is a **separate publish surface** from the plugin's internal version files. Keeping the two in sync is not automatic.

**Release-only marketplace policy:**

- Marketplace manifests advertise **stable** versions only — never `.devN` pre-release markers.
- Dev-cycle versions (`0.2.1.dev0`, etc.) are internal working state: they live in the plugin's `pyproject.toml`, `.claude-plugin/plugin.json`, sub-project `pyproject.toml` files, but MUST NOT be pushed to the marketplace.
- When cutting a stable release, update the marketplace AFTER the plugin repo is tagged and pushed — never before.

**Why:** Claude Code's plugin subsystem uses the version string as the cache key. A dev-cycle version like `0.1.1.dev0` stays the same across many commits; advertising it to the marketplace means every cached user install gets pinned to whichever `0.1.1.dev0` snapshot happened to land first, with no mechanism to invalidate. Stable semver versions change monotonically with each release — they work correctly as cache keys.

**Two-repo release workflow:**

1. **Plugin repo:** `cz bump --increment <MINOR|PATCH>` → updates version files, tags `vX.Y.Z`, commits.
2. **Plugin repo:** `cz changelog --unreleased-version vX.Y.Z --incremental` → CHANGELOG entry, commit.
3. **Plugin repo:** manually bump version files to next dev cycle (`X.Y.(Z+1).dev0`), commit with `bump: Open X.Y.(Z+1).dev0 development cycle`.
4. **Plugin repo:** `git push origin main && git push origin vX.Y.Z`.
5. **Marketplace repo:** edit `.claude-plugin/marketplace.json`, set the plugin's `version` to `X.Y.Z` (the stable tag, NOT the dev-cycle marker), commit with `bump(<plugin-name>): Advertise vX.Y.Z`, push.
6. Users running `claude plugin update <plugin>` now see the new stable version and pull it.

**Cache-staleness recovery:**

If users already have a stale `.devN` snapshot cached (from before this policy was in force), a one-time cleanup is required:

```bash
rm -rf ~/.claude/plugins/cache/<marketplace>/<plugin>/<stale-version>
# Also scrub the registry so next install is fresh:
python3 -c "import json; from pathlib import Path; p=Path.home()/'.claude/plugins/installed_plugins.json'; d=json.loads(p.read_text()); d.get('plugins',{}).pop('<plugin>@<marketplace>', None); p.write_text(json.dumps(d, indent=2))"
```

Then `claude plugin install <plugin>` pulls fresh from the corrected marketplace version.

## Integration with Other Skills

- **[CI/CD](../cicd/SKILL.md)** -- release workflow design, GitHub Actions for automated bumps
- **[Python Project Management](../python-prj-mgmt/SKILL.md)** -- `pyproject.toml` configuration for tool sections
