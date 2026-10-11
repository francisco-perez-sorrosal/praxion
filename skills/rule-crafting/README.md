# Rule Crafting Skill

Skill for creating and managing rules — contextual domain knowledge files that assistants (Claude, Cursor) load automatically based on relevance.

## When to Use

- Creating rules with proper structure, naming, and placement
- Organizing rules using flat, layered, or path-scoped directory structures
- Deciding whether content belongs in a rule, skill, or `CLAUDE.md`
- Debugging rule loading and relevance matching
- Migrating content between `CLAUDE.md`, rules, and skills
- Translating Praxion semantic rules to Codex-native surfaces without losing meaning

## Activation

The skill activates automatically when the assistant detects tasks related to:

- Creating or updating rules
- Debugging rule loading or relevance matching
- Organizing rule files across directories
- Deciding where contextual knowledge should live

You can also trigger it explicitly by asking about rules or referencing it by name.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core reference: structure, locations, naming, content guidelines, decision model |
| `REFERENCE.md` | Extended examples: complete rules, path-specific patterns, layered directories, migrations, Codex adaptation patterns |
| `README.md` | This file — overview and testing guide |

## Existing Rules in This Repository

Rules live in `rules/` (this repo) and are installed to `~/.claude/rules/` via `install.sh`.

| Rule | Purpose |
|------|---------|
| `swe/coding-style.md` | Language-independent structural and design conventions |
| `swe/swe-agent-coordination-protocol.md` | Agent coordination, pipeline execution, parallel protocols, boundary discipline |
| `swe/agent-intermediate-documents.md` | Placement and lifecycle of agent pipeline documents |
| `swe/vcs/git-conventions.md` | Commit scope, staging discipline, secrets, exclusions, message format |
| `writing/readme-style.md` | Technical writing conventions for README files |

## Testing

### In Claude Code (CLI)

**Test rule creation guidance:**

```bash
# Start a Claude Code session
claude

# Ask to create a rule — the skill should activate automatically
> I want to create a rule for our SQL naming conventions

# Or reference it explicitly
> Using the rule-crafting skill, help me write a security rule for auth tokens
```

**Test decision guidance:**

```bash
# Ask about layer placement
> Should our API error handling conventions be a rule or go in CLAUDE.md?

# Ask about organization
> We have 15 rules and they're getting messy — how should I organize them?
```

**Test debugging:**

```bash
# Ask about loading issues
> My rule isn't being picked up by Claude — how do I debug this?

# Check loaded rules
> Run /memory to see which rules are loaded
```

## Related Skills

- [`skill-crafting`](../skill-crafting/) — the spec for creating skills; rules can graduate to skills when they need procedural content

### Validation Checklist

After creating or modifying rules, verify:

- [ ] File uses `<domain>-<rule-intent>.md` naming pattern
- [ ] Content is declarative (constraints), not procedural (steps)
- [ ] `paths` frontmatter (if used) has valid YAML and glob patterns
- [ ] Rule loads in the expected context (verify with `/memory`)
- [ ] No duplication with `CLAUDE.md` content
- [ ] Placed in correct scope (project `.claude/rules/` vs personal `~/.claude/rules/`)
- [ ] Examples included where clarity demands it
