# Versioning

Domain knowledge for version management, changelog generation, and release automation across versioning tools and project types. Covers SemVer strategy, tool-agnostic detection logic, flag mapping for common versioning tools, and breaking change guidelines for textual and configuration ecosystems.

## When to Use

- Bumping versions in a multi-file project
- Generating or updating changelogs
- Configuring release automation (Commitizen, semantic-release, Release Please, Knope)
- Choosing a versioning tool for a new project
- Defining what counts as a breaking change in a non-library project (skills, agents, rules, commands)
- Publishing a Claude Code plugin to a marketplace

## Activation

Activates automatically when the task context matches versioning patterns: version bumps, changelog generation, release automation configuration, breaking change classification. Reference explicitly with "versioning skill."

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Tool detection, flag mapping, breaking change guidelines, gotchas, version strategy patterns, plugin marketplace publishing |
| `references/commitizen.md` | Commitizen config reference, `version_files` patterns, PEP 440 pre-release workflow, common flags, GitHub Actions integration |

## Related Skills

- [`cicd`](../cicd/SKILL.md) -- release workflow design and GitHub Actions for automated version bumps
- [`python-prj-mgmt`](../python-prj-mgmt/SKILL.md) -- `pyproject.toml` configuration for versioning tool sections
