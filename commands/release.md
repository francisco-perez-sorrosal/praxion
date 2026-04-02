---
description: Bump version, update changelog, and create a release tag
argument-hint: [dev|patch|minor|major]
allowed-tools: [Bash(cz:*), Bash(git:*), Bash(gh:*), Bash(pip:*), Read, Grep, Glob]
---

Bump the project version, generate a changelog entry, and create a release tag using the **versioning** skill. The command detects the active versioning tool automatically -- it does not hardcode tool-specific commands.

## Process

1. **Detect versioning tool**: Check project config files for a configured versioning tool -- `pyproject.toml` for `[tool.commitizen]`, `[tool.semantic_release]`, `[tool.bumpversion]`; `.release-please-manifest.json`; `knope.toml`; `package.json` for `semantic-release` dependency. If no tool is found, report and stop
2. **Load the versioning skill**: Activate the `versioning` skill and load the appropriate tool reference file for flag mappings and configuration details
3. **Map argument to intent**:
   - No argument -- auto-detect bump type from conventional commit history
   - `dev` -- dev pre-release increment
   - `patch` -- patch increment
   - `minor` -- minor increment
   - `major` -- major increment
4. **Execute bump**: Run the tool-appropriate bump command with changelog generation, using the flag mapping from the versioning skill
5. **Report results**: Show the new version, files updated, and tag created
6. **Push reminder**: If the tool did not push automatically, remind the user to run `git push --follow-tags`
