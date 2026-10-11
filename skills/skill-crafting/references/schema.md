# Skill YAML Frontmatter Schema

Complete reference for SKILL.md frontmatter fields, validation rules, and examples. Back to [SKILL.md](../SKILL.md).

## Contents

- [Frontmatter Format](#frontmatter-format)
- [Field Reference](#field-reference) -- the portable core fields
- [Claude Code Frontmatter Superset](#claude-code-frontmatter-superset) -- the fields Claude Code adds, and Praxion's staleness fields
- [Validation Rules](#validation-rules) -- how to run the validator, its exit status, every error and warning it prints
- [Complete Example](#complete-example)
- [Field Interaction Matrix](#field-interaction-matrix)
- [Frontmatter vs Body](#frontmatter-vs-body)

## Frontmatter Format

SKILL.md files begin with a YAML frontmatter block delimited by `---` lines:

```markdown
---
name: my-skill
description: What this skill does and when to use it.
---

# Skill Title

Skill body content...
```

The frontmatter is parsed as YAML. The body after the closing `---` is Markdown. The parser requires exact `---` delimiters (no extra whitespace, no alternative delimiters like `...`).

## Field Reference

### `name` (Required)

The skill's unique identifier. Must match the directory name exactly.

| Constraint | Rule |
|-----------|------|
| Type | String |
| Length | 1-64 characters |
| Characters | Lowercase letters, digits and hyphens only |
| Pattern | `^[a-z][a-z0-9]*(-[a-z0-9]+)*$` |
| Starts with a letter | `1st-skill` is invalid |
| No consecutive hyphens | `my--skill` is invalid |
| No leading/trailing hyphens | `-my-skill` and `my-skill-` are invalid |
| Directory match | Must equal the containing directory name |

```yaml
# Valid
name: python-development
name: code-review
name: mcp-crafting
name: refactoring

# Invalid
name: Python-Development    # Uppercase
name: my--skill             # Consecutive hyphens
name: -my-skill             # Leading hyphen
name: my_skill              # Underscore
name: my skill              # Space
```

### `description` (Required)

The primary trigger for skill activation. Claude reads this field to decide whether to load the skill. Write it as a trigger specification, not a summary.

| Constraint | Rule |
|-----------|------|
| Type | String |
| Length | 1-1024 characters |
| Perspective | Third person (injected into system prompt) |

**Structure the description in three parts:**

1. **What it does** -- the capability in one sentence
2. **When to trigger** -- specific contexts and tasks
3. **Key terms** -- domain vocabulary for matching

```yaml
# Good: specific triggers, domain terms
description: >
  Creating and configuring agents (subagents) with effective prompts,
  tool permissions, and lifecycle hooks. Use when building custom agents,
  designing agent workflows, spawning subagents, delegating tasks via
  the Task tool, defining subagent_type, or using the /agents command.

# Bad: vague, no trigger terms
description: Helps with agents

# Bad: too long, essay-style (wastes the 1024 char limit on background)
description: >
  This skill provides comprehensive guidance on the theory and practice
  of building agents within the Claude Code ecosystem, covering all
  aspects from basic configuration to advanced patterns...
```

**Multi-line descriptions** use YAML folded scalar (`>`) or literal scalar (`|`):

```yaml
# Folded scalar (>) -- newlines become spaces
description: >
  First line and second line
  become a single paragraph.

# Literal scalar (|) -- newlines preserved
description: |
  First line stays on its own.
  Second line is separate.
```

Folded scalar (`>`) is the convention for descriptions -- it produces readable YAML while rendering as a single paragraph.

### `license` (Optional)

License for the skill's content and bundled code.

| Constraint | Rule |
|-----------|------|
| Type | String |
| Common values | `MIT`, `Apache-2.0`, `BSD-3-Clause`, `proprietary` |

```yaml
license: MIT
```

Reference a bundled LICENSE file when the license text is long: `license: See LICENSE`.

### `compatibility` (Optional)

Environment requirements or tool compatibility declarations.

| Constraint | Rule |
|-----------|------|
| Type | String |
| Length | Max 500 characters |

```yaml
# Tool compatibility
compatibility: Claude Code

# Tool + version
compatibility: Claude Code 1.0+

# Multiple tools
compatibility: Claude Code, Cursor

# System requirements
compatibility: Requires Python 3.11+, Node.js 18+
```

### `metadata` (Optional)

Arbitrary key-value pairs for additional information. No predefined schema -- use for skill-specific configuration.

| Constraint | Rule |
|-----------|------|
| Type | Object (key-value pairs) |
| Keys | Strings |
| Values | Strings, numbers, booleans, or arrays |

```yaml
metadata:
  owner: platform-team
  upstream-docs: https://docs.example.com/llms.txt
  version: "2.0"
  languages: [python, typescript]
```

### `allowed-tools` (Optional, Experimental)

Pre-approved tools the skill may use. When specified, Claude can use these tools without prompting for permission during skill execution.

| Constraint | Rule |
|-----------|------|
| Type | Array of strings |
| Values | Tool names as recognized by the host (e.g., `Read`, `Write`, `Bash`) |

```yaml
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
```

Tool names are host-specific. Claude Code tools include: `Read`, `Write`, `Edit`, `Glob`, `Grep`, `Bash`, `Agent` (formerly `Task`), `WebFetch`, `WebSearch`.

In Claude Code `allowed-tools` **pre-approves** the listed tools (no permission prompt while the skill is active) — it does **not** restrict; every other tool stays callable, governed by your permission settings. Behavior still varies across non-Claude hosts, so treat it as a Claude Code field for portable skills.

## Claude Code Frontmatter Superset
<!-- last-verified: 2026-10-11 -->

The fields above are the portable Agent Skills core. Claude Code reads them **plus** the fields below. Since custom commands [merged into skills](https://code.claude.com/docs/en/skills), a user-invoked workflow is a skill carrying these same fields — see [user-invoked-skills.md](user-invoked-skills.md) for the user-invoked authoring angle.

| Field | Type | Purpose / constraint |
|-------|------|----------------------|
| `when_to_use` | String | Extra trigger phrases / example requests, appended to `description` in the listing. **Combined `description` + `when_to_use` is truncated at 1,536 chars** (`maxSkillDescriptionChars` setting); put the key use case first. |
| `disable-model-invocation` | Boolean | `true` = only the user can invoke (`/name`); the description leaves model context, and the skill cannot be preloaded into subagents. Default `false`. Use for side-effecting actions. |
| `user-invocable` | Boolean | `false` = hidden from the `/` menu; Claude can still auto-load it. Default `true`. For background knowledge that isn't a user action. |
| `paths` | String / list | Glob patterns scoping auto-activation to matching files (same format as path-specific rules). |
| `context` | String | `fork` runs the skill body as the prompt for a forked subagent. |
| `agent` | String | Subagent type used when `context: fork` (e.g. `Explore`, `Plan`, `general-purpose`, or a custom agent). Default `general-purpose`. |
| `background` | Boolean | Only with `context: fork`. `false` waits for the forked subagent's result in the invoking turn instead of running it in the background. Default `true`. Needs Claude Code 2.1.218 or later. |
| `model` | String | Model while the skill is active (`inherit` keeps the session model). Override lasts the current turn only. |
| `effort` | String | `low`/`medium`/`high`/`xhigh`/`max` while active; overrides session effort. |
| `disallowed-tools` | String / list | Tools removed from Claude's pool while the skill is active (e.g. `AskUserQuestion` for an autonomous loop); the restriction clears with the next user message. Space- or comma-separated string, or a list. |
| `argument-hint` | String | Autocomplete hint, e.g. `[issue-number]` or `[filename] [format]`. |
| `arguments` | String / list | Named positional args for `$name` substitution; names map to positions in order. |
| `hooks` | Object | Hooks registered when the skill is invoked; they keep running for the rest of the session. `once: true` on a hook removes it after its first successful run. |
| `shell` | String | `bash` (default) or `powershell` for bang-prefixed inline injection and fenced ` ```! ` blocks. |

**Praxion staleness fields** (validated by `validate.py`, per `rules/swe/staleness-policy.md`):

| Field | Type | Purpose |
|-------|------|---------|
| `staleness_sensitive_sections` | List | Bare h2/h3 heading texts (in `SKILL.md` or any `references/`/`contexts/` file) the sentinel tracks for drift via `<!-- last-verified: YYYY-MM-DD -->` markers. |
| `staleness_threshold_days` | Number | Per-skill staleness threshold override (global default 120; use 60 for fast-moving API surfaces). |

**Argument substitution & dynamic context** (skill body, Claude Code): `$ARGUMENTS`, `$ARGUMENTS[N]` / `$N`, `$name`; `${CLAUDE_SESSION_ID}`, `${CLAUDE_EFFORT}`, `${CLAUDE_SKILL_DIR}`; and bang-prefixed backtick-quoted dynamic injection (runs once, before Claude sees the body) with a fenced ` ```! ` block for multi-line. Full reference: [Claude Code skills docs](https://code.claude.com/docs/en/skills).

## Validation Rules

`scripts/validate.py` checks the frontmatter and entry page of a skill. It prints each finding as a bullet under a `FAILED` (errors) or `WARNINGS` header.

The validator's accepted-field list lags the harness; see [Invocation Modes](user-invoked-skills.md#invocation-modes) for the unknown-field findings to expect.

### Running the Validator

```bash
# One skill
python3 skills/skill-crafting/scripts/validate.py skills/my-skill/

# Every skills/<name>/ in the repository that holds the script
python3 skills/skill-crafting/scripts/validate.py --all
```

The exit status is 0 if and only if there is no error. Warnings never change it: a skill with warnings alone exits 0 and prints `PASSED` with the warning count. An argument that is not a directory prints `Error: <path> is not a directory` and exits 1; any other argument list prints `Usage: <script> <skill-directory> | --all` and exits 1.

### Errors

Each error marks the skill as malformed. A skill without `SKILL.md` stops at the first row; a skill without a usable frontmatter block stops at the next three rows; otherwise every error below is reported together.

| Check | Message printed |
|-------|-----------------|
| No `SKILL.md` in the directory | `SKILL.md not found in <directory>` |
| File does not start with `---` | `Frontmatter missing: file must start with '---'` |
| No closing `---` line | `Frontmatter missing closing '---' delimiter` |
| Nothing between the delimiters | `Frontmatter is empty` |
| A frontmatter line that is neither `key: value`, an indented continuation, nor blank | `Unexpected frontmatter line: 'text'` |
| A top-level key outside the [Field Reference](#field-reference) and [superset](#claude-code-frontmatter-superset) tables | `Unknown frontmatter fields: a, b` |
| `name` absent | `Missing 'name' in frontmatter (required)` |
| `name` differs from the directory name | `'name' ('X') does not match directory name ('Y')` |
| `name` over 64 characters | `'name' exceeds 64 chars (got N)` |
| `name` contains a run of hyphens | `'name' must not contain consecutive hyphens (got 'X')` |
| `name` does not match `^[a-z][a-z0-9]*(-[a-z0-9]+)*$` | `'name' must be lowercase letters/digits/hyphens, no consecutive hyphens, no leading/trailing hyphens (got 'X')` |
| `description` absent | `Missing 'description' in frontmatter (required)` |
| `description` empty | `'description' is empty` |
| `description` over 1024 characters | `'description' exceeds 1024 chars (got N)` |
| `description` contains `<` or `>` | `'description' must not contain angle brackets (< or >)` |
| `compatibility` over 500 characters | `'compatibility' exceeds 500 chars (got N)` |

A run of hyphens draws its own message. The pattern is matched with each run collapsed to one hyphen, so `a--b` draws the hyphen message alone while `A--b` draws both.

### Warnings

Each warning reads `<hazard> — <fix>`. The skill still loads; the hazard is one that bites later.

| Hazard | Message printed |
|--------|-----------------|
| `SKILL.md` over 500 lines | `SKILL.md is N lines, over 500 — move depth into references/` |
| `argument-hint` with no value | `empty argument-hint — omit the key or give a quoted value` |
| `argument-hint` value not quoted (YAML reads an unquoted `[path]` as a list) | `unquoted argument-hint — quote the value` |
| `disable-model-invocation: true` with a `description` spanning several lines | `user-only skill's description spans N lines — write it on one line` |
| `arguments` declared but the body has no `$ARGUMENTS`, `$N` or `$<name>` placeholder | `arguments declared but the body has no placeholder — add $ARGUMENTS or $<name>` |

## Complete Example

```yaml
---
name: testing-strategy
description: >
  Language-independent testing knowledge: test strategy selection, test pyramid,
  mocking philosophy, fixture and test data patterns, test isolation, coverage
  approach, property-based testing, and naming conventions. Use when deciding
  test strategy, choosing between unit and integration and e2e tests, designing
  mocking boundaries, architecting fixtures, evaluating test coverage philosophy,
  or assessing property-based testing applicability. Also activates for test
  architecture, testing methodology, test pyramid, and test isolation questions.
allowed-tools: [Read, Glob, Grep, Bash]
compatibility: Claude Code
---

# Testing Strategy

Skill body content here...
```

## Field Interaction Matrix

| Field | Affects Activation | Affects Behavior | Visible to User |
|-------|-------------------|-----------------|-----------------|
| `name` | No (directory name is the identity) | No | Yes (in `/skills` list) |
| `description` | **Yes** (primary trigger) | No | Yes (in `/skills` list) |
| `license` | No | No | Yes (metadata) |
| `compatibility` | Weak (may filter in multi-tool setups) | No | Yes (metadata) |
| `metadata` | No | Skill-specific | Yes (metadata) |
| `allowed-tools` | No | **Yes** (pre-approves tool use) | No |

## Frontmatter vs Body

The frontmatter and body serve different purposes in the progressive disclosure model:

| Aspect | Frontmatter | Body |
|--------|-------------|------|
| **When loaded** | At startup (all skills) | On activation (matched skills only) |
| **Token cost** | ~100 tokens per skill (name + description) | Full content (target <5000 tokens) |
| **Purpose** | Trigger activation | Provide instructions |
| **"When to use" info** | Put it here (in `description`) | Not helpful here (loaded after triggering) |

**Common mistake:** Writing a "When to Use This Skill" section in the body. By the time the body loads, the activation decision has already been made. All trigger information must be in the `description` field.
