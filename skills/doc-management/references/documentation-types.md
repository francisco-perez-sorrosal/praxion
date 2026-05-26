# Documentation Types

Per-type guidelines for project documentation. Each type has distinct conventions, required sections, and maintenance triggers. Back to [SKILL.md](../SKILL.md).

## Table of Contents

- [Project README](#project-readme)
- [Catalog README](#catalog-readme)
- [Architecture Documentation](#architecture-documentation)
- [Changelog](#changelog)
- [Contributing Guide](#contributing-guide)
- [API Documentation](#api-documentation)

## Project README

The project entry point. The first document a reader encounters.

### Purpose

Answer three questions in order: What is this? How do I use it? How do I contribute?

### Required Sections

1. **Title and description** -- what the project is and does (1-2 sentences)
2. **Installation / Setup** -- how to get it running
3. **Usage** -- how to use it (examples, commands, configuration)

### Optional Sections (include only when substantive)

- **Prerequisites** -- when the reader's background is uncertain
- **Architecture / Structure** -- when the project has non-obvious organization
- **Contributing** -- when the project accepts external contributions
- **License** -- when not obvious from repository metadata

### Conventions

- Lead with identity, not greetings ("Configuration repository for AI coding assistants" not "Welcome to our project!")
- Omit empty sections entirely
- Use code blocks for anything the reader will copy-paste
- Scale depth with complexity: a library needs API examples; a config repo needs structure explanation
- Add a TL;DR section when the README exceeds quick scanability

### Maintenance Triggers

Update the project README when:
- The project's purpose or scope changes
- Installation or setup steps change
- Key dependencies are added or removed
- The directory structure changes significantly

## Catalog README

Lists all artifacts in a directory. The most drift-prone documentation type.

### Purpose

Provide a scannable inventory of what exists in a directory with enough context for the reader to find what they need.

### Required Elements

1. **Count statement** -- how many artifacts exist ("Ten skills across three categories")
2. **Artifact table** -- every artifact listed with name, description, and relevant metadata
3. **Organization explanation** -- if artifacts are grouped, explain the grouping logic

### Table Format

Use consistent columns per artifact type:

| Artifact Type | Recommended Columns |
|---------------|-------------------|
| Skills | Name, Description, When to Use |
| Agents | Name, Purpose, Output, Key Skills |
| Rules | Name, Scope, Description |
| Commands | Name, Description, Arguments |

### Conventions

- List every artifact that exists on the filesystem (no phantom entries, no omissions)
- Use the exact filename (minus extension) as the artifact name
- Link to the artifact's directory or file
- Keep descriptions to one sentence -- they orient the reader, not replace reading the artifact
- When artifacts are categorized, ensure every artifact appears in exactly one category

### Maintenance Triggers

Update the catalog README when:
- An artifact is added to or removed from the directory
- An artifact is renamed
- An artifact's purpose changes significantly
- The categorization scheme changes

## Architecture Documentation

System design documentation for complex projects. Not every project needs this.

### When to Create

- The project has 3+ interacting components with non-obvious relationships
- Significant design decisions need to be recorded for future maintainers
- The codebase has patterns that are not self-evident from reading the code

### Typical Sections

1. **Overview** -- what the system does and its high-level structure
2. **Components** -- what each major piece does and how they interact
3. **Data flow** -- how information moves through the system
4. **Key decisions** -- architectural decisions with rationale and trade-offs
5. **Constraints** -- known limitations, performance boundaries, compatibility requirements

### Conventions

- Use diagrams (ASCII or Mermaid) for component relationships and data flow
- Record decisions with "Options considered / Decision / Trade-offs" structure
- Date significant decisions for future context
- Keep the document at the level of "why this structure" not "how this code works"

### Staleness Indicators

- Component names in the doc do not match actual module or directory names
- Described data flow does not match actual call patterns (check with Grep)
- Referenced files or modules no longer exist
- New major components exist that are not mentioned

### Dual-Audience Architecture (Agent Pipeline)

For projects using the Praxion agent pipeline (Standard/Full tier), architecture documentation is maintained as two purpose-built documents with distinct audiences and validation models:

**`.ai-state/DESIGN.md`** -- architect-facing design target. Abstracts above concrete code to define the space of valid implementations. Includes a Status column (Designed/Built/Planned/Deprecated) and Source stage metadata. Validated via design coherence (internal consistency, not strict code matching). Template at `skills/software-planning/assets/ARCHITECTURE_TEMPLATE.md`.

**`docs/architecture.md`** -- developer-facing navigation guide. Every component name and file path is verified against the codebase. Present-tense only, no planned items. Validated via code verification (every name and path resolves on disk). Template at `skills/doc-management/assets/ARCHITECTURE_GUIDE_TEMPLATE.md`.

The developer guide is derived from the architect doc -- it is a code-verified subset of the architect doc's Built components. Both share the same 8-section structure. The systems-architect creates both; the implementer updates both; the doc-engineer maintains the developer guide at pipeline checkpoints.

See the [architecture documentation methodology](../../software-planning/references/architecture-documentation.md) for the full lifecycle, section ownership, and validation models.

The static conventions above still apply to projects not using the agent pipeline.

## Changelog

Version history documenting what changed and when.

### When to Maintain

- Projects with versioned releases
- Projects where users need to know what changed between versions
- Projects with breaking changes that require migration guidance

### Format

```markdown
## [Version] - YYYY-MM-DD

### Added
- New feature descriptions

### Changed
- Modifications to existing functionality

### Fixed
- Bug fixes

### Removed
- Deprecated features that were removed
```

### Conventions

- Reverse chronological order (newest first)
- Group changes by type (Added, Changed, Fixed, Removed)
- Write for the user: explain what changed and why it matters, not implementation details
- Include migration notes for breaking changes
- Link to relevant issues or pull requests when available

### Maintenance Triggers

Update on every release. For pre-release projects, update on significant milestones.

## Contributing Guide

Contributor onboarding documentation.

### When to Include

- The project accepts external contributions
- The development workflow has non-obvious steps
- Contribution standards differ from common defaults

Do NOT create a contributing guide for internal-only or single-maintainer projects.

### Typical Sections

1. **Development setup** -- how to get a development environment running
2. **Workflow** -- branch strategy, PR process, review expectations
3. **Standards** -- code style, testing requirements, commit message format
4. **Where to contribute** -- good first issues, areas needing help

### Conventions

- Be specific about requirements ("run `pytest` before submitting" not "make sure tests pass")
- Link to relevant tools and their configuration files
- Keep it up to date with actual process -- a stale contributing guide is worse than none

## API Documentation

Interface contracts for libraries, services, and tools.

### When to Maintain

- The project exposes a public API (library, REST endpoint, CLI, plugin interface)
- Internal APIs are consumed by multiple teams or components
- The API has non-obvious usage patterns or constraints

### Approaches

| Approach | When to Use | Maintenance Cost |
|----------|-------------|-----------------|
| **Inline / docstring** | Libraries, functions, classes | Low (lives with code) |
| **Generated** (from code) | REST APIs, complex libraries | Medium (requires generation step) |
| **Hand-written** | CLI tools, configuration | Higher (manual sync required) |

### Conventions

- Include at least: endpoint/function signature, parameters, return value, example
- Show both success and error cases in examples
- Document default values and optional parameters explicitly
- For generated docs: include the generation command in the project README or contributing guide

### Staleness Indicators

- Function signatures in docs do not match actual code (use Grep to verify)
- Documented parameters include ones that were removed
- Examples produce errors when executed
- Missing recently added endpoints or functions
