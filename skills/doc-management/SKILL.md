---
name: doc-management
description: Writing and maintaining project documentation (README.md, catalogs, architecture docs, changelogs). Covers cross-reference validation, catalog maintenance, documentation freshness, and structural integrity. Use when creating, reviewing, or fixing project documentation, maintaining catalog READMEs, ensuring documentation matches filesystem state, performing a documentation audit, or checking doc freshness.
compatibility: Claude Code
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
---

# Documentation Management

Procedural expertise for writing, maintaining, and validating project-facing documentation. Covers README authoring, cross-reference integrity, catalog maintenance, and staleness detection.

**Satellite files** (loaded on-demand):
- [references/cross-reference-patterns.md](references/cross-reference-patterns.md) -- cross-reference validation procedures, catalog sync, drift scenarios
- [references/documentation-types.md](references/documentation-types.md) -- per-type guidelines for README, architecture, changelog, contributing, API docs

## Gotchas

- **Trusting counts in prose without filesystem verification.** Documentation stating "Contains 5 modules" may silently become wrong after adding or removing one. Always count against the filesystem -- never assume the prose count is current.
- **Phantom catalog entries.** A catalog table may list artifacts that no longer exist on disk (renamed, deleted, moved). Validate every table row against `ls` output before declaring a catalog complete.
- **Missing indirect consumers of referenced files.** Renaming or moving a file breaks not just the one document you are editing, but every document that links to it. Use `Grep` for the old filename/path across all markdown files before finalizing a rename.
- **Structure trees that look correct but are stale.** A documented directory tree can appear plausible even when directories have been added or removed. Always regenerate the tree from the actual filesystem rather than hand-editing an existing one.

## Relationship to readme-style Rule

Does not define documentation conventions -- defines how to apply them.

- **readme-style rule** (auto-loaded): defines WHAT documentation conventions to follow (writing style, structural integrity, naming consistency)
- **doc-management skill** (this file): defines HOW to author, validate, and maintain documentation
- **doc-engineer agent**: autonomous subprocess that uses this skill for documentation quality management
- **code-review skill**: after a code review identifies added, removed, or renamed files, use this skill to update affected documentation

## Core Principles

**Documentation is a living artifact.** Documentation decays the moment the codebase changes. Treat documentation maintenance as part of every change that adds, removes, or renames files.

**The filesystem is the source of truth.** When documentation and the filesystem disagree, the filesystem wins. Documentation must reflect what actually exists -- not what was planned, not what used to exist.

**Cross-reference integrity is non-negotiable.** A broken link or phantom reference is a documentation bug. Every path, count, and name in documentation must be verifiable against the filesystem.

**Right-size the documentation.** Match depth to the artifact's complexity and audience. A simple utility directory needs a few sentences; a complex system needs architecture documentation. Do not create documentation for hypothetical future needs.

## Documentation Types Overview

Six categories of project documentation, each with distinct conventions and maintenance patterns. See [references/documentation-types.md](references/documentation-types.md) for detailed per-type guidelines.

| Type | Purpose | Key Convention |
|------|---------|----------------|
| **Project README** | Entry point -- what it is, how to use it | Lead with identity and usage; omit empty sections |
| **Catalog README** | Lists artifacts in a directory | Every filesystem item listed; counts match reality |
| **Architecture** | System design and decisions | Create only when complexity warrants it |
| **Changelog** | Version history | Chronological; tied to releases or significant milestones |
| **Contributing** | Contributor onboarding | Include only when the project accepts external contributions |
| **API docs** | Interface contracts | Must stay synchronized with implementation |

## README Authoring Workflow

### 1. Assess Structure

Before writing, understand what the README serves:

- **New README**: examine the directory contents, project config, and surrounding documentation to determine scope
- **Existing README**: read it fully, then compare against filesystem state before making changes
- **Catalog README**: inventory the directory to build a complete artifact list

### 2. Determine Content Scope

Match content to the README's role:

- **Project entry point**: identity, purpose, installation, usage, contribution (if applicable)
- **Catalog listing**: table of artifacts with name, purpose, and when-to-use
- **Component README**: what the component does, how to configure it, key design decisions

Omit sections that have no content. An empty "Contributing" section is worse than none.

### 3. Write Content

Apply the readme-style rule conventions:

- Imperative mood for instructions
- Active voice throughout
- One idea per sentence
- Specific over generic ("Requires Python 3.11+" not "recent Python")
- No social filler, hedging, encouragement, or satisfaction checks

For catalog READMEs, use a consistent table format:

```markdown
| Name | Description | When to Use |
|------|-------------|-------------|
| `artifact-name` | What it does | When to activate or invoke it |
```

### 4. Validate Cross-References

After writing, verify every reference in the document. See [references/cross-reference-patterns.md](references/cross-reference-patterns.md) for detailed procedures.

Quick validation:

- Every filesystem path exists (`Glob` or `ls` to verify)
- Every link target exists and has the correct relative path
- Counts in prose match actual item counts
- Names match actual filenames (hyphens vs. underscores, capitalization)

### 5. Review Against Filesystem

Final check: does the documentation accurately reflect the current filesystem state?

