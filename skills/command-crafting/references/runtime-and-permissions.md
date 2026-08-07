# Runtime, Permissions, and Debugging

How a command is discovered at runtime, how Claude's access to invoke it is governed, and how to
debug one that does not appear or does not behave. Load when a command is missing from `/help`,
is being blocked, or is not substituting arguments as written.

Back to [../SKILL.md](../SKILL.md).

## Discovery and Live Reload
<!-- last-verified: 2026-05-25 -->

Discovery timing depends on *where* the command/skill lives:

- **Project / personal locations** (`.claude/skills/`, `~/.claude/skills/`, and `.claude/commands/` files) have **live change detection** — edits, adds, and removals take effect within the session, no restart. Creating a *new top-level* skills directory that did not exist at session start still requires a restart (so it can be watched).
- **Plugin components** (Praxion's `commands/`, `agents/`) are scanned once at session start and cached for the session. A command added mid-session — or installed via `bash install.sh` against a running session — is invisible until a fresh session. Symptom: `/my-new-command` reports "unknown command" despite a valid file at the right path. There is no plugin hot-reload — restart the session.

(Subagents always require a restart on disk edits; the `/agents` interface takes effect immediately.)

## Permission Management
<!-- last-verified: 2026-05-25 -->

Since commands are skills, Claude's invocation access is governed by `Skill(...)` permission rules (the older `SlashCommand:/name:*` form predates the merge):

```text
# In /permissions
Skill(co)          # allow exactly /co
Skill(review-pr *) # allow /review-pr with any arguments
Skill(deploy *)    # (as a deny rule) block /deploy
Skill              # (as a deny rule) Claude can invoke no skills/commands
```

To stop Claude from auto-invoking a *specific* command (e.g. a side-effecting one), set its frontmatter instead — this also removes its description from model context:

```markdown
---
disable-model-invocation: true
---
```

Note the two mechanisms differ in what they cost. A deny rule blocks invocation but the
description still occupies the always-loaded listing budget; `disable-model-invocation: true`
blocks invocation *and* reclaims the budget. Prefer the frontmatter field for commands that
should never be model-invoked, and reserve deny rules for per-user or per-project policy over
commands whose default is auto-invocable.

## Debugging

```bash
# List all commands
ls -R .claude/commands/
ls -R ~/.claude/commands/

# View command content
cat .claude/commands/my-command.md
```

Within Claude Code, the `Read` and `Glob` tools can also inspect command files directly.

Verify: proper `---` delimiters, valid YAML, correct field names, expected argument substitution.

**Frontmatter that does not parse fails silently.** A command whose YAML cannot load registers no
`description` and no `allowed-tools`, but nothing announces the failure — presence-grepping for a
field name succeeds on a file the parser rejects. Parse the frontmatter with a real YAML loader
rather than grepping for field names. Two failure shapes account for most of it:

- An **unindented block scalar** (`description: >` with continuation lines at column 0) — the
  parser is still inside the folded scalar when it meets the next key.
- An **unquoted value** whose first character is YAML-significant (`[`, `{`, `*`, `&`, `>`, `|`),
  or one containing `: `.

When a value could be mistaken for YAML syntax, quote it.
