# Plugin Mechanics and Troubleshooting

Plugin-specific operational knowledge, anti-patterns to avoid, and troubleshooting common issues. Reference material for the [Skill Creator](../SKILL.md) skill.

## Plugin-Specific Progressive Disclosure

### How It Works from Plugins

When Claude Code activates a skill, it injects the skill's **base path** (the absolute directory where the skill resides) alongside the SKILL.md content. This allows the LLM to resolve relative references like `[references/details.md](references/details.md)` to absolute paths — regardless of whether the skill lives in the project (`.claude/skills/`), personal directory (`~/.claude/skills/`), or plugin cache (`~/.claude/plugins/cache/...`).

This is unique to skills. Rules and agents do NOT receive a base path, so they cannot use satellite files for progressive disclosure.

### How Lazy Loading Works

Markdown links in SKILL.md act as navigational cues. Claude sees the links, evaluates whether each reference is relevant to the current task, and issues `Read` tool calls only for the files it needs. Scripts in `scripts/` are executed (via `Bash`), not loaded into context — keeping token cost proportional to output, not source size.

### Permission Caveat

`allowed-tools: [Read]` in frontmatter grants tool permission but not filesystem path permission. For plugin skills, reference files live in `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/...` — a path outside the project directory. Without explicit path access, Claude prompts for permission on every reference file read, and path approvals break on plugin updates (new version = new cache path).

Add a wildcard allowlist to avoid this:

```json
// In settings.json or settings.local.json
{ "permissions": { "additionalDirectories": ["~/.claude/plugins/**"] } }
```

### Debugging Tip

Use `/context` to inspect what's currently loaded in the context window, including which skills and reference files have been read. Useful for verifying progressive disclosure is working as intended.

## Recommended Hooks

Skills cannot install hooks at runtime -- hooks are defined statically in `settings.json` or `settings.local.json`. However, a skill should document recommended hooks that users can configure to complement the skill's behavior:

```markdown
## Recommended hooks

Add this PreToolUse hook to your `settings.json` to guard against destructive commands when working with databases:

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [{
        "type": "prompt",
        "prompt": "If the command contains 'rm -rf', 'DROP TABLE', or 'force push', BLOCK it and suggest the safe alternative."
      }]
    }]
  }
}
```
```

Document domain-specific hooks in the skill body so users can adopt them selectively. A database skill should recommend guarding against `DROP TABLE`; a deployment skill should recommend guarding against force-pushes. Users decide which hooks to enable based on their workflow.

## Persistent State

Skills that need memory across sessions (accumulated gotchas, user preferences, execution logs) use append-only files or structured data:

```markdown
## Execution log

After each run, append results to the log:

```bash
echo "$(date -Iseconds) | $STATUS | $DETAILS" >> execution_log.txt
```

Use the log to maintain consistency across executions and track patterns.
```

For plugin-distributed skills, store persistent data in `${CLAUDE_PLUGIN_DATA}` directories to survive skill upgrades (the plugin cache gets overwritten on reinstall, but `CLAUDE_PLUGIN_DATA` persists). Use append-only logs or JSON files -- avoid databases unless the skill genuinely needs query capabilities.

## Anti-Patterns

- Vague descriptions ("Helps with documents")
- Over-explaining what the agent already knows
- Windows-style paths -- use forward slashes everywhere
- Too many options -- provide one default with escape hatches
- Deeply nested references -- keep one level from `SKILL.md`
- Hard-referencing slash commands from skills -- commands are tool-specific and break portability. Describe the workflow outcome ("commit the changes") and let the agent's discovery mechanism find the right command. Cross-reference other skills instead; list commands in project-level files like `CLAUDE.md`
- Scripts that punt errors to the agent
- Time-based conditionals
- Voodoo constants without justification
- Assuming tools/packages are installed without listing them
- Duplicating rule content in skills -- if a rule covers commit conventions, the skill should not repeat them. Claude loads both when relevant; duplication wastes tokens and creates sync divergence

## Troubleshooting

### Skill Not Activating

1. Verify description includes specific trigger terms
2. Check YAML syntax (spaces not tabs, proper `---` delimiters)
3. If `name` is present, confirm it matches directory name exactly
4. Test with explicit trigger phrases
5. Consult the specific agent's documentation for skill-loading behavior

### YAML Errors

- Use spaces, never tabs
- Quote strings with special characters
- `---` delimiters on their own lines

### Path Issues

- Use forward slashes everywhere
- Verify referenced paths exist
- Use `~` for home directory in personal skills

### Plugin Reference File Permissions

**Symptom:** Claude prompts for permission every time it tries to read a satellite file from a plugin skill, or previously approved paths stop working after a plugin update.

**Cause:** `allowed-tools: [Read]` in frontmatter grants tool permission (Claude can use the Read tool) but not filesystem path permission. Plugin reference files live in `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/...` — a path outside the project directory. Claude treats reads to this path as requiring explicit approval. When the plugin updates, the version segment changes, invalidating all prior approvals.

**Fix:** Add a wildcard allowlist so Claude can read any file in the plugin cache without prompting:

```json
// settings.json or settings.local.json
{
  "permissions": {
    "additionalDirectories": ["~/.claude/plugins/**"]
  }
}
```

This grants read access to all installed plugin files. The wildcard covers version changes, so approvals survive plugin updates.

**Verification:** After adding the allowlist, activate a plugin skill and trigger a reference file read. Use `/context` to confirm the reference file was loaded without a permission prompt.

### Live Agent Spawn Against a Stale Plugin Cache

**Symptom:** A live agent spawn meant to prove a shipped-plugin behavior (a smoke test, a "does the installed plugin actually do X" check) passes or fails inconsistently across sessions, or a session that paused mid-verification silently resumes against a different plugin state than it started with.

**Cause:** The spawn resolves against the **installed plugin cache**, not the working-tree repo. If the cache copy was pinned before the repository advanced (a fix landed on the default branch after the last plugin install/update), the spawn proves the stale cached behavior, not the current repo state — and either a `[BLOCKED]` or a `PASS` from that spawn is void, because it answers a different question than the one being asked.

**Fix:** Before spawning an agent to prove a shipped-plugin behavior, diff the installed copy against the repo:

```bash
diff -q ~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/agents/<agent>.md agents/<agent>.md
```

If they differ, either refresh the installed plugin (reinstall/update) or, when developing the plugin itself, point the session at the working tree directly via `claude --plugin-dir <path>` so the spawn resolves against source rather than cache.

**Verification:** Re-run the spawn only after the diff is empty (or after confirming the working-tree-as-plugin-source flag is active); record which path was used alongside the spawn's result.
