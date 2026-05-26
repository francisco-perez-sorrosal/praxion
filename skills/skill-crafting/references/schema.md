# Skill YAML Frontmatter Schema

Complete reference for SKILL.md frontmatter fields, validation rules, and examples. Back to [SKILL.md](../SKILL.md).

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
| Characters | Lowercase alphanumeric + hyphens only |
| Pattern | `/^[a-z0-9]+(-[a-z0-9]+)*$/` |
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
  default-provider: context-hub
  mcp-tools: chub_search, chub_get, chub_list
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

The fields above are the portable Agent Skills core. Claude Code reads them **plus** the fields below. Since custom commands [merged into skills](https://code.claude.com/docs/en/skills), these apply equally to `commands/*.md` files — see the `command-crafting` skill for the command-authoring angle.

| Field | Type | Purpose / constraint |
|-------|------|----------------------|
| `when_to_use` | String | Extra trigger phrases / example requests, appended to `description` in the listing. **Combined `description` + `when_to_use` is truncated at 1,536 chars** (`maxSkillDescriptionChars` setting); put the key use case first. |
| `disable-model-invocation` | Boolean | `true` = only the user can invoke (`/name`); the description leaves model context, and the skill cannot be preloaded into subagents. Default `false`. Use for side-effecting actions. |
| `user-invocable` | Boolean | `false` = hidden from the `/` menu; Claude can still auto-load it. Default `true`. For background knowledge that isn't a user action. |
| `paths` | String / list | Glob patterns scoping auto-activation to matching files (same format as path-specific rules). |
| `context` | String | `fork` runs the skill body as the prompt for a forked subagent. |
| `agent` | String | Subagent type used when `context: fork` (e.g. `Explore`, `Plan`, `general-purpose`, or a custom agent). Default `general-purpose`. |
| `model` | String | Model while the skill is active (`inherit` keeps the session model). Override lasts the current turn only. |
| `effort` | String | `low`/`medium`/`high`/`xhigh`/`max` while active; overrides session effort. |
| `argument-hint` | String | Autocomplete hint, e.g. `[issue-number]` or `[filename] [format]`. |
| `arguments` | String / list | Named positional args for `$name` substitution; names map to positions in order. |
| `hooks` | Object | Hooks scoped to the skill's lifecycle (all events; for subagents `Stop` auto-converts to `SubagentStop`). |
| `shell` | String | `bash` (default) or `powershell` for bang-prefixed inline injection and fenced ` ```! ` blocks. |

**Praxion staleness fields** (validated by `validate.py`, per `rules/swe/staleness-policy.md`):

| Field | Type | Purpose |
|-------|------|---------|
| `staleness_sensitive_sections` | List | Bare h2/h3 heading texts (in `SKILL.md` or any `references/`/`contexts/` file) the sentinel tracks for drift via `<!-- last-verified: YYYY-MM-DD -->` markers. |
| `staleness_threshold_days` | Number | Per-skill staleness threshold override (global default 120; use 60 for fast-moving API surfaces). |

**Argument substitution & dynamic context** (skill body, Claude Code): `$ARGUMENTS`, `$ARGUMENTS[N]` / `$N`, `$name`; `${CLAUDE_SESSION_ID}`, `${CLAUDE_EFFORT}`, `${CLAUDE_SKILL_DIR}`; and bang-prefixed backtick-quoted dynamic injection (runs once, before Claude sees the body) with a fenced ` ```! ` block for multi-line. Full reference: [Claude Code skills docs](https://code.claude.com/docs/en/skills).

## Validation Rules

The following rules are enforced by `scripts/validate.py`:

### Required Checks

| Check | Rule | Error |
|-------|------|-------|
| Frontmatter present | File must start with `---` | `Missing YAML frontmatter` |
| `name` present | Field must exist | `Missing required field: name` |
| `name` matches directory | `name == dirname` | `Name 'X' does not match directory 'Y'` |
| `name` format | Matches pattern `/^[a-z0-9]+(-[a-z0-9]+)*$/` | `Invalid name format` |
| `name` length | 1-64 characters | `Name too long (max 64)` |
| `description` present | Field must exist | `Missing required field: description` |
| `description` length | 1-1024 characters | `Description too long (max 1024)` |

### Warning Checks

| Check | Threshold | Warning |
|-------|-----------|---------|
| SKILL.md length | >500 lines | `Consider moving content to references/` |
| Description vagueness | No trigger terms detected | `Description may not trigger effectively` |
| Missing README.md | File absent | `Skill lacks human-facing README` |

### Running Validation

```bash
# Validate a single skill
python skills/skill-crafting/scripts/validate.py skills/my-skill/

# Validate all skills
python skills/skill-crafting/scripts/validate.py skills/
```

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