```bash
# List actual contents of a catalog directory
ls -1 <directory>/

# Compare against what the README lists
# Every item in ls output should appear in the README
# Every item in the README should appear in ls output
```

## Cross-Reference Validation

Cross-reference issues are the most common documentation bugs. They arise from file renames, additions, deletions, and restructuring that touch code but not documentation.

### What to Validate

| Check | How | Common Failure |
|-------|-----|----------------|
| **Path references** | Glob/ls each referenced path | File renamed or moved |
| **Link targets** | Verify relative path resolves | Directory restructured |
| **Artifact counts** | Count items, compare to prose | Item added/removed without updating count |
| **Name consistency** | Compare doc names to filenames | Hyphen vs. underscore mismatch |
| **Structure trees** | Compare tree to actual filesystem | New files or directories not reflected |
| **Table completeness** | Compare table rows to directory listing | Missing or phantom entries |

### Detection with Tools

```bash
# Find all markdown links in a file
grep -oP '\[.*?\]\(.*?\)' README.md

# Check if a referenced path exists
ls path/from/markdown/link

# Count items in a directory vs. stated count
ls -1 skills/ | wc -l
```

For detailed procedures and drift scenarios, load [references/cross-reference-patterns.md](references/cross-reference-patterns.md).

## Catalog Maintenance

Catalog READMEs list the artifacts in a directory. They are the most drift-prone documentation because they must stay synchronized with the filesystem.

### Completeness Check

1. List all artifacts in the directory (exclude `README.md` itself, hidden files, and non-artifact files)
2. Compare against the catalog table rows
3. Flag: **phantom entries** (in catalog but not on filesystem) and **missing entries** (on filesystem but not in catalog)

### Naming Consistency

- Use the exact filename (minus extension) when referencing artifacts
- Follow the project's naming convention (check for kebab-case, snake_case, etc.)
- If an artifact was renamed, every documentation reference must update in the same change

### Count Accuracy

When a catalog README states a count in prose ("Ten skills across three categories"), verify:

1. The stated number matches the actual artifact count
2. The category breakdown sums to the total
3. Category assignments are correct (each artifact in the right group)

### Table Format Consistency

All catalog tables within the same project should use the same column structure. Common patterns:

- Skills: Name, Description, When to Use
- Agents: Name, Purpose, Output, Background Safe
- Commands: Name, Description, Arguments
- Rules: Name, Scope, Description

## Documentation Freshness

Stale documentation is documentation that no longer matches reality. Detecting staleness requires comparing documentation claims against the current filesystem and codebase state.

### Freshness Indicators

| Indicator | What It Suggests | How to Check |
|-----------|-----------------|--------------|
| Referenced file does not exist | Rename or deletion without doc update | `ls` or `Glob` the path |
| Count mismatch | Items added or removed | Count directory contents vs. stated number |
| Structure tree differs from filesystem | Restructuring without doc update | Compare tree output to documented tree |
| Name format inconsistency | Naming convention change without doc update | Compare filenames to documented names |
| Missing new artifacts in catalogs | Recent additions not cataloged | Compare `git log --diff-filter=A` to catalog |
| Description does not match behavior | Artifact evolved without updating docs | Read the artifact and compare to description |

### Freshness Assessment Workflow

1. **Identify documentation files**: `Glob` for `**/README.md`, `ARCHITECTURE.md`, `CONTRIBUTING.md`, `CHANGELOG.md`
2. **Check modification dates**: compare documentation last-modified against the files it describes
3. **Validate structural claims**: filesystem paths, counts, names, trees
4. **Flag stale sections**: mark specific sections that need updating, not just "this file is stale"
5. **Prioritize by impact**: a stale project README matters more than a stale internal component README

### Git-Based Freshness

When git is available, use it to detect potential staleness:

```bash
# Files changed since the README was last modified
git log --since="$(git log -1 --format=%ci README.md)" --name-only --pretty=format: | sort -u

# Recently added files that might need catalog entries
git log --diff-filter=A --name-only --since="2 weeks ago" --pretty=format: | sort -u
```

If files in the documented directory changed after the README, the README may be stale.

## Checklist

Before completing documentation work:

**Structural Integrity**

- [ ] Every filesystem path referenced in the document exists
- [ ] Every markdown link target resolves correctly
- [ ] Counts in prose match actual item counts
- [ ] Structure trees reflect the current filesystem state
- [ ] Catalog tables include every artifact (no phantom or missing entries)

**Naming Consistency**

- [ ] Names in documentation match actual filenames
- [ ] Naming convention is consistent throughout (no hyphen/underscore mixing)
- [ ] Renamed artifacts have updated references across all documentation

**Content Quality**

- [ ] Writing follows readme-style rule conventions (imperative mood, active voice, no filler)
- [ ] Each section earns its place -- no empty or placeholder sections
- [ ] Documentation depth matches artifact complexity
- [ ] Examples are provided where the reader needs process knowledge

**Freshness**

- [ ] Documentation reflects the current filesystem state, not a prior version
- [ ] Recently added or removed artifacts are accounted for
- [ ] Description accuracy verified against actual artifact behavior
