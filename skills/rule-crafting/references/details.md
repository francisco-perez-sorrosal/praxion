# Rule Development Guide

Detailed guidance for writing, debugging, and maintaining rules. Back to [SKILL.md](../SKILL.md).

## Contents

- [Rule Loading Mechanics](#rule-loading-mechanics)
- [Writing Effective Rules](#writing-effective-rules)
- [Debugging Rule Loading](#debugging-rule-loading)
- [Rule Lifecycle](#rule-lifecycle)
- [Naming Best Practices](#naming-best-practices)

## Rule Loading Mechanics

### How Claude Discovers Rules

Claude discovers rules from two locations, scanning recursively:

| Location | Scope | Priority |
|----------|-------|----------|
| `.claude/rules/` | Project (shared via git) | Higher |
| `~/.claude/rules/` | Personal (all projects) | Lower |

Rules are loaded based on **relevance matching** -- Claude determines which rules to load based on:

1. **Filename and path** -- the primary signal. `git-conventions.md` loads when working on git-related tasks
2. **Content keywords** -- secondary signal from the rule's content
3. **Path frontmatter** -- rules with `paths:` only load when matching files are active
4. **Task context** -- what the user asked for, what files are open

### Loading Behavior

- Rules are loaded **all-or-nothing** -- the entire file content is injected. There is no partial loading.
- Rules without `paths:` frontmatter are **always-eligible** -- they can load in any context where their domain is relevant
- Rules with `paths:` frontmatter are **file-scoped** -- they only load when Claude is working on files matching the glob patterns
- Multiple rules can load simultaneously when multiple domains are relevant

### Token Budget

All always-loaded content (CLAUDE.md files + rules without `paths:`) shares a 25,000-token budget (failure-mode guardrail). Each new unconditional rule adds to every session's baseline cost.

| Content Type | Token Impact |
|-------------|-------------|
| `~/.claude/CLAUDE.md` | Always loaded |
| `.claude/CLAUDE.md` | Always loaded |
| Rules without `paths:` | Always eligible (loaded by relevance) |
| Rules with `paths:` | Loaded only when file patterns match |

## Writing Effective Rules

### Content Density

Rules should have the highest information-to-token ratio possible. Techniques:

**Tables over prose:**

```markdown
<!-- Bad: verbose prose -->
When writing Python code, use ruff for formatting. When writing TypeScript,
use prettier. When writing Go, use gofmt.

<!-- Good: dense table -->
| Language | Formatter | Linter |
|----------|-----------|--------|
| Python | ruff format | ruff check |
| TypeScript | prettier | eslint |
| Go | gofmt | golangci-lint |
```

**Bullet lists over paragraphs:**

```markdown
<!-- Bad: paragraph -->
Functions should be kept short, ideally under 30 lines. They should do
one thing and be nameable without conjunctions. If a function name
requires "and" or "or", it should be split.

<!-- Good: dense bullets -->
- Target: under 30 lines of logic
- One responsibility per function
- If the name needs "and" or "or", split it
```

**Examples over explanations:**

```markdown
<!-- Good: pattern + anti-pattern side by side -->
| Do | Don't | Why |
|----|-------|-----|
| `is_valid` | `check_validation_status` | Booleans read as yes/no questions |
| `fetch_user(id)` | `get_the_user_by_their_id(id)` | Concise verb phrases |
```

### Scope Management

A well-scoped rule covers **one coherent domain**. Test with this heuristic: can you describe the rule's domain in 3-5 words?

| Domain Description | Scope Quality |
|-------------------|---------------|
| "Git commit conventions" | Good -- single domain |
| "SQL naming rules" | Good -- single domain |
| "Coding style and testing and deployment" | Bad -- three domains, split it |
| "Everything about Python" | Bad -- too broad, split by concern |

### When to Use `paths:` Frontmatter

Use `paths:` when the rule is irrelevant outside specific file types or directories:

```yaml
---
paths:
  - "**/*.sql"
  - "migrations/**"
---

## SQL Conventions
...
```

**Good candidates for `paths:`**:
- Language-specific style rules (only relevant when editing that language)
- API-specific conventions (only relevant when editing API handlers)
- Test conventions (only relevant when editing test files)

**Bad candidates for `paths:`** (keep unconditional):
- Git commit conventions (relevant regardless of file being edited)
- Security constraints (relevant across all code)
- Error handling philosophy (cross-cutting concern)

### Glob Pattern Reference

| Pattern | Matches |
|---------|---------|
| `**/*.ts` | All TypeScript files, any depth |
| `src/api/**` | Everything under `src/api/`, any extension |
| `*.{ts,tsx}` | TypeScript and TSX files in the root |
| `tests/` | All files under `tests/` directory |
| `!**/*.test.ts` | Negation -- exclude test files (not all tools support this) |

## Debugging Rule Loading

### Verify a Rule Loads

Use `/memory` in Claude Code to see which rules are currently loaded. If a rule is not loading when expected:

1. **Check the filename** -- does it contain domain keywords that match the task?
2. **Check `paths:` frontmatter** -- are the glob patterns correct? Are they too narrow?
3. **Check file location** -- is it in `.claude/rules/` or `~/.claude/rules/`?
4. **Check YAML syntax** -- malformed frontmatter silently disables path scoping

### Common Loading Failures

| Symptom | Cause | Fix |
|---------|-------|-----|
| Rule never loads | Generic filename (`notes.md`) | Rename with domain prefix (`sql-naming.md`) |
| Rule never loads | Wrong directory | Move to `.claude/rules/` or `~/.claude/rules/` |
| Rule loads in wrong context | Missing `paths:` frontmatter | Add `paths:` to scope it |
| Rule loads but content seems ignored | Too many competing rules dilute attention | Consolidate or prioritize with clearer language |
| Path-scoped rule never loads | YAML syntax error in frontmatter | Validate `---` delimiters and YAML structure |

## Rule Lifecycle

### Creation

1. Notice a recurring correction or convention Claude should know
2. Check: does this belong in CLAUDE.md, a rule, or a skill? (See decision table in SKILL.md)
3. Write the rule following content guidelines
4. Place in the correct location and verify loading

### Maintenance

- **Audit periodically**: Are existing rules still relevant? Remove stale rules.
- **Monitor token budget**: Use `wc -c` on all unconditional rules to check total size
- **Merge related rules**: When two rules always load together and cover overlapping topics, merge them
- **Split overloaded rules**: When a rule covers unrelated concerns, split by domain

### Migration from CLAUDE.md

When CLAUDE.md grows too large, extract domain-specific sections into rules:

1. Identify a cohesive section (e.g., "SQL Conventions")
2. Create `sql-conventions.md` in `.claude/rules/`
3. Move the content, adding `paths:` frontmatter if appropriate
4. Remove the section from CLAUDE.md
5. Verify the rule loads correctly with `/memory`

### Migration from Skills

When a skill contains declarative constraints that should always be available:

1. Extract the declarative content (conventions, constraints)
2. Leave the procedural content (workflows, step-by-step) in the skill
3. Create a rule with the extracted content
4. Add a reference from the rule to the skill for deeper guidance

## Naming Best Practices

The filename is the single most important factor in whether Claude loads the rule at the right time.

### Effective Naming Patterns

| Pattern | Example | When |
|---------|---------|------|
| `{tool}-{conventions}` | `git-conventions.md` | Tool-specific conventions |
| `{language}-{aspect}` | `python-imports.md` | Language-specific rules |
| `{domain}-{constraint}` | `api-error-handling.md` | Domain constraints |
| `{concern}-{protocol}` | `agent-coordination-protocol.md` | Cross-cutting protocols |

### Names to Avoid

| Bad Name | Problem | Better Name |
|----------|---------|-------------|
| `rules.md` | Self-referential, matches nothing | `coding-conventions.md` |
| `important.md` | Not a domain | `security-constraints.md` |
| `notes.md` | Not a domain | `deployment-conventions.md` |
| `todo.md` | Not declarative knowledge | Move to a tracking system |
| `style.md` | Too vague | `coding-style.md` or `writing-style.md` |

## Anti-Patterns and Fixes

| Anti-Pattern | Problem | Fix |
|-------------|---------|-----|
| Splitting into main + reference | Reference file will not be loaded | Keep rule self-contained |
| Writing procedures ("Step 1: ...") | Rules are knowledge, not workflows | Move procedure to a skill or command |
| Including all related context | Bloats token budget, dilutes other rules | Focus on constraints, link to skills for depth |
| Duplicating CLAUDE.md content | Redundant, risk of conflict | Keep in one place only |
| Extremely long rules (500+ lines) | Token cost, diluted attention | Compress (tables), split by sub-domain, or move to a skill |
| Rules that say "always do X" | If it is truly always, it belongs in CLAUDE.md | Move to CLAUDE.md or scope with `paths:` |
