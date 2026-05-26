# Cross-Reference Patterns

Detailed procedures for validating cross-references in project documentation. Covers filesystem path validation, catalog synchronization, and common drift scenarios. Back to [SKILL.md](../SKILL.md).

## Table of Contents

- [Filesystem Path Validation](#filesystem-path-validation)
- [Catalog Sync Patterns](#catalog-sync-patterns)
- [Name Consistency Checks](#name-consistency-checks)
- [Count Validation](#count-validation)
- [Common Drift Scenarios](#common-drift-scenarios)
- [Automated Checking Approaches](#automated-checking-approaches)

## Filesystem Path Validation

Every path referenced in documentation must resolve to an existing file or directory.

### Procedure

1. Extract all paths from the document:
   - Markdown links: `[text](path/to/file)`
   - Code blocks referencing paths: `skills/doc-management/SKILL.md`
   - Structure trees: indented directory listings
   - Prose references: "see `path/to/file` for details"

2. For each path, verify existence:
   ```bash
   # Single path check
   ls path/to/referenced/file

   # Batch check: extract markdown links and verify
   grep -oP '\]\(\K[^)]+' README.md | while read -r path; do
     [ -e "$path" ] || echo "MISSING: $path"
   done
   ```

3. Classify results:
   - **Valid**: path exists, content matches description
   - **Phantom**: path in documentation but not on filesystem (deletion or rename)
   - **Broken**: link syntax is correct but target moved or was restructured

### Common Path Failures

| Pattern | Cause | Fix |
|---------|-------|-----|
| `skills/old-name/` referenced | Skill directory renamed | Update to new directory name |
| `commands/create_worktree.md` | Naming convention changed (underscore to hyphen) | Update to `commands/create-worktree.md` |
| Relative path wrong depth | File moved to different nesting level | Recalculate relative path |
| Missing trailing slash on directory | Inconsistent convention | Standardize: no trailing slash for files, optional for directories |

## Catalog Sync Patterns

Catalog READMEs must list every artifact in their directory. Sync failures create phantom entries (listed but absent) or missing entries (present but unlisted).

### Full Sync Procedure

1. **Inventory the filesystem**:
   ```bash
   # List all artifact directories (for skills, agents, etc.)
   ls -1d skills/*/

   # List all artifact files (for rules, commands)
   ls -1 rules/swe/*.md rules/writing/*.md
   ```

2. **Inventory the catalog**: extract every artifact name from the README's tables and lists

3. **Diff the two sets**:
   - Items in filesystem but not in catalog = **missing entries** (add them)
   - Items in catalog but not on filesystem = **phantom entries** (remove them)

4. **Verify descriptions**: for each catalog entry, confirm the description still matches the artifact's actual behavior

### Catalog Table Patterns

Maintain consistent column structure per artifact type:

```markdown
<!-- Skills catalog -->
| Skill | Description | When to Use |
|-------|-------------|-------------|

<!-- Agents catalog -->
| Agent | Purpose | Output | Background Safe |
|-------|---------|--------|-----------------|

<!-- Rules catalog -->
| Rule | Scope | Description |
|------|-------|-------------|

<!-- Commands catalog -->
| Command | Description | Arguments |
|---------|-------------|-----------|
```

## Name Consistency Checks

Names in documentation must match actual filenames exactly. Mismatches usually come from naming convention changes that updated files but not documentation.

### What to Check

- **Hyphens vs. underscores**: `create-worktree` vs. `create_worktree`
- **Capitalization**: `README.md` vs. `readme.md`
- **Extension presence**: `sentinel` vs. `sentinel.md`
- **Directory vs. file**: `skills/doc-management/` vs. `skills/doc-management/SKILL.md`

### Detection

```bash
# Extract names from a markdown table column and compare to filesystem
# Adjust the awk field number for the column containing artifact names
grep '|' README.md | awk -F'|' '{print $2}' | tr -d ' `' | sort > /tmp/doc_names
ls -1 <directory>/ | sort > /tmp/fs_names
diff /tmp/doc_names /tmp/fs_names
```

## Count Validation

Prose counts ("Ten skills across three categories") must match reality.

### Procedure

1. Find count claims in the document (search for number words and digits)
2. Count the actual items:
   ```bash
   # Count skills
   ls -1d skills/*/ | wc -l

   # Count agents
   ls -1 agents/*.md | grep -v README | wc -l

   # Count items in a specific category (requires reading the README)
   ```
3. Compare stated count to actual count
4. If the document breaks items into categories, verify each category count sums to the total

### Common Count Failures

- New artifact added without incrementing the count
- Artifact removed without decrementing the count
- Category reassignment without updating both old and new category counts
- Prose says "Seven" but table has 8 rows

## Common Drift Scenarios

Real-world examples of documentation drift, based on patterns observed in project maintenance.

### Scenario: Phantom Skill Entries

**Symptom**: README lists skills that do not exist on the filesystem.
**Cause**: Skills were planned or discussed but never created, or were removed during cleanup.
**Detection**: Cross-reference skill names in README against `ls -1d skills/*/`.
**Fix**: Remove phantom entries from all sections (structure tree, category lists, summary counts).

### Scenario: Naming Convention Migration

**Symptom**: Documentation uses old naming convention (e.g., underscores) while files use new convention (e.g., hyphens).
**Cause**: Files were renamed to follow a new convention, but documentation references were not updated.
**Detection**: Compare documented names character-by-character against actual filenames.
**Fix**: Update all references to use the current filename. Search across all documentation files, not just the one being reviewed.

### Scenario: Missing New Agent in Catalog

**Symptom**: Agent catalog lists N agents but N+1 exist. New agent is functional but undocumented.
**Cause**: Agent was added as part of a feature but the catalog README was not updated in the same change.
**Detection**: Compare `ls -1 agents/*.md | grep -v README | wc -l` to the stated count.
**Fix**: Add the agent to the catalog table, update the count, add to any pipeline diagrams if applicable.

### Scenario: Structure Tree Drift

**Symptom**: The directory structure tree in a README shows outdated file layout.
**Cause**: Files and directories were added or reorganized without updating the tree.
**Detection**: Compare the documented tree against actual `find` or `ls -R` output.
**Fix**: Regenerate the structure tree from the current filesystem. Preserve intentional omissions (e.g., hiding build artifacts) but document what is excluded.

## Automated Checking Approaches

Tools and patterns for systematic cross-reference validation.

### Using Glob

```bash
# Verify all skill directories referenced in README exist
# Extract directory names from README, then glob for each
```

Use `Glob` to find files matching a pattern (e.g., `skills/*/SKILL.md`) and compare against documented entries.

### Using Grep

```bash
# Find all markdown links in a file
grep -oP '\[.*?\]\(.*?\)' README.md

# Find all backtick-quoted paths
grep -oP '`[a-zA-Z0-9_./-]+`' README.md

# Find count words
grep -oiP '(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)\s+(skills?|agents?|commands?|rules?)' README.md
```

### Using Bash

```bash
# Full catalog sync check for a directory
diff <(ls -1d skills/*/ | xargs -I{} basename {} | sort) \
     <(grep -oP '`\K[a-z-]+(?=`)' skills/README.md | sort)
```

### Validation Priority

1. **Project README** -- highest visibility, most cross-references
2. **Catalog READMEs** -- most drift-prone due to frequent artifact changes
3. **Architecture docs** -- less frequent changes but high impact when stale
4. **Component READMEs** -- lowest priority, smaller blast radius
