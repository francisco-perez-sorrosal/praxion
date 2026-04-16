---
name: rule-crafting
description: Creating and managing rules -- contextual domain knowledge
  files loaded automatically based on relevance. Covers rule structure, path-specific
  rules, naming for relevance matching, content guidelines, and the rules-vs-skills-vs-CLAUDE.md
  decision model. Use when creating new rules, updating existing rules, debugging
  rule loading, organizing rule files, or deciding whether something belongs in a
  rule vs skill vs CLAUDE.md. Also covers Claude Code rule authoring, auto-loaded
  rule mechanics, and rule debugging techniques.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
---

# Rules

Guide for creating effective, contextual rules.

**Satellite files** (loaded on-demand):
- [REFERENCE.md](REFERENCE.md) -- complete rule examples, path-specific patterns, migration strategies
- [../skill-crafting/references/artifact-naming.md](../skill-crafting/references/artifact-naming.md) -- naming conventions for all artifact types

## What Are Rules

**Rules** are contextual domain knowledge files that Claude loads automatically based on relevance — no explicit invocation needed.

- Loaded opportunistically by task, active files, and semantic matching
- **All-or-nothing loading** — when a rule is triggered, its entire file content is injected into context. There is no partial or progressive loading within a single rule file. This is why keeping each file focused matters
- Declarative (constraints and conventions), not procedural (workflows)
- One `.md` file per coherent domain area
- Project or personal scope
- Keep rules concise — they share the always-loaded token budget with CLAUDE.md

## File Locations

**Project rules** (shared with team):
```
.claude/rules/<rule-name>.md
```

**Personal rules** (across all projects):
```
~/.claude/rules/<rule-name>.md
```

| Scope | Path | Shared | Priority |
|-------|------|--------|----------|
| Project | `.claude/rules/` | Via git | Higher |
| Personal | `~/.claude/rules/` | No | Lower |

Project rules take precedence over personal rules with the same name.

## Memory Hierarchy

| Priority | Source | Loading |
|---|---|---|
| 1 (highest) | Managed policy (enterprise) | always |
| 2 | Project memory (`.claude/CLAUDE.md`) | always |
| 3 | Project rules (`.claude/rules/`) | when relevant |
| 4 | User memory (`~/.claude/CLAUDE.md`) | always |
| 5 (lowest) | Project local (`.claude/CLAUDE.local.md`) | gitignored override |

Rules override user memory but yield to project memory and managed policy. See `~/.claude/CLAUDE.md` and `rules/CLAUDE.md` for full coverage. Use `/memory` in Claude Code to inspect loaded rules.

## Rule File Structure

Use `##` (h2) as the top-level heading — rules are injected into a larger context, so h1 would conflict with the surrounding document structure.

### Basic Rule

```markdown
## SQL Conventions

- Always use snake_case for column names
- No SELECT * — enumerate columns explicitly
- Explicit JOIN syntax only (no implicit joins)
- Foreign keys must be indexed
```

No frontmatter needed for rules that should load whenever their domain is relevant.

### Path-Specific Rule

Add `paths` frontmatter to restrict loading to specific file patterns:

```markdown
---
paths:
  - "src/api/**/*.ts"
  - "src/api/**/*.tsx"
---

## API Error Handling

- All API handlers must return structured error responses
- Use the ApiError class from `src/lib/errors.ts`
- Never expose internal error details to clients
```

The rule loads only when Claude is working on files matching the glob patterns.

**Glob syntax**:
- `**/*.ts` — all TypeScript files recursively
- `src/api/**` — everything under `src/api/`
- `*.{ts,tsx}` — brace expansion for multiple extensions
- `tests/` — all files under `tests/` directory

## Directory Organization

Scale organization to project complexity. Choose the simplest tier that fits.

| Tier | When | Structure | Example |
|---|---|---|---|
| **Flat** | <10 rules, no language divergence | All rules directly under `.claude/rules/` | `sql.md`, `security.md`, `git-commit-format.md` |
| **Layered** | Multiple languages with divergent conventions | `common/` + `<language>/` subdirectories | See worked example below |
| **Path-Scoped** | Granular per-path targeting needed | Rules with `paths` globs (see [REFERENCE.md](REFERENCE.md)) | `paths: ["src/api/**/*.ts"]` |

Claude loads rules recursively from subdirectories. Language-specific files extend common ones — use the pattern: *"This file extends `common/coding-style.md` with TypeScript-specific conventions."*

**Layered worked example**:

```
.claude/rules/
├── common/              # Universal rules (always loaded when relevant)
│   ├── coding-style.md
│   ├── testing.md
│   └── security.md
├── typescript/          # Extend common with TS specifics
│   ├── coding-style.md
│   └── testing.md
└── python/
    ├── coding-style.md
    └── testing.md
```

## Naming Convention

Pattern: `<domain>-<rule-intent>.md`

The `<domain>` prefix aids Claude's relevance matching. The `<rule-intent>` suffix clarifies scope within the domain. Together they make rules discoverable across any field.

```
Software:     git-commit-format.md, sql-naming.md, api-error-handling.md
Security:     auth-token-handling.md, secrets-management.md
Writing:      technical-writing-style.md, documentation-tone.md
Business:     pricing-model-constraints.md, compliance-gdpr.md
Research:     citation-format.md, data-collection-ethics.md
```

**Naming principles**:
- Lowercase, hyphen-separated
- Domain-oriented — describe the subject area, not the action
- Specific — `git-conventions.md` not `commit.md`
- No generic names — `important.md`, `notes.md`, `stuff.md` hurt relevance matching

## Writing Rule Content

### Be Declarative

State what should be true, not steps to follow. Procedural content belongs in a Skill, not a rule.

