---
description: Reverse /praxion-complete-install — remove rule/script symlinks and offer to remove leftover state from earlier Praxion versions. Plugin body is preserved.
allowed-tools: [Bash]
disable-model-invocation: true
---

<!-- LEGACY-CHUB-CLEANUP: when the shim is deleted, also drop this sentence and step 3 below's "legacy remnants" clause. -->
Remove the system-level symlinks that `/praxion-complete-install` created, and offer to remove leftover state from earlier Praxion versions. The plugin body stays installed — run `claude plugin uninstall praxion` separately if you want to remove it too.

## Procedure

1. **Resolve the plugin root.** Use `CLAUDE_PLUGIN_ROOT` if set; otherwise locate `~/.claude/plugins/cache/bit-agora/praxion/*/`.

2. **Invoke the installer's complete-uninstall mode:**

   ```bash
   "${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/bit-agora/praxion/*/ 2>/dev/null | head -1)}/install.sh" code --complete-uninstall
   ```

   If the plugin is not installed, report: *"Praxion plugin not found — nothing to uninstall."*

3. **Relay consent, in whichever form the installer gives it.** <!-- LEGACY-CHUB-CLEANUP --> When `install.sh` runs on an interactive terminal, it prompts for consent separately on each removal (rules, scripts, legacy remnants from earlier Praxion versions if present); relay those prompts to the user and do not suppress or auto-answer them — each represents a filesystem deletion the user should approve. When run through this command's Bash tool invocation, stdin is not a TTY, so the installer removes nothing on its own and instead prints the exact manual commands for any remnants it found — relay those printed commands to the user verbatim rather than claiming a prompt appeared.

4. **Summarize the outcome**: how many rule symlinks were removed, how many script symlinks, and whether any legacy remnants were removed. Remind the user that the plugin body itself is untouched and requires `claude plugin uninstall praxion` to fully remove.

## Safety

Only symlinks that **point at the plugin cache** (`${CLAUDE_PLUGIN_ROOT}/...`) are removed. Rules or scripts from other sources in `~/.claude/rules/` or `~/.local/bin/` are left alone. The operation is safe to run even if the user has hand-installed other rule or script files.

## Idempotence

Safe to re-run. After the first run, subsequent runs find nothing to remove and exit cleanly.
