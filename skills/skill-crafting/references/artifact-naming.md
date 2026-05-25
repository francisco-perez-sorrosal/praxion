## Context Artifact Naming

Naming conventions for context engineering artifacts: skills, agents, commands, and rules. Consistent naming aids discoverability, relevance matching, and ecosystem coherence.

### Universal Constraints

All artifact identifiers (directory names, filenames, `name` fields):

- Lowercase letters, numbers, and hyphens only
- No consecutive hyphens (`--`), no leading or trailing hyphens
- Kebab-case for multi-word names
- No generic names (`helper`, `utils`, `tools`, `stuff`, `misc`, `common`)
- Skill `name`s additionally cannot contain the reserved words `anthropic` or `claude`, and are capped at 64 characters

### Skills — Directory Names

**Pattern**: `{domain}-{activity}` or `{artifact}-crafting` for meta-skills

The directory name is the skill's identity -- Claude Code infers the `name` from it. Names should communicate what domain the skill covers and what kind of work it enables.

**Semantic categories:**

| Category | Pattern | Examples |
|----------|---------|----------|
| Meta-crafting | `{artifact}-crafting` | `skill-crafting`, `agent-crafting`, `rule-crafting`, `command-crafting`, `mcp-crafting` |
| Domain + activity | `{domain}-{activity}` | `python-development`, `code-review`, `software-planning` |
| Domain + scope | `{domain}-{qualifier}` | `python-prj-mgmt` |
| Single activity | `{gerund}` | `refactoring` |

**Naming principles:**

- Prefer gerund forms (`refactoring`) or noun phrases (`code-review`) over bare nouns
- A bare noun (`documentation`) is too vague -- it could mean writing docs, managing READMEs, doc engineering, or API reference generation. Add a qualifier: `doc-management`, `doc-authoring`, `readme-authoring`
- The name should answer "skill for doing what?" -- `python-development` (developing in Python), `code-review` (reviewing code), `refactoring` (refactoring code)
- Abbreviations acceptable when the long form is unwieldy and the abbreviation is unambiguous: `python-prj-mgmt` (not `python-project-management`)

**Good and bad names:**

| Good | Bad | Why |
|------|-----|-----|
| `doc-management` | `documentation` | Activity vs. bare noun -- "documentation" could mean anything |
| `python-development` | `python` | Specifies the activity, not just the language |
| `code-review` | `review` | Scopes to code, avoids ambiguity with other review types |
| `api-testing` | `testing` | Scopes the domain |
| `skill-crafting` | `skills` | Describes what you do with it, not what it contains |

### Agents — File Names

**Pattern**: `{role}.md` or `{domain}-{role}.md`

Agents are named for their role in the pipeline. The name should complete the sentence "this agent is a ___."

| Pattern | When to Use | Examples |
|---------|-------------|---------|
| Single role noun | Role is universally understood | `researcher`, `implementer`, `verifier`, `sentinel` |
| Domain-qualified role | Role needs scoping | `systems-architect`, `implementation-planner`, `context-engineer`, `doc-engineer` |
| Evocative noun | Role is conceptual, not functional | `promethean` |

**Naming principles:**

- Use role nouns, not verbs -- `researcher` (not `research`), `verifier` (not `verify`)
- Qualify when the bare role is ambiguous -- `systems-architect` (not `architect`, which could mean many things)
- The filename must match the `name` field in frontmatter exactly
- Compound roles use the `{domain}-{role}` pattern, not `{role}-of-{domain}`

### Commands — File Names

**Pattern**: `{verb}-{object}.md` or abbreviation

Commands are user-invoked actions. Names should read as imperative verbs -- what the command does when you run it.

| Pattern | When to Use | Examples |
|---------|-------------|---------|
| Verb-object | Default for all commands | `create-worktree`, `merge-worktree`, `add-rules`, `manage-readme` |
| Verb-qualifier-object | Object needs scoping | `create-simple-python-prj` |
| Abbreviation | High-frequency commands only | `co` (commit), `cop` (commit and push) |

**Naming principles:**

- Start with a verb in imperative mood -- `create`, `add`, `merge`, `manage`
- The filename (minus `.md`) becomes the `/slash-command` name
- Abbreviations are acceptable for commands used many times per session, but document the expansion
- Avoid noun-only names -- `/worktree` tells you nothing; `/create-worktree` tells you what it does

### Rules — File Names and Directory Structure

**Pattern**: `{domain}-{intent}.md` inside `{category}/` directories

Rules are contextual knowledge loaded by relevance. The filename directly affects Claude's ability to match the rule to the right context.

| Level | Convention | Examples |
|-------|-----------|----------|
| Directory | Domain category (broad) | `swe/`, `writing/`, `context-engineering/` |
| Subdirectory | Sub-domain (when needed) | `swe/vcs/` for version control rules |
| File | `{domain}-{intent}.md` | `coding-style.md`, `git-conventions.md`, `readme-style.md` |

**Naming principles:**

- The domain prefix aids relevance matching -- `git-conventions.md` loads when Claude works on commits
- Be specific -- `git-conventions.md` (not `commit.md`)
- Domain-oriented, not action-oriented -- rules describe what to know, not what to do
- Directory names are broad categories; filenames are specific domains within them

**Good and bad names:**

| Good | Bad | Why |
|------|-----|-----|
| `coding-style.md` | `style.md` | Domain is explicit |
| `git-conventions.md` | `git.md` | Specific intent, not catch-all |
| `artifact-naming.md` | `naming.md` | Scoped to artifacts, not generic |
| `swe-agent-coordination-protocol.md` | `agents.md` | Distinguishes from agent definitions |

### Cross-Artifact Consistency

When a skill, agent, and command relate to the same domain, align their names:

| Concern | Skill | Agent | Command |
|---------|-------|-------|---------|
| Documentation | `doc-management` | `doc-engineer` | `manage-readme` |
| Code review | `code-review` | `verifier` | (none) |
| Planning | `software-planning` | `implementation-planner` | (none) |

The names do not need to be identical -- each follows its own type's pattern -- but they should share enough vocabulary that the relationship is obvious.