| Good (constraints) | Bad (procedure — move to Skill) |
|---|---|
| `- Column names use snake_case` | `Step 1: Open the query editor` |
| `- Foreign keys must be indexed` | `Step 2: Write the SELECT statement` |
| `- No implicit joins` | `Step 3: Make sure to use snake_case` |

### Content Guidelines

- **Be specific** — "Use `snake_case` for column names" not "Use good naming"
- **Group by domain** — one file per coherent domain area
- **Include examples** — show correct and incorrect patterns when clarity demands it
- **Explain the _why_** — when a constraint isn't self-evident, briefly state the rationale
- **Token budget awareness** — rules are eagerly loaded within scope (personal = all projects, project = that project), adding to the baseline token cost of every conversation and agent spawn. The ecosystem target is 15,000 tokens for all always-loaded content (CLAUDE.md files + rules). Keep rules concise; if one grows too large, compress it (tables over prose, remove redundancy) or move procedural content to a skill — but never split into main + reference files (see Self-Containment Constraint below)

### Customization Sections

For rules that cover domains with project variation (coding style, testing, security, deployment), use `### [CUSTOMIZE] <Topic>` sub-sections — placed at the end after universal content — to separate universal conventions from project-specific overrides. Use HTML comment placeholders (`<!-- -->`) for author guidance so they don't affect rule semantics. Fully universal rules (e.g., commit format) omit customization entirely.

See [REFERENCE.md#customization-section-examples](REFERENCE.md#customization-section-examples) for worked patterns.

## Rules vs Skills vs CLAUDE.md

Ask: **"Is this something Claude should _know_, or something Claude should _do_?"**

| Question | Answer | Use |
|----------|--------|-----|
| Should Claude always remember this? | Yes | `CLAUDE.md` |
| Should Claude know this in certain contexts? | Yes | Rule |
| Should Claude perform this as a workflow? | Yes | Skill |

| Need | Wrong layer | Right layer |
|------|-------------|-------------|
| "Always use snake_case in Python" | Rule (too lightweight) | `CLAUDE.md` |
| "SQL column naming, join conventions" | `CLAUDE.md` (too verbose) | Rule |
| "How to create a git commit with conventions" | Rule (procedural) | Skill or Command |
| "Commit messages must use imperative mood" | Skill (not procedural) | Rule |
| "Security checklist for auth code" | `CLAUDE.md` (too detailed, not always relevant) | Rule |

## Creation Workflow

1. **Identify** — recognize recurring contextual knowledge Claude needs
2. **Decide layer** — is this CLAUDE.md, a rule, or a skill? (see decision table above)
3. **Name** — use `<domain>-<rule-intent>.md` pattern for relevance matching
4. **Organize** — choose flat, layered, or path-scoped placement
5. **Write** — declarative constraints, not procedures; include examples
6. **Place** — project `.claude/rules/` or personal `~/.claude/rules/`
7. **Verify** — use `/memory` to confirm the rule loads in the expected context
8. **Iterate** — refine based on Claude's behavior; adjust scope, naming, or content
   - **Split** when a rule file covers unrelated concerns (e.g., SQL naming + API auth in one file)
   - **Merge** when two files overlap heavily and are always loaded together
   - **Don't over-split** — closely related topics (commit format + commit rules) can coexist based on reuse patterns
   - Keep each file focused on a single coherent domain

## Self-Containment Constraint

**Rules must be fully self-contained.** Each rule file must carry all its content — never split a rule into a main file plus a reference/satellite file.

**Why:** Only `.md` files directly in `~/.claude/rules/` (and its subdirectories) are loaded by Claude. If a rule references a companion file (e.g., `references/details.md`) that isn't installed alongside it, that content is unreachable in every project except the source repository. The reference becomes a dangling link and the rule loses semantics.

**What this means in practice:**
- Do not create `references/` subdirectories under rules
- Do not use "see `<path>` for details" patterns that point to non-rule files
- If a rule is too large, compress it (tables over prose, remove redundancy) or split it into two independent rules by domain — never into main + supplement
- Skills can use reference files (they control their own loading); rules cannot

**Escape hatch:** Rules can point to skill reference files for supplementary depth. Skills have base path injection on activation, making their reference files resolvable cross-project. A rule can say "When working on UI components, load the `ui-change` skill" — the rule stays lean and the heavy instructions live in the skill's progressively-disclosed reference files. This is the recommended pattern when a rule needs supporting material that exceeds self-containment limits

## Anti-Patterns

| Anti-Pattern | Problem | Fix |
|-------------|---------|-----|
| Generic filenames (`rules1.md`, `stuff.md`) | Hurts relevance matching | Use `<domain>-<rule-intent>.md` |
| Procedural content (step-by-step) | Rules are knowledge, not workflows | Move to a Skill or Command |
| Overly broad rules (everything in one file) | Loads unnecessary context | Split by domain |
| Over-splitting (one constraint per file) | File proliferation, hard to maintain | Group related constraints |
| Splitting into main + reference file | Reference file won't be installed; content lost in other projects | Keep rules self-contained |
| "Always do X" directives | Belongs in always-loaded context | Move to `CLAUDE.md` |
| Duplicating CLAUDE.md content | Redundant, may conflict | Keep in one place only |
| Referencing rule filenames in commands | Filenames aren't invocable | Use semantic hints instead |

## Resources

- [Official Documentation](https://docs.anthropic.com/en/docs/claude-code/memory#rules) -- rules section of Claude Code memory docs
- [rules/README.md](../../rules/README.md) -- user-facing documentation for rules in this repository
- Extended examples: See [REFERENCE.md](REFERENCE.md) for complete rule patterns and migration strategies
