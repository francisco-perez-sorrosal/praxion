---
description: Reverse /praxion-complete-install — remove rule/script symlinks and optional context-hub MCP. Plugin body is preserved.
allowed-tools: [Bash]
disable-model-invocation: true
---

Remove the system-level symlinks and MCP entry that `/praxion-complete-install` created. The plugin body stays installed — run `claude plugin uninstall i-am` separately if you want to remove it too.

## Procedure

1. **Resolve the plugin root.** Use `CLAUDE_PLUGIN_ROOT` if set; otherwise locate `~/.claude/plugins/cache/bit-agora/i-am/*/`.

2. **Invoke the installer's complete-uninstall mode:**

   ```bash
   "${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/bit-agora/i-am/*/ 2>/dev/null | head -1)}/install.sh" code --complete-uninstall
   ```

   If the plugin is not installed, report: *"Praxion plugin not found — nothing to uninstall."*

3. **Relay the installer's interactive prompts.** The installer asks the user for consent separately on each removal (rules, scripts, context-hub MCP). Do not suppress or auto-answer — each prompt represents a filesystem deletion the user should approve.

4. **Summarize the outcome**: how many rule symlinks were removed, how many script symlinks, and whether the MCP entry was removed. Remind the user that the plugin body itself is untouched and requires `claude plugin uninstall i-am` to fully remove.

## Safety

Only symlinks that **point at the plugin cache** (`${CLAUDE_PLUGIN_ROOT}/...`) are removed. Rules or scripts from other sources in `~/.claude/rules/` or `~/.local/bin/` are left alone. The operation is safe to run even if the user has hand-installed other rule or script files.

## Idempotence

Safe to re-run. After the first run, subsequent runs find nothing to remove and exit cleanly.
